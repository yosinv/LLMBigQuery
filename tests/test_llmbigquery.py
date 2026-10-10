from types import SimpleNamespace

import pytest

from llmbigquery.agent import NL2SQLAgent
from llmbigquery.evaluate import results_match, run_eval, summarize
from llmbigquery.guard import UnsafeSQL, check_sql
from llmbigquery.warehouse import CostTooHigh, QueryResult

DS = {"bigquery-public-data.usa_names"}
T = "`bigquery-public-data.usa_names.usa_1910_current`"


# ---------------------------------------------------------------- guard ----
def test_allows_select_and_adds_limit():
    out = check_sql(f"SELECT name FROM {T}", DS, max_rows=100)
    assert "LIMIT 100" in out


def test_keeps_smaller_limit_and_caps_bigger_one():
    assert "LIMIT 5" in check_sql(f"SELECT name FROM {T} LIMIT 5", DS, 100)
    assert "LIMIT 100" in check_sql(f"SELECT name FROM {T} LIMIT 999999", DS, 100)


def test_allows_cte_and_union():
    check_sql(f"WITH x AS (SELECT name FROM {T}) SELECT name FROM x", DS)
    check_sql(f"SELECT name FROM {T} UNION ALL SELECT name FROM {T}", DS)


@pytest.mark.parametrize("sql", [
    f"DELETE FROM {T} WHERE true",
    f"DROP TABLE {T}",
    f"INSERT INTO {T} (name) VALUES ('x')",
    f"SELECT 1; DROP TABLE {T}",
    "SELECT * FROM `my-project.secret.salaries`",
    "SELECT FROM WHERE",
])
def test_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeSQL):
        check_sql(sql, DS)


# ------------------------------------------------------------- compare -----
def qr(rows, cols=("a",)):
    return QueryResult(list(cols), rows, 0)


def test_match_ignores_order_and_aliases_unless_ordered():
    assert results_match(qr([(1,), (2,)], ("x",)), qr([(2,), (1,)], ("y",)))
    assert not results_match(qr([(1,), (2,)]), qr([(2,), (1,)]), ordered=True)


def test_match_tolerates_float_noise():
    assert results_match(qr([(0.49999999,)]), qr([(0.5,)]))
    assert not results_match(qr([(0.49,)]), qr([(0.5,)]))


# --------------------------------------------------------------- agent -----
class FakeLLM:
    """Returns queued SQL strings as tool calls, then a fixed summary."""

    def __init__(self, sqls):
        self.sqls = list(sqls)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if kw.get("tools"):
            sql = self.sqls.pop(0)
            return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"sql": sql})])
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Emma was the top name.")])


class FakeWarehouse:
    def __init__(self, fail_first=None):
        self.fail_first = fail_first
        self.ran = []

    def describe(self, dataset):
        return f"`{dataset}.usa_1910_current`(state STRING, gender STRING, year INT64, name STRING, number INT64)"

    def run(self, sql):
        self.ran.append(sql)
        if self.fail_first:
            err, self.fail_first = self.fail_first, None
            raise err
        return QueryResult(["name"], [("Emma",)], 1_000_000)


def agent(llm, wh):
    return NL2SQLAgent(wh, sorted(DS), llm=llm, model="test-model")


def test_happy_path():
    wh = FakeWarehouse()
    ans = agent(FakeLLM([f"SELECT name FROM {T}"]), wh).ask("top name?")
    assert ans.result.rows == [("Emma",)]
    assert ans.answer == "Emma was the top name."
    assert len(ans.attempts) == 1


def test_self_repairs_after_bigquery_error():
    llm = FakeLLM([f"SELECT nme FROM {T}", f"SELECT name FROM {T}"])
    wh = FakeWarehouse(fail_first=RuntimeError("Unrecognized name: nme"))
    ans = agent(llm, wh).ask("top name?")
    assert ans.result is not None and len(ans.attempts) == 2
    # the error was fed back to the model on the retry
    retry_msgs = llm.calls[1]["messages"]
    assert "Unrecognized name: nme" in retry_msgs[-1]["content"]


def test_unsafe_sql_never_reaches_warehouse():
    wh = FakeWarehouse()
    llm = FakeLLM([f"DROP TABLE {T}", f"SELECT name FROM {T}"])
    ans = agent(llm, wh).ask("top name?")
    assert all("DROP" not in s.upper() for s in wh.ran)
    assert ans.result is not None


def test_cost_guard_triggers_repair():
    wh = FakeWarehouse(fail_first=CostTooHigh("query would scan 900 GB"))
    llm = FakeLLM([f"SELECT * FROM {T}", f"SELECT name FROM {T}"])
    assert agent(llm, wh).ask("top name?").result is not None


def test_gives_up_after_max_repairs():
    llm = FakeLLM([f"DROP TABLE {T}"] * 3)
    ans = agent(llm, FakeWarehouse()).ask("x")
    assert ans.sql is None and len(ans.attempts) == 3


def test_eval_harness_scores_cases():
    cases = [
        {"id": "right", "question": "q1", "gold_sql": "gold"},
        {"id": "wrong", "question": "q2", "gold_sql": "gold"},
    ]

    class TwoRunsWH(FakeWarehouse):
        def run(self, sql):
            correct = sql == "gold" or sql.startswith("SELECT name")
            return QueryResult(["n"], [("Emma",)] if correct else [("Olivia",)], 0)

    wh = TwoRunsWH()
    llm = FakeLLM([f"SELECT name FROM {T}", f"SELECT state FROM {T}"])
    results = run_eval(agent(llm, wh), wh, cases)
    s = summarize(results)
    assert [r.correct for r in results] == [True, False]
    assert s["execution_accuracy"] == 0.5
