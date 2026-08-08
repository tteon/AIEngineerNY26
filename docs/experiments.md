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

## Deferred (explicitly)
vLLM prefix-cache A/B (needs self-hosted serving; ontology block = shared KV tier) ·
FinDER document plane (second talk) · rust episode-loop port.
