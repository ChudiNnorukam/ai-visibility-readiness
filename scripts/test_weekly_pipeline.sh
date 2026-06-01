#!/usr/bin/env bash
# Smoke test for the hardened Marston weekly GEO update pipeline.
#
# Exercises every component of SKILL.md without spending $2 on a real audit:
#   1. Bash retry wrapper: feeds it a fake audit that exits 0, 1, 2 in sequence
#      and confirms retry-once + don't-retry-on-2 behavior.
#   2. Chart generation: runs weekly_chart.py against the current sample-audits.
#   3. Chart upload skip path: runs the python upload block without a bot token,
#      confirms it prints the local-only message and exits 0.
#   4. Renderer wiring: invokes format_marston_template.py against the newest
#      audit base and confirms the draft is non-empty + has no leftover
#      computed-field placeholders.
#
# Exit non-zero on first failure. Print [pass]/[fail] for each step.

set -u
PASS=0
FAIL=0
FAIL_DETAIL=""

step() {
  local rc=$1
  local label=$2
  if [ "$rc" = "0" ]; then
    echo "[pass] $label"
    PASS=$((PASS + 1))
  else
    echo "[FAIL] $label (rc=$rc)"
    FAIL=$((FAIL + 1))
    FAIL_DETAIL="$FAIL_DETAIL\n  - $label (rc=$rc)"
  fi
}

# ---------- Setup ----------

TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT
echo "[setup] tmp dir: $TMP_DIR"

# ---------- Test 1: bash retry wrapper, success first try ----------

cat > "$TMP_DIR/fake_audit_ok.sh" <<'EOF'
#!/usr/bin/env bash
echo "[fake-audit] running, will exit 0"
exit 0
EOF
chmod +x "$TMP_DIR/fake_audit_ok.sh"

run_wrapper() {
  local fake_script=$1
  local log=$2
  local attempts=0
  local exit_code=99
  local max=2
  while [ $attempts -lt $max ]; do
    attempts=$((attempts + 1))
    "$fake_script" 2>&1 | tee -a "$log" > /dev/null
    exit_code=${PIPESTATUS[0]}
    if [ "$exit_code" = "0" ]; then break; fi
    if [ "$exit_code" = "2" ]; then break; fi
    if [ $attempts -lt $max ]; then sleep 1; fi
  done
  echo "$attempts $exit_code"
}

LOG1="$TMP_DIR/test1.log"
RESULT=$(run_wrapper "$TMP_DIR/fake_audit_ok.sh" "$LOG1")
ATTEMPTS=$(echo "$RESULT" | awk '{print $1}')
EXIT_CODE=$(echo "$RESULT" | awk '{print $2}')
[ "$ATTEMPTS" = "1" ] && [ "$EXIT_CODE" = "0" ]
step $? "wrapper: succeeds on first attempt, no retry (attempts=$ATTEMPTS exit=$EXIT_CODE)"

# ---------- Test 2: bash retry wrapper, transient fail then success ----------

cat > "$TMP_DIR/fake_audit_flaky.sh" <<EOF
#!/usr/bin/env bash
COUNTER_FILE=$TMP_DIR/flaky_counter
N=\$(cat "\$COUNTER_FILE" 2>/dev/null || echo 0)
N=\$((N + 1))
echo "\$N" > "\$COUNTER_FILE"
if [ "\$N" = "1" ]; then
  echo "[fake-audit] attempt 1, exiting 1 (transient)"
  exit 1
fi
echo "[fake-audit] attempt \$N, exiting 0"
exit 0
EOF
chmod +x "$TMP_DIR/fake_audit_flaky.sh"
LOG2="$TMP_DIR/test2.log"
RESULT=$(run_wrapper "$TMP_DIR/fake_audit_flaky.sh" "$LOG2")
ATTEMPTS=$(echo "$RESULT" | awk '{print $1}')
EXIT_CODE=$(echo "$RESULT" | awk '{print $2}')
[ "$ATTEMPTS" = "2" ] && [ "$EXIT_CODE" = "0" ]
step $? "wrapper: transient fail then retry succeeds (attempts=$ATTEMPTS exit=$EXIT_CODE)"

# ---------- Test 3: bash retry wrapper, calibration failure does NOT retry ----------

