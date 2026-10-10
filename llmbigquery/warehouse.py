"""Thin BigQuery wrapper: schema introspection, dry-run cost check, execution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class CostTooHigh(RuntimeError):
    """Raised when a dry run says the query would scan more than the budget."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    bytes_processed: int


class Warehouse(Protocol):
    def describe(self, dataset: str) -> str: ...
    def run(self, sql: str) -> QueryResult: ...


class BigQueryWarehouse:
    """Real BigQuery backend. Uses Application Default Credentials (no key files)."""

    def __init__(self, project: str | None = None, max_bytes: int = 2 * 1024**3, max_columns: int = 60):
        from google.cloud import bigquery  # imported lazily so tests don't need it

        self._bq = bigquery
        self.client = bigquery.Client(project=project)
        self.max_bytes = max_bytes
        self.max_columns = max_columns

    def describe(self, dataset: str) -> str:
        """Compact `table(col TYPE, ...)` lines for every table in `project.dataset`."""
        project, ds = dataset.split(".", 1)
        sql = f"""
            SELECT table_name, column_name, data_type
            FROM `{project}.{ds}.INFORMATION_SCHEMA.COLUMNS`
            ORDER BY table_name, ordinal_position
        """
        tables: dict[str, list[str]] = {}
        for row in self.client.query(sql).result():
            cols = tables.setdefault(row.table_name, [])
            if len(cols) < self.max_columns:
                cols.append(f"{row.column_name} {row.data_type}")
        return "\n".join(f"`{dataset}.{t}`({', '.join(c)})" for t, c in tables.items())

    def run(self, sql: str) -> QueryResult:
        # 1. Dry run: BigQuery reports the bytes it *would* scan, for free.
        dry = self.client.query(sql, job_config=self._bq.QueryJobConfig(dry_run=True, use_query_cache=False))
        if dry.total_bytes_processed > self.max_bytes:
            raise CostTooHigh(
                f"query would scan {dry.total_bytes_processed / 1e9:.2f} GB, "
                f"budget is {self.max_bytes / 1e9:.2f} GB"
            )
        # 2. Real run, with a hard server-side cap as a second line of defence.
        job = self.client.query(sql, job_config=self._bq.QueryJobConfig(maximum_bytes_billed=self.max_bytes))
        result = job.result()
        columns = [f.name for f in result.schema]
        rows = [tuple(r.values()) for r in result]
        return QueryResult(columns, rows, job.total_bytes_processed or 0)
