#!/usr/bin/env python3
"""Run run_audit.py with a wall-clock timeout (portable replacement for GNU `timeout`).

macOS does not ship `timeout` or `gtimeout`; coreutils is brew-only.
This wrapper delegates to subprocess.run with a configurable timeout
and propagates the audit's exit code (or 124 on timeout, matching GNU).

Usage:
  python3 run_audit_with_timeout.py --timeout 900 -- <run_audit.py args...>

The `--` separates wrapper args from the args passed to run_audit.py.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> int:
    if "--" not in sys.argv:
        sys.stderr.write("ERROR: missing `--` separator before run_audit.py args\n")
        return 2

    sep = sys.argv.index("--")
    wrapper_argv = sys.argv[1:sep]
    audit_argv = sys.argv[sep + 1 :]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=900, help="Wall-clock seconds (default 900 = 15min)")
    args = parser.parse_args(wrapper_argv)

    here = os.path.dirname(os.path.abspath(__file__))
    audit_script = os.path.join(here, "run_audit.py")
    if not os.path.exists(audit_script):
        sys.stderr.write(f"ERROR: run_audit.py not found next to wrapper at {audit_script}\n")
        return 2

    cmd = [sys.executable, "-u", audit_script] + audit_argv
    try:
        result = subprocess.run(cmd, timeout=args.timeout, check=False)
        return result.returncode
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"\n[timeout] audit exceeded {args.timeout}s wall clock; killed.\n")
        return 124


if __name__ == "__main__":
    sys.exit(main())
