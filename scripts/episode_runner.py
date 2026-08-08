"""Before/after the interface engineering: the same questions, two stacks.

The talk's claim is that ontology use cases only materialize when the agent<->knowledge-base
interface is engineered. This runner makes that claim measurable by composing the interface
from toggles and running identical episodes through two presets:

  naive        what every first integration looks like: label names in the prompt, rows
               dumped as ad-hoc JSON, results silently capped, nothing enforced
  engineered   the SEOCHO contract layer: ontology schema (schema_for_prompt), the
               deterministic guardrail (validate_text2cypher_fallback), rows serialized by
               encode_rows with the truncation disclosure carried in-band

Each toggle is one rung of the before/after ladder, so any single intervention can be
isolated (--schema/--encoding/--disclosure/--enforcement build a custom stack).

Episode mechanics — the instrumented tool, scoring, disclosure detection, the gpt-oss
empty-final nudge — are ported from AIsummit26's agent_interaction.py, which measured these
questions arm-by-arm; this runner recomposes those arms into whole-stack presets and emits
SEOCHO metrics per turn (SEOCHO_METRICS_BACKEND=otlp to export).

    source <env with MARA_API_KEY>
    uv run python scripts/episode_runner.py --databases finbenchl1:1 --repeats 1
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from agents import Agent, ModelSettings, Runner, function_tool
from agents.exceptions import MaxTurnsExceeded

from runmeta import manifest

REPO = Path(__file__).resolve().parent.parent
WS = "default"
DEFAULT_ROW_CAP = 50  # overridden at runtime by policy.max_result_rows — the contract owns the cap
MAX_TURNS = 8
TX_TIMEOUT_S = 60.0


# --------------------------------------------------------------------------------------
# The interface, as toggles
# --------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Stack:
    name: str
    schema: str = "labels"        # labels | ontology
    encoding: str = "json"        # json | csv (csv goes through seocho encode_rows)
    disclosure: bool = False      # carry row_cap + more_available in-band
    enforcement: str = "none"     # none | guardrail

    def describe(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


PRESETS = {
    "naive": Stack("naive"),
    "engineered": Stack("engineered", schema="ontology", encoding="csv",
                        disclosure=True, enforcement="guardrail"),
}


# --------------------------------------------------------------------------------------
# Questions: the full AIsummit26 set, verbatim (gold ref included)
# --------------------------------------------------------------------------------------
QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "ext_easy_1", "audience": "external", "difficulty": "easy",
        "ko": "내 계좌로 지금까지 들어온 이체는 몇 건이고 총액은 얼마인가요?",
        "question": ("For account number {a}: how many transfers has it received in total, "
                     "and what is the total amount received?"),
        "shape": "scalar", "keys": ["n", "total"],
        "ref": ("MATCH (:Account {acct_no:$a,_workspace_id:$ws})<-[t:TRANSFER]-"
                "(:Account {_workspace_id:$ws}) RETURN count(t) AS n, sum(t.amount) AS total"),
    },
    {
        "id": "ext_easy_2", "audience": "external", "difficulty": "easy",
        "ko": "내 계좌에서 나간 이체 건수와 그 중 가장 큰 금액은?",
        "question": ("For account number {a}: how many outgoing transfers are there, and what "
                     "is the single largest amount sent?"),
        "shape": "scalar", "keys": ["n", "biggest"],
        "ref": ("MATCH (:Account {acct_no:$a,_workspace_id:$ws})-[t:TRANSFER]->"
                "(:Account {_workspace_id:$ws}) RETURN count(t) AS n, max(t.amount) AS biggest"),
    },
    {
        "id": "ext_med_1", "audience": "external", "difficulty": "medium",
        "ko": "내 계좌로 돈을 보낸 계좌 중 고위험 채널을 쓴 곳은 어디인가요?",
        "question": ("Which accounts sent money to account number {a} on a transfer whose own "
                     "channel_risk property is 5 or more? Give the five lowest such account "
                     "numbers in ascending order."),
        "shape": "list", "column": "acct",
        "ref": ("MATCH (s:Account {_workspace_id:$ws})-[t:TRANSFER]->"
                "(:Account {acct_no:$a,_workspace_id:$ws}) WHERE t.channel_risk>=5 "
                "RETURN DISTINCT s.acct_no AS acct ORDER BY acct LIMIT 5"),
    },
    {
        "id": "ext_med_2", "audience": "external", "difficulty": "medium",
        "ko": "내가 송금한 계좌들의 실제 소유자는 누구인가요?",
        "question": ("Who owns the accounts that account number {a} has sent money to? Give the "
                     "five lowest owner ids in ascending order."),
        "shape": "list", "column": "owner",
        "ref": ("MATCH (:Account {acct_no:$a,_workspace_id:$ws})-[:TRANSFER]->"
                "(b:Account {_workspace_id:$ws})<-[:OWN]-(o) "
                "RETURN DISTINCT o.id AS owner ORDER BY owner LIMIT 5"),
    },
    {
        "id": "ext_hard_1", "audience": "external", "difficulty": "hard",
        "ko": "내 돈이 두 단계 안에 닿는 계좌는 몇 개이고, 그 중 가장 위험한 등급은?",
        "question": ("Starting from account number {a} and following transfers downstream, how "
                     "many distinct accounts are reachable within two hops, and what is the "
                     "highest risk_tier among them?"),
        "shape": "scalar", "keys": ["n", "worst_risk_tier"],
        "ref": ("MATCH (:Account {acct_no:$a,_workspace_id:$ws})-[:TRANSFER*1..2]->"
                "(b:Account {_workspace_id:$ws}) "
                "RETURN count(DISTINCT b) AS n, max(b.risk_tier) AS worst_risk_tier"),
    },
    {
        "id": "ext_hard_2", "audience": "external", "difficulty": "hard",
        "ko": "내 계좌로 두 단계 안에 돈이 흘러들어온 계좌는 몇 개인가요?",
        "question": ("How many distinct accounts sit within two transfer hops upstream of "
                     "account number {a} — that is, accounts from which money reaches {a} in one "
                     "or two transfers?"),
        "shape": "scalar", "keys": ["n"],
        "ref": ("MATCH (b:Account {_workspace_id:$ws})-[:TRANSFER*1..2]->"
                "(:Account {acct_no:$a,_workspace_id:$ws}) RETURN count(DISTINCT b) AS n"),
    },
    {
        "id": "int_easy_1", "audience": "internal", "difficulty": "easy",
        "ko": "전체 계좌 수와 최고위험(등급 5) 계좌 수는?",
        "question": ("How many accounts are there in total, and how many of them are at "
                     "risk_tier 5?"),
        "shape": "scalar", "keys": ["accounts", "tier5"],
        "ref": ("MATCH (a:Account {_workspace_id:$ws}) RETURN count(a) AS accounts, "
                "sum(CASE WHEN a.risk_tier=5 THEN 1 ELSE 0 END) AS tier5"),
    },
    {
        "id": "int_easy_2", "audience": "internal", "difficulty": "easy",
        "ko": "거래가 가장 많이 오간 채널 상위 5개는?",
        "question": ("Which five channels carry the most transactions? Give the channel codes "
                     "in descending order of total transaction count."),
        "shape": "list", "column": "code",
        "ref": ("MATCH (a:Account {_workspace_id:$ws})-[u:USES_CHANNEL]->"
                "(c:Channel {_workspace_id:$ws}) RETURN c.code AS code, sum(u.tx_count) AS n "
                "ORDER BY n DESC, code LIMIT 5"),
    },
    {
        "id": "int_med_1", "audience": "internal", "difficulty": "medium",
        "ko": "같은 사람이 소유한 계좌끼리 직접 송금이 오간 사례는 몇 건인가요?",
        "question": ("How many distinct ordered pairs of two *different* accounts owned by the "
                     "same party have a direct transfer running from the first to the second? "
                     "Count each pair once however many transfers run between them."),
        "shape": "scalar", "keys": ["n"],
        "ref": ("MATCH (o {_workspace_id:$ws})-[:OWN]->(a:Account {_workspace_id:$ws})"
                "-[:TRANSFER]->(b:Account {_workspace_id:$ws})<-[:OWN]-(o) WHERE a<>b "
                "RETURN count(DISTINCT [a.acct_no,b.acct_no]) AS n"),
    },
    {
        "id": "int_med_2", "audience": "internal", "difficulty": "medium",
        "ko": "100곳이 넘는 상대로부터 입금을 받은 계좌는 어디인가요?",
        "question": ("Which accounts received transfers from more than 100 distinct sending "
                     "accounts? Give the five lowest such account numbers in ascending order."),
        "shape": "list", "column": "acct",
        "ref": ("MATCH (s:Account {_workspace_id:$ws})-[:TRANSFER]->"
                "(t:Account {_workspace_id:$ws}) WITH t, count(DISTINCT s) AS fan "
                "WHERE fan>100 RETURN t.acct_no AS acct ORDER BY acct LIMIT 5"),
    },
    {
        "id": "int_hard_1", "audience": "internal", "difficulty": "hard",
        "ko": "서로 돈이 오가고, 소유자끼리 보증을 서줬고, 같은 기기로 로그인한 계좌 쌍을 찾아주세요.",
        "question": ("Find pairs of accounts that satisfy all three of these at once: money has "
                     "moved between them by transfer, their owners are different parties who "
                     "guarantee one another, and the same login device has signed in to both. "
                     "Give the account number pairs, smaller number first."),
        "shape": "list", "column": "a1",
        "ref": ("MATCH (a:Account {_workspace_id:$ws})-[:TRANSFER]-(b:Account {_workspace_id:$ws}) "
                "WHERE a.acct_no < b.acct_no "
                "MATCH (pa {_workspace_id:$ws})-[:OWN]->(a), (pb {_workspace_id:$ws})-[:OWN]->(b) "
                "WHERE pa<>pb AND (pa)-[:GUARANTEE]-(pb) "
                "MATCH (m:Medium {_workspace_id:$ws})-[:SIGN_IN]->(a), (m)-[:SIGN_IN]->(b) "
                "RETURN DISTINCT a.acct_no AS a1, b.acct_no AS a2 ORDER BY a1,a2 LIMIT 5"),
    },
    {
        # int_hard_1 with the reciprocal/mutual ambiguity removed — kept as a pair, because a
        # schema that makes direction legible does not remove ambiguity from a question, it
        # exposes it (see AIsummit26).
        "id": "int_hard_1b", "audience": "internal", "difficulty": "hard",
        "ko": "서로 돈이 오가고, 소유자 중 한 쪽이 다른 쪽에 보증을 섰고, 같은 기기로 로그인한 계좌 쌍은?",
        "question": ("Find pairs of accounts that satisfy all three of these at once: money has "
                     "moved between them by transfer in either direction, their owners are two "
                     "different parties and one of them guarantees the other in either "
                     "direction, and the same login device has signed in to both. Give the "
                     "account number pairs, smaller number first."),
        "shape": "list", "column": "a1",
        "ref": ("MATCH (a:Account {_workspace_id:$ws})-[:TRANSFER]-(b:Account {_workspace_id:$ws}) "
                "WHERE a.acct_no < b.acct_no "
                "MATCH (pa {_workspace_id:$ws})-[:OWN]->(a), (pb {_workspace_id:$ws})-[:OWN]->(b) "
                "WHERE pa<>pb AND (pa)-[:GUARANTEE]-(pb) "
                "MATCH (m:Medium {_workspace_id:$ws})-[:SIGN_IN]->(a), (m)-[:SIGN_IN]->(b) "
                "RETURN DISTINCT a.acct_no AS a1, b.acct_no AS a2 ORDER BY a1,a2 LIMIT 5"),
    },
    {
        "id": "int_hard_2", "audience": "internal", "difficulty": "hard",
        "ko": "여러 차명계좌에서 한 계좌로 신고기준 아래 금액만 잘게 모으고 있는 사람은 누구인가요?",
        "question": ("Which party owns the largest number of distinct accounts that all send "
                     "money into one single common account, where every one of those transfers "
                     "is below the 10,000,000 reporting threshold? Give the owner id and how "
                     "many of their accounts are involved."),
        "shape": "list", "column": "owner",
        "ref": ("MATCH (o {_workspace_id:$ws})-[:OWN]->(a:Account {_workspace_id:$ws})"
                "-[t:TRANSFER]->(c:Account {_workspace_id:$ws}) WHERE t.amount < 10000000 "
                "WITH o,c,count(DISTINCT a) AS accts WHERE accts>=5 "
                "RETURN o.id AS owner, accts ORDER BY accts DESC, owner LIMIT 3"),
    },
]


def labels_only_schema(ontology: Any) -> Dict[str, Any]:
    """What a plain text2cypher prompt carries: names and endpoint types, nothing about
    direction roles or degree — exactly what the ontology schema restores."""
    nodes = {name: sorted((node.properties or {}).keys())
             for name, node in ontology.nodes.items()}
    rels = {name: f"({rel.source})-[:{name}]->({rel.target})"
            for name, rel in ontology.relationships.items()}
    return {"nodes": nodes, "relationships": rels}


def build_instructions(schema: Dict[str, Any], stack: Stack, row_cap: int,
                       regime: str = "agg") -> str:
    parts = [
        "You are a financial-crime analyst answering questions about a financial graph by "
        "writing Cypher and running it with the run_cypher tool.",
        "",
        "Schema:",
        json.dumps(schema, indent=2, default=str),
        "",
        "Rules:",
        "- Every node pattern must carry the workspace scope, written exactly as "
        "{_workspace_id: $workspace_id}. The harness supplies $workspace_id, $limit and "
        "(where the question names an account) $a; you do not need to define them, and you "
        "must not inline their values.",
        "- Refer to an account the question names by binding acct_no to the $a parameter, "
        "not by inlining the number.",
        "- End every query with LIMIT $limit.",
        "- Call the tool as many times as you need, then answer.",
    ]
    if regime == "rows":
        parts.append(
            "- You may NOT use aggregate functions in Cypher (count, sum, avg, min, max, "
            "collect, percentile). Return the underlying rows and compute the answer "
            "yourself from what you receive.")
    if stack.encoding == "csv":
        parts.append(
            f"- The tool returns rows as CSV: a header line, one line per row, and a final "
            f"line of the form `# row_count=<n> row_cap=<n> truncated=<true|false>`.")
    if stack.disclosure:
        parts.append(
            f"- Results are capped at {row_cap} rows per call and the payload reports when "
            "there were more; page through with SKIP/ORDER BY if you need them. If you "
            "cannot see all the rows the answer depends on, say so in your reply instead of "
            "answering from the rows you happen to have.")
    parts += [
        "",
        "Finish your reply with a single line of the form:",
        "ANSWER: <json>",
        "where <json> is a JSON object for a question asking for named values, or a JSON "
        "array for a question asking for a list. Put nothing after that line.",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------------------------
# The tool: one behaviour per toggle, one record and one metric per call
# --------------------------------------------------------------------------------------
def make_tool(driver, database: str, *, stack: Stack, anchor: Optional[int],
              calls: List[Dict[str, Any]], guardrail_fn, encode_rows, metrics,
              row_cap: int, regime: str = "agg"):
    @function_tool(
        name_override="run_cypher",
        description_override=(
            "Run one read-only Cypher query against the financial graph and return the "
            "rows. Use only labels and relationship types from the schema. $workspace_id, "
            "$limit and $a are supplied for you."),
    )
    def run_cypher(cypher: str) -> str:
        record: Dict[str, Any] = {"cypher": cypher, "outcome": "ok", "db_hits": 0,
                                  "rows": 0, "ms": 0.0, "chars": 0}
        calls.append(record)
        params = {"workspace_id": WS, "ws": WS, "limit": row_cap}
        if anchor is not None:
            params["a"] = anchor
            params["acct_no"] = anchor

        if regime == "rows":
            hit = _AGGREGATE_RE.search(cypher)
            if hit:
                record["outcome"] = "aggregate_rejected"
                record["violations"] = [f"server_side_aggregate:{hit.group(1).lower()}"]
                msg = (f"REJECTED — `{hit.group(1)}(` is an aggregate and this task requires "
                       f"you to compute the answer from the rows yourself. Re-emit the query "
                       f"so it returns the underlying rows, and page through them if there "
                       f"are more than {row_cap}.")
                record["chars"] = len(msg)
                return msg

        if guardrail_fn is not None:
            violations = guardrail_fn(cypher, params)
            if violations:
                record["outcome"] = "guardrail_rejected"
                record["violations"] = violations
                metrics.add("seocho.text2cypher.validation_failure.count", 1,
                            {"reason": violations[0].split(":")[0]})
                msg = ("REJECTED — the query violates the graph schema and was not executed: "
                       + ", ".join(violations)
                       + ". Rewrite it using only the declared labels, relationship types "
                         "and the supplied parameters.")
                record["chars"] = len(msg)
                return msg

        t0 = time.perf_counter()
        with driver.session(database=database) as session:
            tx = session.begin_transaction(timeout=TX_TIMEOUT_S)
            try:
                result = tx.run("PROFILE " + cypher, **params)
                rows = [dict(r) for _, r in zip(range(row_cap), result)]
                summary = result.consume()
                tx.commit()
            except Neo4jError as exc:
                tx.close()
                record["outcome"] = ("timeout" if "Transaction" in (exc.code or "")
                                     and "terminat" in str(exc).lower() else "db_error")
                record["error"] = exc.code
                record["ms"] = (time.perf_counter() - t0) * 1000
                metrics.record("seocho.retrieval.duration", record["ms"] / 1000,
                               {"source": "dozerdb", "outcome": record["outcome"]})
                msg = f"ERROR — {exc.code}: {str(exc)[:220]}"
                record["chars"] = len(msg)
                return msg
            except Exception as exc:
                tx.close()
                record["outcome"] = "timeout"
                record["error"] = type(exc).__name__
                record["ms"] = (time.perf_counter() - t0) * 1000
                metrics.record("seocho.retrieval.duration", record["ms"] / 1000,
                               {"source": "dozerdb", "outcome": "timeout"})
                msg = (f"ERROR — the query was stopped after {TX_TIMEOUT_S:.0f}s: "
                       f"{type(exc).__name__}")
                record["chars"] = len(msg)
                return msg

        record["ms"] = (time.perf_counter() - t0) * 1000
        record["db_hits"] = _db_hits(summary.profile)
        record["rows"] = len(rows)
        more = len(rows) >= row_cap
        record["truncated"] = more
        metrics.record("seocho.retrieval.duration", record["ms"] / 1000,
                       {"source": "dozerdb", "outcome": "success"})

        if stack.encoding == "csv" or stack.disclosure:
            # The engineered path: SEOCHO's canonical rows->context serializer. JSON carries
            # {rows, row_count, truncated, row_cap}; CSV the same fields with keys paid once.
            payload = encode_rows(rows, row_cap=row_cap, truncated=more,
                                  row_format=stack.encoding)
        else:
            # The naive path: the ad-hoc dump every first integration writes. The cap is
            # applied and never mentioned — the silence is the point being measured.
            payload = json.dumps({"rows": rows, "row_count": len(rows)}, default=str)
        record["chars"] = len(payload)
        return payload

    return run_cypher


def _db_hits(plan: Any) -> int:
    if plan is None:
        return 0
    total = int((plan.get("args") or {}).get("DbHits", 0)) if isinstance(plan, dict) else \
        int((getattr(plan, "arguments", None) or {}).get("DbHits", 0))
    children = plan.get("children", []) if isinstance(plan, dict) else \
        getattr(plan, "children", []) or []
    return total + sum(_db_hits(c) for c in children)


# --------------------------------------------------------------------------------------
# Scoring — ported verbatim from AIsummit26 agent_interaction.py
# --------------------------------------------------------------------------------------
_ANSWER_RE = re.compile(r"ANSWER:\s*(.+)\s*$", re.S | re.I)
# The rows regime moves the arithmetic out of the database and into the model; a query
# that aggregates server-side defeats the measurement, so it is enforced, not requested.
_AGGREGATE_RE = re.compile(
    r"\b(count|sum|avg|min|max|collect|percentile\w*|stdev\w*)\s*\(", re.I)
_DISCLOSURE_RE = re.compile(
    r"\b(truncat\w*|incomplete|partial(?:ly)?|not (?:all|every|complete)|only (?:the )?first"
    r"|more (?:rows|records|results) (?:are |were )?(?:available|exist)|capp?ed"
    r"|row cap|limited to|cannot see all|did not see all|may be missing|under[- ]?count\w*"
    r"|lower bound|at least|insufficient (?:data|rows|information)"
    r"|cannot (?:reliably|accurately|fully)|unable to (?:rank|determine|compute|count)"
    r"|not (?:enough|sufficient) (?:rows|data)|beyond the (?:retrieved|returned))\b", re.I)


def discloses_truncation(final_text: str, answer: Any = None) -> bool:
    haystack = [_ANSWER_RE.sub("", final_text or "")]

    def strings(obj):
        if isinstance(obj, str):
            haystack.append(obj)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                haystack.append(str(k))
                strings(v)
        elif isinstance(obj, list):
            for v in obj:
                strings(v)

    strings(answer)
    return any(_DISCLOSURE_RE.search(h) for h in haystack)


def parse_answer(text: str) -> Tuple[Optional[Any], str]:
    m = _ANSWER_RE.search(text or "")
    raw = m.group(1).strip() if m else (text or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        i = raw.find(opener)
        if i < 0:
            continue
        depth = 0
        for j in range(i, len(raw)):
            if raw[j] == opener:
                depth += 1
            elif raw[j] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[i:j + 1]), "parsed"
                    except ValueError:
                        break
    if re.fullmatch(r"[-+]?[\d,]+(?:\.\d+)?", raw):
        try:
            return json.loads(raw.replace(",", "")), "parsed_bare"
        except ValueError:
            pass
    return None, "unparseable"


def _numbers(obj: Any) -> List[float]:
    out: List[float] = []
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append(float(obj))
    elif isinstance(obj, str):
        try:
            out.append(float(obj.replace(",", "").replace("₩", "").strip()))
        except ValueError:
            pass
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _numbers(v)
    return out


def _flatten_scalars(obj: Any) -> List[Any]:
    if isinstance(obj, dict):
        out: List[Any] = []
        for v in obj.values():
            out += _flatten_scalars(v)
        return out
    if isinstance(obj, list):
        out = []
        for v in obj:
            out += _flatten_scalars(v)
        return out
    return [obj]


def score(question: Dict[str, Any], gold_rows: List[Dict[str, Any]],
          answer: Any) -> Dict[str, Any]:
    if answer is None:
        return {"correct": False, "f1": 0.0, "note": "unparseable"}
    if question["shape"] == "scalar":
        gold = gold_rows[0] if gold_rows else {}
        found = _numbers(answer)
        hits = 0
        for key in question["keys"]:
            want = gold.get(key)
            if want is None:
                hits += 1
                continue
            want_f = float(want)
            tol = max(abs(want_f) * 0.001, 0.5)
            if any(abs(f - want_f) <= tol for f in found):
                hits += 1
        n = len(question["keys"])
        return {"correct": hits == n, "f1": hits / n if n else 0.0,
                "gold": gold, "matched_keys": hits}
    col = question["column"]
    gold_set = {str(r[col]) for r in gold_rows if r.get(col) is not None}
    got = {str(v) for v in _flatten_scalars(answer) if v is not None}
    if not gold_set:
        return {"correct": not got, "f1": 1.0 if not got else 0.0, "gold": []}
    tp = len(gold_set & got)
    prec = tp / len(got) if got else 0.0
    rec = tp / len(gold_set)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"correct": rec == 1.0, "f1": round(f1, 4), "recall": round(rec, 4),
            "precision": round(prec, 4), "gold": sorted(gold_set)}


# --------------------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------------------
def mara_model(model: str):
    from agents import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["MARA_API_KEY"],
                         base_url=os.getenv("MARA_BASE_URL",
                                            "https://api.cloud.mara.com/v1"))
    return OpenAIChatCompletionsModel(model=model, openai_client=client)


async def run_episode(*, driver, database: str, sf: int, stack: Stack,
                      question: Dict[str, Any], anchor: Optional[int],
                      gold_rows: List[Dict[str, Any]], schema: Dict[str, Any],
                      guardrail_fn, encode_rows, metrics, model_name: str,
                      repeat: int, max_tokens: Optional[int],
                      row_cap: int = DEFAULT_ROW_CAP, regime: str = "agg",
                      max_turns: int = MAX_TURNS) -> Dict[str, Any]:
    calls: List[Dict[str, Any]] = []
    tool = make_tool(driver, database, stack=stack, anchor=anchor, calls=calls,
                     guardrail_fn=guardrail_fn if stack.enforcement == "guardrail" else None,
                     encode_rows=encode_rows, metrics=metrics, row_cap=row_cap,
                     regime=regime)
    agent = Agent(
        name=f"analyst_{stack.name}",
        instructions=build_instructions(schema, stack, row_cap, regime=regime),
        model=mara_model(model_name),
        model_settings=ModelSettings(temperature=0.0, max_tokens=max_tokens),
        tools=[tool],
    )
    prompt = question["question"].format(a=anchor)
    t0 = time.perf_counter()
    final_text, err = "", None
    usage_in = usage_out = 0
    nudged = False
    try:
        result = await Runner.run(agent, prompt, max_turns=max_turns)
        final_text = str(result.final_output or "")
        usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        if usage is not None:
            usage_in, usage_out = usage.input_tokens, usage.output_tokens
        if not final_text.strip():
            # gpt-oss can spend its whole closing turn in the reasoning channel; one
            # recorded nudge, same for every stack (see AIsummit26).
            nudged = True
            follow_up = result.to_input_list() + [{
                "role": "user",
                "content": ("Reply now with your final answer, ending with the "
                            "ANSWER: <json> line."),
            }]
            result = await Runner.run(agent, follow_up, max_turns=2)
            final_text = str(result.final_output or "")
            usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
            if usage is not None:
                usage_in += usage.input_tokens
                usage_out += usage.output_tokens
    except MaxTurnsExceeded:
        err = "max_turns_exceeded"
    except Exception as exc:
        err = f"{type(exc).__name__}: {str(exc)[:200]}"
    wall_ms = (time.perf_counter() - t0) * 1000

    answer, parse_note = parse_answer(final_text)
    verdict = score(question, gold_rows, answer) if err is None else {
        "correct": False, "f1": 0.0, "note": err}
    metrics.record("seocho.agent.request.duration", wall_ms / 1000,
                   {"operation": "episode", "outcome": "ok" if err is None else "error"})
    metrics.add("seocho.agent.request.count", 1,
                {"operation": "episode", "outcome": "ok" if err is None else "error"})

    db_ms = sum(c["ms"] for c in calls)
    return {
        "sf": sf, "database": database, "stack": stack.name,
        "stack_config": stack.describe(),
        "question_id": question["id"], "repeat": repeat, "row_cap": row_cap,
        "regime": regime, "max_turns": max_turns,
        "audience": question["audience"], "difficulty": question["difficulty"],
        "anchor": anchor,
        "round_trips": len(calls),
        "db_hits": sum(c["db_hits"] for c in calls),
        "rows_into_context": sum(c["rows"] for c in calls),
        "chars_into_context": sum(c["chars"] for c in calls),
        "db_ms": round(db_ms, 1),
        "model_ms": round(max(wall_ms - db_ms, 0.0), 1),
        "wall_ms": round(wall_ms, 1),
        "input_tokens": usage_in, "output_tokens": usage_out,
        "guardrail_rejections": sum(1 for c in calls
                                    if c["outcome"] == "guardrail_rejected"),
        "aggregate_rejections": sum(1 for c in calls
                                    if c["outcome"] == "aggregate_rejected"),
        "db_errors": sum(1 for c in calls if c["outcome"] in ("db_error", "syntax_error")),
        "timeouts": sum(1 for c in calls if c["outcome"] == "timeout"),
        "violations": [v for c in calls for v in (c.get("violations") or [])],
        "parse": parse_note, "error": err, "nudged": nudged,
        "hit_row_cap": any(c.get("truncated") for c in calls),
        "disclosed_truncation": discloses_truncation(final_text, answer),
        "silent_truncation_failure": bool(
            err is None and answer is not None
            and any(c.get("truncated") for c in calls)
            and not verdict.get("correct")
            and not discloses_truncation(final_text, answer)),
        **{f"score_{k}": v for k, v in verdict.items()},
        "calls": [{k: v for k, v in c.items() if k != "cypher"}
                  | {"cypher": c["cypher"][:600]} for c in calls],
        "final_output": final_text[-1200:],
    }


async def main_async(args) -> None:
    from seocho.integrations.openai_agents import encode_rows
    from seocho.metrics import enable_metrics
    from seocho.ontology import Ontology
    from seocho.query.hybrid_planner import policy_from_ontology, schema_for_prompt
    from seocho.query.workload_compiler import validate_text2cypher_fallback

    metrics = enable_metrics()  # SEOCHO_METRICS_BACKEND=otlp + endpoint to export

    ontology = Ontology.from_dict(
        yaml.safe_load((REPO / "ontology/finbench.ontology.yaml").read_text()))
    policy = policy_from_ontology(ontology)
    schemas = {"ontology": schema_for_prompt(ontology, policy),
               "labels": labels_only_schema(ontology)}

    if args.regime == "rows":
        # The rows regime needs the AIsummit26 feasibility ladder (SF1 pageable in 4 pages,
        # SF100 not), so the cap is 200 — set by amending the contract, not bypassing it:
        # the guardrail validates against the same policy the harness pages with.
        policy = dataclasses.replace(policy, max_result_rows=200)
    row_cap = policy.max_result_rows  # one number, owned by the contract
    max_turns = 16 if args.regime == "rows" else MAX_TURNS

    def guardrail_fn(cypher: str, params: Dict[str, Any]) -> List[str]:
        return list(validate_text2cypher_fallback(cypher, params=params, policy=policy))

    stacks: List[Stack] = []
    for name in args.stacks:
        if name in PRESETS:
            stacks.append(PRESETS[name])
        else:
            raise SystemExit(f"unknown stack preset {name!r} (have {sorted(PRESETS)})")
    if args.schema or args.encoding or args.disclosure is not None or args.enforcement:
        stacks.append(Stack(
            "custom",
            schema=args.schema or "labels",
            encoding=args.encoding or "json",
            disclosure=bool(args.disclosure),
            enforcement=args.enforcement or "none"))

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    questions = ([q for q in QUESTIONS if q["id"] in set(args.only)] if args.only
                 else QUESTIONS)

    context: Dict[str, Dict[str, Any]] = {}
    for spec in args.databases:
        db, _, sf = spec.partition(":")
        with driver.session(database=db) as s:
            p99 = s.run("MATCH (a:Account) RETURN percentileDisc(a._out_degree,0.99) AS p"
                        ).single()["p"]
            anchor = s.run("MATCH (a:Account) WHERE a._out_degree>=$p "
                           "RETURN min(a.acct_no) AS a", p=p99).single()["a"]
            gold: Dict[str, List[Dict[str, Any]]] = {}
            for q in questions:
                tx = s.begin_transaction(timeout=120.0)
                try:
                    gold[q["id"]] = [dict(r) for r in tx.run(q["ref"], a=anchor, ws=WS)]
                    tx.commit()
                except Exception:
                    tx.close()
                    gold[q["id"]] = []
        context[db] = {"sf": int(sf or 1), "anchor": anchor, "gold": gold}
        print(f"[gold] {db} anchor={anchor} "
              f"empty={[k for k, v in gold.items() if not v]}", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    results: List[Dict[str, Any]] = []

    async def one(db: str, stack: Stack, q: Dict[str, Any], rep: int) -> None:
        ctx = context[db]
        async with sem:
            r = await run_episode(
                driver=driver, database=db, sf=ctx["sf"], stack=stack, question=q,
                anchor=ctx["anchor"] if q["audience"] == "external" else None,
                gold_rows=ctx["gold"][q["id"]], schema=schemas[stack.schema],
                guardrail_fn=guardrail_fn, encode_rows=encode_rows, metrics=metrics,
                model_name=args.model, repeat=rep, max_tokens=args.max_tokens,
                row_cap=row_cap, regime=args.regime, max_turns=max_turns)
        results.append(r)
        print(f"  {db:12s} {stack.name:10s} {q['id']:11s} r{rep} "
              f"trips={r['round_trips']} ok={r['score_correct']} "
              f"gr={r['guardrail_rejections']} cap={r['hit_row_cap']} "
              f"disc={r['disclosed_truncation']} {r['wall_ms']:.0f}ms", flush=True)

    jobs = [one(db, stack, q, rep) for db in context for stack in stacks
            for q in questions for rep in range(args.repeats)]
    print(f"\n[run] {len(jobs)} episodes, concurrency {args.concurrency}\n", flush=True)
    await asyncio.gather(*jobs)
    driver.close()

    out = {
        "schema_version": "aiengineerny26.before-after.v1",
        "manifest": manifest(model=args.model, stacks=[s.describe() for s in stacks],
                             row_cap=row_cap, max_turns=max_turns, repeats=args.repeats,
                             regime=args.regime, concurrency=args.concurrency,
                             purpose="before/after the agent<->KB interface engineering"),
        "questions": [{k: q[k] for k in ("id", "audience", "difficulty", "ko", "question",
                                         "shape")} for q in questions],
        "episodes": sorted(results, key=lambda r: (r["sf"], r["stack"], r["question_id"],
                                                   r["repeat"])),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {args.out}  ({len(results)} episodes)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--databases", nargs="+", default=["finbenchl1:1"],
                   help="db:scale_factor specs")
    p.add_argument("--stacks", nargs="+", default=["naive", "engineered"])
    p.add_argument("--schema", choices=["labels", "ontology"])
    p.add_argument("--encoding", choices=["json", "csv"])
    p.add_argument("--disclosure", action="store_true", default=None)
    p.add_argument("--enforcement", choices=["none", "guardrail"])
    p.add_argument("--regime", choices=["agg", "rows"], default="agg",
                   help="rows: aggregates banned, answer computed from paged rows")
    p.add_argument("--model", default="gpt-oss-120b")
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--only", nargs="+", default=None)
    p.add_argument("--uri", default="bolt://127.0.0.1:7687")
    p.add_argument("--user", default="neo4j")
    p.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", "neo4jpassword"))
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p.add_argument("--out", default=str(REPO / f"results/before_after_{ts}.json"))
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
