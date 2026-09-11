"""Repository layer for tasks.

PUBLIC API: The TaskRepository interface (method signatures) must not change.
"""

import sqlite3
from typing import Optional


class TaskRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        project_id: int,
        title: str,
        description: str = "",
        priority: int = 0,
        assignee: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> dict:
        cursor = self.conn.execute(
            """INSERT INTO tasks (project_id, title, description, priority, assignee, due_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, title, description, priority, assignee, due_date),
        )
        task_id = cursor.lastrowid
        return self.get_by_id(task_id)  # type: ignore

    def get_by_id(self, task_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        task = dict(row)
        task["labels"] = self._get_labels(task_id)
        return task

    def list_by_project(
        self,
        project_id: int,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conditions = ["project_id = ?"]
        params: list = [project_id]

        if status:
            conditions.append("status = ?")
            params.append(status)
        if assignee:
            conditions.append("assignee = ?")
            params.append(assignee)

        where = " AND ".join(conditions)

        # BUG: count query doesn't apply filters (counts all tasks in project)
        count = self.conn.execute(
            f"SELECT COUNT(*) FROM tasks WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        rows = self.conn.execute(
            f"SELECT * FROM tasks WHERE {where} ORDER BY priority DESC, created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

        tasks = []
        for row in rows:
            task = dict(row)
            task["labels"] = self._get_labels(task["id"])
            tasks.append(task)

        return tasks, count

    def update(self, task_id: int, **fields: object) -> Optional[dict]:
        if not fields:
            return self.get_by_id(task_id)

        # BUG: doesn't update updated_at timestamp
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [task_id]
        self.conn.execute(
            f"UPDATE tasks SET {sets} WHERE id = ?", vals
        )
        return self.get_by_id(task_id)

    def delete(self, task_id: int) -> bool:
        cursor = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0

    def add_labels(self, task_id: int, labels: list[str]) -> None:
        for label in labels:
            try:
                self.conn.execute(
                    "INSERT INTO task_labels (task_id, label) VALUES (?, ?)",
                    (task_id, label),
                )
            except sqlite3.IntegrityError:
                pass  # already exists

    def remove_label(self, task_id: int, label: str) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM task_labels WHERE task_id = ? AND label = ?",
            (task_id, label),
        )
        return cursor.rowcount > 0

    def _get_labels(self, task_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT label FROM task_labels WHERE task_id = ? ORDER BY label",
            (task_id,),
        ).fetchall()
        return [r["label"] for r in rows]

    def search(self, project_id: int, query: str) -> list[dict]:
        # BUG: SQL injection vulnerable - uses string formatting
        rows = self.conn.execute(
            f"SELECT * FROM tasks WHERE project_id = ? AND (title LIKE '%{query}%' OR description LIKE '%{query}%')",
            (project_id,),
        ).fetchall()
        tasks = []
        for row in rows:
            task = dict(row)
            task["labels"] = self._get_labels(task["id"])
            tasks.append(task)
        return tasks

    def get_overdue(self, project_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM tasks
               WHERE project_id = ? AND due_date IS NOT NULL
               AND due_date < date('now') AND status != 'done'
               ORDER BY due_date""",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]
