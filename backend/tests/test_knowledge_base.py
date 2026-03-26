"""
Tests for the knowledge base loader and query interface.

Uses the real JSON files — no mocking required.
"""

import pytest
from backend.services import knowledge_base as kb


@pytest.fixture(autouse=True)
def reload_kb():
    """Reset KB state before each test so tests are independent."""
    kb._loaded = False
    kb._companies = []
    kb._relationships = []
    kb._by_ticker = {}
    kb._by_name_lower = {}
    kb._by_role = {}
    kb._by_theme = {}
    yield
    # leave loaded state for next test (autouse handles reset)


class TestLoad:
    def test_load_populates_companies(self):
        kb.load()
        assert len(kb._companies) > 0

    def test_load_populates_relationships(self):
        kb.load()
        assert len(kb._relationships) > 0

    def test_load_is_idempotent(self):
        kb.load()
        count = len(kb._companies)
        kb.load()
        assert len(kb._companies) == count


class TestCompanyLookups:
    def test_get_company_by_known_ticker(self):
        company = kb.get_company("NVDA")
        assert company is not None
        assert company["ticker"] == "NVDA"
        assert company["name"] == "NVIDIA"

    def test_get_company_case_insensitive(self):
        assert kb.get_company("nvda") == kb.get_company("NVDA")

    def test_get_company_unknown_ticker_returns_none(self):
        assert kb.get_company("ZZZZZ") is None

    def test_get_company_by_name(self):
        company = kb.get_company_by_name("TSMC")
        assert company is not None
        assert company["ticker"] == "TSM"

    def test_get_company_by_name_case_insensitive(self):
        assert kb.get_company_by_name("tsmc") == kb.get_company_by_name("TSMC")

    def test_get_companies_by_role_foundry(self):
        foundries = kb.get_companies_by_role("foundry")
        tickers = [c["ticker"] for c in foundries]
        assert "TSM" in tickers

    def test_get_companies_by_role_ai_accelerator(self):
        accelerators = kb.get_companies_by_role("ai_accelerator")
        tickers = [c["ticker"] for c in accelerators]
        assert "NVDA" in tickers
        assert "AMD" in tickers

    def test_get_companies_by_theme_hbm_memory(self):
        companies = kb.get_companies_by_theme("hbm_memory")
        tickers = [c["ticker"] for c in companies]
        assert "HXSCL" in tickers
        assert "MU" in tickers

    def test_get_companies_by_unknown_role_returns_empty(self):
        assert kb.get_companies_by_role("nonexistent_role") == []

    def test_get_companies_by_unknown_theme_returns_empty(self):
        assert kb.get_companies_by_theme("nonexistent_theme") == []


class TestResolveEntities:
    def test_resolves_ticker_symbols(self):
        companies = kb.resolve_entities(["NVDA", "TSM"])
        tickers = [c["ticker"] for c in companies]
        assert "NVDA" in tickers
        assert "TSM" in tickers

    def test_resolves_company_names(self):
        companies = kb.resolve_entities(["NVIDIA", "TSMC"])
        tickers = [c["ticker"] for c in companies]
        assert "NVDA" in tickers
        assert "TSM" in tickers

    def test_skips_unknown_entities(self):
        companies = kb.resolve_entities(["NVDA", "UNKNOWN_CO"])
        assert len(companies) == 1
        assert companies[0]["ticker"] == "NVDA"

    def test_deduplicates_same_entity(self):
        companies = kb.resolve_entities(["NVDA", "NVIDIA"])
        assert len(companies) == 1

    def test_empty_input_returns_empty(self):
        assert kb.resolve_entities([]) == []


class TestRelationshipLookups:
    def test_get_relationships_for_nvda(self):
        rels = kb.get_relationships("NVDA")
        rel_types = [r["type"] for r in rels]
        assert "foundry_customer" in rel_types
        assert "memory_customer" in rel_types

    def test_get_relationships_case_insensitive(self):
        assert kb.get_relationships("nvda") == kb.get_relationships("NVDA")

    def test_get_inbound_relationships_for_tsm(self):
        rels = kb.get_inbound_relationships("TSM")
        from_tickers = [r["from"] for r in rels]
        assert "NVDA" in from_tickers
        assert "AMD" in from_tickers

    def test_get_relationships_by_type(self):
        rels = kb.get_relationships_by_type("foundry_customer")
        assert len(rels) > 0
        assert all(r["type"] == "foundry_customer" for r in rels)

    def test_get_ecosystem_returns_both_directions(self):
        eco = kb.get_ecosystem("NVDA")
        assert "outbound" in eco
        assert "inbound" in eco
        assert len(eco["outbound"]) > 0

    def test_unknown_ticker_returns_empty_relationships(self):
        assert kb.get_relationships("ZZZZZ") == []
        assert kb.get_inbound_relationships("ZZZZZ") == []


class TestIntrospection:
    def test_all_tickers_is_sorted_list(self):
        tickers = kb.all_tickers()
        assert isinstance(tickers, list)
        assert tickers == sorted(tickers)
        assert "NVDA" in tickers
        assert "TSM" in tickers

    def test_all_companies_returns_list_of_dicts(self):
        companies = kb.all_companies()
        assert isinstance(companies, list)
        assert all(isinstance(c, dict) for c in companies)

    def test_all_relationship_types_returns_known_types(self):
        types = kb.all_relationship_types()
        assert "foundry_customer" in types
        assert "equipment_supplier" in types
        assert "major_customer" in types
