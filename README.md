# claude-code-hooks

I keep hitting the issue that Claude says one thing but then does another, especially when it's putting off work.

So - two Claude Code hooks that catch the moment Claude tries to sidestep the task at hand. Both run when Claude finishes a reply. If the reply fails the check, the hook sends Claude back to fix it before you have to.

They grew out of daily use: one person running a small business with Claude Code as chief of staff, where the expensive failures were not wrong code but small dodges that cost attention.

## reversible-ask-guard: the fake-gate catcher

**The problem.** Claude finishes most of a job, then ends with "want me to apply it?", "say go and I'll run it", or "I'll pick this up next session". It has everything it needs and the step is reversible, but it hands the decision back to you anyway. You end up approving things you never needed to see.

**What it does.** It reads Claude's final message for parking and asking phrases. If one appears and the same paragraph names no real reason to stop, the reply is blocked and Claude is told "do the work, or name the real gate". Real reasons are a missing fact, an external send, something irreversible, money, sensitive data, your taste, a permission wall, or a job still running. It also blocks Claude asking you to relay a message to another agent it could reach itself.

**What it leaves alone.** Real questions, drafts held for your sign-off before they go out, permission walls, finished turns, and anything inside a code block or quote.

**Safety.** It allows at most 4 blocks per session and warns at 3, so a misfire can never trap you in a loop. It fails open on any error, and it logs every decision so you can count false positives.

## operating-commitment-guard: "saying a rule is not filing it"

**The problem.** Claude says "from now on I'll check the date first" or "that won't happen again". Next session it remembers none of it, because nothing was written down.

**What it does.** When the final message makes a commitment about how Claude will operate, the hook checks the session record for a write that *succeeded* this turn to a file a future session will read: `CLAUDE.md`, `AGENTS.md`, a `SKILL.md`, `MEMORY.md` or a memory folder. It also wants a marker line, `WILCO: <change> -> <path>`, so you can see at a glance what was filed and where. If either is missing, Claude goes back and files it.

**Deliberately narrow.** It fires on first-person phrases about operating ("from now on", "I'll always", "won't happen again", "my default is now"), never on task talk ("I'll edit the file"). The word "default" on its own is excluded, because in config work it names a setting ("the default will be 20%"). A missed commitment costs less than a blocked ordinary reply.

## Install

1. Copy `hooks/` somewhere stable, e.g. `~/.claude/hooks/`.
2. Add the Stop entries from `settings.example.json` to `~/.claude/settings.json`, or to a project's `.claude/settings.json`. Keep `"async": false`: an async Stop hook cannot block.
3. Run `python3 tests/test_hooks.py` to confirm both work on your machine. Python 3.8+, standard library only.

Optional settings, both as environment variables:

| variable | hook | what it does |
|---|---|---|
| `STALL_GUARD_SCOPE` | reversible-ask-guard | colon-separated folders; only guard sessions started inside them |
| `STALL_GUARD_STATE` | reversible-ask-guard | where the log and counters live (default `~/.claude/state/stall-guard`) |
| `OPCOMMIT_MODE` | operating-commitment-guard | `block` (default) or `warn` |
| `OPCOMMIT_FILING_PATHS` | operating-commitment-guard | extra files or folders that count as filing (a changelog, a rules folder) |

## Off switch

Delete the hook's entry from `settings.json`, or set it to `"async": true`, which keeps it running but means it can no longer block.

## Honest limits

- Both work on phrase patterns. They catch the common shapes, not every way of saying something.
- Claude Code writes its session record a moment behind, so the commitment guard can occasionally nag once about a write that did land. The retry passes.
- These are seatbelts, not proofs. Read the log after a week and tune the phrases to how your Claude actually talks.

MIT licence.
