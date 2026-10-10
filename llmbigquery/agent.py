"""Question -> SQL -> guarded execution -> self-repair -> natural-language answer."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .guard import UnsafeSQL, check_sql
from .warehouse import CostTooHigh, QueryResult, Warehouse

SQL_TOOL = {
    "name": "submit_sql",
    "description": "Submit one BigQuery Standard SQL SELECT query that answers the question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "A single SELECT statement using fully qualified table names."},
        },
        "required": ["sql"],
    },
}

SYSTEM = """You are a careful analytics engineer writing BigQuery Standard SQL.
Rules:
- Use only the tables and columns listed in the schema. Never invent columns.
- Always use fully qualified names: `project.dataset.table`.
- Read-only: a single SELECT (CTEs are fine). Select only the columns you need.
- If a previous attempt failed, read the error and fix the query; don't repeat it."""


def make_client():
    """Anthropic API by default; set LLM_PROVIDER=bedrock to call Claude on AWS Bedrock."""
    if os.getenv("LLM_PROVIDER", "anthropic").lower() == "bedrock":
        from anthropic import AnthropicBedrock

        return AnthropicBedrock()
    from anthropic import Anthropic

    return Anthropic()


@dataclass
class Attempt:
    sql: str
    error: str | None = None


@dataclass
class Answer:
    question: str
    sql: str | None
    result: QueryResult | None
    answer: str
    attempts: list[Attempt] = field(default_factory=list)
    latency_s: float = 0.0


class NL2SQLAgent:
    def __init__(
        self,
        warehouse: Warehouse,
        datasets: list[str],
        llm: Any | None = None,
        model: str | None = None,
        max_repairs: int = 2,
        max_rows: int = 1000,
        log: Callable[[str], None] = lambda _: None,
    ):
        self.wh = warehouse
        self.datasets = {d.lower() for d in datasets}
        self.llm = llm or make_client()
        self.model = model or os.getenv("LLM_MODEL", "claude-sonnet-5-5")
        self.max_repairs = max_repairs
        self.max_rows = max_rows
        self.log = log
        self._schema = "\n".join(self.wh.describe(d) for d in datasets)

    # -- LLM calls -----------------------------------------------------------
    def _generate_sql(self, question: str, attempts: list[Attempt]) -> str:
        messages = [{"role": "user", "content": f"Schema:\n{self._schema}\n\nQuestion: {question}"}]
        for a in attempts:
            messages.append({"role": "assistant", "content": f"Previous attempt:\n```sql\n{a.sql}\n```"})
            messages.append({"role": "user", "content": f"That failed with: {a.error}\nSubmit a corrected query."})
        resp = self.llm.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM,
            tools=[SQL_TOOL],
            tool_choice={"type": "tool", "name": "submit_sql"},
            messages=messages,
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return block.input["sql"]
        raise RuntimeError("model did not return SQL")

    def _summarize(self, question: str, sql: str, result: QueryResult) -> str:
        preview = [result.columns] + [list(r) for r in result.rows[:50]]
        resp = self.llm.messages.create(
            model=self.model,
            max_tokens=600,
            system="Answer the question in 1-3 sentences using only the query result. "
                   "If the result is empty or doesn't answer it, say so plainly.",
            messages=[{"role": "user", "content": f"Question: {question}\nSQL: {sql}\nResult (first rows): {preview}"}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content).strip()

    # -- main loop -----------------------------------------------------------
    def ask(self, question: str, summarize: bool = True) -> Answer:
        start = time.perf_counter()
        attempts: list[Attempt] = []
        for _ in range(self.max_repairs + 1):
            raw = self._generate_sql(question, attempts)
            try:
                sql = check_sql(raw, self.datasets, self.max_rows)
                result = self.wh.run(sql)
            except (UnsafeSQL, CostTooHigh) as e:
                attempts.append(Attempt(raw, f"{type(e).__name__}: {e}"))
                self.log(f"rejected: {e}")
                continue
            except Exception as e:  # BigQuery errors: bad column, type mismatch, ...
                attempts.append(Attempt(raw, str(e)[:500]))
                self.log(f"query error: {e}")
                continue
            attempts.append(Attempt(sql))
            text = self._summarize(question, sql, result) if summarize else ""
            return Answer(question, sql, result, text, attempts, time.perf_counter() - start)

        return Answer(question, None, None, "I couldn't produce a working query for that question.",
                      attempts, time.perf_counter() - start)
