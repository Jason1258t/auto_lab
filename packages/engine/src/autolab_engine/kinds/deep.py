"""Step kinds for deep research (pipelines/deep_research/).

The idea: split the topic into sub-questions, search for each one, then
ask "what is still missing?" and search again, a few rounds. Every model
call stays small: one sub-question, one fact, or a short list of claims.
The rounds are separate steps in the pipeline file, so the runner needs
no loops.
"""

import json
import re
from typing import Any

from autolab_engine.kinds.base import StepContext, StepFailed
from autolab_engine.kinds.research import (
    _MARK,
    _MARK_WITH_SPACE,
    _SENTENCE_END,
    NO_SOURCE,
    mark_unsourced,
)


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
    synthesize, so `write` and the work assembly work as for research.
    A question may be a plain text or a section {heading, question}."""
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
        # A plain sub-question (1.x) or a section {heading, question} (1.3.0).
        heading = question["heading"] if isinstance(question, dict) else question
        sections.append(
            {
                "heading": heading,
                "question": question["question"] if isinstance(question, dict) else question,
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


_NOT_WORD = re.compile(r"[^\w]+")


def _claim_key(claim: str) -> str:
    """The same claim with other case, spaces or punctuation -> one key."""
    return _NOT_WORD.sub(" ", claim.lower()).strip()


async def dedup(ctx: StepContext) -> dict[str, Any]:
    """Remove repeated facts inside each section of `group` (the same fact
    found on several pages). Code drops exact repeats (the same claim up
    to case and punctuation); then one call per section with 2+ facts:
    which facts say the same as another one? Of each such pair the fact
    with the higher number is dropped, so one of them always stays.

    Output: the sections with fewer facts (same shape as in group; the
    numbered facts stay in group's output) and `dropped`."""
    sections = []
    dropped = 0
    for section in ctx.resolve(ctx.step.for_each):
        seen: set[str] = set()
        facts = []
        for fact in section["facts"]:
            key = _claim_key(fact["claim"])
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            facts.append(fact)
        sections.append(section | {"facts": facts})
    asked = [s for s in sections if len(s["facts"]) >= 2]
    try:  # no answer at all: keep the facts (a repeat is not an error)
        answers = await ctx.ask_each(asked) if asked else []
    except StepFailed:
        answers = []
        ctx.notes.append("no answer from the model; only exact repeats removed")
    repeats: dict[int, set[int]] = {}  # id(section) -> fact numbers to drop
    for section, answer in answers:
        numbers = {f["number"] for f in section["facts"]}
        drop = repeats.setdefault(id(section), set())
        for pair in answer["repeats"]:
            a, b = pair["n"], pair["same_as"]
            if a in numbers and b in numbers and a != b:
                drop.add(max(a, b))
    out = []
    for section in sections:
        drop = repeats.get(id(section), set())
        dropped += len(drop)
        facts = [f for f in section["facts"] if f["number"] not in drop]
        out.append(section | {"facts": facts, "fact_numbers": [f["number"] for f in facts]})
    return {"sections": out, "dropped": dropped}


# How many paragraphs a part gets, by its number of facts: up to 3 -> 1,
# up to 6 -> 2, more -> 3 (deep_research 1.3.0).
def _paragraphs_for(facts: int) -> int:
    return 1 if facts <= 3 else 2 if facts <= 6 else 3


def _max_parts(facts: int) -> int:
    """Parts of a section: one per 3 facts, 1 to 3."""
    return max(1, min(3, facts // 3))


async def subplan(ctx: StepContext) -> dict[str, Any]:
    """One call per section (from group): split it into parts (sub-
    sections), each with a heading, its main point and its facts. Code
    keeps only fact numbers of this section, each fact in one part only,
    and drops parts without facts. Facts the model left out are not used.

    Output: sections (heading, question, parts, previous: the heading of
    the section before it) and parts (flat, for the write step: section,
    heading, point, facts, fact_numbers, paragraphs)."""
    sections = []
    parts: list[dict[str, Any]] = []
    for section, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        claims = {f["number"]: f["claim"] for f in section["facts"]}
        used: set[int] = set()
        found = []
        # At most one part per 3 facts; the facts of extra parts go to
        # the last part that is kept.
        limit = _max_parts(len(claims))
        kept = answer["parts"][:limit]
        for extra in answer["parts"][limit:]:
            kept[-1] = kept[-1] | {"facts": kept[-1]["facts"] + extra["facts"]}
        for part in kept:
            numbers = []
            for n in part["facts"]:
                if n in claims and n not in used:
                    used.add(n)
                    numbers.append(n)
            if not numbers:
                continue
            found.append(
                {
                    "section": section["heading"],
                    "heading": part["heading"].strip(),
                    "point": part["point"].strip(),
                    "fact_numbers": numbers,
                    "facts": [{"number": n, "claim": claims[n]} for n in numbers],
                    "paragraphs": _paragraphs_for(len(numbers)),
                }
            )
        if not found:
            ctx.skipped += 1
            continue
        sections.append(
            {
                "heading": section["heading"],
                "question": section.get("question", section["heading"]),
                "previous": sections[-1]["heading"] if sections else None,
                "parts": [{"heading": p["heading"], "point": p["point"]} for p in found],
            }
        )
        parts += found
    if not parts:
        raise StepFailed("no section got a part with facts")
    return {"sections": sections, "parts": parts}


# "[3, 5]" or "[3,5]" -> "[3][5]": the model sometimes joins numbers.
_JOINED_MARKS = re.compile(r"\[(\d+(?:\s*,\s*\d+)+)\]")


def split_marks(text: str) -> str:
    return _JOINED_MARKS.sub(
        lambda m: "".join(f"[{n.strip()}]" for n in m.group(1).split(",")), text
    )


# A paragraph with JSON in it, or a made-up chat turn: a small model lost
# track of the format (seen with qwen2.5:3b). Such a paragraph is dropped.
_BROKEN = re.compile(r"[{}]|\"\w+\":|^(user|assistant)$", re.MULTILINE)


def unwrap_json(paragraph: str) -> str:
    """A paragraph that is a JSON object ({"text": "...", "citation":
    [13]}, seen with qwen2.5:3b) -> its text with the numbers as [n]
    marks. Any other paragraph is returned as it is."""
    try:
        data = json.loads(paragraph)
    except ValueError:
        return paragraph
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        return paragraph
    numbers = []
    for value in data.values():
        if isinstance(value, list):
            for n in value:  # 13, "13" or "[13]"
                digits = str(n).strip("[] ")
                if digits.isdigit():
                    numbers.append(int(digits))
    marks = "".join(f"[{n}]" for n in numbers if f"[{n}]" not in data["text"])
    return f"{data['text'].strip()} {marks}".strip()


def clean_paragraph(paragraph: str, allowed: set[int]) -> tuple[str | None, int]:
    """A written paragraph made safe: unwrapped from JSON, "[3, 5]" split,
    marks of facts outside `allowed` removed, "no source" notes added.
    (None, 0) if nothing is left or the paragraph is broken. Returns the
    text and the number of sentences without a source."""

    def check_mark(match: re.Match) -> str:
        return match.group(0) if int(match.group(1)) in allowed else ""

    paragraph = unwrap_json(paragraph.strip())
    text = _MARK_WITH_SPACE.sub(check_mark, split_marks(paragraph)).strip()
    if not text or _BROKEN.search(text):
        return None, 0
    return mark_unsourced(text)


def _used(text: str) -> list[int]:
    return sorted({int(n) for n in _MARK.findall(text)})


async def write_parts(ctx: StepContext) -> dict[str, Any]:
    """One call per part: 1 to 3 paragraphs from the part's facts. As in
    `write`: marks of facts outside the part are removed, sentences
    without a mark get the "no source" note."""
    written = []
    unsourced = 0
    for part, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        answer = await ctx.in_task_language(part, answer, lambda a: "\n\n".join(a["paragraphs"]))
        allowed = set(part["fact_numbers"])
        paragraphs = []
        # At most the planned number: a model asked for 1 paragraph from
        # 1 fact and writing 3 only repeats itself.
        for paragraph in answer["paragraphs"][: part["paragraphs"]]:
            text, marked = clean_paragraph(paragraph, allowed)
            if text is None:
                continue
            unsourced += marked
            paragraphs.append(text)
        if not paragraphs:
            ctx.skipped += 1
            continue
        text = "\n\n".join(paragraphs)
        written.append(
            {
                "section": part["section"],
                "heading": part["heading"],
                "text": text,
                "fact_numbers": _used(text),
            }
        )
    if not written:
        raise StepFailed("no part was written")
    if unsourced:
        ctx.notes.append(f"{unsourced} sentences without a source")
    return {"parts": written, "unsourced_sentences": unsourced}


async def cover(ctx: StepContext) -> dict[str, Any]:
    """Use the facts the text left out (deep_research 1.4.0). Code keeps a
    coverage table: for each planned part (config.plan, from subplan) the
    facts it should use and the facts its text (config.parts, from
    write_parts) cites. Facts of a section (config.sections, from dedup)
    that subplan put in no part go to the last part of their section. A
    part that was not written starts with no text.

    While a part has unused facts, the model adds one paragraph with up to
    config.facts_per_call of them (default 4), at most config.max_calls
    calls per part (default 3). The [n] marks of the new paragraph are the
    report of what it used; marks of other facts are removed.

    Output: parts (the texts with the new paragraphs, in plan order),
    coverage (per part: planned, used, unused), added_paragraphs, unused
    (facts still left out), unsourced_sentences."""
    config = ctx.step.config
    plan = ctx.resolve(config["plan"])
    texts = {(p["section"], p["heading"]): p["text"] for p in ctx.resolve(config["parts"])}
    per_call = int(config.get("facts_per_call", 4))
    max_calls = int(config.get("max_calls", 3))

    # The coverage table: planned facts per part, with claims.
    table = [
        {
            "section": p["section"],
            "heading": p["heading"],
            "point": p["point"],
            "planned": {f["number"]: f["claim"] for f in p["facts"]},
            "text": texts.get((p["section"], p["heading"]), ""),
        }
        for p in plan
    ]
    if config.get("sections"):
        for section in ctx.resolve(config["sections"]):
            rows = [r for r in table if r["section"] == section["heading"]]
            if not rows:
                continue
            planned = {n for r in rows for n in r["planned"]}
            for fact in section["facts"]:
                if fact["number"] not in planned:
                    rows[-1]["planned"][fact["number"]] = fact["claim"]

    added = unsourced = 0
    for row in table:
        for _ in range(max_calls):
            unused = [n for n in row["planned"] if n not in _used(row["text"])]
            if not unused:
                break
            batch = unused[:per_call]
            item = {
                "section": row["section"],
                "heading": row["heading"],
                "point": row["point"],
                # Without the "no source" notes: they are for people.
                "text": row["text"].replace(f" {NO_SOURCE}", ""),
                "facts": [{"number": n, "claim": row["planned"][n]} for n in batch],
            }
            answer = await ctx.ask(item=item)
            if answer is None:
                ctx.skipped += 1
                break
            answer = await ctx.in_task_language(item, answer, "paragraph")
            text, marked = clean_paragraph(answer["paragraph"], set(batch))
            if text is None or not _used(text):
                ctx.skipped += 1  # nothing usable: do not ask about these again
                break
            row["text"] = f"{row['text']}\n\n{text}".strip()
            added += 1
            unsourced += marked

    parts, coverage = [], []
    for row in table:
        used = _used(row["text"])
        coverage.append(
            {
                "section": row["section"],
                "heading": row["heading"],
                "planned": sorted(row["planned"]),
                "used": used,
                "unused": sorted(set(row["planned"]) - set(used)),
            }
        )
        if row["text"]:
            parts.append(
                {
                    "section": row["section"],
                    "heading": row["heading"],
                    "text": row["text"],
                    "fact_numbers": used,
                }
            )
    left = sum(len(c["unused"]) for c in coverage)
    if left:
        ctx.notes.append(f"{left} facts still not used")
    if unsourced:
        ctx.notes.append(f"{unsourced} new sentences without a source")
    return {
        "parts": parts,
        "coverage": coverage,
        "added_paragraphs": added,
        "unused": left,
        "unsourced_sentences": unsourced,
    }


def _sentences(paragraph: str) -> list[str]:
    """The sentences of a paragraph; a "no source" note stays with the
    sentence before it."""
    found: list[str] = []
    for piece in _SENTENCE_END.split(paragraph):
        if not piece.strip():
            continue
        # "blue. *(⚠ no source)* Next" splits after the full stop, so the
        # note may start the next piece: move it back.
        if piece.strip().startswith(NO_SOURCE) and found:
            found[-1] += f" {NO_SOURCE}"
            piece = piece.strip()[len(NO_SOURCE) :].strip()
            if not piece:
                continue
        found.append(piece)
    return found


# Verdicts of check_text that remove a sentence.
_REMOVE = {"new", "wrong"}


async def check_text(ctx: StepContext) -> dict[str, Any]:
    """Check every sentence of the written parts against the quotes
    (deep_research 1.4.0, idea D). A sentence with [n] marks is checked
    against the quotes of those facts; a sentence without marks (a link
    or an explanation) against the quotes of the facts its paragraph
    cites. The model says per sentence: "ok" (the quotes support it, or it
    only links them without a new claim), "new" (a claim the quotes do
    not make) or "wrong" (against the quotes). "new" and "wrong" sentences
    are removed; a sentence without an answer stays.

    Config: parts (written parts, e.g. cover.parts), facts (numbered facts
    with quotes, e.g. group.facts), batch_size. Output: parts (checked
    texts), removed (heading, sentence, verdict: for people), verdicts,
    unsourced_sentences (left in the final texts)."""
    config = ctx.step.config
    quotes = {f["number"]: f["quote"] for f in ctx.resolve(config["facts"])}
    parts = ctx.resolve(config["parts"])

    # Every sentence, with where it is and the quotes to check it against.
    items: list[dict[str, Any]] = []
    layout: list[list[list[int]]] = []  # part -> paragraph -> item indexes
    for p_index, part in enumerate(parts):
        paragraphs = []
        for paragraph in part["text"].split("\n\n"):
            cited = _used(paragraph)
            indexes = []
            for sentence in _sentences(paragraph):
                marks = _used(sentence)
                numbers = marks or cited or part["fact_numbers"]
                items.append(
                    {
                        "part": p_index,
                        "sentence": sentence,
                        # The model sees the sentence without marks and notes.
                        "text": _MARK_WITH_SPACE.sub("", sentence.replace(f" {NO_SOURCE}", "")),
                        "quotes": [quotes[n] for n in numbers if n in quotes][:4],
                    }
                )
                indexes.append(len(items) - 1)
            paragraphs.append(indexes)
        layout.append(paragraphs)

    size = int(config.get("batch_size", 1))
    answered = await ctx.ask_batches([i for i in items if i["quotes"]], size)
    verdict_of = {id(item): answer["verdict"] for item, answer in answered}
    verdicts: dict[str, int] = {}
    for verdict in verdict_of.values():
        verdicts[verdict] = verdicts.get(verdict, 0) + 1

    removed = []
    checked = []
    for p_index, part in enumerate(parts):
        paragraphs = []
        for indexes in layout[p_index]:
            kept = []
            for i in indexes:
                verdict = verdict_of.get(id(items[i]))
                if verdict in _REMOVE:
                    removed.append(
                        {
                            "heading": part["heading"],
                            "sentence": items[i]["text"],
                            "verdict": verdict,
                        }
                    )
                else:
                    kept.append(items[i]["sentence"])
            if kept:
                paragraphs.append(" ".join(kept))
        if paragraphs:
            text = "\n\n".join(paragraphs)
            checked.append(part | {"text": text, "fact_numbers": _used(text)})
    if not checked:
        raise StepFailed("every sentence failed the check")
    unsourced = sum(p["text"].count(NO_SOURCE) for p in checked)
    return {
        "parts": checked,
        "removed": removed,
        "verdicts": verdicts,
        "unsourced_sentences": unsourced,
    }


# The model talks about the task instead of doing it: "Here is an
# introduction of 3 to 5 sentences: ..." (2 of 6 works of the 1.3.0 eval).
_META = re.compile(r"^\s*(here is|here's|here are|below is|sure|вот |ниже |конечно)", re.IGNORECASE)
_FIRST_SENTENCE = re.compile(r"^.*?[.!?:](\s+|$)", re.DOTALL)
META_NOTE = (
    "Your last answer talked about the task. Reply with the text itself only: "
    "no words about the task, the instructions or the number of sentences."
)


def is_meta(text: str) -> bool:
    return bool(_META.match(text))


async def _not_meta(ctx: StepContext, item: Any, answer: dict[str, Any]) -> dict[str, Any]:
    """Ask once more if the text talks about the task; if it still does,
    drop its first sentence (the talk). Counted in the step summary."""
    if not is_meta(answer["text"]):
        return answer
    retry = await ctx.ask(item=item, extra_note=META_NOTE)
    if retry is not None and not is_meta(retry["text"]):
        return retry
    ctx.notes.append("a text talked about the task; its first sentence was dropped")
    return answer | {"text": _FIRST_SENTENCE.sub("", answer["text"], count=1).strip()}


async def compose(ctx: StepContext) -> dict[str, Any]:
    """A short text without facts: an introduction, a conclusion, or (with
    for_each) the opening sentences of each section. The answer must have
    a "text" field; it is checked for the task language, and asked again
    if it talks about the task ("Here is an introduction..."). With
    for_each: {"texts": [answer or None, ...]} in the order of the items."""
    if ctx.step.for_each:
        items = ctx.resolve(ctx.step.for_each)
        answers = {id(item): data for item, data in await ctx.ask_each(items)}
        texts = []
        for item in items:
            data = answers.get(id(item))
            if data:
                data = await _not_meta(ctx, item, await ctx.in_task_language(item, data, "text"))
            texts.append(data)
        return {"texts": texts}
    answer = await ctx.ask()
    if answer is None:
        raise StepFailed("the model gave no valid answer")
    answer = await ctx.in_task_language(None, answer, "text")
    return await _not_meta(ctx, None, answer)


def _text_of(ctx: StepContext, step_id: str | None) -> dict[str, Any] | None:
    return ctx.outputs.get(step_id) if step_id else None


async def assemble(ctx: StepContext) -> dict[str, Any]:
    """No model: put the report together from earlier steps (config: step
    ids). intro, then per section (from `sections`) its heading, its lead
    (from `leads`, a compose step with for_each over the same sections)
    and its written parts (from `parts`), then the conclusion. Fact numbers
    are renumbered 1, 2, 3... in the order of first use; `facts` (the
    numbered facts of the group step) get the new numbers.

    Output: paragraphs (heading or None, level 2/3, text, fact_numbers),
    facts; the same shape the work builder reads from write + group."""
    config = ctx.step.config
    sections = ctx.resolve(config["sections"])
    written = ctx.resolve(config["parts"])
    leads = (_text_of(ctx, config.get("leads")) or {}).get("texts") or [None] * len(sections)
    paragraphs: list[dict[str, Any]] = []
    if intro := _text_of(ctx, config.get("intro")):
        paragraphs.append({"heading": None, "level": 2, "text": intro["text"]})
    for section, lead in zip(sections, leads, strict=False):
        parts = [p for p in written if p["section"] == section["heading"]]
        if not parts:
            continue
        lead_text = lead["text"] if lead else ""
        paragraphs.append({"heading": section["heading"], "level": 2, "text": lead_text})
        paragraphs += [{"heading": p["heading"], "level": 3, "text": p["text"]} for p in parts]
    if conclusion := _text_of(ctx, config.get("conclusion")):
        paragraphs.append(
            {"heading": conclusion.get("heading"), "level": 2, "text": conclusion["text"]}
        )

    # New numbers in the order of first use.
    new: dict[int, int] = {}
    for paragraph in paragraphs:
        for n in _MARK.findall(paragraph["text"]):
            new.setdefault(int(n), len(new) + 1)

    def renumber(match: re.Match) -> str:
        return f"[{new[int(match.group(1))]}]" if int(match.group(1)) in new else match.group(0)

    for paragraph in paragraphs:
        paragraph["text"] = _MARK.sub(renumber, paragraph["text"])
        paragraph["fact_numbers"] = sorted({int(n) for n in _MARK.findall(paragraph["text"])})
    facts = [
        fact | {"number": new[fact["number"]]}
        for fact in ctx.resolve(config["facts"])
        if fact["number"] in new
    ]
    facts.sort(key=lambda f: f["number"])
    return {"paragraphs": paragraphs, "facts": facts}


HANDLERS = {
    "plan_each": plan_each,
    "gaps": gaps,
    "group": group,
    "abstract": abstract,
    "dedup": dedup,
    "subplan": subplan,
    "write_parts": write_parts,
    "cover": cover,
    "check_text": check_text,
    "compose": compose,
    "assemble": assemble,
}
