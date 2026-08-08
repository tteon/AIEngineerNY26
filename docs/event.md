# AIE NYC 2026 — event brief

AI Engineer New York 2026 · **Oct 12–14** · Sheraton NY Times Square · presented by Arize.
"Where AI Engineering Meets Wall Street" — production AI across banking, hedge funds,
fintech, insurance, asset management. 1,000+ in-person engineers/leaders, 150K+ livestream,
speakers from Morgan Stanley, BlackRock, Capital One, Bloomberg, Goldman Sachs, Two Sigma.

The audience self-description that matters: **"not in discovery mode — actively deploying,
optimizing, and investing."** Talks are expected to be production systems and
infrastructure challenges, not use-case tours.

## CFP (sessionize.com/aienyc2026)

| | |
|---|---|
| Deadline | **Sep 12, 2026** — wave decisions **Aug 15 / Sep 1 / Sep 15** |
| Our target | **Stage Talk (15–20 min), Wave 1 → submit by Aug 14** |
| Acceptance | 5–15% historical |
| Tracks | Mainstage: AI in Financial Services. Evergreen: **evals, infrastructure** |
| Hard rules | No vendor-only pitches (tooling vendors should bring customers); no generic AI-conf talks; originality valued |
| Speaker support | Economy flights + 2–3 nights hotel, free attendance |

## Why our work fits

| Event expectation | What we bring |
|---|---|
| Finance-native content | LDBC FinBench AML graph: accounts, transfers, mule accounts, guarantees. Question set is two *finance personas*: external customer-facing (latency-SLO-bound, 200ms p50 / 1s p99) vs internal AML investigator (completeness-bound) |
| Production/infra, not demos | Before/after the agent↔KB interface engineering, same questions, SF1→100, measured episodes with manifests and raw samples for every number |
| Evals track | The before/after composite IS an eval: accuracy, silent-truncation rate, guardrail recovery, tokens, latency — per intervention |
| Observability (Arize audience) | Every delta attributed via OTLP metrics (retrieval duration, context token counts, validation failures) — "which engineering moved which needle" as telemetry, not opinion |
| Compliance resonance | **Silent truncation failure**: an AML answer that is wrong off a truncated view *without saying so* — measured, and model-family-dependent (gpt-oss +51pp without the disclosure signal; DeepSeek instead exhausts its turn budget). In finance this is a regulatory exposure, not a UX bug |

## Talk scope decision (2026-08-08)

Finance has two data planes and this talk covers the first:

1. **Transactions → LDBC FinBench graph** — this talk. Deep, measured, done well.
2. **Documents → FinDER (SEC 10-K RAG)** — second in line; appears in the abstract only
   as one roadmap sentence ("the same discipline applies to the document KB").

## Positioning risks

- **seocho is our own open-source middleware** → frame findings-first, tool-agnostic.
  The interventions are *principles* (schema contract, deterministic enforcement, cheaper
  row encoding, in-band truncation disclosure, caps owned by the contract); seocho is the
  instrument that happens to implement them. Never "use seocho" — always "engineer these
  five seams; here is what each one bought us."
- **No generic-AI framing**: every slide number comes from the AML graph at stated scale,
  with the two finance personas carrying the SLO/completeness split.
