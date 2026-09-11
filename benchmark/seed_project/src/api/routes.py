"""API routes for task management."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.models.schemas import (
    CommentCreate,
    CommentResponse,
    ErrorResponse,
    ProjectCreate,
    ProjectList,
    ProjectResponse,
    ProjectStats,
    TaskCreate,
    TaskList,
    TaskResponse,
    TaskUpdate,
)
from src.services import task_service
from src.database import get_db
from src.repositories.project_repo import ProjectRepository
from src.repositories.comment_repo import CommentRepository
from src.services.task_service import TaskServiceError

router = APIRouter()


# --- Project endpoints ---

@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(data: ProjectCreate) -> ProjectResponse:
    with get_db() as conn:
        repo = ProjectRepository(conn)
        existing = repo.get_by_name(data.name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"detail": "Project already exists", "code": "duplicate"},
            )
        project = repo.create(data.name, data.description)
        return ProjectResponse(
            id=project["id"],
            name=project["name"],
            description=project["description"],
            created_at=project["created_at"],
            archived=bool(project["archived"]),
        )


@router.get("/projects", response_model=ProjectList)
def list_projects(
    include_archived: bool = Query(default=False),
) -> ProjectList:
    with get_db() as conn:
        repo = ProjectRepository(conn)
        projects = repo.list_all(include_archived=include_archived)
        items = [
            ProjectResponse(
                id=p["id"],
                name=p["name"],
                description=p["description"],
                created_at=p["created_at"],
                archived=bool(p["archived"]),
            )
            for p in projects
        ]
        return ProjectList(projects=items, total=len(items))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int) -> ProjectResponse:
    with get_db() as conn:
        repo = ProjectRepository(conn)
        project = repo.get_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectResponse(
            id=project["id"],
            name=project["name"],
            description=project["description"],
            created_at=project["created_at"],
            archived=bool(project["archived"]),
        )


@router.get("/projects/{project_id}/stats", response_model=ProjectStats)
def get_project_stats(project_id: int) -> ProjectStats:
    try:
        return task_service.get_project_stats(project_id)
    except TaskServiceError as e:
        if e.code == "not_found":
            raise HTTPException(status_code=404, detail=e.message)
        raise HTTPException(status_code=400, detail=e.message)


# --- Task endpoints ---

@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=201,
)
def create_task(project_id: int, data: TaskCreate) -> TaskResponse:
    try:
        return task_service.create_task(project_id, data)
    except TaskServiceError as e:
        if e.code == "not_found":
            raise HTTPException(status_code=404, detail=e.message)
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/projects/{project_id}/tasks", response_model=TaskList)
def list_tasks(
    project_id: int,
    status: Optional[str] = Query(default=None),
    assignee: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TaskList:
    tasks, total = task_service.list_tasks(
        project_id, status=status, assignee=assignee, limit=limit, offset=offset
    )
    return TaskList(tasks=tasks, total=total)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int) -> TaskResponse:
    try:
        return task_service.get_task(task_id)
    except TaskServiceError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, data: TaskUpdate) -> TaskResponse:
    try:
        return task_service.update_task(task_id, data)
    except TaskServiceError as e:
        if e.code == "not_found":
            raise HTTPException(status_code=404, detail=e.message)
        if e.code == "invalid_transition":
            raise HTTPException(status_code=422, detail=e.message)
        raise HTTPException(status_code=400, detail=e.message)


@router.get(
    "/projects/{project_id}/tasks/search",
    response_model=list[TaskResponse],
)
def search_tasks(
    project_id: int,
    q: str = Query(..., min_length=1),
) -> list[TaskResponse]:
    return task_service.search_tasks(project_id, q)


# --- Comment endpoints ---

@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
def create_comment(task_id: int, data: CommentCreate) -> CommentResponse:
    # Verify task exists
    try:
        task_service.get_task(task_id)
    except TaskServiceError:
        raise HTTPException(status_code=404, detail="Task not found")

    with get_db() as conn:
        repo = CommentRepository(conn)
        comment = repo.create(task_id, data.author, data.body)
        return CommentResponse(**comment)


@router.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
def list_comments(task_id: int) -> list[CommentResponse]:
    with get_db() as conn:
        repo = CommentRepository(conn)
        comments = repo.list_by_task(task_id)
        return [CommentResponse(**c) for c in comments]
