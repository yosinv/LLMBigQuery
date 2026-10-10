# LLMBigQuery

**Natural-language questions → generated SQL → Google BigQuery → natural-language answers.**

An exploratory Python project demonstrating how a language model can translate analytics questions into SQL, query BigQuery, and return a readable answer. The current implementation is a **proof of concept**, not a production-ready query service.

## Architecture

```text
User question
    ↓
LangChain SQLDatabaseChain + LLM
    ↓
SQLAlchemy / BigQuery dialect
    ↓
Google BigQuery
    ↓
Query result → language-model answer
```

## Tech stack

- Python, LangChain (legacy API), OpenAI LLM
- Google Cloud BigQuery and service-account authentication
- SQLAlchemy, BigQuery SQLAlchemy dialect, python-dotenv

## Run the existing proof of concept

1. Create a Python virtual environment.
2. Install compatible versions of the libraries imported by `bigquerOpenAi.py`. The script uses **legacy LangChain interfaces**, so recent releases may require code migration.
3. Provision a BigQuery dataset and a service account with **read-only** access to the specific dataset.
4. Store the service-account JSON file **outside** the repository.
5. Update the example placeholders for `key_path`, `dotenv_path`, table and question in `bigquerOpenAi.py`, or refactor them into environment variables.
6. Run `python bigquerOpenAi.py` only after reviewing the SQL and credentials configuration.

> ⚠️ This demo executes LLM-generated SQL. Do **not** grant write/admin privileges or run it against sensitive production datasets without SQL allowlisting, cost limits, auditing and human approval.

## Example interaction (illustrative, not an executed test)

**Question:** “How many orders were placed last month?”

**Intended flow:** Generate a scoped `SELECT COUNT(*)` query against an orders table, execute it in BigQuery and summarize the returned count. Actual output depends on the configured schema and data.

## Design notes and current limitations

- **Database abstraction:** SQLAlchemy is used to expose BigQuery through LangChain's SQL utilities.
- **Credentials:** The prototype currently contains a placeholder for a local JSON key. Prefer workload identity or environment-based credentials for a production implementation.
- **Compatibility:** The original proof of concept documents LangChain/SQLAlchemy compiler compatibility difficulties. Those are historical notes, not endorsed installation instructions.
- **Safety:** Generated SQL is not currently validated as read-only.
- **Quality:** There is no automated evaluation suite or reproducible demo dataset yet.

## Portfolio roadmap

- [ ] Replace legacy LangChain APIs with maintained packages
- [ ] Implement configurable read-only SQL policy and query dry-runs
- [ ] Add schema-aware prompt context and sample dataset
- [ ] Add example screenshots and real demo output
- [ ] Add `pyproject.toml`, unit tests and GitHub Actions
- [ ] Add tracing and question-to-SQL evaluation

## Status

Exploratory project from 2023; this README describes the code as it exists rather than claiming production readiness.
