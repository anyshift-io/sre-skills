"""
Control-only screening eval for the candidate iam-deceptive-escalation-auditor skill.

There is NO SKILL.md and NO treatment arm here. This harness measures one thing: does a
COLD agent (no skill, generic "review this policy for problems" prompt) fail on this
domain? A skill is worth building only if the cold agent scores LOW (mean < 4/7) on these
deliberately deceptive fixtures.

For each fixture, runs N trials in the control condition only:
- Control: the agent is given the raw IAM policy JSON and a generic "audit this policy"
  prompt. It uses whatever it brings from training.

Each agent output is graded against the 7-item rubric (rubric.md) by an LLM judge, anchored
to the deterministic reference audit (_audit.py, via scenarios.py) as ground truth.

Final report: per-fixture mean control score, stdev across trials, the aggregate mean, and
a screening verdict (build the skill only if the cold agent is weak here).

Requirements:
- ANTHROPIC_API_KEY environment variable.
- `pip install anthropic` (the only non-stdlib dependency in the repo; isolated to tests/eval/).

Usage:
    python tests/eval/run_eval.py --trials 5
    python tests/eval/run_eval.py --trials 1 --fixtures 02,05,07   # smoke test
    python tests/eval/run_eval.py --trials 5 --fresh               # ignore prior results

Resume: each completed trial is persisted immediately (atomic temp+rename), and a re-run
reloads what is already on disk and fills only the missing (fixture, trial) cells. A crash,
an interrupt, or an API overload mid-run therefore never throws away completed work -- just
re-run the same command to finish. Pass --fresh to start clean.

Cost note: 7 fixtures x 1 condition x 5 trials, plus a judge call per output, is
~35 agent calls + ~35 judge calls = ~70 LLM calls. Expect a few dollars depending on model.
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
from scenarios import SCENARIOS, load_fixture_text, expected_audit  # noqa: E402

DEFAULT_AGENT_MODEL = os.environ.get("EVAL_AGENT_MODEL", "claude-sonnet-4-6")
DEFAULT_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096

# SKILL.md lives at the skill root (three levels up from tests/eval/).
SKILL_MD = Path(__file__).resolve().parents[2] / "SKILL.md"


def build_control_prompt(scenario: dict) -> str:
    return f"""You are a cloud security engineer reviewing an AWS IAM policy for misconfigurations.

Principal: {scenario['principal']}
Context: {scenario['role']}

Here is the policy, exactly as returned by the IAM API:

{load_fixture_text(scenario)}

Audit this policy. Identify any over-broad grant or privilege-escalation path: anything that
lets this principal do more than it should, or escalate to administrator. For each, give the
severity and the fix. Be specific."""


def build_treatment_prompt(scenario: dict, skill_md_text: str) -> str:
    """Treatment arm: the SAME audit ask and the SAME policy JSON as control, plus SKILL.md
    prepended as the methodology to apply. The only variable between arms is the skill, so
    the lift is attributable to it."""
    return f"""You are a cloud security engineer reviewing an AWS IAM policy for misconfigurations. Apply the methodology below to the policy that follows it.

==== METHODOLOGY (SKILL.md) ====
{skill_md_text}
==== END METHODOLOGY ====

Principal: {scenario['principal']}
Context: {scenario['role']}

Here is the policy, exactly as returned by the IAM API:

{load_fixture_text(scenario)}

Apply the methodology above. Identify any over-broad grant or privilege-escalation path, or
state that an apparent escalation is neutralised. For each finding give the severity and the
fix, and name what you cannot determine from the policy alone. Be specific."""


JUDGE_SYSTEM = """You are an expert AWS / cloud-security evaluator grading an IAM policy audit against a 7-item rubric. Each item is binary: 1 (pass) or 0 (fail). Be strict but fair; no partial credit.

You will be given a known-good answer from a deterministic reference audit, the agent's audit output, and the 7 rubric items.

Return JSON only (no prose), with this exact schema:

