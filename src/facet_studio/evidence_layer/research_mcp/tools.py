"""Research tools: search / fetch / quote, with a source ledger.

The default search provider is a local fixture directory. There is no
fabricated web search: if no provider is configured, `search_external` fails
explicitly. `fetch_source` works with any public http(s) URL.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from .ledger import SourceError, SourceLedger, source_id_for

DEFAULT_TIMEOUT = 20


# ---------------------------------------------------------------- html -> text

class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg"}
    _BREAK = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
              "article", "section", "blockquote", "tr", "td"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._SKIP:
            self.skip += 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._SKIP and self.skip:
            self.skip -= 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    text = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _meta(html: str, *keys: str) -> str:
    for key in keys:
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
            html or "", re.I)
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
                html or "", re.I)
        if m:
            return " ".join(m.group(1).split())
    return ""


def _title(html: str) -> str:
    title = _meta(html, "og:title", "twitter:title")
    if title:
        return title
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    return " ".join(re.sub(r"<[^>]+>", "", m.group(1)).split()) if m else ""


def _publisher(html: str, url: str) -> str:
    pub = _meta(html, "og:site_name", "application-name", "publisher")
    if pub:
        return pub
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- fetch / quote

def fetch_url(url: str, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; lmind-research/1.0; +https://example.local)",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        import certifi
        verify = certifi.where()
    except Exception:  # noqa: BLE001
        verify = True
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, verify=verify)
    except Exception as e:  # noqa: BLE001
        raise SourceError("fetch_failed", f"抓取失败 {url}: {type(e).__name__}: {e}") from e
    if resp.status_code >= 400:
        raise SourceError("fetch_failed", f"抓取失败 {url}: HTTP {resp.status_code}")
    if not resp.encoding:
        resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text
    text = html_to_text(html)
    if len(text) < 20:
        raise SourceError("empty_text", f"{url} 没有可读正文")
    return {
        "url": url,
        "title": _title(html),
        "publisher": _publisher(html, url),
        "text": text,
        "text_hash": "sha256:" + __import__("hashlib").sha256(
            " ".join(text.split()).encode("utf-8")).hexdigest(),
    }


_SENT_RE = re.compile(r"[^。！？!?\.]+[。！？!?\.]?")


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENT_RE.findall(text or "") if p.strip()]


def extract_quote(text: str, query: str | None = None,
                  *, max_chars: int = 500) -> dict:
    """Return a verbatim quote from `text`; never generate text."""
    text = text or ""
    if not text.strip():
        raise SourceError("empty_text", "没有可抽取的正文")
    q = " ".join((query or "").split()).lower()
    candidates: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if q and q in line.lower():
            candidates.append(line)
            continue
        for sent in _sentences(line):
            if q and q in sent.lower():
                candidates.append(sent)
    if not candidates:
        if q:
            raise SourceError("quote_not_found",
                              f"在正文中找不到 query={query!r} 的逐字片段")
        # No query: take the first substantive paragraph/sentence.
        for line in text.splitlines():
            line = line.strip()
            if len(line) >= 20 and not re.search(r"cookie|登录|注册|隐私政策|广告", line, re.I):
                candidates.append(line)
                break
        if not candidates:
            candidates = [text.strip()]
    quote = candidates[0]
    if len(quote) > max_chars:
        raise SourceError(
            "quote_too_long",
            f"命中段落 {len(quote)} 字，超过 {max_chars}；请给更具体的 query 或人工截取逐字片段",
        )
    start = text.find(quote)
    return {"quote": quote, "start": start if start >= 0 else None,
            "end": (start + len(quote)) if start >= 0 else None}


def fetch_source(url: str, *, query: str | None = None,
                 supports: list[str] | None = None,
                 timeout: int = DEFAULT_TIMEOUT,
                 ledger: SourceLedger | None = None) -> dict:
    page = fetch_url(url, timeout=timeout)
    quote = extract_quote(page["text"], query)["quote"]
    if ledger is not None:
        return ledger.add_external(
            url=url, quote=quote, title=page["title"], publisher=page["publisher"],
            text=page["text"], supports=supports, retrieved_by="http",
        )
    return {
        "source_id": source_id_for(url, quote),
        "source_type": "external_source",
        "url": url,
        "title": page["title"],
        "publisher": page["publisher"],
        "retrieved_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "quote": quote,
        "quote_hash": "sha256:" + __import__("hashlib").sha256(
            " ".join(quote.split()).encode("utf-8")).hexdigest(),
        "text": page["text"],
        "text_hash": page["text_hash"],
        "supports": list(supports or []),
        "retrieved_by": "http",
        "status": "retrieved",
    }


def quote_source(*, url: str | None = None, source_id: str | None = None,
                 query: str | None = None, ledger: SourceLedger | None = None,
                 timeout: int = DEFAULT_TIMEOUT) -> dict:
    if source_id:
        if ledger is None or ledger.get(source_id) is None:
            raise SourceError("unknown_source", f"没有 source_id={source_id!r}")
        rec = ledger.get(source_id)
        text = rec.get("text") or ""
        if not text:
            raise SourceError("no_text", f"{source_id} 没有抓取正文，无法重新抽取 quote")
        q = extract_quote(text, query) if query else {
            "quote": rec["quote"], "start": None, "end": None}
        return {"source_id": source_id, "url": rec["url"], "quote": q["quote"],
                "start": q.get("start"), "end": q.get("end"),
                "retrieved_at": rec["retrieved_at"], "text_hash": rec.get("text_hash")}
    if not url:
        raise SourceError("missing_url", "需要 url 或 source_id")
    page = fetch_url(url, timeout=timeout)
    q = extract_quote(page["text"], query)
    return {"url": url, "title": page["title"], "publisher": page["publisher"],
            "quote": q["quote"], "start": q.get("start"), "end": q.get("end"),
            "text_hash": page["text_hash"]}


# ---------------------------------------------------------------- search

def _score(query: str, text: str, title: str) -> int:
    terms = [t.lower() for t in re.findall(r"[\w一-鿿]+", query or "") if len(t) > 1]
    if not terms:
        return 0
    hay = (title + "\n" + text).lower()
    return sum(hay.count(t) for t in terms)


def search_external(query: str, *, fixture_dir: str | Path | None = None,
                    urls: list[str] | None = None, limit: int = 5,
                    timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Search configured sources.

    - `fixture_dir`: JSON files with {url,title,publisher,text}; offline tests.
    - `urls`: fetch these URLs and keep pages containing the query.
    - otherwise: explicit `no_search_provider` error (never fabricate results).
    """
    results: list[dict] = []
    if fixture_dir:
        for p in sorted(Path(fixture_dir).glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            text = data.get("text") or ""
            score = _score(query, text, data.get("title") or "")
            if score <= 0:
                continue
            q = extract_quote(text, query)["quote"]
            results.append({
                "provider": "fixture", "url": data.get("url"),
                "title": data.get("title") or "", "publisher": data.get("publisher") or "",
                "snippet": q, "score": score,
            })
    elif urls:
        for url in urls:
            page = fetch_url(url, timeout=timeout)
            score = _score(query, page["text"], page["title"])
            if score <= 0:
                continue
            results.append({
                "provider": "url_fetch", "url": url, "title": page["title"],
                "publisher": page["publisher"],
                "snippet": extract_quote(page["text"], query)["quote"],
                "score": score,
            })
    else:
        raise SourceError(
            "no_search_provider",
            "没有配置搜索 provider。请提供 fixture_dir 或 urls，或直接调用 fetch_source(url)。",
        )
    results.sort(key=lambda x: (-x["score"], x["url"] or ""))
    return {"query": query, "items": results[:limit],
            "truncated": len(results) > limit}


def ledger_to_prompt(ledger: SourceLedger) -> str:
    return ledger.render()
