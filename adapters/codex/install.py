#!/usr/bin/env python3
"""Install only the Codex adapter; install.sh owns the shared CLI and panel."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shlex
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = "Vibe Board: bind Codex session"


def merge_hooks(settings: dict, command: str, *, uninstall: bool) -> dict:
    """Remove only our handlers, preserving mixed groups and all other configuration."""
    result = copy.deepcopy(settings)
    hooks = result.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    for event in ("SessionStart", "SessionEnd"):
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise ValueError(f"{event} must be a list")
        kept = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"invalid {event} hook group")
            handlers = group["hooks"]
            if any(not isinstance(h, dict) for h in handlers):
                raise ValueError(f"invalid {event} hook handler")
            remaining = [
                h
                for h in handlers
                if h.get("statusMessage") != STATUS and h.get("command") != command
            ]
            if remaining:
                kept.append({**group, "hooks": remaining})
        if not uninstall:
            kept.append(
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 3,
                            "statusMessage": STATUS,
                        }
                    ]
                }
            )
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if not hooks:
        result.pop("hooks", None)
    return result


def configure(config_dir: Path, *, uninstall: bool = False) -> None:
    settings_path = config_dir / "hooks.json"
    skill = config_dir / "skills" / "vibeboard"
    source = ROOT / "adapters" / "codex" / "skills" / "vibeboard"
    command = shlex.join([sys.executable, str(ROOT / "adapters" / "codex" / "hook.py")])
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError("hooks.json must contain an object; no files changed")
    updated = merge_hooks(settings, command, uninstall=uninstall)
    if skill.exists() or skill.is_symlink():
        if not skill.is_symlink() or not str(skill.resolve()).endswith(
            "/adapters/codex/skills/vibeboard"
        ):
            raise ValueError(f"refusing to replace an unrelated skill: {skill}")
    # Validate every input before touching either configuration or the skill link.
    if updated != settings:
        config_dir.mkdir(parents=True, exist_ok=True)
        mode = stat.S_IMODE(settings_path.stat().st_mode) if settings_path.exists() else 0o600
        fd, tmp = tempfile.mkstemp(dir=config_dir, prefix=".vibeboard-hooks-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(updated, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
            os.chmod(tmp, mode)
            os.replace(tmp, settings_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    if skill.is_symlink():
        skill.unlink()
    if not uninstall:
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.symlink_to(source, target_is_directory=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    config_dir = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    try:
        configure(config_dir, uninstall=args.uninstall)
    except (ValueError, OSError) as error:
        print(f"Codex adapter: {error}", file=sys.stderr)
        return 1
    print(f"Codex adapter {'removed from' if args.uninstall else 'installed in'} {config_dir}")
    if not args.uninstall:
        print("In Codex CLI, open /hooks to review and trust the two Vibe Board hooks.")
        print("Run codex --no-daemon in iTerm2 so each session inherits its own pane environment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