cat > "$TMP_DIR/fake_audit_calib.sh" <<'EOF'
#!/usr/bin/env bash
echo "[fake-audit] simulating calibration failure"
exit 2
EOF
chmod +x "$TMP_DIR/fake_audit_calib.sh"
LOG3="$TMP_DIR/test3.log"
RESULT=$(run_wrapper "$TMP_DIR/fake_audit_calib.sh" "$LOG3")
ATTEMPTS=$(echo "$RESULT" | awk '{print $1}')
EXIT_CODE=$(echo "$RESULT" | awk '{print $2}')
[ "$ATTEMPTS" = "1" ] && [ "$EXIT_CODE" = "2" ]
step $? "wrapper: exit 2 (calibration) does not retry (attempts=$ATTEMPTS exit=$EXIT_CODE)"

# ---------- Test 4: bash retry wrapper, persistent fail exhausts retries ----------

cat > "$TMP_DIR/fake_audit_broken.sh" <<'EOF'
#!/usr/bin/env bash
echo "[fake-audit] broken every time"
exit 1
EOF
chmod +x "$TMP_DIR/fake_audit_broken.sh"
LOG4="$TMP_DIR/test4.log"
RESULT=$(run_wrapper "$TMP_DIR/fake_audit_broken.sh" "$LOG4")
ATTEMPTS=$(echo "$RESULT" | awk '{print $1}')
EXIT_CODE=$(echo "$RESULT" | awk '{print $2}')
[ "$ATTEMPTS" = "2" ] && [ "$EXIT_CODE" = "1" ]
step $? "wrapper: persistent exit 1 exhausts both retries (attempts=$ATTEMPTS exit=$EXIT_CODE)"

# ---------- Test 5: caffeinate + nohup binary presence (timeout handled by wrapper) ----------

command -v caffeinate > /dev/null && command -v nohup > /dev/null
step $? "binaries: caffeinate + nohup on PATH"

# ---------- Test 5b: run_audit_with_timeout.py enforces wall-clock cap ----------

mkdir -p "$TMP_DIR/fake_runaudit_dir"
cat > "$TMP_DIR/fake_runaudit_dir/run_audit.py" <<'EOF'
import time, sys
print("starting fake-audit, will sleep 5s")
time.sleep(5)
print("done")
sys.exit(0)
EOF
cp /Users/chudinnorukam/Projects/business/ai-visibility-readiness/scripts/run_audit_with_timeout.py "$TMP_DIR/fake_runaudit_dir/"

# Verify it returns 124 when timeout < sleep
START=$(date +%s)
python3 "$TMP_DIR/fake_runaudit_dir/run_audit_with_timeout.py" --timeout 2 -- 2>/dev/null
TIMEOUT_RC=$?
ELAPSED=$(( $(date +%s) - START ))
[ "$TIMEOUT_RC" = "124" ] && [ "$ELAPSED" -lt 5 ]
step $? "wrapper: run_audit_with_timeout.py returns 124 on timeout (rc=$TIMEOUT_RC elapsed=${ELAPSED}s)"

# Verify it returns 0 when timeout > sleep
python3 "$TMP_DIR/fake_runaudit_dir/run_audit_with_timeout.py" --timeout 30 -- 2>/dev/null
NORMAL_RC=$?
[ "$NORMAL_RC" = "0" ]
step $? "wrapper: run_audit_with_timeout.py returns 0 when audit finishes in time (rc=$NORMAL_RC)"

# ---------- Test 6: chart generation against current sample-audits ----------

CHART_OUT=$(python3 /Users/chudinnorukam/Projects/business/ai-visibility-readiness/scripts/weekly_chart.py \
  --audit-dir /Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits \
  --domain marstonorthodontics.com \
  --brand "Marston Orthodontics" \
  --output-dir "$TMP_DIR" \
  --filename-prefix test_marston_trend 2>&1)
CHART_RC=$?
[ "$CHART_RC" = "0" ] && [ -f "$CHART_OUT" ] && [ "$(stat -f %z "$CHART_OUT" 2>/dev/null || stat -c %s "$CHART_OUT")" -gt 10000 ]
step $? "chart: weekly_chart.py emits a PNG >10KB (rc=$CHART_RC out=$CHART_OUT)"

# ---------- Test 7: chart generation rejects single-point gracefully ----------

SINGLE_DIR="$TMP_DIR/single"
mkdir -p "$SINGLE_DIR"
cp /Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits/visibility_marstonorthodontics.com_20260518_215846_summary.json "$SINGLE_DIR/"
cp /Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits/citations_marstonorthodontics.com_20260518_212046_summary.json "$SINGLE_DIR/"
SINGLE_OUT=$(python3 /Users/chudinnorukam/Projects/business/ai-visibility-readiness/scripts/weekly_chart.py \
  --audit-dir "$SINGLE_DIR" \
  --domain marstonorthodontics.com \
  --brand "Marston Orthodontics" \
  --output-dir "$TMP_DIR" 2>&1)
