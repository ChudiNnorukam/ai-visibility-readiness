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
#   seo_orchestrator.sh --cadence auto         # LAUNCHD ENTRYPOINT: full blog suite +
#                                              #   weekly(Sun) + ctr(Mon) + status, day-gated
#   seo_orchestrator.sh --cadence blog         # all 9 chudi-blog workflows (voice Sun-gated)
#   seo_orchestrator.sh --cadence weekly       # weekly marketing-agent SEO
#   seo_orchestrator.sh --cadence ctr          # GSC/BWT CTR agent (dry-run)
#   seo_orchestrator.sh --cadence ctr --apply  # ... and open the review PR
#   seo_orchestrator.sh --cadence status       # just the roll-up (read-only)
#   seo_orchestrator.sh --cadence all          # blog + weekly + ctr + status (ignores day gating)
#   seo_orchestrator.sh --cadence auto --dry-run   # kickstart-test: full path, NO live writes
#
# The 9 blog workflows (exec seo aeo geo aao system brand ranking-agent voice) were 9
# staggered crontab jobs that silently died when the Mac slept (cron skips missed jobs).
# Consolidated here + scheduled via one launchd agent (StartCalendarInterval = catch-up-on-wake).
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

# The gsc-ctr agent needs google-api-python-client, installed in the 3.13
# framework Python (this matches the original cron's interpreter). seo_weekly +
# seo_status run on /usr/bin/python3 (stdlib / system deps). Fall back to PATH.
PY_FRAMEWORK="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
[ -x "$PY_FRAMEWORK" ] || PY_FRAMEWORK="$(command -v python3 || echo /usr/bin/python3)"
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

# Global dry-run can also be forced via env (used by the launchd kickstart-test).
[ "${SEO_ORCH_DRYRUN:-0}" = "1" ] && DRYRUN=1

log "=========================================================="
log "ORCHESTRATOR RUN  cadence=$CADENCE engine=$ENGINE apply=$APPLY dry_run=$DRYRUN"

DOW=$(date +%u)   # 1=Mon ... 7=Sun

# --- cadence -> step flags (bash 3.2 safe; no case fall-through) -------------
# The 9 chudi-blog workflows, in their original staggered order (exec first).
# voice was a Sunday-only cron, so it is day-gated below.
BLOG_WORKFLOWS="exec seo aeo geo aao system brand ranking-agent"

DO_BLOG=0; DO_WEEKLY=0; DO_CTR=0
case "$CADENCE" in
  blog|daily) DO_BLOG=1 ;;                 # daily kept as an alias to blog
  weekly)     DO_WEEKLY=1 ;;
  ctr)        DO_CTR=1 ;;
  status)     : ;;                         # roll-up only
  all)        DO_BLOG=1; DO_WEEKLY=1; DO_CTR=1 ;;
  auto)       # the launchd entrypoint: blog daily, weekly Sun, ctr Mon
              DO_BLOG=1
              [ "$DOW" -eq 7 ] && DO_WEEKLY=1   # Sunday
              [ "$DOW" -eq 1 ] && DO_CTR=1      # Monday
              ;;
  *) log "unknown cadence: $CADENCE (expected blog|weekly|ctr|status|auto|all)"; exit 2 ;;
esac

# run one chudi-blog workflow (DRY_RUN-aware). Each blog-*.sh sources lib.sh,
# which sets its own PATH (npx/tsx/node) and logs to content/blog-agent.log.
run_blog() {
  local name="$1"
  if [ "$DRYRUN" -eq 1 ]; then
    run_step "blog-$name" "$BLOG" env DRY_RUN=true /bin/bash "scripts/workflows/blog-$name.sh"
  else
    run_step "blog-$name" "$BLOG" /bin/bash "scripts/workflows/blog-$name.sh"
  fi
}

# --- dispatch ---------------------------------------------------------------
if [ "$DO_BLOG" -eq 1 ]; then
  for wf in $BLOG_WORKFLOWS; do
    run_blog "$wf"
  done
  # voice: Sunday only (matches the original Sun 06:00 cron), or on a full 'all' run.
  if [ "$DOW" -eq 7 ] || [ "$CADENCE" = "all" ]; then
    run_blog voice
  else
    log "STEP SKIP: blog-voice (Sunday-only; today is dow=$DOW)"
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
  run_step "gsc-ctr-pr-agent (ctr)" "$SCRIPTS" "$PY_FRAMEWORK" gsc-ctr-pr-agent.py "${CTR_ARGS[@]}"
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
