# Agent session review

Status: in progress since 2026-11-13. This replaces the triage-agent and Nitro ideas, and supersedes the span-store design in `observe-optimize.md` for now.

## Problem

**Coding agents start every session with no memory of the machine they run on, so they keep making the same mistakes.** They call a program that isn't installed, use the wrong Python, or trip over a shell quirk. Each failure is cheap on its own, but the agent repeats it in the next session, and the one after. Nobody notices, because the evidence is spread across transcripts thousands of lines long.

The logs that would show this already sit on the developer's machine. Claude Code writes JSONL under `~/.claude/projects`, and OpenCode exports each session as JSON. Nobody reads them.

**Orchestra Review reads those local logs and finds the mistakes that recur across sessions, with step-level evidence, so that each one can become a single line in `AGENTS.md` or `CLAUDE.md`.** It also flags waste inside a session. Nothing is uploaded.

The user is a developer or founder who builds with Claude Code or OpenCode. The question it answers is: *what does my agent keep getting wrong, and what one line would stop it?*

### Why this framing: the first run on real data (2026-11-13)

The first version led with waste inside a session. On the author's own 24 sessions (3,576 tool calls), that rule found almost nothing: blind retries and unchanged repeats were zero once permission denials stopped counting as failures. Agents rarely loop inside one session.

What did stand out was repetition *across* sessions. 32 of the 69 failed steps (46%) matched a mistake seen in another session. Examples:
- PDF reads failing because `pdftoppm` is not installed (8 sessions);
- `No module named 'fitz'` (5 sessions);
- zsh treating `echo ====` as `=` expansion (several sessions).

Each of these has a one-line fix, and none of them is visible from inside a single session.

## What counts as waste

The definitions are deliberately narrow, so that every flagged step can be defended:

| Finding | Rule | Wasted steps |
| --- | --- | --- |
| Recurring mistake | Failures in 2 or more sessions share the same last error line, ignoring numbers, ids and runs of `=` | Reported as failed steps across sessions. Each one is a candidate for a line in `AGENTS.md` or `CLAUDE.md`. Bare "Exit code N" lines are ignored because they say nothing about the cause. |
| Blind retry | The same tool and target fails again with identical output, and no edit or successful shell or harness call happened in between | The blind retries. A fix-and-rerun loop is never counted. |
| Unchanged repeat | The same read, search, web or shell call returns identical output 3 or more times within 15 steps | Every occurrence after the first |
| Failure streak | 4 or more failed steps in a row | Shown as evidence; adds no wasted steps, to avoid double counting |

Wasted steps are the union of blind retries and unchanged repeats. Claude Code calls refused by a permission rule or the auto-mode classifier, or interrupted by the user, are counted as blocked, not failed.

## Honesty rules

- Tokens and cost appear only where the source records them. OpenCode records cost for each message. Claude Code records it only in an occasional `cost-state` entry; otherwise cost is reported as unknown, never estimated from a price table.
- Assistant entries in Claude Code repeat usage for each content block. Usage is counted once per `message.id`.
- Lines that cannot be parsed are counted and reported, not hidden.
- Evidence shown in the report is redacted for likely secrets (bearer tokens, `KEY=value` assignments, long hex or base64 strings, and known key prefixes). People will screenshot it.

## Shape

- A standalone Python package, `review/` (`orchestra_review`), using only the standard library and supporting Python 3.11 or later. It installs with `pipx install ./review` or runs as `python -m orchestra_review`. It does not need Docker or the control-plane stack.
- Importers turn each source into one session model: a list of steps (tool, kind, target, ok, exit code, output digest, timestamp) plus usage.
- Detectors work only on that model, so a new agent source needs only a new importer.
- The command-line tool prints a text report or `--json`.

## Acceptance for the first slice (met 2026-11-13; see `docs/PROGRESS.md`)

1. `python -m orchestra_review` prints a report from the real Claude Code and OpenCode sessions on this Mac.
2. Each finding names the session, the step numbers and a redacted excerpt of the target and error.
3. Unknown cost is shown as unknown.
4. Unit tests cover both importers (from synthetic fixtures), every detector, deduplicated usage, blocked calls and redaction. They run with pytest in the API container (Python 3.11) and in CI.

## Second slice: fixes and measurement (built 2026-11-13)

1. **One suggested line per recurring mistake.**
   - Known causes get a fixed rule: a missing program, a Python module that can't be imported, zsh `=` expansion, and zsh globs that match nothing.
   - For any other cause, a local Ollama model can draft a line (`--model`). The evidence goes to the model inside `<evidence>` tags as redacted data.
   - A draft is kept only if it is 20–220 characters, names a distinctive word from the cause, and has no URL or download, delete, `sudo`, `eval` or base64 pattern. This matters because log text is untrusted, and the line ends up in a file the agent obeys.
2. **`apply`** appends chosen lines with a marker `<!-- orchestra-review:<id> <date> -->`.
   - It writes each line once.
   - It refuses drafted lines unless `--include-drafted` is passed.
3. **Measurement.** Each marker is matched to the sessions that read its file:
   - the Claude Code global file governs Claude Code sessions;
   - the OpenCode global file governs OpenCode sessions;
   - a project file governs that project's sessions.

   The report compares sessions that hit the mistake before and after the date. Below 5 sessions afterwards, it reports "too early".

## Next

- **Applied 2026-11-13T17:58Z:** the six rule-based lines went into `~/.claude/CLAUDE.md`, with the owner's approval. Baseline: 8, 5, 5, 5, 2 and 2 of 20 Claude Code sessions hit these mistakes before. Let sessions accumulate until the comparison stops reading "too early".
- **Exposure (built 2026-11-13):** each fix rule also defines which steps *attempted* the action:
  - shell commands that mention the module or program;
  - Read calls on `.pdf` files;
  - shell commands with a word starting with `=`;
  - shell commands with a glob.

  Before and after both count only sessions that tried the action, and the verdict stays "too early" until 5 such sessions follow the marker. Sessions that hit the mistake always count as having tried it. These are approximations; for example, `[[ a == b ]]` is safe in zsh but still counts as an attempt.
- Verify the model drafter against a real model. The Nitro's Ollama is not reachable over Tailscale yet, and the Mac has none.
- A plain-language explanation of in-session findings from a model, which must cite step numbers.
- A view in the dashboard.
- Before-and-after measurement: add a suggested instruction, then compare waste in later sessions.
- A README rewrite and the LinkedIn post, written once there are real numbers.
