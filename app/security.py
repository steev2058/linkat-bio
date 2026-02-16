import html
import re
import time
from collections import defaultdict, deque
from urllib.parse import urlparse


_rate = defaultdict(deque)


def sanitize_text(v: str, max_len: int = 220) -> str:
    v = (v or "").strip()
    v = re.sub(r"\s+", " ", v)
    v = html.escape(v[:max_len])
    return v


def valid_http_url(url: str) -> bool:
    try:
        u = urlparse((url or "").strip())
        if u.scheme not in {"http", "https"}:
            return False
        if not u.netloc:
            return False
        raw = url.lower()
        if raw.startswith("javascript:") or raw.startswith("data:"):
            return False
        # block obvious internal targets for redirect abuse
        if any(x in (u.hostname or "") for x in ["localhost", "127.0.0.1", "0.0.0.0"]):
            return False
        return True
    except Exception:
        return False


def check_rate_limit(key: str, limit: int = 120, period_sec: int = 60) -> bool:
    now = time.time()
    q = _rate[key]
    while q and now - q[0] > period_sec:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True
