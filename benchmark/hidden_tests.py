"""Hidden tests for evaluating benchmark quality.

These tests are NOT visible to Claude during the benchmark.
They are run after each strategy completes to evaluate the final code quality.

Tests cover:
1. Bug fixes (filtered count, updated_at, SQL injection)
2. Feature implementation (batch status update)
3. Requirement retention (API compat, no new deps, repo interfaces)
4. Regression detection
5. Code quality
"""

import importlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_hidden_tests(project_dir: str) -> dict[str, Any]:
    """Run all hidden evaluations against a completed project directory.

    Returns a dict with test results and scores.
    """
    results: dict[str, Any] = {
        "tests": {},
        "scores": {},
        "total_score": 0,
        "max_score": 0,
    }

    project = Path(project_dir)
    sys.path.insert(0, str(project))

    # Reload modules from this project dir
    os.chdir(project)

    try:
        _run_deterministic_tests(project, results)
        _check_requirement_retention(project, results)
        _check_regressions(project, results)
        _check_code_quality(project, results)
    finally:
        sys.path.pop(0)

    # Calculate total
    results["total_score"] = sum(results["scores"].values())
    results["max_score"] = len(results["scores"]) * 1  # 1 point each
    return results


def _run_deterministic_tests(project: Path, results: dict) -> None:
    """Run pytest on visible tests and check specific hidden conditions."""

    # 1. Do visible tests pass?
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
        capture_output=True, text=True, cwd=str(project), timeout=60,
    )
    passed = r.returncode == 0
    results["tests"]["visible_tests_pass"] = {
        "passed": passed,
        "stdout": r.stdout[-2000:] if r.stdout else "",
        "stderr": r.stderr[-1000:] if r.stderr else "",
    }
    results["scores"]["visible_tests"] = 1 if passed else 0

    # 2. Check filtered count bug fix
    try:
        from src.database import get_db, init_db, DB_PATH
        import src.database as db_mod
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_db = Path(td) / "hidden_test.db"
            db_mod.DB_PATH = test_db
            init_db()
            with get_db() as conn:
                conn.execute("INSERT INTO projects (name) VALUES ('TestProj')")
                pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO tasks (project_id, title, assignee) VALUES (?, 'T1', 'alice')",
                    (pid,),
                )
                conn.execute(
                    "INSERT INTO tasks (project_id, title, assignee) VALUES (?, 'T2', 'bob')",
                    (pid,),
                )
                conn.execute(
                    "INSERT INTO tasks (project_id, title, assignee) VALUES (?, 'T3', 'alice')",
                    (pid,),
                )

            # Now test via the repo
            from src.repositories.task_repo import TaskRepository
            with get_db() as conn:
                repo = TaskRepository(conn)
                tasks, total = repo.list_by_project(pid, assignee="alice")
                count_fix = (len(tasks) == total == 2)

            results["tests"]["filtered_count_bug"] = {
                "passed": count_fix,
                "expected": "total=2 when filtered to alice",
                "got": f"tasks={len(tasks)}, total={total}",
            }
            results["scores"]["filtered_count_fix"] = 1 if count_fix else 0
    except Exception as e:
        results["tests"]["filtered_count_bug"] = {"passed": False, "error": str(e)}
        results["scores"]["filtered_count_fix"] = 0

    # 3. Check updated_at bug fix
    try:
        import importlib
        import src.database as db_mod2
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_db2 = Path(td) / "hidden_test2.db"
            db_mod2.DB_PATH = test_db2
            init_db()
            with get_db() as conn:
                conn.execute("INSERT INTO projects (name) VALUES ('TP')")
                pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO tasks (project_id, title, updated_at) VALUES (?, 'T', '2020-01-01 00:00:00')",
                    (pid,),
                )
                tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            from src.repositories.task_repo import TaskRepository
            with get_db() as conn:
                repo = TaskRepository(conn)
                repo.update(tid, title="Updated Title")
                task = repo.get_by_id(tid)
                updated_at = task["updated_at"] if task else "not found"
                fixed = updated_at != "2020-01-01 00:00:00"

            results["tests"]["updated_at_bug"] = {
                "passed": fixed,
                "expected": "updated_at changed from 2020-01-01",
                "got": f"updated_at={updated_at}",
            }
            results["scores"]["updated_at_fix"] = 1 if fixed else 0
    except Exception as e:
        results["tests"]["updated_at_bug"] = {"passed": False, "error": str(e)}
        results["scores"]["updated_at_fix"] = 0

    # 4. Check SQL injection fix
    try:
        import src.database as db_mod3
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_db3 = Path(td) / "hidden_test3.db"
            db_mod3.DB_PATH = test_db3
            init_db()
            with get_db() as conn:
                conn.execute("INSERT INTO projects (name) VALUES ('TP')")
                pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO tasks (project_id, title) VALUES (?, 'Normal Task')",
                    (pid,),
                )

            from src.repositories.task_repo import TaskRepository
            import inspect
            source = inspect.getsource(TaskRepository.search)
            # The vulnerability is f-string/format interpolation of 'query' into SQL
            # Fixed code uses parameterized queries (?) for the search term
            has_fstring_injection = "{query}" in source
            has_format_injection = ".format(" in source and "query" in source
            fixed = not has_fstring_injection and not has_format_injection

            results["tests"]["sql_injection_fix"] = {
                "passed": fixed,
                "expected": "search uses parameterized queries",
            }
            results["scores"]["sql_injection_fix"] = 1 if fixed else 0
    except Exception as e:
        results["tests"]["sql_injection_fix"] = {"passed": False, "error": str(e)}
        results["scores"]["sql_injection_fix"] = 0

    # 5. Check batch status update feature
    try:
        from fastapi.testclient import TestClient
        import src.database as db_mod4
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_db4 = Path(td) / "hidden_test4.db"
            db_mod4.DB_PATH = test_db4
            init_db()
            from src.app import app
            client = TestClient(app)

            # Create project and tasks
            proj = client.post("/api/v1/projects", json={"name": "BatchTest"}).json()
            pid = proj["id"]
            t1 = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T1"}).json()
            t2 = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T2"}).json()

            # Try batch update
            resp = client.patch(
                f"/api/v1/projects/{pid}/tasks/batch",
                json={"task_ids": [t1["id"], t2["id"]], "status": "in_progress"},
            )
            batch_works = resp.status_code in (200, 207)
            if batch_works:
                data = resp.json()
                # Verify tasks actually updated
                task1 = client.get(f"/api/v1/tasks/{t1['id']}").json()
                task2 = client.get(f"/api/v1/tasks/{t2['id']}").json()
                batch_works = (
                    task1["status"] == "in_progress"
                    and task2["status"] == "in_progress"
                )

            results["tests"]["batch_update_feature"] = {
                "passed": batch_works,
                "status_code": resp.status_code,
            }
            results["scores"]["batch_update"] = 1 if batch_works else 0
    except Exception as e:
        results["tests"]["batch_update_feature"] = {"passed": False, "error": str(e)}
        results["scores"]["batch_update"] = 0


