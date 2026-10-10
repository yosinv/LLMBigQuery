"""Static safety checks on model-generated SQL, before anything touches BigQuery."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop,
    exp.Alter, exp.Command, exp.TruncateTable, exp.Grant,
)


class UnsafeSQL(ValueError):
    """Raised when generated SQL is not a single read-only query."""


def check_sql(sql: str, allowed_datasets: set[str], max_rows: int = 1000) -> str:
    """Return a safe, row-limited version of `sql` or raise UnsafeSQL.

    Rules:
      * exactly one statement, and it must be a SELECT (CTEs and UNIONs allowed)
      * no DML / DDL anywhere in the tree
      * every table must live in an allowed `project.dataset`
      * a LIMIT is enforced so a bad query can't stream millions of rows back
    """
    try:
        statements = sqlglot.parse(sql, read="bigquery")
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"could not parse SQL: {e}") from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise UnsafeSQL(f"expected exactly one statement, got {len(statements)}")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union, exp.Except, exp.Intersect)):
        raise UnsafeSQL(f"only SELECT queries are allowed, got {tree.key.upper()}")
    if any(tree.find_all(*FORBIDDEN)):
        raise UnsafeSQL("query contains a data-modifying statement")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not table.db and table.name.lower() in cte_names:
            continue
        dataset = ".".join(p for p in (table.catalog, table.db) if p).lower()
        if dataset not in allowed_datasets:
            raise UnsafeSQL(f"table `{table.sql(dialect='bigquery')}` is outside the allowed datasets")

    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name)
        except (AttributeError, ValueError):
            current = None
    if current is None or current > max_rows:
        tree = tree.limit(max_rows, copy=True)

    return tree.sql(dialect="bigquery")
