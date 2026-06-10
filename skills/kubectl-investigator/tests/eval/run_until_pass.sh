#!/usr/bin/env bash
# Run the ablation eval fixture-by-fixture, retrying each fixture until BOTH arms
# (control + treatment) have all TRIALS trials. Leans on run_eval.py's resume
# (fills only missing trials) and per-call backoff. Safe to interrupt and re-run.
#
# Usage: bash tests/eval/run_until_pass.sh [TRIALS] [MAX_ATTEMPTS_PER_FIXTURE]
set -u
cd "$(dirname "$0")/../.."   # -> skills/kubectl-investigator
TRIALS="${1:-1}"
MAX_ATTEMPTS="${2:-12}"
OUT="tests/eval/eval_results.json"

FIXTURES=(
  01-oom-cascade
  02-dns-resolution-failure
  03-cascading-failure-retry-storm
  04-deploy-correlator-serialization
  05-outside-reference-paths-third-party-rate-limit
  06-ambiguous-t0-slow-burn
  07-blast-radius-asymmetric-revert
  08-deploy-correlator-confirmation-bias
  09-zero-changes-external-cert-expiry
  10-multi-region-asymmetry
  11-capacity-bound-organic-growth
)

complete() {  # exit 0 if fixture $1 has >=TRIALS in each arm
  python - "$1" "$TRIALS" "$OUT" <<'PY'
import json, sys
fx, T, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    d = json.load(open(out))
except Exception:
    sys.exit(1)
c = sum(1 for r in d if r["incident"] == fx and r["condition"] == "control")
t = sum(1 for r in d if r["incident"] == fx and r["condition"] == "treatment")
print(f">>> {fx}: control {c}/{T}, treatment {t}/{T}")
sys.exit(0 if c >= T and t >= T else 1)
PY
}

echo "=== run_until_pass: TRIALS=$TRIALS, $((${#FIXTURES[@]})) fixtures ==="
for fx in "${FIXTURES[@]}"; do
  echo "----- fixture $fx -----"
  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    python -u tests/eval/run_eval.py --fixtures "$fx" --trials "$TRIALS" --output "$OUT" 2>&1 \
      | grep -E 'investigate|ERROR on' || true
    if complete "$fx"; then
      echo "    $fx COMPLETE (attempt $attempt)"
      break
    fi
    echo "    $fx incomplete after attempt $attempt; retrying..."
    sleep 5
  done
  complete "$fx" >/dev/null || echo "!!! $fx still incomplete after $MAX_ATTEMPTS attempts; moving on"
done

echo "=== ALL FIXTURES PROCESSED — final summary ==="
python tests/eval/run_eval.py --trials "$TRIALS" --output "$OUT" 2>&1 | sed -n '/^Fixture/,$p'
