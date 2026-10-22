---
name: vibeboard
description: Maintain the user's shared Vibe Board in iTerm2. Use when the user asks to manage board tasks or progress, or when carrying out multi-step work in a pane connected to Vibe Board. Simple questions and unrelated todo services do not need board entries.
---

# Vibe Board for Codex

The board belongs to the user and is shared across agents. Keep the work you are
already authorized to do visible there; a board item does not authorize new work.

## Working with the board

- Read `vibeboard list --mine` and reuse the matching item rather than duplicating
  it after resume or context compaction. Use `vibeboard list` for the project.
- For multi-step work, create an item and useful sub-steps, then `vibeboard claim ID`.
  An item may have steps, but a step cannot have more steps.
- Record a newly discovered blocker with `--origin issue`; record new requested
  scope with `--origin added`. Keep the original plan visible.
- Keep status, `--next` and `--waiting` accurate. `me` in a waiting message means
  the human, not Codex. On finishing, mark steps done before their parent.
- Do not take over another session's items or change unrelated tasks unless asked.
  Do not mark incomplete work done just because the conversation is ending.

## Commands

```sh
vibeboard list [--all | --project PATH] [--mine] [--json]
vibeboard show ID
vibeboard add "title" [--parent ID] [--origin plan|issue|added] [--desc "details"]
vibeboard claim ID
vibeboard set ID --status waiting --waiting "me: decision needed" --next "next action"
vibeboard set ID --depends ID,ID
vibeboard done ID
```

Statuses are `todo`, `doing`, `waiting`, `later`, `done`. IDs can be the full ID,
a unique prefix, or a unique part of the title. Use `--json` for structured output.

If `vibeboard` is missing from PATH, use the absolute CLI path in the session-start
message, or `${VIBEBOARD_HOME:-$HOME/.iterm-vibe-board}/bin/vibeboard`.

## Session identity

The adapter binds Codex's `session_id` and `cwd` to the iTerm2 pane. Use
`codex --no-daemon` so the process inherits this pane's environment; a wrapper
already supplying `--no-daemon` needs no extra flag. Review new hooks with `/hooks`.
Hooks are not automatically trusted by installation.

Binding is deliberately disabled in tmux and outside iTerm2. In those environments,
use explicit `--project PATH` and leave items unassigned (`--driver none`); do not
claim an agent identity or guess a pane. If binding fails, report it briefly and
continue the user's authorized work rather than turning setup into the task.
