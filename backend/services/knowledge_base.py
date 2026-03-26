"""
Knowledge base — in-memory index of curated semiconductor/AI infra companies
and their supply-chain relationships.

Loaded lazily on first access. All public functions are safe to call before
an explicit load(); they will trigger loading automatically.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_KB_DIR = Path(__file__).parent.parent / "knowledge"

# Raw data
_companies: list[dict] = []
_relationships: list[dict] = []

# Indexes built at load time
_by_ticker: dict[str, dict] = {}
_by_name_lower: dict[str, dict] = {}
_by_role: dict[str, list[dict]] = {}
_by_theme: dict[str, list[dict]] = {}

_loaded = False


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load() -> None:
    """Load and index the knowledge base from JSON files. Idempotent."""
    global _companies, _relationships, _loaded
    global _by_ticker, _by_name_lower, _by_role, _by_theme

    companies_path = _KB_DIR / "companies.json"
    relationships_path = _KB_DIR / "relationships.json"

    _companies = json.loads(companies_path.read_text(encoding="utf-8"))
    _relationships = json.loads(relationships_path.read_text(encoding="utf-8"))

    _by_ticker = {}
    _by_name_lower = {}
    _by_role = {}
    _by_theme = {}

    for company in _companies:
        ticker = company.get("ticker", "").upper()
        if ticker:
            _by_ticker[ticker] = company

        name = company.get("name", "")
        if name:
            _by_name_lower[name.lower()] = company

        for role in company.get("roles", []):
            _by_role.setdefault(role, []).append(company)

        for theme in company.get("themes", []):
            _by_theme.setdefault(theme, []).append(company)

    _loaded = True
    logger.info(
        "Knowledge base loaded: %d companies, %d relationships",
        len(_companies),
        len(_relationships),
    )


def _ensure_loaded() -> None:
    if not _loaded:
        load()


# ---------------------------------------------------------------------------
# Company lookups
# ---------------------------------------------------------------------------

def get_company(ticker: str) -> dict | None:
    """Return the company record for *ticker*, or None if not found."""
    _ensure_loaded()
    return _by_ticker.get(ticker.upper())


def get_company_by_name(name: str) -> dict | None:
    """Case-insensitive exact name lookup."""
    _ensure_loaded()
    return _by_name_lower.get(name.lower())


def get_companies_by_role(role: str) -> list[dict]:
    """Return all companies that have *role* in their roles list."""
    _ensure_loaded()
    return list(_by_role.get(role, []))


def get_companies_by_theme(theme: str) -> list[dict]:
    """Return all companies that have *theme* in their themes list."""
    _ensure_loaded()
    return list(_by_theme.get(theme, []))


def resolve_entities(names: list[str]) -> list[dict]:
    """
    Given a list of ticker symbols or company names (as returned by the LLM),
    return matching KB company records. Skips unrecognised entities.
    """
    _ensure_loaded()
    results = []
    seen: set[str] = set()
    for name in names:
        company = get_company(name) or get_company_by_name(name)
        if company and company["ticker"] not in seen:
            results.append(company)
            seen.add(company["ticker"])
    return results


# ---------------------------------------------------------------------------
# Relationship lookups
# ---------------------------------------------------------------------------

def get_relationships(ticker: str) -> list[dict]:
    """All relationships where *ticker* is the source (from)."""
    _ensure_loaded()
    t = ticker.upper()
    return [r for r in _relationships if r.get("from", "").upper() == t]


def get_inbound_relationships(ticker: str) -> list[dict]:
    """All relationships where *ticker* is the target (to)."""
    _ensure_loaded()
    t = ticker.upper()
    return [r for r in _relationships if r.get("to", "").upper() == t]


def get_relationships_by_type(rel_type: str) -> list[dict]:
    """All relationships of a given type across the entire graph."""
    _ensure_loaded()
    return [r for r in _relationships if r.get("type") == rel_type]


def get_ecosystem(ticker: str) -> dict[str, list[dict]]:
    """
    Return a dict with outbound and inbound relationships for *ticker*,
    useful for quickly mapping the supply-chain neighbourhood.
    """
    return {
        "outbound": get_relationships(ticker),
        "inbound": get_inbound_relationships(ticker),
    }


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------

def all_tickers() -> list[str]:
    _ensure_loaded()
    return sorted(_by_ticker.keys())


def all_companies() -> list[dict]:
    _ensure_loaded()
    return list(_companies)


def all_relationship_types() -> list[str]:
    _ensure_loaded()
    return sorted({r.get("type", "") for r in _relationships if r.get("type")})
