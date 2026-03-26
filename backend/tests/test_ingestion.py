"""
Tests for the ingestion pipeline.

Network calls are mocked so tests run offline and deterministically.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.ingestion import fetch_article, _extract, IngestionError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>NVIDIA Reports Record Revenue</title>
  <meta property="og:title" content="NVIDIA Reports Record Revenue in Q4" />
</head>
<body>
  <article>
    <h1>NVIDIA Reports Record Revenue</h1>
    <p>NVIDIA Corporation today reported record revenue of $22.1 billion for the fourth quarter.</p>
    <p>Data center revenue reached $18.4 billion, up 409% year over year.</p>
    <p>CEO Jensen Huang said demand for Blackwell architecture GPUs remains strong.</p>
  </article>
</body>
</html>
"""

PAYWALLED_HTML = """
<!DOCTYPE html>
<html>
<head><title>Article - Paywalled</title></head>
<body>
  <p>Subscribe to read more.</p>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Unit tests: _extract (no network)
# ---------------------------------------------------------------------------

class TestExtract:
    def test_extracts_title_from_og_meta(self):
        article = _extract("https://example.com/article", MINIMAL_HTML)
        assert "NVIDIA" in article.title

    def test_extracts_body_text(self):
        article = _extract("https://example.com/article", MINIMAL_HTML)
        assert "record revenue" in article.text.lower()

    def test_sets_source_domain(self):
        article = _extract("https://www.reuters.com/article/123", MINIMAL_HTML)
        assert article.source_domain == "reuters.com"

    def test_char_count_matches_text_length(self):
        article = _extract("https://example.com/article", MINIMAL_HTML)
        assert article.char_count == len(article.text)

    def test_extraction_method_is_set(self):
        article = _extract("https://example.com/article", MINIMAL_HTML)
        assert article.extraction_method in ("trafilatura", "beautifulsoup")

    def test_truncates_to_max_chars(self, monkeypatch):
        monkeypatch.setattr("backend.services.ingestion.settings.max_article_chars", 50)
        article = _extract("https://example.com/article", MINIMAL_HTML)
        assert article.char_count <= 50

    def test_raises_on_empty_content(self):
        empty_html = "<html><body></body></html>"
        with pytest.raises(IngestionError):
            _extract("https://example.com/article", empty_html)


# ---------------------------------------------------------------------------
# Integration tests: fetch_article (network mocked)
# ---------------------------------------------------------------------------

class TestFetchArticle:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        mock_response = MagicMock()
        mock_response.text = MINIMAL_HTML
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            article = await fetch_article("https://example.com/article")

        assert article.url == "https://example.com/article"
        assert article.char_count > 0

    @pytest.mark.asyncio
    async def test_timeout_raises_ingestion_error(self):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(IngestionError, match="timed out"):
                await fetch_article("https://example.com/article")

    @pytest.mark.asyncio
    async def test_http_4xx_raises_ingestion_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError("not found", request=MagicMock(), response=mock_response)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=http_error)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(IngestionError, match="404"):
                await fetch_article("https://example.com/article")

    @pytest.mark.asyncio
    async def test_network_error_raises_ingestion_error(self):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.RequestError("connection refused", request=MagicMock())
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(IngestionError, match="Network error"):
                await fetch_article("https://example.com/article")
