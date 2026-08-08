# AIEngineerNY26

**Multi-agent × scalability × context-interchange, measured on the SEOCHO stack.**

AIsummit26 measured the agent↔graph-DB exchange for a single agent and, in a raw-Bolt
replay, mapped where a fleet breaks: the exchange scales past the GIL in one native
process (16 agents, 820k rows/s, 2.0 cores), hot-node writes serialize on the lock queue
(p99 1.1→200 ms), and the rows→context layer caches nothing (identical result sets are
paid in full, 200×). Those numbers came from bypassing the middleware — fast to measure,
blind to everything SEOCHO instruments.

This repo is the on-stack sequel. SEOCHO lives here as a resident upstream
(`vendor/seocho`, pinned to `aisummit26-interface-v1`), so experiments run through the
contract layer with its observability on:

- **ontology as the operating contract** — `schema_for_prompt`, planner policy, guardrails
- **`encode_rows`** — the canonical rows→context serializer (JSON/CSV, the AIsummit26
  measurement upstreamed as tteon/seocho#466)
- **spec'd metrics** — `seocho.retrieval.duration`, `seocho.context.assembly.duration`,
  context token counts, text2cypher stages… exported over OTLP
  (`SEOCHO_METRICS_BACKEND=otlp`, `SEOCHO_METRICS_OTLP_ENDPOINT=…`)

## Layout

```
vendor/seocho     resident upstream (git submodule, pinned tag)
ontology/         the FinBench ontology contract (from AIsummit26)
scripts/          experiments; smoke_stack.py proves the five stack layers
results/          measurement runs (manifest + raw samples, always)
```

## Setup

```
git submodule update --init
uv sync
uv run python scripts/smoke_stack.py           # needs the DozerDB container running
```

## Roadmap

1. Multi-agent episode runner on SEOCHO (ontology + encode_rows + metrics per turn)
2. Thread-per-agent native data plane vs the Python plane, same episodes, same metrics
3. Prefix-cache A/B on self-hosted vLLM: the ontology block as the shared KV tier,
   per-episode history as the session-resident object
