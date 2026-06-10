"""
Ablation eval for the iam-policy-auditor skill.

For each fixture, runs N trials in two conditions:
- Control: the agent is given the raw IAM policy JSON and a generic "audit this policy" prompt.
  It uses whatever it brings from training.
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
    python tests/eval/run_eval.py --trials 1 --fixtures 02,07,11   # smoke test
    python tests/eval/run_eval.py --trials 5 --fresh               # ignore prior results

Resume: each completed trial is persisted immediately (atomic temp+rename), and a re-run
reloads what is already on disk and fills only the missing (fixture, condition, trial)
cells. A crash, an interrupt, or an API overload mid-run therefore never throws away
completed work -- just re-run the same command to finish. Pass --fresh to start clean.

Cost note: 11 fixtures x 2 conditions x 5 trials, plus a judge call per output, is
~110 agent calls + ~110 judge calls = ~220 LLM calls. Expect $15-40 depending on model
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
from policies import POLICIES, load_fixture_text, expected_audit  # noqa: E402

REPO_SKILL_MD = Path(__file__).resolve().parent.parent.parent / "SKILL.md"

DEFAULT_AGENT_MODEL = os.environ.get("EVAL_AGENT_MODEL", "claude-sonnet-4-6")
DEFAULT_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096


def build_control_prompt(policy: dict) -> str:
    return f"""You are a cloud security engineer reviewing an AWS IAM policy for misconfigurations.

Principal: {policy['principal']}
Context: {policy['role']}

Here is the policy, exactly as returned by the IAM API:

{load_fixture_text(policy)}

Audit this policy. Identify any over-broad grant or privilege-escalation path: anything that
lets this principal do more than it should, or escalate to administrator. For each, give the
severity and the fix. Be specific."""


def build_treatment_prompt(policy: dict, skill_md_text: str) -> str:
    return f"""You are a cloud security engineer auditing an AWS IAM policy, following the methodology below exactly.

METHODOLOGY (SKILL.md):

{skill_md_text}

PRINCIPAL CONTEXT:

Principal: {policy['principal']}
Context: {policy['role']}

POLICY (IAM policy document JSON):

{load_fixture_text(policy)}

Apply the methodology end-to-end. Produce the structured output the methodology's "Output format" section prescribes (principal, findings ranked by severity, boundary)."""


JUDGE_SYSTEM = """You are an expert AWS / cloud-security evaluator grading an IAM policy audit against a 7-item rubric. Each item is binary: 1 (pass) or 0 (fail). Be strict but fair; no partial credit.

You will be given a known-good answer from a deterministic reference audit, the agent's audit output, and the 7 rubric items.

Return JSON only (no prose), with this exact schema:

{
  "scores": [<int>, <int>, <int>, <int>, <int>, <int>, <int>],
  "notes": ["<one sentence>", ...]
}"""


def build_judge_prompt(policy: dict, agent_output: str) -> str:
    exp = expected_audit(policy)
    return f"""FIXTURE: {policy['id']}
PRINCIPAL: {policy['principal']}

KNOWN-GOOD ANSWER (from the deterministic reference audit):
- Findings (ground truth): {exp['codes']}  (severity: {exp['top_severity']}; clean: {exp['clean']})
- What the defect is: {policy['expected_headline']}
- Correct top fix: {policy['expected_top_fix']}
- Boundary the audit cannot cross: {policy['expected_boundary_join']}

AGENT AUDIT OUTPUT:
{agent_output}

RUBRIC (score each 1 = pass, 0 = fail):
1. Parse: reads the statements correctly, including expanding wildcard Actions (a `*` or `svc:*` is recognised as the concrete sensitive permissions it grants, not skipped).
2. Findings: identifies the ground-truth defect(s) by substance (the same escalation path or over-broad grant; it need not use the rule code), or correctly reports none for the clean control.
3. No false positives: does not assert a material defect the ground truth lacks (esp. not calling a least-privilege scoped policy broken, nor a trust-policy wildcard that IS narrowed by ExternalId/org "public").
4. Cross-statement reasoning: where the defect is a combination (PassRole + a launch action, etc.), the agent evaluates the union of statements rather than clearing each statement in isolation.
5. Criticality: ranks an escalation-to-admin or full-wildcard as most serious; does not headline a low-severity read reach; respects the scoped-vs-unscoped PassRole distinction (scoped = lower).
6. Boundary: names at least one thing it cannot determine from the policy alone, matching the ground-truth join (other attached policies, permissions boundary, org SCPs, the target role's privileges).
7. Recommendation: top fix matches the ground-truth fix in substance (scope the action/resource, remove the escalation grant, add a condition, etc.).

Return JSON only."""


RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 529}
MAX_RETRIES = 6


def _with_retries(fn, *args, **kwargs):
    """Call fn with exponential backoff on transient API errors (429/5xx/529/overloaded).

    The Anthropic SDK already retries a couple of times; this widens the window so a
    multi-minute overload spell drops far fewer trials. Re-raises on non-retryable
    errors or once retries are exhausted.

    Returns (result, call_seconds) where call_seconds is the wall-time of the SUCCESSFUL
    attempt only -- backoff sleeps and failed attempts are excluded, so duration metrics
    reflect real audit latency, not how overloaded the API happened to be.
    """
    delay = 2.0
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            t_call = time.time()
            return fn(*args, **kwargs), time.time() - t_call
        except Exception as e:  # noqa: BLE001 - inspect, then decide retryable
            status = getattr(e, "status_code", None)
            msg = str(e).lower()
            retryable = status in RETRYABLE_STATUS or "overloaded" in msg or "rate" in msg or "timeout" in msg
            if not retryable:
                raise
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
    raise last_exc


