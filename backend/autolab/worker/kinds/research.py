"""Step kinds of research pipelines (pipeline_spec.md, section 4).

Code checks what code can check: quotes are looked up in the page text,
fact numbers and [n] marks are checked. The model is only asked what
code cannot decide.
"""

import logging
import re
from typing import Any

from autolab.worker.kinds.base import StepContext, StepFailed
from autolab.worker.web import FetchError, fetch_page, searxng_search

log = logging.getLogger(__name__)

# Typographic characters a model often "fixes" when it copies a quote.
_SAME_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def normalize(text: str) -> str:
    """For the quote check: the same characters and single spaces."""
    return re.sub(r"\s+", " ", text.translate(_SAME_CHARS)).strip()


def quote_in_text(quote: str, text: str) -> bool:
    return normalize(quote) in normalize(text)


async def search(ctx: StepContext) -> dict[str, Any]:
    """Run each query in SearxNG; keep unique URLs, at most max_sources."""
    per_query = int(ctx.step.config.get("results_per_query", 5))
    max_sources = int(ctx.step.config.get("max_sources", 5))
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for query in ctx.resolve(ctx.step.from_):
        try:
            found = await searxng_search(ctx.http, ctx.settings.searxng_url, query, per_query)
        except Exception as exc:  # one failed query is not the end
            log.warning("task %s: search %r failed: %s", ctx.task.id, query, exc)
            continue
        for result in found:
            if result["url"] not in seen and len(results) < max_sources:
                seen.add(result["url"])
                results.append(result)
    if not results:
        raise StepFailed("the search found nothing (is SearxNG running?)")
    return {"results": results}


async def fetch(ctx: StepContext) -> dict[str, Any]:
    """Download the result pages (only public http(s) addresses)."""
    config = ctx.step.config
    sources = []
    for result in ctx.resolve(ctx.step.from_):
        try:
            page = await fetch_page(
                ctx.http,
                result["url"],
                max_bytes=int(config.get("max_bytes", 2_000_000)),
                max_chars=int(config.get("max_chars", 6000)),
                resolver=ctx.resolver,
            )
        except FetchError as exc:
            log.info("task %s: skip %s: %s", ctx.task.id, result["url"], exc)
            ctx.skipped += 1
            continue
        if page.text:
            sources.append(
                {"title": result["title"] or page.title, "url": page.url, "text": page.text}
            )
    if not sources:
        raise StepFailed("no page could be read")
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
    if not facts:
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


async def write(ctx: StepContext) -> dict[str, Any]:
    """One paragraph per section. [n] marks that are not facts of this
    section are removed, so every mark points to a real fact."""
    paragraphs = []
    for section, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        allowed = set(section["fact_numbers"])

        def check_mark(match: re.Match, allowed: set[int] = allowed) -> str:
            return match.group(0) if int(match.group(1)) in allowed else ""

        text = _MARK.sub(check_mark, answer["paragraph"]).strip()
        used = sorted({int(n) for n in _MARK.findall(text)})
        paragraphs.append({"heading": section["heading"], "text": text, "fact_numbers": used})
    return {"paragraphs": paragraphs}


HANDLERS = {
    "search": search,
    "fetch": fetch,
    "summarize": summarize,
    "verify": verify,
    "synthesize": synthesize,
    "write": write,
}
