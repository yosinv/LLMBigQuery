"""Execution-accuracy evaluation: does the agent's query return the same data as a gold query?"""
from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .agent import NL2SQLAgent
from .warehouse import QueryResult, Warehouse


def _norm(v: Any) -> Any:
    if isinstance(v, (float, Decimal)):
        return round(float(v), 4)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, str):
        return v.strip()
    return v


def results_match(pred: QueryResult, gold: QueryResult, ordered: bool = False) -> bool:
    """Compare result *values*, not column names, so aliases don't matter.

    Order matters only when the question asks for it (`ordered: true`).
    """
    p = [tuple(_norm(v) for v in r) for r in pred.rows]
    g = [tuple(_norm(v) for v in r) for r in gold.rows]
    if ordered:
        return p == g
    key = lambda r: tuple((x is None, str(type(x)), str(x)) for x in r)  # noqa: E731
    return sorted(p, key=key) == sorted(g, key=key)


@dataclass
class CaseResult:
    id: str
    question: str
    correct: bool
    attempts: int
    repaired: bool
    latency_s: float
    gb_scanned: float
    predicted_sql: str | None
    error: str | None = None


def load_cases(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text())
    return data["cases"]


def run_eval(agent: NL2SQLAgent, warehouse: Warehouse, cases: list[dict]) -> list[CaseResult]:
    out: list[CaseResult] = []
    for case in cases:
        gold = warehouse.run(case["gold_sql"])
        ans = agent.ask(case["question"], summarize=False)
        correct = ans.result is not None and results_match(ans.result, gold, case.get("ordered", False))
        out.append(CaseResult(
            id=case["id"],
            question=case["question"],
            correct=correct,
            attempts=len(ans.attempts),
            repaired=len(ans.attempts) > 1 and ans.result is not None,
            latency_s=round(ans.latency_s, 2),
            gb_scanned=round((ans.result.bytes_processed if ans.result else 0) / 1e9, 3),
            predicted_sql=ans.sql,
            error=None if ans.result else (ans.attempts[-1].error if ans.attempts else "no attempt"),
        ))
    return out


def summarize(results: list[CaseResult]) -> dict:
    n = len(results) or 1
    return {
        "cases": len(results),
        "execution_accuracy": round(sum(r.correct for r in results) / n, 3),
        "fixed_by_self_repair": sum(r.repaired and r.correct for r in results),
        "failed_to_produce_sql": sum(r.predicted_sql is None for r in results),
        "median_latency_s": round(statistics.median([r.latency_s for r in results]), 2) if results else 0,
        "total_gb_scanned": round(sum(r.gb_scanned for r in results), 3),
    }


def write_report(results: list[CaseResult], model: str, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s = summarize(results)
    with open(out_dir / "results.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")
    lines = [
        f"# Eval report — `{model}`", "",
        "| Metric | Value |", "|---|---|",
        *[f"| {k.replace('_', ' ')} | {v} |" for k, v in s.items()], "",
        "| Case | Correct | Attempts | Latency (s) |", "|---|---|---|---|",
        *[f"| {r.id} | {'✅' if r.correct else '❌'} | {r.attempts} | {r.latency_s} |" for r in results],
    ]
    path = out_dir / "report.md"
    path.write_text("\n".join(lines) + "\n")
    return path
