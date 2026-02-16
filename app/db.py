import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from app.config import DB_PATH


def utcnow() -> str:
    return datetime.utcnow().isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                language TEXT DEFAULT 'ar',
                plan_type TEXT DEFAULT 'FREE',
                plan_expires_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                slug TEXT UNIQUE,
                display_name TEXT,
                bio TEXT,
                avatar_path TEXT,
                theme_color TEXT DEFAULT '#0f172a',
                featured_video_url TEXT,
                offer_title TEXT,
                offer_url TEXT,
                is_published INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                platform TEXT,
                position INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(page_id) REFERENCES pages(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                plan_type TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                redeemed_by_user_id INTEGER,
                redeemed_at TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(redeemed_by_user_id) REFERENCES users(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER NOT NULL,
                link_id INTEGER,
                event_type TEXT NOT NULL,
                ip TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(page_id) REFERENCES pages(id),
                FOREIGN KEY(link_id) REFERENCES links(id)
            )
            """
        )


def ensure_user(tg_user_id: int, username: Optional[str] = None):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE tg_user_id=?", (tg_user_id,)).fetchone()
        if row:
            return row
        conn.execute(
            "INSERT INTO users (tg_user_id, username, created_at) VALUES (?, ?, ?)",
            (tg_user_id, username or "", utcnow()),
        )
        return conn.execute("SELECT * FROM users WHERE tg_user_id=?", (tg_user_id,)).fetchone()


def ensure_page(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pages WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return row
        now = utcnow()
        conn.execute(
            "INSERT INTO pages (user_id, created_at, updated_at) VALUES (?, ?, ?)",
            (user_id, now, now),
        )
        return conn.execute("SELECT * FROM pages WHERE user_id=?", (user_id,)).fetchone()


def is_paid(user_row) -> bool:
    if not user_row:
        return False
    plan = user_row["plan_type"]
    if plan == "FREE":
        return False
    exp = user_row["plan_expires_at"]
    if not exp:
        return False
    return datetime.fromisoformat(exp) > datetime.utcnow()


def redeem_voucher_for_user(user_id: int, code: str):
    with get_conn() as conn:
        v = conn.execute("SELECT * FROM vouchers WHERE code=?", (code.upper(),)).fetchone()
        if not v:
            return False, "الكود غير موجود"
        if not v["is_active"]:
            return False, "الكود غير مفعّل"
        if v["redeemed_by_user_id"]:
            return False, "الكود مستخدم سابقاً"
        expires_at = (datetime.utcnow() + timedelta(days=int(v["duration_days"]))).isoformat()
        conn.execute(
            "UPDATE vouchers SET redeemed_by_user_id=?, redeemed_at=?, expires_at=?, is_active=0 WHERE id=?",
            (user_id, utcnow(), expires_at, v["id"]),
        )
        conn.execute(
            "UPDATE users SET plan_type=?, plan_expires_at=? WHERE id=?",
            (v["plan_type"], expires_at, user_id),
        )
        return True, f"تم تفعيل الباقة {v['plan_type']} حتى {expires_at[:10]}"
