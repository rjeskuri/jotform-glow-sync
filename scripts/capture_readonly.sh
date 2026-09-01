#!/bin/bash
# GET-only capture of what the Python tools see and plan, for before/after
# comparisons around a refactor: run it before (`scripts/capture_readonly.sh
# out/before`), refactor, run it after, then `diff -r out/before out/after`
# must be empty. Needs JOTFORM_API_KEY in the environment and a Roster
# export (ROSTER=path, default: the newest data/roster_*.csv). Writes nothing
# to any live system; the outputs contain club names and counts, never
# girls' names (the sync's dry-run plan and form_status's report do not list
# them), except backups/ which is gitignored anyway.
set -euo pipefail
OUT="${1:?usage: scripts/capture_readonly.sh <out dir>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
: "${JOTFORM_API_KEY:?set JOTFORM_API_KEY (load .env: set -a; source .env; set +a)}"
PY="$REPO/.venv/bin/python3"; [ -x "$PY" ] || PY=python3
ROSTER="${ROSTER:-$(ls -t data/roster_*.csv 2>/dev/null | head -1 || true)}"
[ -n "$ROSTER" ] || { echo "no Roster export found: ROSTER=<csv> or sheets_client.py export Roster data/roster_<date>.csv" >&2; exit 1; }
mkdir -p "$OUT"
echo "roster: $ROSTER -> $OUT"

# 1. form_status for every form, minus the fields that change between runs
"$PY" tools/form_status.py --roster "$ROSTER" --json \
  | "$PY" -c 'import json,sys; r=json.load(sys.stdin)
for f in r:
    f.pop("submissions", None); f.pop("last_submission", None)
    for k in ("missing_from_form","not_in_roster"):
        if f.get("region_check"): f["region_check"][k]=sorted(f["region_check"][k])
    if f.get("region_check"): f["region_check"]["rosters_out_of_date"]=sorted(map(list,f["region_check"]["rosters_out_of_date"]))
    f["rule_problems"]=sorted(f["rule_problems"])
print(json.dumps(r, indent=1, sort_keys=True))' > "$OUT/form_status.json"

# 2. the sync's dry-run plan per live region (no --apply anywhere)
for spec in "Africa:262382821971058" "Asia:262383129464057" "Latin America:262383455778067" "U.S:262382706852058"; do
  region="${spec%%:*}"; form="${spec##*:}"
  "$PY" sync_attendance_form.py "$ROSTER" --roster --region "$region" --form "$form" \
    --summary-json "$OUT/plan_${form}.json" > "$OUT/dryrun_${form}.txt" 2>&1 || echo "  ! sync dry run for $region exited $?"
  "$PY" -c 'import json,sys; s=json.load(open(sys.argv[1])); s.pop("plan_hash",None); json.dump(s, open(sys.argv[1],"w"), indent=1, sort_keys=True)' "$OUT/plan_${form}.json" 2>/dev/null || true
done

# 3. the translations audit (read-only)
"$PY" tools/add_translations.py --audit > "$OUT/translations_audit.txt" 2>&1 || echo "  ! translations audit exited $?"

echo "captured: $(ls "$OUT" | wc -l | tr -d ' ') files"
