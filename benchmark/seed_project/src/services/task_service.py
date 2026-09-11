"""Service layer for task business logic."""

from datetime import datetime
from typing import Optional

from src.database import get_db
from src.models.schemas import (
    ProjectStats,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from src.repositories.comment_repo import CommentRepository
from src.repositories.project_repo import ProjectRepository
from src.repositories.task_repo import TaskRepository


class TaskServiceError(Exception):
    def __init__(self, message: str, code: str = "service_error"):
        self.message = message
        self.code = code
        super().__init__(message)


# Valid status transitions
VALID_TRANSITIONS = {
    "todo": ["in_progress"],
    "in_progress": ["review", "todo"],
    "review": ["done", "in_progress"],
    "done": ["todo"],
}


def create_task(project_id: int, data: TaskCreate) -> TaskResponse:
    with get_db() as conn:
        project_repo = ProjectRepository(conn)
        task_repo = TaskRepository(conn)

        project = project_repo.get_by_id(project_id)
        if project is None:
            raise TaskServiceError("Project not found", "not_found")

        if project["archived"]:
            raise TaskServiceError(
                "Cannot add tasks to archived project", "project_archived"
            )

        task = task_repo.create(
            project_id=project_id,
            title=data.title,
            description=data.description,
            priority=data.priority,
            assignee=data.assignee,
            due_date=data.due_date,
        )

        if data.labels:
            task_repo.add_labels(task["id"], data.labels)
            task = task_repo.get_by_id(task["id"])

        return _task_to_response(task)  # type: ignore


def get_task(task_id: int) -> TaskResponse:
    with get_db() as conn:
        repo = TaskRepository(conn)
        task = repo.get_by_id(task_id)
        if task is None:
            raise TaskServiceError("Task not found", "not_found")
        return _task_to_response(task)


def update_task(task_id: int, data: TaskUpdate) -> TaskResponse:
    with get_db() as conn:
        repo = TaskRepository(conn)
        task = repo.get_by_id(task_id)
        if task is None:
            raise TaskServiceError("Task not found", "not_found")

        fields = data.model_dump(exclude_unset=True)

        # Validate status transition
        if "status" in fields:
            new_status = fields["status"]
            current_status = task["status"]
            valid = VALID_TRANSITIONS.get(current_status, [])
            if new_status not in valid:
                raise TaskServiceError(
                    f"Cannot transition from '{current_status}' to '{new_status}'. "
                    f"Valid transitions: {valid}",
                    "invalid_transition",
                )

        updated = repo.update(task_id, **fields)
        return _task_to_response(updated)  # type: ignore


def list_tasks(
    project_id: int,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[TaskResponse], int]:
    with get_db() as conn:
        repo = TaskRepository(conn)
        tasks, total = repo.list_by_project(
            project_id, status=status, assignee=assignee, limit=limit, offset=offset
        )
        return [_task_to_response(t) for t in tasks], total


def search_tasks(project_id: int, query: str) -> list[TaskResponse]:
    with get_db() as conn:
        repo = TaskRepository(conn)
        tasks = repo.search(project_id, query)
        return [_task_to_response(t) for t in tasks]


def get_project_stats(project_id: int) -> ProjectStats:
    with get_db() as conn:
        project_repo = ProjectRepository(conn)
        task_repo = TaskRepository(conn)

        project = project_repo.get_by_id(project_id)
        if project is None:
            raise TaskServiceError("Project not found", "not_found")

        tasks, total = task_repo.list_by_project(project_id, limit=10000)
        overdue = task_repo.get_overdue(project_id)

        by_status: dict[str, int] = {}
        by_priority: dict[int, int] = {}

        for task in tasks:
            s = task["status"]
            by_status[s] = by_status.get(s, 0) + 1
            p = task["priority"]
            by_priority[p] = by_priority.get(p, 0) + 1

        return ProjectStats(
            project_id=project_id,
            project_name=project["name"],
            total_tasks=total,
            by_status=by_status,
            by_priority=by_priority,
            overdue_count=len(overdue),
        )


def _task_to_response(task: dict) -> TaskResponse:
    return TaskResponse(
        id=task["id"],
        project_id=task["project_id"],
        title=task["title"],
        description=task["description"],
        status=task["status"],
        priority=task["priority"],
        assignee=task.get("assignee"),
        due_date=task.get("due_date"),
        created_at=datetime.fromisoformat(task["created_at"]),
        updated_at=datetime.fromisoformat(task["updated_at"]),
        labels=task.get("labels", []),
    )
