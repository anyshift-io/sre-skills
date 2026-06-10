"""
Ablation eval for the sqs-queue-auditor skill.

For each fixture, runs N trials in two conditions:
- Control: the agent is given the raw GetQueueAttributes JSON and a generic "audit this
  SQS queue" prompt. It uses whatever it brings from training.
- Treatment: the agent is given the same JSON plus SKILL.md as the methodology to follow.

Each agent output is graded against the 7-item rubric (rubric.md) by an LLM judge, anchored
to the deterministic reference audit (_audit.py) as ground truth.

Final report: per-fixture mean score (control vs treatment), lift (= treatment - control),
stdev across trials, and a verdict.

Requirements:
- ANTHROPIC_API_KEY environment variable.
- `pip install anthropic` (the only non-stdlib dependency in the repo; isolated to tests/eval/).

Usage:
    python tests/eval/run_eval.py --trials 5
    python tests/eval/run_eval.py --trials 1 --fixtures 02,04,08   # smoke test

Resumable: every (fixture, condition, trial) cell is written to --output the moment it
completes, and on start the runner loads whatever is already in --output and skips the
cells it finds. A crash, a rate-limit, or a Ctrl-C loses at most the one in-flight cell;
re-run the exact same command and it fills only the gaps. Use --force to ignore existing
results and re-run every cell. A cell whose agent or judge call raises is simply not
recorded, so it is retried on the next run.

Cost note: 8 fixtures x 2 conditions x 5 trials, plus a judge call per output, is
~80 agent calls + ~80 judge calls = ~160 LLM calls. Expect $10-30 depending on model
(Sonnet recommended for cost; Opus for highest agent quality).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from queues import QUEUES, load_fixture_text, expected_audit  # noqa: E402

REPO_SKILL_MD = Path(__file__).resolve().parent.parent.parent / "SKILL.md"

DEFAULT_AGENT_MODEL = os.environ.get("EVAL_AGENT_MODEL", "claude-sonnet-4-6")
DEFAULT_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096


def build_control_prompt(queue: dict) -> str:
    return f"""You are an SRE reviewing an AWS SQS queue configuration for misconfigurations.

Queue: {queue['queue']}
Role: {queue['role']}

Here is the full configuration, exactly as returned by the SQS API:

{load_fixture_text(queue)}

Audit this queue. Identify any misconfiguration that could drop, duplicate, or lose messages, or expose the queue. For each, give the severity and the fix. Be specific."""


def build_treatment_prompt(queue: dict, skill_md_text: str) -> str:
    return f"""You are an SRE auditing an AWS SQS queue, following the methodology below exactly.

METHODOLOGY (SKILL.md):

{skill_md_text}

QUEUE CONTEXT:

Queue: {queue['queue']}
Role: {queue['role']}

CONFIGURATION (GetQueueAttributes output):

{load_fixture_text(queue)}

Apply the methodology end-to-end. Produce the structured output the methodology's "Output format" section prescribes (queue, findings ranked by severity, boundary)."""


JUDGE_SYSTEM = """You are an expert AWS / SRE evaluator grading an SQS queue audit against a 7-item rubric. Each item is binary: 1 (pass) or 0 (fail). Be strict but fair; no partial credit.

You will be given a known-good answer from a deterministic reference audit, the agent's audit output, and the 7 rubric items.

Return JSON only (no prose), with this exact schema:

{
  "scores": [<int>, <int>, <int>, <int>, <int>, <int>, <int>],
  "notes": ["<one sentence>", ...]
}"""


def build_judge_prompt(queue: dict, agent_output: str) -> str:
    exp = expected_audit(queue)
    return f"""QUEUE: {queue['id']}
NAME: {queue['queue']}

KNOWN-GOOD ANSWER (from the deterministic reference audit):
- Findings (ground truth): {exp['codes']}  (severity: {exp['top_severity']}; clean: {exp['clean']})
- What the defect is: {queue['expected_headline']}
- Correct top fix: {queue['expected_top_fix']}
- Boundary the audit cannot cross: {queue['expected_boundary_join']}

AGENT AUDIT OUTPUT:
{agent_output}

RUBRIC (score each 1 = pass, 0 = fail):
1. Parse: parses the embedded RedrivePolicy and string-typed seconds correctly.
2. Findings: identifies the ground-truth defect(s) by substance (or correctly reports none for the clean control).
3. No false positives: does not assert a material misconfiguration the ground truth lacks (esp. not calling an aws:SourceArn-scoped wildcard "public").
4. Criticality: ranks silent-message-loss defects as most serious; does not headline a soft flag.
5. Boundary: names at least one thing it cannot determine from config alone, matching the ground-truth join.
6. Honesty on soft flags: presents flags that depend on consumers/data/producers as flags to verify, not confirmed bugs.
7. Recommendation: top fix matches the ground-truth fix in substance.

Return JSON only."""


def cell_key(result: dict) -> tuple[str, str, int]:
    """Identity of one (fixture, condition, trial) cell, used to skip completed work."""
    return (result["queue"], result["condition"], result["trial"])


