#!/usr/bin/env python3
"""Claude Code status bar — receives JSON on stdin, writes one-line status to stdout."""

import json
import os
import subprocess
import sys
import time

RESET  = "\033[0m"
EMPTY  = "\033[38;2;100;100;100m"  # #646464 — empty bar segments (dimmed)
SEP    = " • "

# ── helpers ──────────────────────────────────────────────────────────────────


def progress_bar(pct: float) -> str:
    """10-char progress bar. Both segments use █ (same glyph = same height).
    Filled = terminal default color; empty = #646464 lighter grey for contrast."""
    filled = min(10, int(pct / 10))
    empty  = 10 - filled
    return f"[{'█' * filled}{EMPTY}{'█' * empty}{RESET}]"


def colored_pct(pct: float) -> str:
    return f"{round(pct)}%"


def token_display(used: int, total: int) -> str:
    def k(n: int) -> str:
        return f"{int(n / 1000 + 0.5)}k"
    return f"{k(used)}/{k(total) if total else '200k'}"


def git_branch(cwd: str) -> str:
    if not cwd:
        return "-"
    for args in [["symbolic-ref", "--short", "HEAD"], ["rev-parse", "--short", "HEAD"]]:
        try:
            r = subprocess.run(
                ["git", "-C", cwd, "--no-optional-locks"] + args,
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    return "-"


def fmt_countdown(secs: int) -> str:
    if secs <= 0:
        return "Reset soon"
    if secs >= 3600:
        return f"Reset in {secs // 3600}h {(secs % 3600) // 60}m"
    return f"Reset in {secs // 60}m"



# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Parse JSON from Claude Code
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    # Extract fields
    model    = (data.get("model") or {}).get("display_name", "Unknown")
    ctx      = data.get("context_window") or {}
    used_pct = float(ctx.get("used_percentage") or 0)
    in_tok   = int((ctx.get("current_usage") or {}).get("input_tokens") or 0)
    ctx_size = int(ctx.get("context_window_size") or 200000)
    cwd      = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or ""

    # Real-time session usage from rate_limits.five_hour (matches Settings → Usage page).
    # Cache the last known values so restarts don't reset to 0% / 5h 0m.
    CACHE = "/tmp/claude_rate_limits_cache.json"
    five_hour = (data.get("rate_limits") or {}).get("five_hour") or {}

    if five_hour.get("resets_at"):
        # Fresh data — persist it
        try:
            with open(CACHE, "w") as f:
                json.dump(five_hour, f)
        except OSError:
            pass
    else:
        # No data yet (e.g. fresh start) — load last known values
        try:
            with open(CACHE) as f:
                five_hour = json.load(f)
        except (OSError, ValueError):
            pass

    sess_pct  = five_hour.get("used_percentage")
    resets_at = five_hour.get("resets_at")

    now  = int(time.time())
    secs = max(0, int(resets_at) - now) if resets_at else 5 * 3600

    # Build components
    bar      = progress_bar(used_pct)
    pct_s    = colored_pct(used_pct)
    tok_s    = token_display(in_tok, ctx_size)
    branch   = git_branch(cwd)
    dir_name = os.path.basename(cwd) or "-"
    cntdwn   = fmt_countdown(secs)
    sess_s   = f"{round(sess_pct)}% used" if sess_pct is not None else f"{round(used_pct)}% used"

    # Assemble the single-line output — no truncation
    line = (
        f"{model} {bar} {pct_s}"
        f"{SEP}{tok_s}"
        f"{SEP}{branch}"
        f"{SEP}{dir_name}"
        f"{SEP}{cntdwn}"
        f"{SEP}{sess_s}"
    )

    sys.stdout.write(line)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
