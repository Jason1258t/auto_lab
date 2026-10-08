"""Step kinds of research pipelines (pipeline_spec.md, section 4).

Code checks what code can check: quotes are looked up in the page text,
fact numbers and [n] marks are checked. The model is only asked what
code cannot decide.
"""

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlsplit

from autolab.worker.kinds.base import StepContext, StepFailed
from autolab.worker.llm_manager import CHARS_PER_TOKEN
from autolab.worker.web import FetchError, fetch_page, searxng_search

log = logging.getLogger(__name__)

# Typographic characters a model often "fixes" when it copies a quote.
_SAME_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def normalize(text: str) -> str:
    """For the quote check: the same characters and single spaces."""
    return re.sub(r"\s+", " ", text.translate(_SAME_CHARS)).strip()


def quote_in_text(quote: str, text: str) -> bool:
    return normalize(quote) in normalize(text)


def _domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.removeprefix("www.")


async def search(ctx: StepContext) -> dict[str, Any]:
    """Run each query in SearxNG; keep unique URLs as candidates for fetch.

    Config: results_per_query; max_candidates (old name: max_sources);
    max_per_domain (default: no limit), so one site cannot fill the list;
    skip_seen: skip URLs that earlier steps already found or read (later
    rounds of a deep research); optional: no queries or no results is not
    an error (the output is empty).
    """
    config = ctx.step.config
    per_query = int(config.get("results_per_query", 5))
    max_candidates = int(config.get("max_candidates", config.get("max_sources", 5)))
    max_per_domain = int(config.get("max_per_domain", 0)) or None
    optional = bool(config.get("optional", False))
    results: list[dict[str, str]] = []
    seen: set[str] = _earlier_urls(ctx) if config.get("skip_seen") else set()
    per_domain: dict[str, int] = {}
    queries = ctx.resolve(ctx.step.from_)
    if not queries and optional:
        return {"results": []}
    for query in queries:
        try:
            found = await searxng_search(ctx.http, ctx.settings.searxng_url, query, per_query)
        except Exception as exc:  # one failed query is not the end
            log.warning("task %s: search %r failed: %s", ctx.task.id, query, exc)
            continue
        for result in found:
            domain = _domain(result["url"])
            if result["url"] in seen or len(results) >= max_candidates:
                continue
            if max_per_domain and per_domain.get(domain, 0) >= max_per_domain:
                continue
            seen.add(result["url"])
            per_domain[domain] = per_domain.get(domain, 0) + 1
            results.append(result)
    if not results and not optional:
        raise StepFailed("the search found nothing (is SearxNG running?)")
    return {"results": results}


def _earlier_urls(ctx: StepContext) -> set[str]:
    """URLs in the results or sources of all earlier steps."""
    urls: set[str] = set()
    for output in ctx.outputs.values():
        for key in ("results", "sources"):
            for item in output.get(key) or []:
                if isinstance(item, dict) and isinstance(item.get("url"), str):
                    urls.add(item["url"])
    return urls


# max_chars: auto = this share of the model's window, in characters
# (drafts/token_budgets.md, phase 3). The rest is for the prompt and the
# answer.
AUTO_PAGE_SHARE = 0.5


def page_chars(ctx: StepContext, value: Any) -> int:
    """max_chars of a fetched page: a number, or 'auto' (from the window)."""
    if value == "auto":
        if ctx.model is None:
            return 6000
        return int(ctx.model.context_length * AUTO_PAGE_SHARE * CHARS_PER_TOKEN)
    return int(value)


async def fetch(ctx: StepContext) -> dict[str, Any]:
    """Download candidate pages (only public http(s) addresses) until
    target_sources pages are readable. A page is readable if it has at
    least min_chars characters of text, so cookie walls and error pages do
    not count. Pages are fetched `parallel` at a time, in search order.

    Config (defaults keep version 1.0.0 working as before): target_sources
    (all candidates), min_sources (1), min_chars (1), parallel (1),
    max_bytes, max_chars (a number, or 'auto': half of the model's window).
    """
    config = ctx.step.config
    candidates = ctx.resolve(ctx.step.from_)
    target = int(config.get("target_sources", len(candidates))) or len(candidates)
    min_sources = int(config.get("min_sources", 1))
    min_chars = max(1, int(config.get("min_chars", 1)))
    parallel = max(1, int(config.get("parallel", 1)))

    async def read(result: dict[str, str]) -> dict[str, str] | None:
        try:
            page = await fetch_page(
                ctx.http,
                result["url"],
                max_bytes=int(config.get("max_bytes", 2_000_000)),
                max_chars=page_chars(ctx, config.get("max_chars", 6000)),
                resolver=ctx.resolver,
            )
        except FetchError as exc:
            log.info("task %s: skip %s: %s", ctx.task.id, result["url"], exc)
            return None
        if len(page.text.strip()) < min_chars:
            log.info("task %s: skip %s: too little text", ctx.task.id, result["url"])
            return None
        return {"title": result["title"] or page.title, "url": page.url, "text": page.text}

    sources: list[dict[str, str]] = []
    tried = failed = 0
    for start in range(0, len(candidates), parallel):
        if len(sources) >= target:
            break
        batch = candidates[start : start + parallel]
        tried += len(batch)
        for page in await asyncio.gather(*(read(result) for result in batch)):
            if page is None:
                failed += 1
            elif len(sources) < target:  # the last batch may bring more than needed
                sources.append(page)
    ctx.skipped += failed
    if len(sources) < min_sources:
        raise StepFailed(
            f"only {len(sources)} of {tried} pages could be read; at least {min_sources} needed"
        )
    return {"sources": sources}