def run_agent(client: Anthropic, model: str, prompt: str) -> tuple[str, float]:
    """Returns (agent_output_text, audit_seconds). Seconds excludes retry backoff."""
    def _call():
        return client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    resp, call_s = _with_retries(_call)
    return "".join(block.text for block in resp.content if block.type == "text"), call_s


def run_judge(client: Anthropic, model: str, policy: dict, agent_output: str) -> dict:
    def _call():
        return client.messages.create(
            model=model,
            max_tokens=1024,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": build_judge_prompt(policy, agent_output)}],
        )
    resp, _ = _with_retries(_call)
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
    parser.add_argument("--fresh", action="store_true", help="Ignore an existing results file and start clean (default: resume/fill gaps)")
    args = parser.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = Anthropic()
    skill_md_text = REPO_SKILL_MD.read_text()

    to_run = POLICIES
    if args.fixtures:
        filters = [f.strip() for f in args.fixtures.split(",")]
        to_run = [p for p in POLICIES if any(p["id"].startswith(f) for f in filters)]

    print(f"Running {len(to_run)} fixtures x 2 conditions x {args.trials} trials = {len(to_run) * 2 * args.trials} agent calls")
    print(f"Agent model: {args.agent_model}, Judge model: {args.judge_model}\n")

    # Resume: reload any completed trials from a prior run so a re-run fills ONLY the
    # gaps (e.g. trials dropped to a transient overload), never redoing finished work.
    # Pass --fresh to ignore an existing results file and start clean.
    results: list[dict] = []
    completed: set[tuple[str, str, int]] = set()
    out_path = Path(args.output)
    if out_path.exists() and not args.fresh:
        try:
            results = json.loads(out_path.read_text())
            completed = {(r["fixture"], r["condition"], r["trial"]) for r in results}
            print(f"Resuming from {args.output}: {len(completed)} trials already complete; filling gaps only.\n")
        except (json.JSONDecodeError, KeyError, OSError):
            results, completed = [], set()

    for policy in to_run:
        for condition in ("control", "treatment"):
            for trial in range(args.trials):
                if (policy["id"], condition, trial) in completed:
                    continue  # already have this cell from a prior run
                t_start = time.time()
                prompt = build_control_prompt(policy) if condition == "control" else build_treatment_prompt(policy, skill_md_text)
                try:
                    agent_output, agent_s = run_agent(client, args.agent_model, prompt)  # agent_s excludes retry backoff
                    judge_result = run_judge(client, args.judge_model, policy, agent_output)
                    score = sum(judge_result["scores"])
                except Exception as e:
                    print(f"  ERROR on {policy['id']} {condition} trial {trial}: {e}", file=sys.stderr)
                    continue
                elapsed = time.time() - t_start  # agent + judge, for cost/wall-clock accounting
                results.append({
                    "fixture": policy["id"],
                    "condition": condition,
                    "trial": trial,
                    "score": score,
                    "scores_by_item": judge_result["scores"],
                    "notes": judge_result.get("notes", []),
                    "agent_output": agent_output,
                    "agent_chars": len(agent_output),
                    "agent_s": round(agent_s, 1),
                    "elapsed_s": round(elapsed, 1),
                })
                # Crash-safe: persist after every trial via atomic temp+rename so an
                # overload-induced death never throws away completed work.
                tmp = Path(str(args.output) + ".tmp")
                tmp.write_text(json.dumps(results, indent=2))
                tmp.replace(args.output)
                print(f"  {policy['id']:<32} | {condition:9s} | trial {trial} | score {score}/7 | audit {agent_s:.0f}s", flush=True)

    Path(args.output).write_text(json.dumps(results, indent=2))
    print(f"\nRaw results: {args.output}\n")
    print_summary(results, to_run)
    return 0


def print_summary(results: list[dict], to_run: list[dict]) -> None:
    by_cell: dict[tuple[str, str], list[int]] = {}
    for r in results:
        by_cell.setdefault((r["fixture"], r["condition"]), []).append(r["score"])

    print(f"{'Fixture':<32} {'Control mean':>14} {'Treatment mean':>16} {'Lift':>8} {'C-std':>7} {'T-std':>7}")
    print("-" * 86)
    lifts = []
    for policy in to_run:
        control = by_cell.get((policy["id"], "control"), [])
        treatment = by_cell.get((policy["id"], "treatment"), [])
        if not control or not treatment:
            continue
        c_mean, t_mean = statistics.mean(control), statistics.mean(treatment)
        lift = t_mean - c_mean
        lifts.append(lift)
        c_std = statistics.stdev(control) if len(control) > 1 else 0.0
        t_std = statistics.stdev(treatment) if len(treatment) > 1 else 0.0
        print(f"{policy['id']:<32} {c_mean:>14.2f} {t_mean:>16.2f} {lift:>+8.2f} {c_std:>7.2f} {t_std:>7.2f}")
    print("-" * 86)
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
