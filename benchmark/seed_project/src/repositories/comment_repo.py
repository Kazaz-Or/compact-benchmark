"""Repository layer for comments."""

import sqlite3
from typing import Optional


class CommentRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, task_id: int, author: str, body: str) -> dict:
        cursor = self.conn.execute(
            "INSERT INTO comments (task_id, author, body) VALUES (?, ?, ?)",
            (task_id, author, body),
        )
        return self.get_by_id(cursor.lastrowid)  # type: ignore

    def get_by_id(self, comment_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM comments WHERE id = ?", (comment_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_by_task(self, task_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM comments WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, comment_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM comments WHERE id = ?", (comment_id,)
        )
        return cursor.rowcount > 0
