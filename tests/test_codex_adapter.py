import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from adapters.codex import install
from vibeboard import store

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "adapters" / "codex" / "hook.py"


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBEBOARD_HOME", str(tmp_path / "board"))
    monkeypatch.setenv("TERM_SESSION_ID", "w0t1p0:abc-123")
    monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
    monkeypatch.delenv("TMUX", raising=False)
    return tmp_path / "board"


def fire(event):
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(result.stdout) if result.stdout else None


def command(*args):
    result = subprocess.run(
        [sys.executable, "-m", "vibeboard", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_codex_lifecycle_and_task_ownership(board, tmp_path):
    project = tmp_path / "project with spaces"
    event = {"hook_event_name": "SessionStart", "session_id": "codex-1", "cwd": str(project)}
    output = fire(event)
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert store.identity() == ("codex-1", str(project))
    item = command("add", "Implement the feature", "--json")
    assert item["driver"] == item["created_by"] == "codex-1"
    assert item["project"] == str(project)
    command("claim", item["id"], "--json")
    assert command("list", "--mine", "--json")[0]["status"] == "doing"
    started = store.get_pane("ABC-123")["started_at"]
    fire({**event, "source": "compact", "transcript_path": "/not/a/claude/transcript.jsonl"})
    assert store.get_pane("ABC-123")["started_at"] == started
    assert len(command("list", "--mine", "--json")) == 1
    assert command("done", item["id"], "--json")["status"] == "done"
    assert fire({"hook_event_name": "SessionEnd", "session_id": "codex-1"}) is None
    assert store.identity() == (store.ME, None)
    assert store.get(item["id"])["driver"] == "codex-1"  # history survives exit


def test_resume_and_two_panes_stay_separate(board, monkeypatch):
    event = {"hook_event_name": "SessionStart", "session_id": "first", "cwd": "/project/a"}
    fire(event)
    monkeypatch.setenv("TERM_SESSION_ID", "w0t1p1:def-456")
    fire({**event, "session_id": "second", "cwd": "/project/b"})
    assert store.identity() == ("second", "/project/b")
    assert store.get_pane("ABC-123")["session"] == "first"
    # A stale end event must not clear another session's current binding.
    fire({"hook_event_name": "SessionEnd", "session_id": "first"})
    assert store.identity() == ("second", "/project/b")
    fire({"hook_event_name": "SessionEnd", "session_id": "second"})
    fire({**event, "session_id": "second", "cwd": "/project/b", "source": "resume"})
    assert store.get_pane("DEF-456")["ended_at"] is None


def test_nested_codex_returns_pane_to_existing_agent(board):
    store.set_pane("ABC-123", session="claude-outer", project="/project", started_at=store.now())
    fire({"hook_event_name": "SessionStart", "session_id": "codex-inner", "cwd": "/project/sub"})
    assert store.identity()[0] == "codex-inner"
    fire({"hook_event_name": "SessionEnd", "session_id": "codex-inner"})
    assert store.identity() == ("claude-outer", "/project")


@pytest.mark.parametrize("environment", ["tmux", "no-pane"])
def test_does_not_invent_pane_identity(board, monkeypatch, environment):
    if environment == "tmux":
        monkeypatch.setenv("TMUX", "/tmp/a-tmux-socket")
    else:
        monkeypatch.delenv("TERM_SESSION_ID")
    assert fire({"hook_event_name": "SessionStart", "session_id": "x", "cwd": "/project"}) is None
    assert not (board / "panes").exists()


@pytest.mark.parametrize(
    "event",
    [
        None,
        [],
        {},
        {"session_id": 12},
        {
            "hook_event_name": "SessionStart",
            "session_id": "x",
            "cwd": "relative",
        },
        {
            "hook_event_name": "SessionStart",
            "session_id": "x",
            "cwd": "/p",
            "agent_id": "sub",
        },
    ],
)
def test_ignores_incomplete_or_non_root_events(board, event):
    assert fire(event) is None
    assert not (board / "panes").exists()


def test_board_failure_does_not_break_codex(board):
    board.write_text("not a directory")
    assert fire({"hook_event_name": "SessionStart", "session_id": "x", "cwd": "/p"}) is None


def test_install_is_idempotent_and_preserves_other_hooks(tmp_path):
    config_dir = tmp_path / "custom codex home"
    config_dir.mkdir()
    path = config_dir / "hooks.json"
    existing = {
        "description": "user-owned",
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "existing-stop"}]}],
            "SessionStart": [
                {
                    "matcher": "resume",
                    "hooks": [
                        {"type": "command", "command": "keep-me"},
                        {
                            "type": "command",
                            "command": "old-board-hook",
                            "statusMessage": install.STATUS,
                        },
                    ],
                }
            ],
        },
    }
    path.write_text(json.dumps(existing))
    os.chmod(path, 0o600)
    install.configure(config_dir)
    first = path.read_text()
    install.configure(config_dir)
    assert path.read_text() == first
    data = json.loads(first)
    assert data["description"] == "user-owned"
    assert data["hooks"]["Stop"] == existing["hooks"]["Stop"]
    assert data["hooks"]["SessionStart"][0] == {
        "matcher": "resume",
        "hooks": [{"type": "command", "command": "keep-me"}],
    }
    added = data["hooks"]["SessionStart"][-1]["hooks"][0]
    assert shlex.split(added["command"])[1] == str(HOOK)
    assert path.stat().st_mode & 0o777 == 0o600
    skill = config_dir / "skills" / "vibeboard"
    assert (skill / "SKILL.md").is_file()
    install.configure(config_dir, uninstall=True)
    data = json.loads(path.read_text())
    assert data["hooks"]["Stop"] == existing["hooks"]["Stop"]
    assert data["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "keep-me"
    assert "SessionEnd" not in data["hooks"]
    assert not skill.exists()


def test_invalid_config_is_never_overwritten(tmp_path):
    path = tmp_path / "hooks.json"
    path.write_text("{broken")
    with pytest.raises(ValueError):
        install.configure(tmp_path)
    assert path.read_text() == "{broken"
    assert not (tmp_path / "skills").exists()


def test_existing_skill_is_not_replaced(tmp_path):
    skill = tmp_path / "skills" / "vibeboard"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("user's own skill")
    with pytest.raises(ValueError, match="unrelated skill"):
        install.configure(tmp_path)
    assert not (tmp_path / "hooks.json").exists()
    assert (skill / "SKILL.md").read_text() == "user's own skill"
