#!/usr/bin/env bash
#
# seo_orchestrator.sh - single headless entrypoint for the SEO / AI-SEO crons.
# ============================================================================
# Consolidates the previously-scattered cron scripts behind ONE command and
# always prints + logs the SEO+GEO status roll-up at the end of every run.
#
# Layered consolidation:
#   - CRONS call THIS script (headless bash/python; can't invoke a Claude skill).
#   - the OPERATOR calls /audit-converge (the deep interactive agentic loop).
# Both are "single entrypoints", at their own layer.
#
# Usage:
#   seo_orchestrator.sh --cadence daily        # daily blog-seo workflow (chudi-blog)
#   seo_orchestrator.sh --cadence weekly       # weekly marketing-agent SEO
#   seo_orchestrator.sh --cadence ctr          # weekly GSC/BWT CTR agent (dry-run)
#   seo_orchestrator.sh --cadence ctr --apply  # ... and open the review PR
#   seo_orchestrator.sh --cadence status       # just the roll-up (read-only)
#   seo_orchestrator.sh --cadence all          # daily + weekly + ctr + status
#
# Flags:
#   --engine gsc|bing|both   CTR engine(s)   (default: gsc)
#   --apply                  let the CTR step open a real PR (default: dry-run)
#   --dry-run                force dry-run on every step
#
# Design: `set -uo pipefail` WITHOUT `-e` - one failing step must never abort
# the status roll-up. Every step is logged with its exit code; the run continues.

set -uo pipefail

# --- paths ------------------------------------------------------------------
BLOG="$HOME/Projects/active/chudi-blog"
MKTG="$HOME/Projects/business/marketing-agent"
AIVR="$HOME/Projects/business/ai-visibility-readiness"
SCRIPTS="$AIVR/scripts"
LOG_DIR="$HOME/.claude/cron/seo"
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/orchestrator.log"
STATUS_HISTORY="$LOG_DIR/status-history.jsonl"

# --- defaults ---------------------------------------------------------------
CADENCE=""
ENGINE="gsc"
APPLY=0
DRYRUN=0

# --- args -------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --cadence) CADENCE="${2:-}"; shift 2 ;;
    --engine)  ENGINE="${2:-gsc}"; shift 2 ;;
    --apply)   APPLY=1; shift ;;
    --dry-run) DRYRUN=1; shift ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "[orchestrator] unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$CADENCE" ]; then
  echo "[orchestrator] --cadence is required (daily|weekly|ctr|status|all)" >&2
  exit 2
fi

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

log() { echo "[$(ts)] $*" | tee -a "$RUN_LOG"; }

# run_step <label> <dir> <command...> : run, tee to log, capture exit, NEVER abort.
run_step() {
  local label="$1" dir="$2"; shift 2
  log "STEP START: $label  (cwd=$dir)  cmd: $*"
  if [ ! -d "$dir" ]; then
    log "STEP SKIP: $label - directory not found: $dir"
    return 0
  fi
  local rc=0
  ( cd "$dir" && "$@" ) >>"$RUN_LOG" 2>&1 || rc=$?
  if [ "$rc" -eq 0 ]; then
    log "STEP OK: $label"
  else
    log "STEP FAIL: $label (exit $rc) - continuing"
  fi
  return 0
}

log "=========================================================="
log "ORCHESTRATOR RUN  cadence=$CADENCE engine=$ENGINE apply=$APPLY dry_run=$DRYRUN"

# --- cadence -> step flags (bash 3.2 safe; no case fall-through) -------------
DO_DAILY=0; DO_WEEKLY=0; DO_CTR=0
case "$CADENCE" in
  daily)  DO_DAILY=1 ;;
  weekly) DO_WEEKLY=1 ;;
  ctr)    DO_CTR=1 ;;
  status) : ;;  # roll-up only
  all)    DO_DAILY=1; DO_WEEKLY=1; DO_CTR=1 ;;
  *) log "unknown cadence: $CADENCE (expected daily|weekly|ctr|status|all)"; exit 2 ;;
esac

# --- dispatch ---------------------------------------------------------------
if [ "$DO_DAILY" -eq 1 ]; then
  if [ "$DRYRUN" -eq 1 ]; then
    run_step "blog-seo (daily)" "$BLOG" env DRY_RUN=true /bin/bash scripts/workflows/blog-seo.sh
  else
    run_step "blog-seo (daily)" "$BLOG" /bin/bash scripts/workflows/blog-seo.sh
  fi
fi

if [ "$DO_WEEKLY" -eq 1 ]; then
  if [ "$DRYRUN" -eq 1 ]; then
    run_step "seo_weekly (weekly)" "$MKTG" /usr/bin/python3 scripts/seo_weekly.py --dry-run
  else
    run_step "seo_weekly (weekly)" "$MKTG" /usr/bin/python3 scripts/seo_weekly.py
  fi
fi

if [ "$DO_CTR" -eq 1 ]; then
  CTR_ARGS=(--property "https://chudi.dev/" --impression-floor 50 --engine "$ENGINE")
  if [ "$APPLY" -eq 1 ] && [ "$DRYRUN" -eq 0 ]; then
    CTR_ARGS+=(--apply)
  fi
  run_step "gsc-ctr-pr-agent (ctr)" "$SCRIPTS" /usr/bin/python3 gsc-ctr-pr-agent.py "${CTR_ARGS[@]}"
fi

# --- status roll-up: ALWAYS, regardless of step outcomes --------------------
log "----- SEO + GEO STATUS ROLL-UP -----"
if [ -f "$SCRIPTS/seo_status.py" ]; then
  /usr/bin/python3 "$SCRIPTS/seo_status.py" 2>&1 | tee -a "$RUN_LOG"
  # Append the machine-readable snapshot to a history file for trend queries.
  /usr/bin/python3 "$SCRIPTS/seo_status.py" --json 2>/dev/null \
    | /usr/bin/python3 -c 'import sys,json; print(json.dumps(json.load(sys.stdin)))' \
    >>"$STATUS_HISTORY" 2>/dev/null \
    && log "status snapshot appended to $STATUS_HISTORY" \
    || log "status snapshot append skipped"
else
  log "seo_status.py not found at $SCRIPTS - skipping roll-up"
fi

log "ORCHESTRATOR RUN COMPLETE  cadence=$CADENCE"
log "=========================================================="
