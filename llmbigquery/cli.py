"""Command line: `python -m llmbigquery ask "..."` or `python -m llmbigquery eval evals/usa_names.yaml`."""
from __future__ import annotations

import argparse
import os
import sys

import yaml
from dotenv import load_dotenv

from .agent import NL2SQLAgent
from .evaluate import load_cases, run_eval, summarize, write_report
from .warehouse import BigQueryWarehouse


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="llmbigquery", description="Ask BigQuery questions in plain English.")
    parser.add_argument("--project", default=os.getenv("GCP_PROJECT"), help="GCP project that pays for queries")
    parser.add_argument("--max-gb", type=float, default=float(os.getenv("MAX_GB_PER_QUERY", "2")),
                        help="refuse any query that would scan more than this (dry-run checked)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="answer one question")
    ask.add_argument("question")
    ask.add_argument("--dataset", action="append", required=True, help="project.dataset the agent may query")

    ev = sub.add_parser("eval", help="run an eval suite and write a report")
    ev.add_argument("suite", help="YAML file with gold questions")
    ev.add_argument("--out", default="evals/out")

    args = parser.parse_args(argv)
    wh = BigQueryWarehouse(project=args.project, max_bytes=int(args.max_gb * 1024**3))

    if args.cmd == "ask":
        agent = NL2SQLAgent(wh, args.dataset, log=lambda m: print(f"  · {m}", file=sys.stderr))
        ans = agent.ask(args.question)
        print(f"\nSQL:\n{ans.sql}\n\nAnswer: {ans.answer}")
        print(f"\n({len(ans.attempts)} attempt(s), {ans.latency_s:.1f}s)", file=sys.stderr)
        return 0 if ans.sql else 1

    suite = yaml.safe_load(open(args.suite))
    agent = NL2SQLAgent(wh, [suite["dataset"]])
    results = run_eval(agent, wh, load_cases(args.suite))
    report = write_report(results, agent.model, args.out)
    print(summarize(results))
    print(f"report: {report}")
    return 0
