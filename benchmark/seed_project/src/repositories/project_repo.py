"""Repository layer for projects."""

import sqlite3
from typing import Optional


class ProjectRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, name: str, description: str = "") -> dict:
        cursor = self.conn.execute(
            "INSERT INTO projects (name, description) VALUES (?, ?)",
            (name, description),
        )
        return self.get_by_id(cursor.lastrowid)  # type: ignore

    def get_by_id(self, project_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_by_name(self, name: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_all(self, include_archived: bool = False) -> list[dict]:
        if include_archived:
            rows = self.conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM projects WHERE archived = 0 ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]

    def archive(self, project_id: int) -> bool:
        cursor = self.conn.execute(
            "UPDATE projects SET archived = 1 WHERE id = ?", (project_id,)
        )
        return cursor.rowcount > 0

    def delete(self, project_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        )
        return cursor.rowcount > 0
