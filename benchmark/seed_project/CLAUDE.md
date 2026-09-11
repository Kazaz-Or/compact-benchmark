# TaskFlow API

A task management REST API built with Python, FastAPI, and SQLite.

## Architecture

```
src/
  database.py          - SQLite connection management
  app.py               - FastAPI app entry point
  models/schemas.py    - Pydantic request/response schemas
  repositories/        - Data access layer (one repo per table)
  services/            - Business logic layer
  api/routes.py        - HTTP route handlers
tests/
  conftest.py          - Shared fixtures
  test_basic.py        - Core API tests
```

## Commands

- Run tests: `python -m pytest tests/ -v`
- Run app: `python -m uvicorn src.app:app --reload`
- Type check: `python -m mypy src/`
- Lint: `python -m ruff check src/`

## Constraints

- **Public API signatures cannot change.** The schemas in `src/models/schemas.py` are consumed by external clients.
- **No new runtime dependencies.** Only stdlib + fastapi + pydantic + uvicorn.
- **Existing error response schemas must remain compatible.** Error detail format is `{"detail": "message"}` or `{"detail": {"detail": "msg", "code": "code"}}`.
- **Repository interfaces cannot change.** Method signatures in `*_repo.py` are stable.
- **Existing integration tests must continue to pass.**

## Known issues

- The task list `total` count may not match filtered results.
- Task `updated_at` may not reflect recent changes.
- The search endpoint has not been security-reviewed.
