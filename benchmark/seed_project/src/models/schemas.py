"""Pydantic models for request/response schemas.

PUBLIC API: These schemas are part of the public API contract.
Do not change field names, types, or remove fields.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Project schemas ---

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime
    archived: bool


class ProjectList(BaseModel):
    projects: list[ProjectResponse]
    total: int


# --- Task schemas ---

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    priority: int = Field(default=0, ge=0, le=3)
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    labels: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0, le=3)
    assignee: Optional[str] = None
    due_date: Optional[str] = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    status: str
    priority: int
    assignee: Optional[str]
    due_date: Optional[str]
    created_at: datetime
    updated_at: datetime
    labels: list[str] = Field(default_factory=list)


class TaskList(BaseModel):
    tasks: list[TaskResponse]
    total: int


# --- Comment schemas ---

class CommentCreate(BaseModel):
    author: str = Field(..., min_length=1, max_length=50)
    body: str = Field(..., min_length=1)


class CommentResponse(BaseModel):
    id: int
    task_id: int
    author: str
    body: str
    created_at: datetime


# --- Error schemas ---

class ErrorResponse(BaseModel):
    detail: str
    code: str


# --- Stats schemas ---

class ProjectStats(BaseModel):
    project_id: int
    project_name: str
    total_tasks: int
    by_status: dict[str, int]
    by_priority: dict[int, int]
    overdue_count: int
