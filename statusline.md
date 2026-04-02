# Claude-Code-Statusline

A single-line status bar for [Claude Code](https://claude.ai/code) that shows model, context usage, git branch, session limits, and reset timer — all in real-time with no token cost.

```
Sonnet 4.6 [██████████] 29% • 1k/200k • main • myproject • Reset in 2h 52m • 38% used
```

---

## What it shows

| Segment | Source |
|---|---|
| Model name | `model.display_name` from Claude Code JSON |
| Progress bar + % | `context_window.used_percentage` (current conversation) |
| Token usage | `context_window.current_usage.input_tokens` / `context_window_size` |
| Git branch | `git symbolic-ref` from the current working directory |
| Directory | `basename` of `workspace.current_dir` |
| Reset timer | `rate_limits.five_hour.resets_at` — same as Settings → Usage page |
| Session % used | `rate_limits.five_hour.used_percentage` — same as Settings → Usage page |

> **No tokens are consumed.** Claude Code passes all data via JSON stdin each time it renders the status bar. There are no API calls.

---

## Design

- Progress bar uses `█` for both filled and empty segments (same glyph = uniform height). Filled = terminal default color, empty = dimmed `#646464`.
- No truncation — all values are shown in full.
- Separator: ` • `

---

## Install

### 1. Copy the script

```bash
curl -o ~/.claude/statusline.py \
  https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/statusline.py
chmod +x ~/.claude/statusline.py
```

Or manually copy `statusline.py` to `~/.claude/statusline.py`.

### 2. Edit `~/.claude/settings.json`

Add (or update) the `statusLine` key:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/YOUR_USERNAME/.claude/statusline.py"
  }
}
```

Replace `YOUR_USERNAME` with your macOS username (run `whoami` if unsure).

### 3. Restart Claude Code

The status bar appears immediately after restarting.

---

## Requirements

- macOS (tested) or Linux
- Python 3 (pre-installed on macOS)
- Claude Code CLI ≥ 2.1.x (needs `rate_limits` field in statusline JSON — introduced around v2.1.6)
- `git` in `$PATH` (optional — shows `-` if not available)

---

## Script (`statusline.py`)

```python
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


def main() -> None:
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    model    = (data.get("model") or {}).get("display_name", "Unknown")
    ctx      = data.get("context_window") or {}
    used_pct = float(ctx.get("used_percentage") or 0)
    in_tok   = int((ctx.get("current_usage") or {}).get("input_tokens") or 0)
    ctx_size = int(ctx.get("context_window_size") or 200000)
    cwd      = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or ""

    # Real-time session usage from rate_limits.five_hour (matches Settings → Usage page)
    five_hour = (data.get("rate_limits") or {}).get("five_hour") or {}
    sess_pct  = five_hour.get("used_percentage")
    resets_at = five_hour.get("resets_at")

    now  = int(time.time())
    secs = max(0, int(resets_at) - now) if resets_at else 5 * 3600

    bar      = progress_bar(used_pct)
    pct_s    = colored_pct(used_pct)
    tok_s    = token_display(in_tok, ctx_size)
    branch   = git_branch(cwd)
    dir_name = os.path.basename(cwd) or "-"
    cntdwn   = fmt_countdown(secs)
    sess_s   = f"{round(sess_pct)}% used" if sess_pct is not None else f"{round(used_pct)}% used"

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
```

---

## Known Issues & Fixes

### Session data shows 0% / Reset in 5h 0m on startup

**Symptom:** Right after launching Claude Code, the status bar shows `Reset in 5h 0m • 0% used` even though the Settings → Usage page shows the correct values (e.g. `Resets in 2h 27min • 58% used`).

**Root cause:** Claude Code only populates `rate_limits` in the statusline JSON after the first API call in a session. On a fresh start (idle screen, no conversation yet), the field is absent — so the script had no data and fell back to defaults.

**Fix:** Cache the last known `rate_limits.five_hour` values to `/tmp/claude_rate_limits_cache.json` whenever real data is received. On the next startup (before any API call), load from the cache instead of defaulting to zero.

```python
CACHE = "/tmp/claude_rate_limits_cache.json"
five_hour = (data.get("rate_limits") or {}).get("five_hour") or {}

if five_hour.get("resets_at"):
    # Fresh data — persist it
    with open(CACHE, "w") as f:
        json.dump(five_hour, f)
else:
    # No data yet (fresh start) — restore last known values
    try:
        with open(CACHE) as f:
            five_hour = json.load(f)
    except (OSError, ValueError):
        pass
```

The `resets_at` value is an absolute epoch timestamp, so the countdown remains accurate even when served from cache.

---

## Files

| File | Purpose |
|---|---|
| `~/.claude/statusline.py` | The status bar script |
| `~/.claude/settings.json` | Points Claude Code to the script via `statusLine.command` |
| `/tmp/claude_rate_limits_cache.json` | Runtime cache for session data (auto-created) |
