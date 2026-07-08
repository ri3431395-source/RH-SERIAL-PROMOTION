import sqlite3
import threading
import config

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    with _lock:
        conn = _connect()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_promo (
                user_id INTEGER PRIMARY KEY,
                file_id TEXT NOT NULL,
                file_unique_id TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()


# ---------------- user promo video ----------------

def set_user_promo(user_id: int, file_id: str, file_unique_id: str = ""):
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO user_promo (user_id, file_id, file_unique_id, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(user_id) DO UPDATE SET file_id=excluded.file_id, "
            "file_unique_id=excluded.file_unique_id, updated_at=CURRENT_TIMESTAMP",
            (user_id, file_id, file_unique_id),
        )
        conn.commit()
        conn.close()


def get_user_promo(user_id: int):
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT file_id FROM user_promo WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else None


# ---------------- global admin-fixed end video ----------------

def set_setting(key: str, value: str):
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
        conn.close()


def get_setting(key: str):
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT value FROM bot_settings WHERE key=?", (key,)
        ).fetchone()
        conn.close()
        return row[0] if row else None


def set_admin_end_video(file_id: str):
    set_setting("admin_end_video_file_id", file_id)


def get_admin_end_video():
    return get_setting("admin_end_video_file_id")


def set_default_promo(file_id: str):
    set_setting("default_promo_file_id", file_id)


def get_default_promo():
    return get_setting("default_promo_file_id")
