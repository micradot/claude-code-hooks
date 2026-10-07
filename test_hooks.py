#!/usr/bin/env python3
"""Run: python3 test_hooks.py   (no dependencies)"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = HERE
STALL = os.path.join(HOOKS, "reversible-ask-guard.py")
OPC = os.path.join(HOOKS, "operating-commitment-guard.py")
STATE = tempfile.mkdtemp()
fails = 0


def run(hook, payload, env=None):
    e = dict(os.environ, STALL_GUARD_STATE=STATE, **(env or {}))
    p = subprocess.run([sys.executable, hook], input=json.dumps(payload), capture_output=True, text=True, env=e)
    return p.returncode


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(("PASS" if ok else "FAIL"), label, f"(want {want}, got {got})")


n = 0
def stall(text, **kw):
    global n
    n += 1
    return run(STALL, {"session_id": f"s{n}", "cwd": "/tmp", "last_assistant_message": text, **kw})


print("-- reversible-ask-guard")
check("parks work with no gate -> block", stall("Done with the first half.\n\nI'll do the rest next."), 2)
check("asks for an unneeded go -> block", stall("The fix is ready. Want me to apply it?"), 2)
check("relay to another agent -> block", stall("Codex has the brief. Tell codex: run the tests."), 2)
check("ask with a real gate (external send) -> allow", stall("Draft is below. Want me to send it to the supplier? It goes out under your name."), 0)
check("finished turn -> allow", stall("Fixed the bug and the tests pass. Undo: git revert abc123."), 0)
check("ask inside a code fence is ignored -> allow", stall("Here is the template:\n\n```\nwant me to run this?\n```\n\nApplied."), 0)
check("stop_hook_active -> allow", stall("Want me to apply it?", stop_hook_active=True), 0)
check("out of scope cwd -> allow",
      run(STALL, {"session_id": "scope", "cwd": "/tmp", "last_assistant_message": "Want me to apply it?"},
          env={"STALL_GUARD_SCOPE": "/nonexistent-root"}), 0)
capped = [run(STALL, {"session_id": "cap", "cwd": "/tmp", "last_assistant_message": "Shall I?"}) for _ in range(6)]
check("cap stops blocking after 4", capped, [2, 2, 2, 2, 0, 0])


def transcript(records):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return path


def turn(write_path=None, error=False):
    recs = [{"type": "user", "message": {"role": "user", "content": "please fix it"}}]
    if write_path:
        recs.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": write_path}}]}})
        res = {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
        if error:
            res["is_error"] = True
        recs.append({"type": "user", "message": {"content": [res]}})
    return transcript(recs)


cwd = tempfile.mkdtemp()
claude_md = os.path.join(cwd, "CLAUDE.md")
open(claude_md, "w").close()
m = 0
def opc(text, tpath):
    global m
    m += 1
    return run(OPC, {"session_id": f"o{m}", "cwd": cwd, "transcript_path": tpath, "last_assistant_message": text})


print("-- operating-commitment-guard")
check("commitment, nothing filed, no marker -> block", opc("Sorry. From now on I'll check the date first.", turn()), 2)
check("commitment, filed but no marker -> block", opc("From now on I'll check the date first.", turn(claude_md)), 2)
check("commitment, filed + WILCO -> allow", opc("From now on I'll check the date first.\nWILCO: date check -> CLAUDE.md", turn(claude_md)), 0)
check("filing write that FAILED does not count -> block", opc("I'll always check.\nWILCO: check -> CLAUDE.md", turn(claude_md, error=True)), 2)
check("write to an ordinary file does not count -> block", opc("I'll always check.\nWILCO: x -> y", turn(os.path.join(cwd, "notes.md"))), 2)
check("task talk is not a commitment -> allow", opc("I'll edit the config file and grab the value from here.", turn()), 0)
check("'the default will be 20%' is not a commitment -> allow", opc("Going forward, the default will be 20% after sunset.", turn()), 0)
check("warn mode never blocks", run(OPC, {"session_id": "w", "cwd": cwd, "transcript_path": turn(), "last_assistant_message": "From now on I'll check."}, env={"OPCOMMIT_MODE": "warn"}), 0)
check("extra filing path counts",
      run(OPC, {"session_id": "x", "cwd": cwd, "transcript_path": turn("/var/tmp/rules/log.md"),
                "last_assistant_message": "From now on I'll log it.\nWILCO: log -> rules"},
          env={"OPCOMMIT_FILING_PATHS": "/var/tmp/rules"}), 0)

print("\nall passed" if not fails else f"\n{fails} failed")
sys.exit(1 if fails else 0)
