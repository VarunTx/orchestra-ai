# Orchestra Review

Finds the mistakes your coding agent keeps repeating across sessions, using the logs already on your machine. Nothing is uploaded.

It reads:
- Claude Code transcripts in `~/.claude/projects` (or `$CLAUDE_CONFIG_DIR/projects`);
- OpenCode sessions for a project directory, through `opencode session export`.

```sh
python -m orchestra_review                      # run from review/, or after `pipx install ./review`
orchestra-review --since 30d --opencode-project ~/code/my-app
orchestra-review --json > review.json
orchestra-review apply <id> --to ~/.claude/CLAUDE.md   # write a suggested line with a dated marker
orchestra-review --model qwen3:4b --model-url http://localhost:11434   # let a local model draft lines no rule covers
```

The report shows:
- **Recurring mistakes:** failures in two or more sessions with the same cause. Each is a candidate for one line in `AGENTS.md` or `CLAUDE.md`.
- **In-session waste:** blind retries (the same call fails again with the same output and nothing changed in between) and unchanged repeats (the same call returns the same output three times within 15 steps).
- **Usage:** tokens, and cost only where the agent recorded it. Cost is never estimated.
- **Suggested lines:** one per recurring mistake. They come from a rule, or are drafted by a local model when one is configured. A drafted line is kept only if it names the cause and contains no URL or command that downloads or deletes anything. `apply` writes drafted lines only with `--include-drafted`.
- **Fixes in place:** for each marked line in `~/.claude/CLAUDE.md`, the OpenCode global `AGENTS.md`, or a project's `AGENTS.md` or `CLAUDE.md`, how many sessions that read the file hit the mistake before and after the line was added.

Evidence in the report is redacted for likely secrets. It needs Python 3.11 or later, with no other dependencies. The rules and their limits are in `docs/plans/agent-session-review.md`.
