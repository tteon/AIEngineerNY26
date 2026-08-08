"""Prove the resident SEOCHO stack end to end before building experiments on it.

Five checks, each one layer of the stack this repo depends on:
  1. seocho imports from the vendored submodule (pinned tag, not PyPI)
  2. the ontology contract loads and compiles to a prompt schema
  3. a live 200-row page comes back from DozerDB under the workspace scope
  4. encode_rows — seocho's canonical rows->context serializer — encodes it both ways
  5. the metrics seam accepts a spec'd histogram sample (backend from env:
     SEOCHO_METRICS_BACKEND=otlp + SEOCHO_METRICS_OTLP_ENDPOINT for real export,
     unset -> validating no-op)

    uv run python scripts/smoke_stack.py [database]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WS = "default"


def main() -> None:
    database = sys.argv[1] if len(sys.argv) > 1 else "finbenchl1"

    import seocho
    origin = Path(seocho.__file__).resolve()
    assert (REPO / "vendor/seocho") in origin.parents, f"seocho came from {origin}, not the submodule"
    print(f"[1] seocho {getattr(seocho, '__version__', '?')} from {origin.parent}")

    from seocho.ontology import Ontology
    from seocho.query.hybrid_planner import policy_from_ontology, schema_for_prompt

    doc = yaml.safe_load((REPO / "ontology/finbench.ontology.yaml").read_text())
    ontology = Ontology.from_dict(doc)
    schema = schema_for_prompt(ontology, policy_from_ontology(ontology))
    print(f"[2] ontology -> prompt schema: {len(schema.get('nodes', schema))} node types")

    import neo4j

    auth = ("neo4j", os.getenv("NEO4J_PASSWORD", "neo4jpassword"))
    with neo4j.GraphDatabase.driver("bolt://127.0.0.1:7687", auth=auth) as driver:
        records, _, _ = driver.execute_query(
            "MATCH (a:Account {_workspace_id:$ws})-[t:TRANSFER]->(b:Account {_workspace_id:$ws}) "
            "RETURN a.acct_no AS src, b.acct_no AS dst, t.amount AS amount, "
            "t.channel_risk AS risk LIMIT 200",
            ws=WS, database_=database,
        )
    rows = [dict(r) for r in records]
    print(f"[3] {database}: {len(rows)} rows under workspace scope")

    from seocho.integrations.openai_agents import encode_rows

    js = encode_rows(rows, row_cap=200, truncated=True, row_format="json")
    cs = encode_rows(rows, row_cap=200, truncated=True, row_format="csv")
    print(f"[4] encode_rows: json {len(js):,} B, csv {len(cs):,} B ({len(cs)/len(js):.0%})")

    from seocho.metrics import METRIC_SPECS, enable_metrics

    metrics = enable_metrics()  # backend from SEOCHO_METRICS_BACKEND (default none)
    t0 = time.perf_counter()
    metrics.record("seocho.retrieval.duration", time.perf_counter() - t0,
                   {"source": "dozerdb", "outcome": "success"})
    backend = os.getenv("SEOCHO_METRICS_BACKEND", "none")
    print(f"[5] metrics seam ok: backend={backend}, {len(METRIC_SPECS)} spec'd instruments")

    print("\nstack ready.")


if __name__ == "__main__":
    main()
