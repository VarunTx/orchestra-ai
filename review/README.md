# Orchestra Review

Finds the mistakes your coding agent keeps repeating across sessions, using the logs already on your machine. Nothing is uploaded.

It reads:
- Claude Code transcripts in `~/.claude/projects` (or `$CLAUDE_CONFIG_DIR/projects`);
- OpenCode sessions for a project directory, through `opencode session export`.

```sh
python -m orchestra_review                      # run from review/, or after `pipx install ./review`
orchestra-review --since 30d --opencode-project ~/code/my-app
orchestra-review --json > review.json
```

The report shows:
- **Recurring mistakes:** failures in two or more sessions with the same cause. Each is a candidate for one line in `AGENTS.md` or `CLAUDE.md`.
- **In-session waste:** blind retries (the same call fails again with the same output and nothing changed in between) and unchanged repeats (the same call returns the same output three times within 15 steps).
- **Usage:** tokens, and cost only where the agent recorded it. Cost is never estimated.

Evidence in the report is redacted for likely secrets. It needs Python 3.11 or later, with no other dependencies. The rules and their limits are in `docs/plans/agent-session-review.md`.