def load_existing(path: Path) -> list[dict]:
    """Load prior results from a previous (possibly crashed) run; empty list if none/corrupt."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        print(f"  WARN: could not read existing {path}, starting fresh", file=sys.stderr)
        return []


def write_results(path: Path, results: list[dict]) -> None:
    """Atomically rewrite the results file (temp + rename) so a crash never truncates it."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(results, indent=2))
    tmp.replace(path)


def run_agent(client: Anthropic, model: str, prompt: str) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def run_judge(client: Anthropic, model: str, queue: dict, agent_output: str) -> dict:
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": build_judge_prompt(queue, agent_output)}],
    )
    raw = "".join(block.text for block in resp.content if block.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=5, help="Trials per (fixture, condition) cell")
    parser.add_argument("--fixtures", default="", help="Comma-separated fixture IDs (prefix match); empty = all")
    parser.add_argument("--agent-model", default=DEFAULT_AGENT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--output", default="eval_results.json", help="Where to write the raw results")
    parser.add_argument("--force", action="store_true", help="Ignore existing results in --output and re-run every cell")
    args = parser.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = Anthropic()
    skill_md_text = REPO_SKILL_MD.read_text()

    to_run = QUEUES
    if args.fixtures:
        filters = [f.strip() for f in args.fixtures.split(",")]
        to_run = [q for q in QUEUES if any(q["id"].startswith(f) for f in filters)]

    output_path = Path(args.output)
    results = [] if args.force else load_existing(output_path)
    done = {cell_key(r) for r in results}

    # The full grid of cells this invocation is responsible for.
    planned = [
        (queue, condition, trial)
        for queue in to_run
        for condition in ("control", "treatment")
        for trial in range(args.trials)
    ]
    remaining = [cell for cell in planned if (cell[0]["id"], cell[1], cell[2]) not in done]

    print(f"Grid: {len(to_run)} fixtures x 2 conditions x {args.trials} trials = {len(planned)} cells")
    if done and not args.force:
        print(f"Resuming: {len(planned) - len(remaining)} cell(s) already in {output_path.name}, {len(remaining)} to run")
    print(f"Agent model: {args.agent_model}, Judge model: {args.judge_model}\n")

    for queue, condition, trial in remaining:
        t_start = time.time()
        prompt = build_control_prompt(queue) if condition == "control" else build_treatment_prompt(queue, skill_md_text)
        try:
            agent_output = run_agent(client, args.agent_model, prompt)
            judge_result = run_judge(client, args.judge_model, queue, agent_output)
            score = sum(judge_result["scores"])
        except Exception as e:
            print(f"  ERROR on {queue['id']} {condition} trial {trial}: {e} (will retry on next run)", file=sys.stderr)
            continue
        elapsed = time.time() - t_start
        results.append({
            "queue": queue["id"],
            "condition": condition,
            "trial": trial,
            "score": score,
            "scores_by_item": judge_result["scores"],
            "notes": judge_result.get("notes", []),
            "agent_output": agent_output,
            "elapsed_s": round(elapsed, 1),
        })
        # Persist after every cell so a crash loses at most this one.
        write_results(output_path, results)
        print(f"  {queue['id']:<40} | {condition:9s} | trial {trial} | score {score}/7 | {elapsed:.0f}s")

    print(f"\nRaw results: {output_path}\n")
    print_summary(results, to_run)
    return 0


def print_summary(results: list[dict], to_run: list[dict]) -> None:
    by_cell: dict[tuple[str, str], list[int]] = {}
    for r in results:
        by_cell.setdefault((r["queue"], r["condition"]), []).append(r["score"])

    print(f"{'Fixture':<40} {'Control mean':>14} {'Treatment mean':>16} {'Lift':>8} {'C-std':>7} {'T-std':>7}")
    print("-" * 94)
    lifts = []
    for queue in to_run:
        control = by_cell.get((queue["id"], "control"), [])
        treatment = by_cell.get((queue["id"], "treatment"), [])
        if not control or not treatment:
            continue
        c_mean, t_mean = statistics.mean(control), statistics.mean(treatment)
        lift = t_mean - c_mean
        lifts.append(lift)
        c_std = statistics.stdev(control) if len(control) > 1 else 0.0
        t_std = statistics.stdev(treatment) if len(treatment) > 1 else 0.0
        print(f"{queue['id']:<40} {c_mean:>14.2f} {t_mean:>16.2f} {lift:>+8.2f} {c_std:>7.2f} {t_std:>7.2f}")
    print("-" * 94)
    if lifts:
        aggregate = statistics.mean(lifts)
        positive = sum(1 for l in lifts if l > 0)
        zero = sum(1 for l in lifts if l == 0)
        negative = sum(1 for l in lifts if l < 0)
        print(f"\nAggregate lift: {aggregate:+.2f}/7 across {len(lifts)} fixtures")
        print(f"  Positive lift: {positive}, Zero: {zero}, Negative: {negative}")
        verdict = (
            "Skill is clearly valuable" if aggregate >= 1.0 and positive >= 2 * negative
            else "Skill provides marginal lift" if aggregate >= 0.3
            else "Skill is not clearly adding value; investigate why before shipping"
        )
        print(f"  Verdict: {verdict}")


if __name__ == "__main__":
    sys.exit(main())
