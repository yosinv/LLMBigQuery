# LLMBigQuery

**Ask BigQuery questions in plain English. Claude writes the SQL. Guardrails stop it from doing damage, and an eval harness measures whether its answers are actually right.**

Most text-to-SQL demos stop at "it generated a query." In production the hard parts are what happens next: a hallucinated column, a `DELETE`, a query that scans 5 TB, an answer that *looks* right but isn't. This project is built around those failure modes.

```
question ──► Claude (tool call: submit_sql)
                 │
                 ▼
          SQL guard (sqlglot)        single SELECT only · no DML/DDL anywhere in the tree
                 │                   allow-listed datasets only · LIMIT enforced
                 ▼
          BigQuery dry run           refuse if it would scan more than the budget (free check)
                 │
                 ▼
          execute                    maximum_bytes_billed as a hard server-side cap
                 │
        error? ──┴──► feed the error back to Claude and retry (self-repair, max 2)
                 │
                 ▼
          Claude summarizes the result in 1–3 sentences
```

## Quick start

```bash
pip install -e ".[dev]"
cp .env.example .env              # add ANTHROPIC_API_KEY and GCP_PROJECT
gcloud auth application-default login

python -m llmbigquery ask "What was the most common girl's name in 2010?" \
  --dataset bigquery-public-data.usa_names
```

Prefer AWS? Set `LLM_PROVIDER=bedrock` and the same code calls Claude on Amazon Bedrock with your AWS credentials.

## Evaluation: does it actually get the right answer?

```bash
python -m llmbigquery eval evals/usa_names.yaml
```

Each case in `evals/usa_names.yaml` has a question and a hand-written **gold SQL**. The harness runs both and compares the **returned data**, not the SQL text. Two different queries that produce the same answer both count as correct. Row order only matters when the question asks for it.

The report (`evals/out/report.md`) tracks:

| Metric | Why it matters |
|---|---|
| Execution accuracy | Share of questions answered with the correct data |
| Fixed by self-repair | How often feeding the BigQuery error back to the model rescued a failed query |
| Failed to produce SQL | Questions where every attempt was rejected or errored |
| Median latency | End-to-end response time |
| GB scanned | Cost of the agent's queries |

Swap `LLM_MODEL` and re-run to compare models on the same suite.

## Safety design

- **Read-only by construction.** The SQL is parsed into a syntax tree. Anything other than a single `SELECT` (CTEs and `UNION` allowed) is rejected *before* it reaches BigQuery: string checks miss things like `SELECT 1; DROP TABLE x`, the parser doesn't.
- **Data boundary.** Tables outside the datasets you pass with `--dataset` are rejected, so the model can't wander into other data the credentials can see.
- **Two cost limits.** A free dry run rejects expensive queries up front, and `maximum_bytes_billed` makes BigQuery itself refuse to run past the budget.
- **No key files.** Uses Application Default Credentials instead of a downloaded service-account JSON.

## Tests

```bash
pytest
```

17 offline tests with a fake model and a fake warehouse: guard rules (DML, multi-statement, foreign datasets, limit capping), self-repair with error feedback, unsafe SQL never reaching the warehouse, the cost guard, giving up after max retries, and eval scoring.

## Project layout

```
llmbigquery/
  agent.py      generate → guard → run → repair → summarize
  guard.py      sqlglot-based safety checks
  warehouse.py  BigQuery: schema introspection, dry run, execution
  evaluate.py   execution-accuracy harness and report
  cli.py        `ask` and `eval` commands
evals/usa_names.yaml   12 gold questions on a free public dataset
tests/                 offline unit tests
```

## History

v1 (2023) was a LangChain `SQLDatabaseChain` + OpenAI prototype. v2 is a rewrite focused on what makes text-to-SQL trustworthy: guardrails, cost control, self-repair, and measurement.

---

Yosi Navaro · Data Engineering Manager · [github.com/yosinv](https://github.com/yosinv)