def _check_requirement_retention(project: Path, results: dict) -> None:
    """Check if early requirements were preserved through context transitions."""

    # 1. API schema compatibility — check that core schema fields still exist
    try:
        from src.models.schemas import (
            TaskResponse, TaskCreate, TaskUpdate, TaskList,
            ProjectResponse, ProjectCreate, ProjectList,
            CommentResponse, CommentCreate, ErrorResponse, ProjectStats,
        )
        # Check TaskResponse has required fields
        fields = TaskResponse.model_fields
        required = {"id", "project_id", "title", "description", "status",
                     "priority", "assignee", "due_date", "created_at", "updated_at", "labels"}
        missing = required - set(fields.keys())
        compat = len(missing) == 0

        results["tests"]["api_schema_compat"] = {
            "passed": compat,
            "missing_fields": list(missing) if missing else [],
        }
        results["scores"]["api_compat"] = 1 if compat else 0
    except Exception as e:
        results["tests"]["api_schema_compat"] = {"passed": False, "error": str(e)}
        results["scores"]["api_compat"] = 0

    # 2. No new runtime dependencies
    try:
        pyproject = project / "pyproject.toml"
        content = pyproject.read_text()
        # Check that dependencies section hasn't grown
        import re
        deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if deps_match:
            deps_text = deps_match.group(1)
            dep_count = len([l for l in deps_text.strip().split("\n") if l.strip().strip(",")])
            no_new = dep_count <= 3  # fastapi, uvicorn, pydantic
        else:
            no_new = True

        results["tests"]["no_new_deps"] = {
            "passed": no_new,
            "dep_count": dep_count if deps_match else 0,
        }
        results["scores"]["no_new_deps"] = 1 if no_new else 0
    except Exception as e:
        results["tests"]["no_new_deps"] = {"passed": False, "error": str(e)}
        results["scores"]["no_new_deps"] = 0

    # 3. Repository interface stability
    try:
        from src.repositories.task_repo import TaskRepository
        import inspect
        sig = inspect.signature(TaskRepository.list_by_project)
        params = list(sig.parameters.keys())
        # Must still have: self, project_id, status, assignee, limit, offset
        required_params = {"self", "project_id", "status", "assignee", "limit", "offset"}
        stable = required_params.issubset(set(params))

        results["tests"]["repo_interface_stable"] = {
            "passed": stable,
            "params": params,
        }
        results["scores"]["repo_interface"] = 1 if stable else 0
    except Exception as e:
        results["tests"]["repo_interface_stable"] = {"passed": False, "error": str(e)}
        results["scores"]["repo_interface"] = 0


