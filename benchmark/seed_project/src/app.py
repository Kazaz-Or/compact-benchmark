"""FastAPI application entry point."""

from fastapi import FastAPI

from src.api.routes import router
from src.database import init_db

app = FastAPI(title="TaskFlow API", version="0.1.0")
app.include_router(router, prefix="/api/v1")


@app.on_event("startup")
def startup() -> None:
    init_db()
