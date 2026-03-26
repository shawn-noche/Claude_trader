# Event-to-Trade Engine

A causal reasoning engine that maps financial news to trade candidates across the semiconductor and AI infrastructure universe.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
```

## Run

```bash
cd /path/to/event-to-trade
uvicorn backend.main:app --reload
```

API docs: http://localhost:8000/docs

## Test

```bash
pytest backend/tests/ -v
```

## Current status

| Step | Module | Status |
|------|--------|--------|
| 1 | Ingestion | Done |
| 2 | Classifier + KB | Stub |
| 3 | Impact engine + Ranker | Stub |
| 4 | Trade idea narrative | Stub |
| 5 | Frontend | Not started |
