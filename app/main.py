from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import secrets

from app.config import APP_NAME, ADMIN_USERNAME, ADMIN_PASSWORD
from app.db import init_db, get_conn
from app.services import record_view, record_click, gen_code

app = FastAPI(title=APP_NAME)
security = HTTPBasic()
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def admin_auth(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/u/{slug}", response_class=HTMLResponse)
def public_page(slug: str, request: Request):
    with get_conn() as conn:
        page = conn.execute("SELECT * FROM pages WHERE slug=? AND is_published=1", (slug,)).fetchone()
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        links = conn.execute("SELECT * FROM links WHERE page_id=? AND is_active=1 ORDER BY position ASC", (page["id"],)).fetchall()
        user = conn.execute("SELECT * FROM users WHERE id=?", (page["user_id"],)).fetchone()
    record_view(page["id"], request.client.host if request.client else "", request.headers.get("user-agent", ""))
    show_watermark = True
    if user and user["plan_type"] != "FREE" and user["plan_expires_at"]:
        show_watermark = False
    return templates.TemplateResponse(
        "public_page.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "page": page,
            "links": links,
            "show_watermark": show_watermark,
        },
    )


@app.get("/r/{link_id}")
def redirect_link(link_id: int, request: Request):
    with get_conn() as conn:
        link = conn.execute("SELECT * FROM links WHERE id=? AND is_active=1", (link_id,)).fetchone()
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")
    record_click(link["page_id"], link_id, request.client.host if request.client else "", request.headers.get("user-agent", ""))
    return RedirectResponse(link["url"], status_code=302)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, _: bool = Depends(admin_auth)):
    with get_conn() as conn:
        users = conn.execute("SELECT * FROM users ORDER BY id DESC LIMIT 100").fetchall()
        pages = conn.execute("SELECT * FROM pages ORDER BY id DESC LIMIT 100").fetchall()
        vouchers = conn.execute("SELECT * FROM vouchers ORDER BY id DESC LIMIT 200").fetchall()
        total_views = conn.execute("SELECT COUNT(*) c FROM analytics_events WHERE event_type='view'").fetchone()["c"]
        total_clicks = conn.execute("SELECT COUNT(*) c FROM analytics_events WHERE event_type='click'").fetchone()["c"]
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "users": users,
            "pages": pages,
            "vouchers": vouchers,
            "total_views": total_views,
            "total_clicks": total_clicks,
        },
    )


@app.post("/admin/voucher/create")
def admin_voucher_create(
    plan_type: str = Form(...),
    duration_days: int = Form(...),
    _: bool = Depends(admin_auth),
):
    code = gen_code(10)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO vouchers (code, plan_type, duration_days, created_at) VALUES (?, ?, ?, datetime('now'))",
            (code, plan_type, duration_days),
        )
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/voucher/{voucher_id}/disable")
def admin_voucher_disable(voucher_id: int, _: bool = Depends(admin_auth)):
    with get_conn() as conn:
        conn.execute("UPDATE vouchers SET is_active=0 WHERE id=?", (voucher_id,))
    return RedirectResponse(url="/admin", status_code=303)
