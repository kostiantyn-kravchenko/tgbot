import os
import psycopg

DATABASE_URL = (os.getenv("DATABASE_PRIVATE_URL")
 or os.getenv("DATABASE_URL"))
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

def init_db():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_state (
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    memory_on BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (chat_id, user_id)
                );
            """)
        conn.commit()

def load_state(chat_id: int, user_id: int) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT summary, memory_on FROM user_state WHERE chat_id=%s AND user_id=%s",
                (chat_id, user_id),
            )
            row = cur.fetchone()
    if row:
        return {"summary": row[0] or "", "memory_on": bool(row[1])}
    return {"summary": "", "memory_on": True}

def save_state(chat_id: int, user_id: int, summary: str, memory_on: bool) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_state (chat_id, user_id, summary, memory_on)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (chat_id, user_id)
                DO UPDATE SET
                    summary = EXCLUDED.summary,
                    memory_on = EXCLUDED.memory_on,
                    updated_at = NOW();
            """, (chat_id, user_id, summary, memory_on))
        conn.commit()

def clear_state(chat_id: int, user_id: int) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_state WHERE chat_id=%s AND user_id=%s", (chat_id, user_id))
        conn.commit()
