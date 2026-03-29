# Event-to-Trade Engine

A causal reasoning engine that maps financial news articles to trade candidates across the semiconductor and AI infrastructure universe.

**Input:** Financial news article URL
**Output:** Structured analysis including event classification, impact buckets (beneficiaries/losers by order), ranked candidates, and top trade ideas.

---

## Architecture

| Step | Component | Status |
|------|-----------|--------|
| 1 | Article ingestion (trafilatura + BeautifulSoup) | ✅ Complete |
| 2 | Event classifier (LLM + typed schemas) | ✅ Complete |
| 3 | Hybrid impact engine (LLM + KB constraint) | ✅ Complete |
| 4 | Deterministic ranker (Formula B: order/confidence/tradability/priced-in) | ✅ Complete |
| 5 | Trade idea generator (LLM + anti-hallucination) | ✅ Complete |
| 6 | Web frontend (single-page HTML/CSS/JS) | ✅ Complete |

---

## Setup & Run

### Requirements
- Python 3.11+
- Anthropic API key (from https://console.anthropic.com)

### Installation

```bash
# Extract the project
cd Claude_trader

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Edit .env and add your API key
# ANTHROPIC_API_KEY=sk-ant-...
```

### Run the server

```bash
uvicorn backend.main:app --reload
```

Then open http://localhost:8000 in your browser.

The app will also expose:
- API docs: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json

### Run tests

```bash
pytest backend/tests/ -v
# 142 tests, all passing
```

---

## Project Structure

```
Claude_trader/
├── backend/
│   ├── api/routes.py              # POST /api/v1/analyze
│   ├── services/
│   │   ├── ingestion.py           # Article fetching + parsing
│   │   ├── classifier.py          # Event classification (LLM)
│   │   ├── knowledge_base.py      # In-memory KB (28 companies, 40 relationships)
│   │   ├── impact_engine.py       # Impact mapping (LLM + KB constraints)
│   │   ├── ranker.py              # Deterministic scoring (Formula B)
│   │   ├── trade_idea_generator.py# Trade idea generation (LLM)
│   │   └── llm_client.py          # Anthropic SDK wrapper
│   ├── schemas/                   # Pydantic v2 models
│   │   ├── article.py
│   │   ├── event.py
│   │   ├── impact.py
│   │   └── analysis.py
│   ├── prompts/                   # LLM prompt templates
│   │   ├── classify_event.txt
│   │   ├── map_impacts.txt
│   │   └── trade_ideas.txt
│   ├── knowledge/                 # Curated KB data
│   │   ├── companies.json         # 28 semiconductor/AI infra companies
│   │   └── relationships.json     # 40 supply-chain relationships
│   ├── tests/                     # 142 tests, 100% passing
│   ├── config.py
│   └── main.py
├── frontend/
│   └── index.html                 # Single-page UI (no build step, no CDN)
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
└── README.md
```

---

## Core Features

### 1. Article Ingestion
- Async fetch via httpx (15s timeout, 20K char limit)
- Trafilatura primary extractor + BeautifulSoup fallback
- Metadata extraction (title, author, date, domain)

### 2. Event Classification
- Claude analyzes article → returns typed `Event`
- 11 event types (earnings, guidance, supply_chain, etc.)
- Focal entities, direction, magnitude, time horizon, confidence

### 3. Hybrid Impact Engine
- Resolves entities against KB (28 companies)
- Builds constrained universe via 2-hop graph traversal
- Claude assesses impact on each candidate
- **Anti-hallucination:** Only accepts KB tickers
- Filters low-confidence candidates (< 0.40)

### 4. Deterministic Ranker (Formula B)
- Balances economic exposure + underreacted opportunities
- Scoring: 25% order + 30% confidence + 20% tradability + 25% priced-in
- Fresh second-order names can beat stale direct names

### 5. Trade Idea Generator
- Produces up to 3 structured ideas from top candidates
- Each idea: why_now, key_mechanism, underappreciated angle, risk
- No invented financial figures (sourced from article/KB only)

### 6. Web Frontend
- Zero dependencies (single HTML file, embedded CSS/JS)
- Dark theme, monospace tickers, real-time analysis
- Results: article summary, event grid, impact buckets, candidates table, trade ideas

---

## API Reference

### POST `/api/v1/analyze`

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://reuters.com/article/..."}'
```

**Response (200):**
- `request_id`, `analyzed_at`, `duration_seconds`
- `article` (metadata)
- `event` (classification)
- `impact_buckets` (6 directional categories)
- `candidates` (ranked by score)
- `top_trade_ideas` (up to 3 structured ideas)

**Error (422):**
- Invalid URL, network failure, or parsing error

**Graceful degradation (200):**
- Impact mapping fails → empty candidates/ideas but still returns event

---

## Configuration

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
LOG_LEVEL=INFO
FETCH_TIMEOUT_SECONDS=15
MAX_ARTICLE_CHARS=20000
CLAUDE_MODEL=claude-sonnet-4-6
LLM_MAX_TOKENS=4096
```

---

## Knowledge Base

**28 Companies:** NVDA, AMD, TSM, INTC, AVGO, QCOM, MRVL, HXSCL, MU, ASML, AMAT, LRCX, KLAC, AMKR, ASX, COHR, LITE, ANET, CSCO, SMCI, HPE, DELL, VRT, ETN, SSNLF, MSFT, GOOGL, AMZN, META

**40 Relationships:** foundry_customer, memory_customer, equipment_supplier, packaging_customer, component_supplier_to, major_customer, networking_customer, asic_customer, infrastructure_customer, server_customer

---

## Testing

```bash
# All tests
pytest backend/tests/ -v

# Single test file
pytest backend/tests/test_ranker.py -v

# Coverage report
pytest backend/tests/ --cov=backend --cov-report=html
```

---

## Next Steps (Deferred)

- Live market data (stock prices, options, technicals)
- SQLite caching layer
- Extended knowledge base
- PDF report generation
- TradingView integration

---

## License

Personal use. Built with Claude API.
