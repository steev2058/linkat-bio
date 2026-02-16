import random
import string
from datetime import datetime, timedelta
from slugify import slugify

from app.db import get_conn, utcnow
from app.security import valid_http_url, sanitize_text


def gen_code(n=10):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(n))


def generate_unique_slug(name: str) -> str:
    base = slugify(name or "")
    if not base:
        base = "u-" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    slug = base[:40]
    with get_conn() as conn:
        i = 1
        candidate = slug
        while conn.execute("SELECT id FROM pages WHERE slug=?", (candidate,)).fetchone():
            i += 1
            candidate = f"{slug[:34]}-{i}"
        return candidate


def upsert_page_field(page_id: int, field: str, value):
    with get_conn() as conn:
        conn.execute(f"UPDATE pages SET {field}=?, updated_at=? WHERE id=?", (value, utcnow(), page_id))


def add_link(page_id: int, title: str, url: str, platform: str = "custom"):
    if not valid_http_url(url):
        raise ValueError("invalid_url")
    safe_title = sanitize_text(title, 80)
    safe_url = (url or "").strip()
    with get_conn() as conn:
        max_pos = conn.execute("SELECT COALESCE(MAX(position),0) AS m FROM links WHERE page_id=?", (page_id,)).fetchone()["m"]
        conn.execute(
            "INSERT INTO links (page_id, title, url, platform, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (page_id, safe_title, safe_url, platform, max_pos + 1, utcnow()),
        )


def list_links(page_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM links WHERE page_id=? AND is_active=1 ORDER BY position ASC", (page_id,)).fetchall()


def remove_link(page_id: int, index: int):
    links = list_links(page_id)
    if index < 1 or index > len(links):
        return False
    link_id = links[index - 1]["id"]
    with get_conn() as conn:
        conn.execute("UPDATE links SET is_active=0 WHERE id=?", (link_id,))
    return True


def reorder_link(page_id: int, from_pos: int, to_pos: int):
    links = list_links(page_id)
    n = len(links)
    if from_pos < 1 or from_pos > n or to_pos < 1 or to_pos > n:
        return False
    arr = list(links)
    item = arr.pop(from_pos - 1)
    arr.insert(to_pos - 1, item)
    with get_conn() as conn:
        for i, l in enumerate(arr, start=1):
            conn.execute("UPDATE links SET position=? WHERE id=?", (i, l["id"]))
    return True


def plan_limits(user_row):
    plan = user_row["plan_type"]
    exp = user_row["plan_expires_at"]
    paid_active = False
    if plan != "FREE" and exp:
        try:
            paid_active = datetime.fromisoformat(exp) > datetime.utcnow()
        except Exception:
            paid_active = False
    if not paid_active:
        return {
            "plan": "FREE",
            "max_links": 3,
            "watermark": True,
            "custom_theme": False,
            "featured_video": False,
            "reorder": False,
        }
    if plan == "PRO_1":
        return {
            "plan": "PRO_1",
            "max_links": 999,
            "watermark": False,
            "custom_theme": True,
            "featured_video": False,
            "reorder": True,
        }
    return {
        "plan": "PRO_3",
        "max_links": 999,
        "watermark": False,
        "custom_theme": True,
        "featured_video": True,
        "reorder": True,
    }


def record_view(page_id: int, ip: str = "", ua: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analytics_events (page_id, link_id, event_type, ip, user_agent, created_at) VALUES (?, NULL, 'view', ?, ?, ?)",
            (page_id, ip, ua, utcnow()),
        )


def record_click(page_id: int, link_id: int, ip: str = "", ua: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analytics_events (page_id, link_id, event_type, ip, user_agent, created_at) VALUES (?, ?, 'click', ?, ?, ?)",
            (page_id, link_id, ip, ua, utcnow()),
        )


def stats_for_user(user_id: int):
    with get_conn() as conn:
        page = conn.execute("SELECT * FROM pages WHERE user_id=?", (user_id,)).fetchone()
        if not page:
            return {"views_total": 0, "clicks_total": 0, "views_7d": 0, "clicks_7d": 0, "top_links": []}
        page_id = page["id"]
        since = (datetime.utcnow() - timedelta(days=7)).isoformat()
        views_total = conn.execute("SELECT COUNT(*) c FROM analytics_events WHERE page_id=? AND event_type='view'", (page_id,)).fetchone()["c"]
        clicks_total = conn.execute("SELECT COUNT(*) c FROM analytics_events WHERE page_id=? AND event_type='click'", (page_id,)).fetchone()["c"]
        views_7d = conn.execute("SELECT COUNT(*) c FROM analytics_events WHERE page_id=? AND event_type='view' AND created_at>=?", (page_id, since)).fetchone()["c"]
        clicks_7d = conn.execute("SELECT COUNT(*) c FROM analytics_events WHERE page_id=? AND event_type='click' AND created_at>=?", (page_id, since)).fetchone()["c"]
        top = conn.execute(
            """
            SELECT l.title, l.url, COUNT(a.id) c
            FROM analytics_events a
            JOIN links l ON l.id=a.link_id
            WHERE a.page_id=? AND a.event_type='click'
            GROUP BY l.id
            ORDER BY c DESC
            LIMIT 5
            """,
            (page_id,),
        ).fetchall()
        return {
            "views_total": views_total,
            "clicks_total": clicks_total,
            "views_7d": views_7d,
            "clicks_7d": clicks_7d,
            "top_links": top,
        }
