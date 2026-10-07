"""Step kinds for deep research (pipelines/deep_research/).

The idea: split the topic into sub-questions, search for each one, then
ask "what is still missing?" and search again, a few rounds. Every model
call stays small: one sub-question, one fact, or a short list of claims.
The rounds are separate steps in the pipeline file, so the runner needs
no loops.
"""

from typing import Any

from autolab.worker.kinds.base import StepContext, StepFailed


def _clean(texts: list[str]) -> list[str]:
    """Strip, drop empty ones and repeats (case does not matter)."""
    seen: set[str] = set()
    out = []
    for text in texts:
        key = text.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(text.strip())
    return out


def _earlier_queries(ctx: StepContext) -> set[str]:
    return {
        q.strip().lower()
        for output in ctx.outputs.values()
        for q in output.get("queries") or []
        if isinstance(q, str)
    }


async def plan_each(ctx: StepContext) -> dict[str, Any]:
    """Search queries for each item (a sub-question). Output: all queries
    in one list without repeats, at most config.max_queries."""
    queries: list[str] = []
    for _, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        queries += answer["queries"]
    queries = _clean(queries)[: int(ctx.step.config.get("max_queries", 50))]
    if not queries:
        raise StepFailed("the model wrote no search queries")
    return {"queries": queries}


def _sample(items: list[Any], limit: int) -> list[Any]:
    """At most `limit` items, spread over the whole list (not just the
    first ones), so every round and sub-question is seen."""
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


async def gaps(ctx: StepContext) -> dict[str, Any]:
    """What is still missing? The model sees the sub-questions (in its
    prompt, from steps.<outline>) and the claims found so far (`claims`,
    at most config.max_claims), and writes new search queries. Queries
    that were already searched are dropped. No queries left is fine: the
    next round then has nothing to do."""
    facts = ctx.resolve(ctx.step.from_)
    claims = [f["claim"] for f in _sample(facts, int(ctx.step.config.get("max_claims", 40)))]
    answer = await ctx.ask(claims=claims)
    if answer is None:
        raise StepFailed("the model gave no valid answer")
    done = _earlier_queries(ctx)
    queries = [q for q in _clean(answer["queries"]) if q.lower() not in done]
    return {
        "queries": queries[: int(ctx.step.config.get("max_queries", 10))],
        "missing": answer.get("missing", []),
    }


async def group(ctx: StepContext) -> dict[str, Any]:
    """One call per fact: which sub-question does it answer? The sections
    of the report are the sub-questions (config.questions_from), each with
    its facts (at most config.max_facts_per_section). Same output as
    synthesize, so `write` and the work assembly work as for research."""
    questions = ctx.resolve(ctx.step.config["questions_from"])
    limit = int(ctx.step.config.get("max_facts_per_section", 12))
    buckets: list[list[dict]] = [[] for _ in questions]
    for fact, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        number = answer["question"]
        if 1 <= number <= len(questions) and len(buckets[number - 1]) < limit:
            buckets[number - 1].append(fact)
    numbered: list[dict] = []
    sections = []
    for question, facts in zip(questions, buckets, strict=True):
        if not facts:
            continue
        start = len(numbered) + 1
        numbered += [fact | {"number": start + i} for i, fact in enumerate(facts)]
        sections.append(
            {
                "heading": question,
                "fact_numbers": list(range(start, start + len(facts))),
                "facts": [{"number": start + i, "claim": f["claim"]} for i, f in enumerate(facts)],
            }
        )
    if not sections:
        raise StepFailed("no fact fits any sub-question")
    return {"summary": None, "sections": sections, "facts": numbered}


async def abstract(ctx: StepContext) -> dict[str, Any]:
    """A short summary of the finished report (one call). It becomes the
    summary of the work."""
    answer = await ctx.ask()
    if answer is None:
        raise StepFailed("the model gave no valid summary")
    answer = await ctx.in_task_language(None, answer, "summary")
    return {"summary": answer["summary"]}


HANDLERS = {
    "plan_each": plan_each,
    "gaps": gaps,
    "group": group,
    "abstract": abstract,
}
