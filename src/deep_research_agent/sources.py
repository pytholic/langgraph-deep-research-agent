"""Source extraction from the agent's virtual file system.

Parses the structured markdown files written by search tools (Tavily, arXiv)
into source metadata dicts suitable for display in the CLI or web UI.

Created by @pytholic on 2026.04.06
"""

import re
from urllib.parse import urlparse

_FILE_HEADER_RE = re.compile(
    r"^#\s+(?:Search Result|Arxiv Paper):\s*(?P<title>.+?)\n\n"
    r"\*\*URL:\*\*\s*(?P<url>.+?)\n"
    r"\*\*Query:\*\*\s*(?P<query>.+?)\n"
    r"\*\*Date:\*\*\s*(?P<date>.+?)\n\n"
    r"## Summary\n(?P<summary>.+?)(?:\n\n|$)",
    re.DOTALL,
)


def extract_sources(files: dict[str, str]) -> list[dict[str, str | float]]:
    """Parse structured source metadata from the agent's virtual files.

    Args:
        files: Mapping of filename → markdown content from ``state["files"]``.

    Returns:
        List of source dicts with keys: title, url, snippet, domain, date,
        source_type ("arxiv" | "web"), and score.
    """
    sources: list[dict[str, str | float]] = []
    seen_urls: set[str] = set()
    for filename, content in files.items():
        m = _FILE_HEADER_RE.match(content)
        if not m:
            continue
        url = m.group("url").strip()
        # filter duplicated urls
        if url in seen_urls:
            continue
        seen_urls.add(url)
        is_arxiv = "arxiv" in filename.lower() or "arxiv.org" in url
        domain = urlparse(url).netloc or url[:40]
        snippet = m.group("summary").strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        sources.append(
            {
                "title": m.group("title").strip(),
                "url": url,
                "snippet": snippet,
                "domain": domain,
                "date": m.group("date").strip(),
                "source_type": "arxiv" if is_arxiv else "web",
                "score": 0.0,
            }
        )
    return sources