{
  "scores": [<int>, <int>, <int>, <int>, <int>, <int>, <int>],
  "notes": ["<one sentence>", ...]
}"""


def build_judge_prompt(scenario: dict, agent_output: str) -> str:
    exp = expected_audit(scenario)
    return f"""FIXTURE: {scenario['id']}
PRINCIPAL: {scenario['principal']}

KNOWN-GOOD ANSWER (from the deterministic reference audit):
- Findings (ground truth): {exp['codes']}  (severity: {exp['top_severity']}; clean: {exp['clean']})
- What the defect is: {scenario['expected_headline']}
- Correct top fix: {scenario['expected_top_fix']}
- Boundary the audit cannot cross: {scenario['expected_boundary_join']}

AGENT AUDIT OUTPUT:
{agent_output}

RUBRIC (score each 1 = pass, 0 = fail):
1. Parse: reads the statements correctly, including expanding wildcard Actions (a `*` or `svc:*` is recognised as the concrete sensitive permissions it grants, not skipped).
2. Findings: identifies the ground-truth defect(s) by substance (the same escalation path or over-broad grant; it need not use the rule code), or correctly reports none for a deceptive-clean fixture.
3. No false positives: does not assert a material defect the ground truth lacks (esp. not calling a Deny-neutralised PassRole, a Resource-scoped Action '*', a broken-back AssumeRole, or a read-only wildcard a live privilege escalation).
4. Cross-statement reasoning: where the defect is a combination (PassRole + a launch action split across attached policies, etc.), the agent evaluates the union of statements rather than clearing each statement in isolation; and conversely recognises when a Deny or a scope neutralises an apparent combo.
5. Criticality: ranks a real escalation-to-admin as most serious, and does NOT headline a neutralised or read-only grant as critical.
6. Boundary: names at least one thing it cannot determine from the policy alone, matching the ground-truth join (other attached policies, permissions boundary, org SCPs, the target role's privileges).
7. Recommendation: top fix matches the ground-truth fix in substance (scope the action/resource, remove the escalation grant, add a condition; or correctly state no fix is needed for a neutralised policy).

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


def run_judge(client: Anthropic, model: str, scenario: dict, agent_output: str) -> dict:
    def _call():
        return client.messages.create(
            model=model,
            max_tokens=1024,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": build_judge_prompt(scenario, agent_output)}],
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
    parser.add_argument("--trials", type=int, default=5, help="Trials per fixture (control only)")
    parser.add_argument("--fixtures", default="", help="Comma-separated fixture IDs (prefix match); empty = all")
    parser.add_argument("--agent-model", default=DEFAULT_AGENT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--output", default="eval_results.json", help="Where to write the raw results")
    parser.add_argument("--fresh", action="store_true", help="Ignore an existing results file and start clean (default: resume/fill gaps)")
    # Default treatment-only: control cells are already on disk from screening and reused.
    parser.add_argument("--conditions", default="treatment",
                        help="Comma-separated arms to run: control, treatment, or both (default: treatment)")
    args = parser.parse_args()

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    bad = [c for c in conditions if c not in ("control", "treatment")]
    if bad:
        print(f"ERROR: unknown condition(s) {bad}; valid: control, treatment", file=sys.stderr)
        return 2

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    skill_md_text = ""
    if "treatment" in conditions:
        if not SKILL_MD.exists():
            print(f"ERROR: treatment arm needs a SKILL.md at {SKILL_MD}", file=sys.stderr)
            return 1
        skill_md_text = SKILL_MD.read_text()

    client = Anthropic()

    to_run = SCENARIOS
    if args.fixtures:
        filters = [f.strip() for f in args.fixtures.split(",")]
        to_run = [s for s in SCENARIOS if any(s["id"].startswith(f) for f in filters)]

    n_cells = len(to_run) * len(conditions) * args.trials
    print(f"LIFT eval [{', '.join(conditions)}]: {len(to_run)} fixtures x {len(conditions)} conditions x {args.trials} trials = {n_cells} agent calls")
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

    for scenario in to_run:
        for condition in conditions:
            for trial in range(args.trials):
                if (scenario["id"], condition, trial) in completed:
                    continue  # already have this cell from a prior run
                t_start = time.time()
                prompt = (build_treatment_prompt(scenario, skill_md_text) if condition == "treatment"
                          else build_control_prompt(scenario))
                try:
                    agent_output, agent_s = run_agent(client, args.agent_model, prompt)  # agent_s excludes retry backoff
                    judge_result = run_judge(client, args.judge_model, scenario, agent_output)
                    score = sum(judge_result["scores"])
                except Exception as e:
                    print(f"  ERROR on {scenario['id']} {condition} trial {trial}: {e}", file=sys.stderr)
                    continue
                elapsed = time.time() - t_start  # agent + judge, for cost/wall-clock accounting
                results.append({
                    "fixture": scenario["id"],
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
                print(f"  {scenario['id']:<40} | {condition:9s} | trial {trial} | score {score}/7 | audit {agent_s:.0f}s", flush=True)

    Path(args.output).write_text(json.dumps(results, indent=2))
    print(f"\nRaw results: {args.output}\n")
    print_summary(results, to_run)
    return 0


def print_summary(results: list[dict], to_run: list[dict]) -> None:
    ctrl: dict[str, list[int]] = {}
    treat: dict[str, list[int]] = {}
    for r in results:
        bucket = ctrl if r.get("condition") == "control" else treat
        bucket.setdefault(r["fixture"], []).append(r["score"])

    print(f"{'Fixture':<40} {'Control':>8} {'Treat':>8} {'Lift':>8} {'Nc':>4} {'Nt':>4}")
    print("-" * 80)
    c_means: list[float] = []
    t_means: list[float] = []
    lifts: list[float] = []
    paired_ids: list[str] = []
    for scenario in to_run:
        cs = ctrl.get(scenario["id"], [])
        ts = treat.get(scenario["id"], [])
        if not cs and not ts:
            continue
        c = statistics.mean(cs) if cs else float("nan")
        t = statistics.mean(ts) if ts else float("nan")
        c_str = f"{c:>8.2f}" if cs else f"{'n/a':>8}"
        t_str = f"{t:>8.2f}" if ts else f"{'n/a':>8}"
        if cs and ts:
            lift = t - c
            lifts.append(lift); c_means.append(c); t_means.append(t); paired_ids.append(scenario["id"])
            l_str = f"{lift:>+8.2f}"
            flag = "  <- treat still <5" if t < 5.0 else ("  <- no lift" if lift <= 0 else "")
        else:
            l_str = f"{'-':>8}"
            flag = ""
        print(f"{scenario['id']:<40} {c_str} {t_str} {l_str} {len(cs):>4} {len(ts):>4}{flag}")
    print("-" * 80)

    if not lifts:
        print("\nNo paired control/treatment fixtures to summarize "
              f"(control: {sum(len(v) for v in ctrl.values())} cells, "
              f"treatment: {sum(len(v) for v in treat.values())} cells).")
        return

    c_agg = statistics.mean(c_means)
    t_agg = statistics.mean(t_means)
    print(f"\nAggregate: control {c_agg:.2f}/7  ->  treatment {t_agg:.2f}/7   (lift {t_agg - c_agg:+.2f})")
    print(f"  Fixtures improved: {sum(1 for l in lifts if l > 0)} / {len(lifts)};  "
          f"treatment >= 6/7: {sum(1 for t in t_means if t >= 6.0)} / {len(t_means)};  "
          f"treatment >= 5/7: {sum(1 for t in t_means if t >= 5.0)} / {len(t_means)}")
    weakest = min(zip(t_means, paired_ids))
    print(f"  Weakest treatment fixture: {weakest[1]} at {weakest[0]:.2f}/7 "
          "(the next one to close with a SKILL.md edit)")


if __name__ == "__main__":
    sys.exit(main())
