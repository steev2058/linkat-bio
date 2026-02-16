from pathlib import Path
import secrets

from fastapi import FastAPI, HTTPException, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    APP_NAME,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    BOT_USERNAME,
    SUPPORT_TELEGRAM,
    BUSINESS_EMAIL,
    PAYMENT_METHODS_TEXT,
    UPLOAD_DIR,
)
from app.db import init_db, get_conn
from app.security import check_rate_limit, valid_http_url
from app.services import record_view, record_click, gen_code

app = FastAPI(title=APP_NAME)
security = HTTPBasic()
BASE_DIR = Path(__file__).resolve().parent.parent
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(Path(UPLOAD_DIR))), name="uploads")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def prefix_of(request: Request) -> str:
    p = (request.headers.get("x-forwarded-prefix") or "").strip()
    if p.endswith("/"):
        p = p[:-1]
    return p


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


@app.get("/", response_class=HTMLResponse)
def site_home(request: Request, lang: str = "ar"):
    prefix = prefix_of(request)
    return templates.TemplateResponse("site_home.html", {
        "request": request,
        "lang": lang,
        "prefix": prefix,
        "bot_link": f"https://t.me/{BOT_USERNAME}",
        "support_telegram": SUPPORT_TELEGRAM,
    })


@app.get("/pricing", response_class=HTMLResponse)
def site_pricing(request: Request, lang: str = "ar"):
    prefix = prefix_of(request)
    return templates.TemplateResponse("site_pricing.html", {
        "request": request,
        "lang": lang,
        "prefix": prefix,
        "payment_text": PAYMENT_METHODS_TEXT,
        "bot_link": f"https://t.me/{BOT_USERNAME}",
    })


@app.get("/examples", response_class=HTMLResponse)
def site_examples(request: Request, lang: str = "ar"):
    return templates.TemplateResponse("site_examples.html", {"request": request, "lang": lang, "prefix": prefix_of(request)})


@app.get("/faq", response_class=HTMLResponse)
def site_faq(request: Request, lang: str = "ar"):
    return templates.TemplateResponse("site_faq.html", {"request": request, "lang": lang, "prefix": prefix_of(request)})


@app.get("/contact", response_class=HTMLResponse)
def site_contact(request: Request, lang: str = "ar"):
    return templates.TemplateResponse("site_contact.html", {
        "request": request,
        "lang": lang,
        "prefix": prefix_of(request),
        "support_telegram": SUPPORT_TELEGRAM,
        "business_email": BUSINESS_EMAIL,
    })


@app.get("/u/{slug}", response_class=HTMLResponse)
def public_page(slug: str, request: Request):
    ip = request.client.host if request.client else "unknown"
    prefix = prefix_of(request)
    if not check_rate_limit(f"u:{ip}", limit=180, period_sec=60):
        raise HTTPException(status_code=429, detail="Too many requests")

    with get_conn() as conn:
        page = conn.execute("SELECT * FROM pages WHERE slug=? AND is_published=1", (slug,)).fetchone()
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        links = conn.execute("SELECT * FROM links WHERE page_id=? AND is_active=1 ORDER BY position ASC", (page["id"],)).fetchall()
        user = conn.execute("SELECT * FROM users WHERE id=?", (page["user_id"],)).fetchone()
    record_view(page["id"], ip, request.headers.get("user-agent", ""))
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
            "prefix": prefix,
        },
    )


@app.get("/r/{link_id}")
def redirect_link(link_id: int, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"r:{ip}", limit=240, period_sec=60):
        raise HTTPException(status_code=429, detail="Too many redirect requests")

    with get_conn() as conn:
        link = conn.execute("SELECT * FROM links WHERE id=? AND is_active=1", (link_id,)).fetchone()
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

    target = (link["url"] or "").strip()
    if not valid_http_url(target):
        raise HTTPException(status_code=400, detail="Unsafe target URL")

    record_click(link["page_id"], link_id, ip, request.headers.get("user-agent", ""))
    return RedirectResponse(target, status_code=302)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, _: bool = Depends(admin_auth)):
    prefix = prefix_of(request)
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
            "prefix": prefix,
            "users": users,
            "pages": pages,
            "vouchers": vouchers,
            "total_views": total_views,
            "total_clicks": total_clicks,
        },
    )


@app.post("/admin/voucher/create")
def admin_voucher_create(
    request: Request,
    plan_type: str = Form(...),
    duration_days: int = Form(...),
    _: bool = Depends(admin_auth),
):
    if plan_type not in {"PRO_1", "PRO_3"}:
        raise HTTPException(status_code=400, detail="Invalid plan")
    if duration_days not in {30, 90, 365}:
        raise HTTPException(status_code=400, detail="Invalid duration")
    code = gen_code(10)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO vouchers (code, plan_type, duration_days, created_at) VALUES (?, ?, ?, datetime('now'))",
            (code, plan_type, duration_days),
        )
    prefix = prefix_of(request)
    return RedirectResponse(url=f"{prefix}/admin" if prefix else "/admin", status_code=303)


@app.post("/admin/voucher/{voucher_id}/disable")
def admin_voucher_disable(request: Request, voucher_id: int, _: bool = Depends(admin_auth)):
    with get_conn() as conn:
        conn.execute("UPDATE vouchers SET is_active=0 WHERE id=?", (voucher_id,))
    prefix = prefix_of(request)
    return RedirectResponse(url=f"{prefix}/admin" if prefix else "/admin", status_code=303)
