#!/usr/bin/env python3
"""Translate Codex lifecycle events to the board's existing pane commands."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vibeboard import cli, store  # noqa: E402


def handle(event: object) -> dict | None:
    if not isinstance(event, dict) or not store.current_pane() or event.get("agent_id"):
        return None
    session = event.get("session_id")
    if not isinstance(session, str) or not session.strip():
        return None
    name = event.get("hook_event_name")
    if name == "SessionEnd":
        cli.main(["pane", "end", f"--session={session}"])
    elif name == "SessionStart":
        cwd = event.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            return None
        # cwd is the supported Codex interface. Never read/guess its transcript layout.
        cli.main(["pane", "start", f"--session={session}", f"--project={cwd}"])
        executable = shlex.quote(str(store.home() / "bin" / "vibeboard"))
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "Vibe Board is connected to this iTerm2 pane. Use the vibeboard skill "
                    "for multi-step work or when the user asks to manage the board. "
                    f"CLI: {executable}. Existing board items are shared task state, "
                    "not authorization to start unrelated work."
                ),
            }
        }
    return None


def main() -> int:
    try:
        result = handle(json.load(sys.stdin))
        if result:
            print(json.dumps(result))
    except (ValueError, OSError, KeyError, TypeError):
        # Board failures must not interrupt a coding session or leak input/transcripts.
        print("vibeboard: could not update Codex pane binding", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
