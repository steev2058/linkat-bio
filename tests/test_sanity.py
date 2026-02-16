import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.services import generate_unique_slug


def test_health():
    c = TestClient(app)
    r = c.get('/api/health')
    assert r.status_code == 200
    assert r.json().get('status') == 'ok'


def test_slug_generation():
    s = generate_unique_slug('مرحبا بكم في لينكات')
    assert s
    assert len(s) <= 40
