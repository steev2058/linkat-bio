PY=python3

install:
	$(PY) -m pip install -r requirements.txt

dev:
	$(PY) scripts/dev.py

web:
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

bot:
	$(PY) -m bot.main

test:
	$(PY) -m pytest -q

seed:
	$(PY) -m scripts.seed_sample