async def summarize(ctx: StepContext) -> dict[str, Any]:
    """Facts with quotes, one call per source. A fact whose quote is not in
    the page text is dropped: the model may not invent quotes."""
    facts = []
    dropped = 0
    for source, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        for fact in answer["facts"]:
            if quote_in_text(fact["quote"], source["text"]):
                facts.append(
                    {
                        "claim": fact["claim"],
                        "quote": fact["quote"],
                        "source": {"title": source["title"], "url": source["url"]},
                    }
                )
            else:
                dropped += 1
    if not facts and not ctx.step.config.get("optional"):
        raise StepFailed("no fact with a quote that is really in the sources")
    return {"facts": facts, "dropped_quotes": dropped}


async def verify(ctx: StepContext) -> dict[str, Any]:
    """One call per fact: does the quote support the claim? Keeps facts
    whose verdict is in config.keep."""
    keep = set(ctx.step.config.get("keep", ["supported"]))
    kept = []
    verdicts: dict[str, int] = {}
    for fact, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        verdicts[answer["verdict"]] = verdicts.get(answer["verdict"], 0) + 1
        if answer["verdict"] in keep:
            kept.append(fact | {"verdict": answer["verdict"]})
    if not kept:
        raise StepFailed("no fact passed the check")
    return {"facts": kept, "verdicts": verdicts}


async def synthesize(ctx: StepContext) -> dict[str, Any]:
    """Plan the report from the numbered facts. Code drops fact numbers that
    do not exist and sections that are left empty, and adds the facts
    (number, claim) to each section for the write step."""
    facts = ctx.resolve(ctx.step.from_)
    numbered = [fact | {"number": i} for i, fact in enumerate(facts, start=1)]
    answer = await ctx.ask()
    if answer is None:
        raise StepFailed("the model gave no valid plan")
    sections = []
    for section in answer["sections"]:
        numbers = sorted({n for n in section["fact_numbers"] if 1 <= n <= len(facts)})
        if numbers:
            sections.append(
                {
                    "heading": section["heading"],
                    "fact_numbers": numbers,
                    "facts": [{"number": n, "claim": facts[n - 1]["claim"]} for n in numbers],
                }
            )
    if not sections:
        raise StepFailed("the plan uses no existing fact")
    return {"summary": answer["summary"], "sections": sections, "facts": numbered}


_MARK = re.compile(r"\[(\d+)\]")
# A mark with the spaces before it, so removing it leaves no " ." behind.
_MARK_WITH_SPACE = re.compile(r"\s*\[(\d+)\]")
# A sentence ends with . ! or ? (and maybe its [n] marks), then a space.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=\])\s+(?=[A-Z])")

# Shown after a sentence that cites no fact (decided 2026-10-07): the
# reviewer sees at a glance what to check. Small models often add such
# sentences although the prompt says "use only these facts".
NO_SOURCE = "*(\u26a0 no source)*"


def mark_unsourced(text: str) -> tuple[str, int]:
    """Add NO_SOURCE after every sentence without a [n] mark."""
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    marked = 0
    out = []
    for sentence in sentences:
        if not _MARK.search(sentence):
            sentence = f"{sentence} {NO_SOURCE}"
            marked += 1
        out.append(sentence)
    return " ".join(out), marked


async def write(ctx: StepContext) -> dict[str, Any]:
    """One paragraph per section. [n] marks that are not facts of this
    section are removed, so every mark points to a real fact. Sentences
    without any mark are marked as "no source" for the reviewer."""
    paragraphs = []
    unsourced = 0
    for section, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        answer = await ctx.in_task_language(section, answer, "paragraph")
        allowed = set(section["fact_numbers"])

        def check_mark(match: re.Match, allowed: set[int] = allowed) -> str:
            return match.group(0) if int(match.group(1)) in allowed else ""

        text = _MARK_WITH_SPACE.sub(check_mark, answer["paragraph"]).strip()
        used = sorted({int(n) for n in _MARK.findall(text)})
        text, marked = mark_unsourced(text)
        unsourced += marked
        paragraphs.append({"heading": section["heading"], "text": text, "fact_numbers": used})
    if unsourced:
        ctx.notes.append(f"{unsourced} sentences without a source")
    return {"paragraphs": paragraphs, "unsourced_sentences": unsourced}


HANDLERS = {
    "search": search,
    "fetch": fetch,
    "summarize": summarize,
    "verify": verify,
    "synthesize": synthesize,
    "write": write,
}
