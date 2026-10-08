"""Web access for the steps `search` and `fetch` (pipeline_spec.md, 8).

Fetched text is untrusted data. Rules:
- only http and https;
- only public addresses: the host is resolved first, and private,
  loopback and link-local addresses are refused (no requests into the
  server's own network);
- redirects are followed by hand, and every hop is checked again;
- a time limit, a size limit, and only text/html or text/plain.

Known limit: the address is checked before the request; a host that
changes its DNS answer between the check and the request (DNS rebinding)
is not caught. Fine for one server with a local model; revisit before
anything sensitive runs next to the worker.
"""

import asyncio
import ipaddress
import logging
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

log = logging.getLogger(__name__)

Resolver = Callable[[str], Awaitable[list[str]]]

MAX_REDIRECTS = 3
SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head", "nav", "footer", "form"}
# If a page has these, only their text is used (menus and side bars are
# outside them on most sites).
CONTENT_TAGS = {"main", "article"}
BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "li",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "section",
    "article",
}


class FetchError(Exception):
    """A page cannot be used. The message is short and safe."""


@dataclass(frozen=True)
class Page:
    url: str  # after redirects
    title: str
    text: str


# A temporary DNS failure (EAI_AGAIN) is tried again after these pauses.
# Seen on the server: six parallel page downloads all failed to resolve in
# the same millisecond, and the same names resolved a moment later.
DNS_RETRY_SECONDS = (1.0, 3.0)


async def resolve(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    for pause in (*DNS_RETRY_SECONDS, None):
        try:
            infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            if exc.errno != socket.EAI_AGAIN or pause is None:
                raise
            await asyncio.sleep(pause)
        else:
            return sorted({info[4][0] for info in infos})
    raise AssertionError("unreachable")


async def check_url(url: str, resolver: Resolver) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("only http and https addresses")
    try:
        addresses = await resolver(parts.hostname)
    except OSError as exc:
        log.info("cannot resolve %s: %s", parts.hostname, exc)
        raise FetchError("the host name cannot be resolved") from exc
    if not addresses:
        raise FetchError("the host name cannot be resolved")
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise FetchError("the address is not public")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.content_parts: list[str] = []  # text inside <main> / <article>
        self.title_parts: list[str] = []
        self.skip_depth = 0
        self.content_depth = 0
        self.in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self.in_title = True
        if tag in CONTENT_TAGS:
            self.content_depth += 1
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif tag in BLOCK_TAGS:
            self._add("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in CONTENT_TAGS and self.content_depth:
            self.content_depth -= 1
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag in BLOCK_TAGS:
            self._add("\n")

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        elif not self.skip_depth:
            self._add(data)

    def _add(self, text: str) -> None:
        self.parts.append(text)
        if self.content_depth:
            self.content_parts.append(text)


def html_to_text(html: str) -> tuple[str, str]:
    """(title, text). Text: one paragraph per line, single spaces."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    raw = "".join(parser.content_parts) if "".join(parser.content_parts).strip() else ""
    raw = raw or "".join(parser.parts)
    lines = (re.sub(r"\s+", " ", line).strip() for line in raw.split("\n"))
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()
    return title, "\n".join(line for line in lines if line)


async def fetch_page(
    client: httpx.AsyncClient, url: str, *, max_bytes: int, max_chars: int, resolver: Resolver
) -> Page:
    for _ in range(MAX_REDIRECTS + 1):
        await check_url(url, resolver)
        try:
            async with client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("a redirect without a target")
                    url = urljoin(url, location)
                    continue
                if response.status_code != 200:
                    raise FetchError(f"the page answered {response.status_code}")
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type not in ("text/html", "text/plain"):
                    raise FetchError(f"not a text page ({content_type or 'unknown type'})")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        break  # keep the start of a very large page
                text = bytes(body[:max_bytes]).decode(response.encoding or "utf-8", "replace")
        except httpx.HTTPError as exc:
            raise FetchError("the page cannot be downloaded") from exc
        if content_type == "text/html":
            title, text = html_to_text(text)
        else:
            title = ""
        return Page(url=url, title=title, text=text[:max_chars])
    raise FetchError("too many redirects")


async def searxng_search(
    client: httpx.AsyncClient, base_url: str, query: str, limit: int
) -> list[dict[str, str]]:
    """Results of one query: title, url, snippet."""
    response = await client.get(
        base_url.rstrip("/") + "/search", params={"q": query, "format": "json"}
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return [
        {"title": r.get("title", ""), "url": r["url"], "snippet": r.get("content", "")}
        for r in results[:limit]
        if r.get("url")
    ]
