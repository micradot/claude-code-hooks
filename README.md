# claude-code-hooks

I keep hitting the issue that Claude says one thing but then does another, especially when it's putting off work.

So - two Claude Code hooks that catch the moment Claude tries to sidestep the task at hand. Both run when Claude finishes a reply. If the reply fails the check, the hook sends Claude back to fix it before you have to.

They grew out of daily use: one person running a small business with Claude Code as chief of staff, where the expensive failures were not wrong code but small dodges that cost attention.

What it looks like (a real one, from the day this README was updated):

```text
Claude:  ...what i haven't done is read those 54 and judge how many were wrong. i'll do
         that tonight alongside the reminder-promise build. nothing needs you until i
         bring you the public-repo update to approve.

Hook:    STALL GUARD: your last message parks work or asks for a go.
         Do the work now, or name the real gate in that same paragraph.

Claude:  (reads all 54 there and then, writes up which were right and which were wrong,
         and reports the numbers in the same reply)
```

The work that was going to happen "tonight" happened a few minutes later, without being asked.

## reversible-ask-guard: the fake-gate catcher

**The problem.** Claude finishes most of a job, then ends with "want me to apply it?", "say go and I'll run it", or "I'll pick this up next session". It has everything it needs and the step is reversible, but it hands the decision back to you anyway. You end up approving things you never needed to see.

**What it does.** It reads Claude's final message for parking and asking phrases. If one appears and the same paragraph names no real reason to stop, the reply is blocked and Claude is told "do the work, or name the real gate". Real reasons are a missing fact, an external send, something irreversible, money, sensitive data, your taste, a permission wall, or a job still running. It also blocks Claude asking you to relay a message to another agent it could reach itself.

**What it leaves alone.** Real questions, drafts held for your sign-off before they go out, permission walls, finished turns, and anything inside a code block or quote.
Defaults already applied in the same paragraph may offer a narrow undo or wording swap; those decisions are logged as `allow-optout`.

**Safety.** It allows at most 4 blocks per session and warns at 3, so a misfire can never trap you in a loop. It fails open on any error, and it logs every decision so you can count false positives.

### "I'll remind you" needs something that will fire

Claude also promises to come back later: "I'll remind you", "I'll flag it when", "once they reply I'll...". A sentence is not a reminder. The same hook now checks that a calendar event or scheduled task was actually created this turn, with a matching successful tool result. Otherwise Claude has to create the calendar block with the date and the words you'll need, or say "nothing will remind you".

Code blocks, quotations, "I'll edit the file", "I'll run the tests now" and promises conditional on your next reply are left to the existing checks. "I'll check back" and "I'll follow up" need a later-time cue in the same clause, such as tomorrow, a weekday, a date or once someone replies. An immediate-work cue anywhere in that clause leaves it alone. Background Bash starts never count as completed reminders, even if Bash is configured as a create tool. This uses the same four-block cap and log. If the session record cannot be read, it fails open.

`STALL_GUARD_REMINDER_TOOLS` is a JSON list of exact create-tool names. The defaults cover `CronCreate`, `ScheduleWakeup`, `mcp__scheduled-tasks__create_scheduled_task`, `mcp__calendar__create_event`, `mcp__google_calendar__create_event` and `mcp__gcal__create_event`. Replace the list with your own connector's create tools if needed. An empty list disables these exemptions. Use create tools only, never read/list tools or general shell tools. Shell commands do not count in this version.

A successful create proves something was scheduled, not that it has the right date, recipient or text. The hook doesn't inspect those details. Check them. The session record can also lag behind a successful create, which may cause one extra nag. Misfire rates for this addition have not been measured yet.

## operating-commitment-guard: "saying a rule is not filing it"

**The problem.** Claude says "from now on I'll check the date first" or "that won't happen again". Next session it remembers none of it, because nothing was written down.

**What it does.** When the final message makes a commitment about how Claude will operate, the hook checks the session record for a write that *succeeded* this turn to a file a future session will read: `CLAUDE.md`, `AGENTS.md`, a `SKILL.md`, `MEMORY.md` or a memory folder. It also wants a marker line, `WILCO: <change> -> <path>`, so you can see at a glance what was filed and where. If either is missing, Claude goes back and files it.

**Deliberately narrow.** It fires on first-person phrases about operating ("from now on", "I'll always", "won't happen again", "my default is now"), never on task talk ("I'll edit the file"). The word "default" on its own is excluded, because in config work it names a setting ("the default will be 20%"). A missed commitment costs less than a blocked ordinary reply.

## Install

1. Copy the two `.py` hook files somewhere stable, e.g. `~/.claude/hooks/`.
2. Add the Stop entries from `settings.example.json` to `~/.claude/settings.json`, or to a project's `.claude/settings.json`. Keep `"async": false`: an async Stop hook cannot block.
3. Run `python3 tests/test_hooks.py` (from this folder) to confirm both work on your machine. Python 3.8+, standard library only.

Optional settings, both as environment variables:

| variable | hook | what it does |
|---|---|---|
| `STALL_GUARD_SCOPE` | reversible-ask-guard | colon-separated folders; only guard sessions started inside them |
| `STALL_GUARD_REMINDER_TOOLS` | reversible-ask-guard | JSON list of exact reminder-create tool names; replaces the defaults, `[]` disables exemptions |
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
