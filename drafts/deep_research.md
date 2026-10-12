# deep_research: problems and next steps

Working document for the `deep_research` pipeline (`pipelines/deep_research/`).
Started 2026-10-12 from the evals of 1.3.0 and 1.4.0 (`quality/topics.yaml`,
`qwen2.5:7b`, medium, 8k context, six technical topics). Facts and numbers
are from `CURRENT_STATE.md` and the eval outputs; read the runs, not only
this file.

## Goal

A well written text with checked facts and enough material. For a run of
about 3 hours: "a solid piece of work, not a collection of quotes"
(author, 2026-10-09). Quality comes before speed.

## Where we are (1.4.0)

Chain: outline → rounds of search/fetch/summarize/gaps → verify → group →
dedup → subplan → write_parts → cover → check_text → compose → assemble.
Every claim keeps a source and an exact quote.

| Question | 1.3.0 | 1.4.0 |
|---|---|---|
| Works done (of 6) | 6 | 4 (2 failed in search) |
| Cited facts, per topic | 26-46 | 12-54 |
| Share of kept facts that are cited | 20-30% | 63-86% |
| Minutes per topic | 68-94 | 47-63 |
| Sentences removed by `check_text` | - | 2-4 per topic |

## Problems

1. **The 1.4.0 eval is not a fair comparison.** `local_llm` and `attention`
   failed: "the search found nothing". Is SearxNG up? The search is also thin
   on `quantization` (30 facts, 7 sources; 1.3.0 had 167 facts, 20 sources).
   Fewer sources means fewer facts and shorter text, so the totals say little
   about `cover` and `check_text`.
2. **Stock phrases are still there.** "This report delves into...",
   "This section explains/explores..." at the start of almost every section.
   The ban in 1.4.0 caught only the intro of the old kind.
3. **`check_text` is cautious, so its value is unclear.** On 7B it removed
   few sentences and mostly vague ones. Two of four removed in `rag` look like
   real facts (chunk size 512 tokens with 10-20% overlap; MRL). The one
   `wrong` verdict is a general sentence. We do not know how many wrong
   sentences it misses.
4. **"No source" sentences stay.** 4-17 per topic. They are the "why it
   matters" part and can carry wrong claims (1.3.0 example: VACUUM and
   locks instead of the xmin horizon).
5. **Overlapping sections.** A part equal to a section in meaning, a thin
   last section. Open since 1.3.0.
6. **Search depends on one engine.** When SearxNG returns nothing, the whole
   topic fails. The retry rounds help only with short blocks.
7. **We do not measure text quality.** The compare table counts words and
   facts. Reading works by hand takes the author's time.

## Next steps

Order is a proposal; the author decides.

1. Check SearxNG on the server, rerun `local_llm` and `attention` with
   1.4.0 (about 2.5 h on the server). Then the 1.3.0/1.4.0 table is full.
2. Find why `quantization` found 7 sources: queries, or blocked pages?
   Look at `1_r1_plan.json` and the search output of that run.
3. Read 2 works as a reader (not as numbers) and write down what is still
   wrong: repeated ideas, empty paragraphs, bad transitions.
4. Remove stock phrases with a second pass in `compose`, or with a code
   check and one re-ask (like the "talks about the task" check).
5. Decide on `check_text`: keep as is, or add a mark for `new` sentences
   instead of removing them. Needs a hand check of 30-40 verdicts.
6. Overlapping sections: merge or drop parts in `subplan` by a similarity
   check (code first, model for pairs).
7. A cheap quality score for `compare`: share of paragraphs with a cited
   fact, repeated n-grams, count of stock phrases.

## Not now

- Speed work (paused by the author).
- Cloud models for this pipeline. It is built for 3-8B; a cloud provider
  would change what is the bottleneck.
- Parallel tasks and "competitive with Perplexity / GPT Researcher": the
  meaning of "competitive" is still an open question in `CURRENT_STATE.md`.
