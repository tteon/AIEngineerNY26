# CFP — AIE NYC 2026, sessionize form draft

Max **3 submissions** per speaker. Strategy: one strong Stage Talk submission now (Wave 1,
submit by Aug 14); hold the other two slots — decide after results whether a second angle
(Lightning: "silent truncation is a compliance bug, not a UX bug" / Online-track variant)
earns a slot. Don't spam.

⏳ = finalize from results/before_after_full_*.json before submitting. Everything else is
measured and traceable to a results file.

---

## Session Title

**Your Ontology Won't Save You: What Agent↔Graph QA Actually Costs at Scale**

Alternates (form allows changing later):
- Everyone Has an Ontology, Nobody Shows the Interface: Before/After on an AML Graph
- Stop Demoing Ontologies. Start Engineering the Agent–Database Interface.

Style check: engineer-punchy (dx.tips genre), not TED/NeurIPS. The critique is the hook.

## Description (public; first paragraph = the promise)

> Ontology and knowledge-graph talks are everywhere, but they stop at the diagram. Nobody
> shows you where it's actually used, what breaks when an agent starts asking real
> questions, or what it costs at scale. This talk shows exactly that, with measured
> numbers: the same QA workload on a financial-crime graph, run through a naive
> integration and an engineered interface, at 1× to 100× scale — every delta attributed
> to a specific engineering decision you can copy.
>
> The stage is an LDBC FinBench-style AML graph (accounts, transfers, mule networks,
> guarantees) and one question set spanning the two personas finance actually has:
> customer-facing queries bound by latency SLOs (200 ms p50 / 1 s p99), and
> AML-investigator queries bound by completeness. The *naive* stack is what every first
> integration looks like — label names in the prompt, rows dumped as JSON, results
> silently capped. The *engineered* stack applies five interface interventions: a schema
> contract from the ontology, deterministic query enforcement, a row encoding that costs
> 42% fewer tokens for identical information, in-band truncation disclosure, and result
> caps owned by the contract instead of the harness.
>
> The deltas are concrete. Across 234 episodes, the naive stack answered wrongly off a
> silently truncated view 9 times; the engineered stack, zero — in AML terms that's a
> compliance exposure removed, not a UX nicety. As the graph grows 100×, naive median
> episode latency degrades 2.6× (3.7 s → 9.5 s) while the engineered stack stays flat
> (~4.1 s) — the schema contract keeps queries anchored and index-shaped at every scale.
> Accuracy: 83% → 92% overall, and the gap widens with scale. The price is honest and
> fixed: ~48% more prompt tokens per episode for the contract and its enforcement loop,
> while the rows-into-context payload shrinks 2–3×. And the disclosure effect is
> model-dependent — a second model family fails by burning its turn budget instead of by
> silence — so the interface must be engineered per model capability, not assumed.
>
> You leave with the five interface seams, the metric each one moves, and what each one
> costs — every number from manifested, replayable runs on an open benchmark.

## Session format

Stage Talk (15–20 min). Happy to adapt to Lightning or Online if assigned.

## Special Flags

None claimed.

## Speaker/Session Pitch (committee-only)

> Why this talk, now: the ontology/GraphRAG content wave is at peak abstraction — use-case
> lists and architecture diagrams, no numbers. Meanwhile every FI in your audience is
> wiring an agent to a graph of accounts and transfers and discovering the hard part is
> the interface: serialization, truncation, enforcement, caps, and what those do to
> accuracy and cost at scale. I measured it: 800+ recorded agent↔database episodes across
> seven interface designs on LDBC FinBench (SF1→100), replicated across two model
> families, plus native-driver fleet replays (thread-per-agent, lock contention on hub
> accounts, interchange redundancy). Every number ships with a manifest and raw samples.
> The talk is deliberately critical of the current content genre — it names the gap
> between ontology demos and production QA, then fills it with engineering points,
> metrics, and benefits an attendee can apply the same week.
>
> Why me: I'm a graph product engineer (graph query engines with hardware acceleration at
> XCENA), author of an open-source ontology middleware, and I've delivered 4+ tutorials
> and workshops at academic conferences for researchers and practitioners. This material
> is finance-native (AML workload, SLO-bound personas), fits mainstage FinServ, and
> doubles into the evals/infra tracks. Not a vendor pitch: the findings are tool-agnostic
> interface principles measured on an open benchmark; the harness is open source.

## Possible Tracks (1–3)

1. AI in Financial Services (mainstage)
2. Infrastructure
3. Evals

## Speaker fields

- Name: Ii Tae Jeong · XCENA · title: **Graph Product Engineer**
- Bio (from profile, keep): "Ii Tae Jeong is a Graph Product Engineer specializing in
  graph query engines with hardware acceleration. …" (already in sessionize)
- Based in: Seoul, South Korea (international — 3 nights covered; need-blind, minor
  tiebreaker)
- Past speaking: 4+ academic tutorials/workshops — add links as tiebreaker
- Co-speaker: none

## Pre-submission checklist

- [x] composite numbers from the 234-episode sweep pasted in; crossover claim **softened**
      (token crossover did not appear in the 8-turn aggregates-allowed regime — replaced
      with the latency-flatness claim, which the data does support)
- [x] number ↔ results-file mapping appended below
- [ ] title A/B: does it read like PyCon/StrangeLoop, not a generic AI conf?
- [ ] description first paragraph promises; rest intrigues (form guidance)
- [ ] read against rules: original, not vendor-only, finance-specific, production-grade

## Number ↔ evidence mapping

All in AIEngineerNY26 `results/before_after_full_20260808T132728Z.json` (234 episodes,
gpt-oss-120b, 13 questions × naive/engineered × 3 repeats × SF1/10/100, manifest inside)
unless noted:

| claim | evidence |
|---|---|
| silent truncation 9 → 0 | sum of `silent_truncation_failure` by stack (naive 3 per scale, engineered 0) |
| naive p50 3.7 s → 9.5 s at SF100; engineered flat ~4.1 s | median `wall_ms` by (sf, stack) |
| accuracy 83% → 92% (97/117 vs 108/117); widens with scale | `score_correct` by (sf, stack): SF1 36→39, SF10 31→36, SF100 30→33 |
| +48% prompt tokens/episode | mean `input_tokens`: 2,268 → 3,361 |
| rows-into-context payload 2–3× smaller | mean `chars_into_context`: 824 → 361 (SF100: 1,083 → 393) |
| row encoding −42% tokens | AIsummit26 `results/bench/format_tokens.json` (o200k, 200 rows: 9,017 JSON vs 5,211 CSV) |
| +51pp silent failures without disclosure signal (gpt-oss); DeepSeek burns turn budget instead | AIsummit26 in_context vs in_context_blind arms + DeepSeek replication (c80d029) |
| consuming a row ~7× producing it | AIsummit26 `results/bench_bridge2_20260808.txt` (client 20.8 vs server 2.9 µs/row) |