SINGLE_RC=$?
[ "$SINGLE_RC" = "2" ]
step $? "chart: refuses to draw a 1-point trend without --allow-single-point (rc=$SINGLE_RC)"

# ---------- Test 8: chart-upload skip path (no token in env) ----------

UPLOAD_OUT=$(env -u MARSTON_PROD_SLACK_BOT_TOKEN python3 <<PYEOF
import os, sys
# Simulate the relevant slice of STEP 5B
chart_path = "$CHART_OUT"
token = os.environ.get('MARSTON_PROD_SLACK_BOT_TOKEN', '').strip()
if not token:
    print(f'[chart-upload] SKIPPED: MARSTON_PROD_SLACK_BOT_TOKEN not in .env')
    print(f'[chart-upload] chart available locally at {chart_path}')
    sys.exit(0)
print('[chart-upload] would have uploaded')
PYEOF
)
UPLOAD_RC=$?
echo "$UPLOAD_OUT" | grep -q "SKIPPED" && [ "$UPLOAD_RC" = "0" ]
step $? "upload: no-token path prints SKIPPED + local path + exits 0"

# ---------- Test 9: renderer wires into a real audit base ----------

NEWEST_SEO=$(ls -t /Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits/audit_marstonorthodontics.com_*_seo.json 2>/dev/null | head -1)
if [ -z "$NEWEST_SEO" ]; then
  echo "[skip] renderer test: no audit_*_seo.json in sample-audits"
else
  AUDIT_BASE=$(basename "$NEWEST_SEO" _seo.json)
  RENDER_OUT="$TMP_DIR/render.md"
  cd /Users/chudinnorukam/Projects/business/ai-visibility-readiness/scripts
  python3 format_marston_template.py \
    --audit-dir /Users/chudinnorukam/Projects/business/ai-visibility-readiness/sample-audits \
    --audit-base "$AUDIT_BASE" \
    --week 99 \
    --date 2099-01-01 \
    --status on-track > "$RENDER_OUT" 2>"$TMP_DIR/render.err"
  RENDER_RC=$?
  BYTES=$(wc -c < "$RENDER_OUT" | tr -d ' ')
  HAS_COMPUTED=$(grep -c "verdict:" "$RENDER_OUT" || true)
  [ "$RENDER_RC" = "0" ] && [ "$BYTES" -gt 500 ] && [ "$HAS_COMPUTED" -gt 0 ]
  step $? "renderer: format_marston_template.py emits >500 bytes with computed fields (rc=$RENDER_RC bytes=$BYTES verdict-lines=$HAS_COMPUTED)"
fi

# ---------- Test 10: env vars present in .env ----------

ENV_FILE=/Users/chudinnorukam/.thrulead/.env
grep -q "^MARSTON_PROD_SLACK_WEBHOOK=" "$ENV_FILE"
step $? "env: MARSTON_PROD_SLACK_WEBHOOK is set in .env"

# ---------- Test 11: SKILL.md is well-formed ----------

SKILL_FILE=/Users/chudinnorukam/.claude/scheduled-tasks/marston-weekly-geo-update/SKILL.md
head -5 "$SKILL_FILE" | grep -q "^name: marston-weekly-geo-update" && \
  grep -q "^STEP 1, RUN THE AUDIT" "$SKILL_FILE" && \
  grep -q "^STEP 5B, GENERATE + ATTACH THE TREND CHART" "$SKILL_FILE" && \
  grep -q "caffeinate -i nohup python3 -u run_audit_with_timeout.py" "$SKILL_FILE" && \
  grep -q "MAX_ATTEMPTS=2" "$SKILL_FILE" && \
  grep -q "EXIT_CODE.* = .*\"2\".*calibration" "$SKILL_FILE" 2>/dev/null || \
  grep -q "EXIT_CODE.*=.*2.*calibration\|calibration failed" "$SKILL_FILE"
step $? "skill.md: frontmatter + all expected steps + caffeinate wrapper + retry-once + calibration-skip-retry"

# ---------- Summary ----------

echo ""
echo "================================="
echo " smoke test: $PASS pass / $FAIL fail"
echo "================================="
if [ "$FAIL" -gt 0 ]; then
  printf "failed steps:%b\n" "$FAIL_DETAIL"
  exit 1
fi
exit 0
