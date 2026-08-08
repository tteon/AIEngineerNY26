# Experiment ledger — what each run exists to show

The talk's purpose (owner's words, 2026-08-08): ontology content is everywhere but
abstract; QA is the real workload; show concretely how it is used, how scalability is
covered, and present metrics, engineering points, and benefits — critically. Each
experiment below feeds one pillar. A result that contradicts its hypothesis is reported,
not massaged.

## E1. Composite before/after, agg regime — DONE
`results/before_after_full_20260808T132728Z.json` (234 eps, gpt-oss-120b, SF1/10/100)

- **Question**: does whole-stack interface engineering pay, on the workload where the DB
  is allowed to aggregate (short episodes, few rows)?
- **Answer**: accuracy 83→92% (gap widens with scale), silent truncation 9→0, naive p50
  degrades 2.6× over SF1→100 while engineered stays flat ~4.1 s; price = +48% prompt
  tokens, payload −2–3×. Token crossover: **did not appear** in this regime — said so.
- **Talk role**: the composite chart + compliance number + latency-flatness claim.

## E2. rows regime (crossover regime) — the interchange main event
`--regime rows`: aggregates banned (enforced), cap 200 (contract amended via policy, not
bypassed), 16 turns. SF1 (anchor ~800 transfers = 4 pages, feasible) vs SF100 (~16,700 =
84 pages, infeasible by construction). 13q × 2 stacks × 2 repeats × {SF1, SF100}.

- **Question**: when rows actually flow — the graph version of every RAG/QA system that
  pulls context and lets the model synthesize — which interface interventions carry?
- **Hypotheses**: (a) naive silent truncation explodes (no signal, silent cap);
  (b) the token crossover appears here: with row payloads dominating, CSV's −42% beats
  the engineered stack's fixed premium; (c) on infeasible-scale questions engineered
  *discloses* the bounded view, naive answers wrong silently.
- **Falsifier**: no crossover even here → the honest claim becomes "there is no
  crossover; the premium buys correctness and disclosure, period."
- **Talk role**: interchange slide numbers; compliance claim under stress.

## E3. Fleet on-stack (concurrency 1→16) — scalability's second axis
Same workload (13q × 2 stacks × 1 repeat, SF10), concurrency ∈ {1, 4, 8, 16}, OTLP on.

- **Question**: SF scaled the data; production also scales the *load*. As concurrent
  agents rise, where does the python plane saturate — LLM API, DB, or client consume
  (the measured ~1.3-core GIL ceiling)?
- **Method**: episode p50/p99 vs concurrency; attribution via OTLP split (retrieval
  duration vs episode duration vs inflight). MARA rate-limit errors are data, not noise.
- **Talk role**: "what breaks at fleet scale" slide, joined with the native replay
  numbers (16 threads, 820k rows/s, hub-lock p99 1.1→200 ms) for the data-plane argument.

## E4. Second model family (DeepSeek-V3.2, agg regime)
13q × 2 stacks × 1 repeat × {SF1, SF100}, --max-tokens 16384.

- **Question**: is the before/after delta a property of the interface or of gpt-oss?
- **Prior**: the blind-gap did NOT replicate on DeepSeek (it pages unprompted, then
  exhausts its 16-turn budget — failure moves from silently-wrong to no-answer).
- **Hypothesis**: the engineered advantage persists but its *composition* shifts — which
  is itself the claim "interfaces are engineered per model capability."
- **Falsifier**: delta vanishes → report it; the talk's generality section weakens and
  says so.
- **Talk role**: generality defense; the per-model-engineering slide.

## Verdicts (2026-08-09, all results in results/, manifests inside)

- **E2** `rows_regime_20260808T141301Z.json` (104 eps): H-a **confirmed hard** — naive
  silently wrong off truncated views 34/52, zero disclosures; engineered 12/52 with 8
  disclosures. H-b (token crossover) **refuted** — engineered pays ~4× input tokens
  *because it does the work* (5–8 pages, history resend amplification; MARA has no prefix
  cache — verified same day, cached_tokens absent AND TTFT flat, prefill ~21k tok/s so
  the cost is money, not latency). H-c partial: both stacks collapse vs agg regime
  (25–38% vs 83–92%) — engineering limits damage, cannot rescue the pattern. Rule #1
  stands: keep aggregation in the database.
- **E3** `fleet_c{1,4,8,16}_*.json`: python plane holds to 16 concurrent agents — p50
  +60% (4.0→6.4 s), accuracy stable. OTLP attribution: mean DB retrieval flat-to-falling
  across concurrency (10.9→8.1 s), so the inflation is entirely LLM/API-side. The GIL
  wall is not the binding constraint at this workload; LLM latency is.
- **E4** `deepseek_agg_*.json` (52 eps, n=13/cell — preliminary): the before/after delta
  **vanishes** on DeepSeek-V3.2 (naive 20/26 vs engineered 18/26); guardrail retry loops
  cost more on a reasoning model (p50 ~48–52 s vs naive ~29 s) and engineered even shows
  2 silent TFs at SF100. Interface deltas are model-contingent — the
  per-model-engineering claim, measured at whole-stack level.
- **E2b** `e2b_encoding_*.json` (12 eps, tiny n — directional only): with reasoning
  accounting on (runner now records per-call reasoning_tokens/TTFT via MARA's SambaNova
  usage extensions), CSV pages triggered ~5× the reasoning spend of JSON pages on
  summation-heavy questions (9.4k vs 1.7k/ep; ext_easy_1: 24.9k vs 3.4k) — the cheaper
  wire encoding can cost more end-to-end when the model must compute over the rows.
  Also observed: temp-0 episodes are not bitwise deterministic on MARA (same config,
  different outcomes across runs) — repeats are load-bearing. Needs a proper follow-up
  before it becomes a talk claim. Rows-regime output is ~94–99% reasoning tokens either
  way: the interchange's hidden cost is reasoning, and without a prefix cache it is
  billed in full.

## Deferred (explicitly)
vLLM prefix-cache A/B (needs self-hosted serving; ontology block = shared KV tier) ·
FinDER document plane (second talk) · rust episode-loop port · E2b at proper scale
(more questions/repeats/models) before the encoding↔reasoning claim goes on stage.