def _check_regressions(project: Path, results: dict) -> None:
    """Check for common regressions."""

    try:
        from fastapi.testclient import TestClient
        import src.database as db_mod
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_db = Path(td) / "reg_test.db"
            db_mod.DB_PATH = test_db
            from src.database import init_db
            init_db()
            from src.app import app
            client = TestClient(app)

            # Create project
            proj = client.post("/api/v1/projects", json={"name": "RegTest"}).json()
            pid = proj["id"]

            # Test: creating task in non-existent project
            resp = client.post("/api/v1/projects/9999/tasks", json={"title": "X"})
            not_found_works = resp.status_code == 404

            # Test: invalid status transition still rejected
            t = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
            resp = client.patch(f"/api/v1/tasks/{t['id']}", json={"status": "done"})
            transition_guard = resp.status_code == 422

            # Test: labels still work
            t2 = client.post(
                f"/api/v1/projects/{pid}/tasks",
                json={"title": "T2", "labels": ["a", "b"]},
            ).json()
            labels_work = set(t2.get("labels", [])) == {"a", "b"}

            # Test: comments still work with cascade delete
            cid = client.post(
                f"/api/v1/tasks/{t['id']}/comments",
                json={"author": "x", "body": "y"},
            ).json()["id"]
            comments_work = (
                client.get(f"/api/v1/tasks/{t['id']}/comments").status_code == 200
            )

            all_pass = all([not_found_works, transition_guard, labels_work, comments_work])

            results["tests"]["regression_checks"] = {
                "passed": all_pass,
                "not_found": not_found_works,
                "transition_guard": transition_guard,
                "labels": labels_work,
                "comments": comments_work,
            }
            results["scores"]["no_regressions"] = 1 if all_pass else 0
    except Exception as e:
        results["tests"]["regression_checks"] = {"passed": False, "error": str(e)}
        results["scores"]["no_regressions"] = 0


def _check_code_quality(project: Path, results: dict) -> None:
    """Run linting and type checking."""

    # Ruff
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/", "--quiet"],
        capture_output=True, text=True, cwd=str(project), timeout=30,
    )
    lint_clean = r.returncode == 0
    results["tests"]["lint"] = {
        "passed": lint_clean,
        "issues": r.stdout[:500] if r.stdout else "",
    }
    results["scores"]["lint_clean"] = 1 if lint_clean else 0

    # Diff size (smaller is better, scored separately)
    r2 = subprocess.run(
        ["git", "diff", "--stat", "HEAD"],
        capture_output=True, text=True, cwd=str(project), timeout=10,
    )
    results["tests"]["diff_stat"] = r2.stdout[:1000] if r2.stdout else "no git"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python hidden_tests.py <project_dir>")
        sys.exit(1)
    results = run_hidden_tests(sys.argv[1])
    print(json.dumps(results, indent=2))
