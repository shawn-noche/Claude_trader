"""
Article ingestion pipeline.

Flow:
  1. Fetch raw HTML via httpx (async, with timeout)
  2. Extract clean text via trafilatura
  3. Fall back to BeautifulSoup if trafilatura returns nothing
  4. Normalize into Article schema
"""

import logging
from urllib.parse import urlparse
from datetime import datetime, timezone

import httpx
import trafilatura
from trafilatura import bare_extraction
from bs4 import BeautifulSoup

from backend.config import settings
from backend.schemas.article import Article

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class IngestionError(Exception):
    """Raised when article cannot be fetched or parsed."""


async def fetch_article(url: str) -> Article:
    """
    Fetch and parse an article from *url*.

    Raises IngestionError on any unrecoverable failure.
    """
    raw_html = await _fetch_html(url)
    article = _extract(url, raw_html)
    return article


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _fetch_html(url: str) -> str:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.fetch_timeout_seconds,
            headers=_HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.TimeoutException as exc:
        raise IngestionError(f"Fetch timed out after {settings.fetch_timeout_seconds}s: {url}") from exc
    except httpx.HTTPStatusError as exc:
        raise IngestionError(
            f"HTTP {exc.response.status_code} fetching {url}"
        ) from exc
    except httpx.RequestError as exc:
        raise IngestionError(f"Network error fetching {url}: {exc}") from exc


def _extract(url: str, html: str) -> Article:
    domain = urlparse(url).netloc.lstrip("www.")

    # --- attempt 1: trafilatura ---
    result = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
        output_format="txt",
        with_metadata=True,
        favor_precision=True,
    )

    if result:
        return _build_from_trafilatura(url, domain, result, html)

    # --- attempt 2: BeautifulSoup fallback ---
    logger.warning("trafilatura returned nothing for %s — falling back to BeautifulSoup", url)
    return _build_from_soup(url, domain, html)


def _build_from_trafilatura(url: str, domain: str, result, html: str) -> Article:
    # bare_extraction returns a Document (dataclass-like) with metadata fields
    meta = bare_extraction(html, with_metadata=True, include_comments=False, include_tables=False)

    text = result if isinstance(result, str) else str(result)
    text = text[: settings.max_article_chars]

    title = ""
    author = None
    published_date = None

    if meta:
        title = getattr(meta, "title", None) or ""
        author = getattr(meta, "author", None) or None
        raw_date = getattr(meta, "date", None)
        if raw_date:
            try:
                published_date = datetime.fromisoformat(str(raw_date)).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                published_date = None

    if not title:
        title = _extract_title_from_html(html)

    return Article(
        url=url,
        title=title,
        text=text,
        author=author,
        published_date=published_date,
        source_domain=domain,
        char_count=len(text),
        extraction_method="trafilatura",
    )


def _build_from_soup(url: str, domain: str, html: str) -> Article:
    soup = BeautifulSoup(html, "lxml")

    # Remove boilerplate tags
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    title = _extract_title_from_soup(soup)

    # Best-effort body text: prefer <article>, then <main>, then <body>
    body = (
        soup.find("article")
        or soup.find("main")
        or soup.find("body")
        or soup
    )
    paragraphs = body.find_all("p")  # type: ignore[union-attr]
    text = "\n\n".join(p.get_text(separator=" ", strip=True) for p in paragraphs if p.get_text(strip=True))

    if not text:
        text = body.get_text(separator="\n", strip=True)  # type: ignore[union-attr]

    text = text[: settings.max_article_chars]

    if not text:
        raise IngestionError(f"Could not extract any text from {url}")

    return Article(
        url=url,
        title=title,
        text=text,
        author=None,
        published_date=None,
        source_domain=domain,
        char_count=len(text),
        extraction_method="beautifulsoup",
    )


def _extract_title_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return _extract_title_from_soup(soup)


def _extract_title_from_soup(soup: BeautifulSoup) -> str:
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):  # type: ignore[union-attr]
        return og_title["content"].strip()  # type: ignore[index]
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""
