"""User login sessions: random tokens, stored only as hashes, that can be revoked."""
import hashlib
import secrets


SESSION_DAYS = 7


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(conn, user_id: int) -> str:
    """Returns the token for the client. Only its hash is saved."""
    token = secrets.token_urlsafe(32)
    await conn.execute("DELETE FROM user_sessions WHERE user_id = $1 AND expires_at < CURRENT_TIMESTAMP", user_id)
    await conn.execute(
        """
        INSERT INTO user_sessions (token_hash, user_id, expires_at)
        VALUES ($1, $2, CURRENT_TIMESTAMP + make_interval(days => $3))
        """,
        hash_token(token),
        user_id,
        SESSION_DAYS,
    )
    return token


async def find_session_user_id(pool, token: str) -> int | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM user_sessions WHERE token_hash = $1 AND expires_at > CURRENT_TIMESTAMP",
            hash_token(token),
        )
    return row["user_id"] if row else None


async def delete_session(pool, token: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_sessions WHERE token_hash = $1", hash_token(token))


async def delete_user_sessions(conn, user_id: int) -> None:
    await conn.execute("DELETE FROM user_sessions WHERE user_id = $1", user_id)
