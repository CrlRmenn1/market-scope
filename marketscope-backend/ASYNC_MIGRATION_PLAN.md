# Async/PostgreSQL migration plan for MarketScope FastAPI backend

## 1. Why migrate?
- psycopg2 is synchronous: blocks the event loop, limits concurrency, causes slow endpoints under load.
- Async drivers (asyncpg, databases, SQLAlchemy async) allow FastAPI to handle many requests in parallel.
- Connection pooling reduces connection overhead and improves DB throughput.

## 2. Migration steps

### a. Choose async DB library
- Recommended: `asyncpg` (raw, fastest) or `databases` (higher-level, easier migration)
- For full ORM: SQLAlchemy 1.4+ async support

### b. Refactor DB access
- Replace all `psycopg2.connect` and cursor usage with async equivalents
- Use a global connection pool (created at startup, closed at shutdown)
- All DB calls become `await pool.fetch(...)` or `await database.fetch_all(...)`

### c. Update FastAPI endpoints
- Change all endpoints that hit the DB to `async def`
- Use `await` for all DB calls

### d. Test and optimize
- Test all endpoints for correctness and speed
- Use `EXPLAIN ANALYZE` in psql to check for slow queries

## 3. Example: asyncpg usage

```python
import asyncpg
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
async def startup():
    app.state.pool = await asyncpg.create_pool(dsn="postgresql://user:pass@host:port/dbname", min_size=2, max_size=10)

@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    pool = app.state.pool
    row = await pool.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    return dict(row) if row else {}
```

## 4. Next steps
- Pick a table/endpoint to migrate first (e.g., login or history)
- Refactor, test, then repeat for all DB access
- Remove all psycopg2 usage when done

---

Let me know if you want to start with a specific endpoint, or want a full async refactor for the whole backend!