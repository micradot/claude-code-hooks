#!/usr/bin/env python3
"""Run: python3 test_hooks.py   (no dependencies)"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
STALL = os.path.join(HOOKS, "reversible-ask-guard.py")
OPC = os.path.join(HOOKS, "operating-commitment-guard.py")
STATE = tempfile.mkdtemp()
fails = 0
total = 0


def run(hook, payload, env=None):
    if hook == STALL:
        check_relaxation(payload.get("last_assistant_message", ""))
    payload = dict(payload, session_id=os.path.basename(STATE) + "-" + payload.get("session_id", "test"))
    e = dict(os.environ, STALL_GUARD_STATE=STATE, **(env or {}))
    p = subprocess.run([sys.executable, hook], input=json.dumps(payload), capture_output=True, text=True, env=e)
    return p.returncode


def check(label, got, want):
    global fails, total
    total += 1
    ok = got == want
    fails += not ok
    print(("PASS" if ok else "FAIL"), label, f"(want {want}, got {got})")


# Actual preimage oracle: no synthetic input may acquire a new block.
import runpy
_CANDIDATE = runpy.run_path(STALL)
_BASELINE = runpy.run_path(os.path.join(HERE, "pre_optout_stall.py"))

def check_relaxation(text):
    old = _BASELINE["judge"](text)[0]
    new = _CANDIDATE["judge"](text)[0]
    (lambda ok, label: check(label, ok, True))(new == old or new == "allow-optout",
                      f"relax-only: old={old}, new={new}")


n = 0
def stall(text, **kw):
    global n
    n += 1
    return run(STALL, {"session_id": f"s{n}", "cwd": "/tmp", "last_assistant_message": text, **kw})



# Applied defaults offer reversal only, never permission for new work.
optout_path = os.path.join(STATE, "optout-synthetic.jsonl")
with open(optout_path, "w") as handle:
    handle.write(json.dumps({"type": "user", "message": {"content": "edit the heading"}}) + "\n")
OPTOUT_CASES = [('apply then swap back', "I've applied the shorter heading. If you'd rather the longer one, say so and I'll swap it back.", 0), ('kept then unless', 'I kept the existing wording, unless you want it changed.', 0), ('took it to mean then say so', "I took it to mean the current draft. Say so and I'll change it back.", 0), ('left as is then rather', "I left it as the current draft. If you'd rather the other wording, say so.", 0), ('new work despite completion', "Done: I kept the draft. If you want it standing for future read-alouds, say so and I'll add it to the skill.", 2), ('nothing applied', "If you'd rather the longer heading, say so and I'll swap it back.", 2), ('say go despite completion', "I've applied the heading. Say go and I'll do it.", 2), ('banned in same paragraph', "I've applied the heading. Say so and I'll swap it back. Nothing needs you.", 2), ('undo verb', "Done: wording applied. Say so and I'll undo it.", 0), ('put back verb', "I went with the short heading. Say so and I'll put it back.", 0), ('revert verb', "I set it to the current value. Say so and I'll revert it.", 0), ('drop verb', "I spelled it the usual way. Say so and I'll drop it.", 0), ('unchanged default', 'The heading stays as it is, unless you want it changed.', 0), ('curly contraction', 'I’ve applied the heading. Say so and I’ll swap it back.', 0), ('different paragraphs', "I've applied the heading.\n\nSay so and I'll swap it back.", 2), ('additional ask', "I've applied the heading. Say so and I'll swap it back. Want me to update the rest?", 2), ('second same trigger', "I've applied the heading. Say so and I'll swap it back. Say go and I'll do the rest.", 2), ('not done', "Not done: the heading is ready. Say so and I'll swap it back.", 2), ('future evidence', "I will have it done. Say so and I'll swap it back.", 2), ('have not applied', "I haven't applied it yet. Say so and I'll swap it back.", 2), ('quoted evidence', 'The example was "I kept the heading". Say so and I\'ll swap it back.', 2), ('reversal plus new work', "I've applied the heading. Say so and I'll swap it back and add the rest.", 2), ('applied after offer', "Say so and I'll swap it back. I've applied the heading.", 2), ('got is not applied', "I've got the draft ready. Say so and I'll swap it back.", 2)]
OPTOUT_CASES.extend([('rather without applied default', "If you'd rather the longer heading, say so.", 0), ('rather offers new work', "I've applied the heading. If you'd rather add it to the skill, say so.", 0), ('done nothing', "I've done nothing yet. Say so and I'll swap it back.", 2), ('future check still blocks', "I've applied the heading. Say so and I'll swap it back. I'll remind you tomorrow.", 2), ('different paragraph ask', "I've applied the heading. Say so and I'll swap it back.\n\nWant me to do the rest?", 2)])
OPTOUT_CASES.extend([('meaning already chosen', 'The label is compact, which I took to be what you meant. Say so and I will drop it.', 0), ('would rather keep', 'I renamed the heading. If you would rather keep the earlier wording, say so.', 0), ('quoted alternative', "I kept the direction north. If you did mean 'south', say so and I'll swap it back.", 0), ('double quoted alternative', 'I took the direction to mean north. If you did mean "south", say so and I will switch it back.', 2), ('curly quoted alternative', 'I chose north. If you did mean ‘south’, say so and I’ll change it back.', 2), ('prefer alternative', 'I left the heading short. If you prefer the earlier wording, say so.', 0), ('contracted rather', "I kept it compact. If you'd rather the earlier wording, say so.", 0), ('quoted chosen default', "I chose 'compact' for the label. Say so and I'll undo it.", 2), ('renamed noun reverse', "I renamed the heading. Say so and I'll rename the heading back.", 0), ('bare reverse switch', "I went with compact wording. Say so and I'll switch back.", 0), ('new work exclusion without old trigger', 'I kept the draft. If you would rather build a new page, say so.', 0), ('new work exclusion with old trigger', "I kept the draft. If you would rather build a new page, say so and I'll swap it back.", 2), ('quoted offer is not optout', 'I kept the draft. The sample says "if you would rather keep it, say so".', 0), ('meaning not applied yet', "I could take it to be the short heading. Say so and I'll undo it.", 2), ('negated meaning', "I never took it to be the short heading. Say so and I'll undo it.", 2), ('quoted completion noun', 'The sample says "I chose compact". Say so and I\'ll change it back.', 2), ('scope creep exact shape', "If you'd rather keep the old name, say so.", 0), ('past action took', "I took the direction to mean north. Say so and I'll swap it back.", 2), ('past action kept', "I kept that. Say so and I'll swap it back.", 0), ('past action left', "I left them alone. Say so and I'll swap it back.", 0), ('past action went with', "I went with the heading. Say so and I'll swap it back.", 0), ('past action used', "I used it. Say so and I'll swap it back.", 2), ('past action chose', "I chose a shorter heading. Say so and I'll swap it back.", 2), ('past action spelled', "I spelled the title compactly. Say so and I'll swap it back.", 0), ('past action set', "I set the heading to compact. Say so and I'll swap it back.", 0), ('past action applied', "I applied the shorter heading. Say so and I'll swap it back.", 0), ('past action dropped', "I dropped the extra word. Say so and I'll swap it back.", 0), ('past action renamed', "I renamed the heading. Say so and I'll swap it back.", 0), ('participle applied', "I've applied the compact form. Say so and I will revert it.", 0), ('participle chosen', "I've chosen the compact form. Say so and I will revert it.", 2), ('participle used', "I've used the compact form. Say so and I will revert it.", 2), ('participle set', "I've set the compact form. Say so and I will revert it.", 0), ('participle kept', "I've kept the compact form. Say so and I will revert it.", 0), ('participle left', "I've left the compact form. Say so and I will revert it.", 0), ('participle spelled', "I've spelled the compact form. Say so and I will revert it.", 0), ('participle taken', "I've taken the compact form. Say so and I will revert it.", 2), ('participle gone', "I've gone with the compact form. Say so and I will revert it.", 2), ('participle done', "I've done the heading in the compact form. Say so and I will revert it.", 0), ('participle dropped', "I've dropped the compact form. Say so and I will revert it.", 0), ('participle renamed', "I've renamed the compact form. Say so and I will revert it.", 0), ('reverse form swap the title back', 'I used the compact heading. Say so and I will swap the title back.', 2), ('reverse form change the wording', 'I used the compact heading. Say so and I will change the wording.', 2), ('reverse form put the title back', 'I used the compact heading. Say so and I will put the title back.', 2), ('reverse form undo', 'I used the compact heading. Say so and I will undo.', 2), ('reverse form drop it', 'I used the compact heading. Say so and I will drop it.', 2), ('reverse form revert', 'I used the compact heading. Say so and I will revert.', 2), ('reverse form switch the wording back', 'I used the compact heading. Say so and I will switch the wording back.', 2), ('reverse form rename back', 'I used the compact heading. Say so and I will rename back.', 2), ('new-work word add', "I kept the heading. If you would rather add another item, say so and I'll swap it back.", 2), ('new-work word build', "I kept the heading. If you would rather build another item, say so and I'll swap it back.", 2), ('new-work word create', "I kept the heading. If you would rather create another item, say so and I'll swap it back.", 2), ('new-work word install', "I kept the heading. If you would rather install another item, say so and I'll swap it back.", 2), ('new-work word run', "I kept the heading. If you would rather run another item, say so and I'll swap it back.", 2), ('new-work word extend', "I kept the heading. If you would rather extend another item, say so and I'll swap it back.", 2), ('new-work word update', "I kept the heading. If you would rather update another item, say so and I'll swap it back.", 2), ('new-work word make', "I kept the heading. If you would rather make another item, say so and I'll swap it back.", 2)])
OPTOUT_CASES.extend([('accept search then change', "I used the search tool. Say so and I'll change the heading.", 2), ('accept chosen nothing applied', "I chose a repair approach. Nothing has been applied. Say so and I'll change the file.", 2), ('accept search then undo', "I used the search tool. Say so and I'll undo it.", 2), ('accept north south reversal', "I kept the direction north. If you did mean 'south', say so and I'll swap it back.", 0), ('accept independent apply', "I've applied the heading. Say so and I'll swap it back. Want me to apply it?", 2), ('accept independent go', "I've applied the heading. Say so and I'll swap it back. Say go and I'll do it.", 2), ('accept independent add', "I've applied the heading. Say so and I'll swap it back. Say so and I'll add a page.", 2), ('accept independent banned', "I've applied the heading. Say so and I'll swap it back. Nothing needs you.", 2), ('applied then change without back', "I've applied the heading. Say so and I'll change the file.", 2), ('applied then swap without back', "I've applied the heading. Say so and I'll swap the file.", 2), ('applied then switch without back', "I've applied the heading. Say so and I'll switch the file.", 2), ('applied then change back', "I've applied the heading. Say so and I'll change it back.", 0), ('applied then switch back', "I've applied the heading. Say so and I'll switch it back.", 0), ('completion contradicted by nothing applied', "I kept the heading. Nothing has been applied. Say so and I'll undo it.", 2), ('completion contradicted by nothing changed', "I kept the heading. Nothing was changed. Say so and I'll swap it back.", 2), ('completion contradicted by not applied', "I kept the heading. It has not been applied. Say so and I'll revert it.", 2), ('completion contradicted by no changes', "I kept the heading. No changes have been made. Say so and I'll undo it.", 2), ('bare took unrelated', "I took a look at the draft. Say so and I'll undo it.", 2), ('taken unrelated', "I've taken a look at the draft. Say so and I'll undo it.", 2), ('gone unrelated', "I've gone through the draft. Say so and I'll undo it.", 2)])
for label, text, want in OPTOUT_CASES:
    check("optout " + label, stall(text, transcript_path=optout_path), want)
    if want == 0 and label not in {'quoted offer is not optout', 'scope creep exact shape', 'rather offers new work', 'rather without applied default', 'new work exclusion without old trigger'}:
        rows = [json.loads(line) for line in open(os.path.join(STATE, "log.jsonl"))]
        sid = os.path.basename(STATE) + "-s" + str(n)
        check("optout logs " + label,
              (rows[-1].get("session") == sid[:8] and rows[-1].get("decision") == "allow-optout"
               and rows[-1].get("phrase") in text.replace("’", "'")), True)
        check("optout does not consume cap " + label,
              os.path.exists(os.path.join(STATE, "blocks-" + sid + ".count")), False)

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



# These transcripts are synthetic, written by this test, never read from sessions.
def reminder_records(name="CronCreate", command=None, error=False, result="ok", pending=False):
    recs = [{"type": "user", "message": {"content": "please remind me"}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "rem-1", "name": name,
                 "input": {"command": command} if command is not None else {}}]}}]
    if not pending:
        recs.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "rem-1", "is_error": error, "content": result}]}})
    return recs


def future_tests():
    def fixture(records):
        fd, path = tempfile.mkstemp(suffix=".jsonl", dir=STATE)
        with os.fdopen(fd, "w") as handle:
            for rec in records:
                handle.write(json.dumps(rec) + "\n")
        return path

    def test(label, text, want, records=None, path=None, expect_future=None, env=None):
        tpath = path if path is not None else fixture(records if records is not None else [
            {"type": "user", "message": {"content": "please help"}}])
        rc, err = RUN_FUTURE(text, tpath, label, env)
        ok = rc == want
        if expect_future is not None:
            ok = ok and (("you promised to come back later" in err) == expect_future)
        RECORD_FUTURE(ok, label, rc)

    for i, text in enumerate([
        "I'll remind you tomorrow.", "I’ll remind you next week.", "I will remind you on Friday.",
        "I'll raise it on 15 oct.", "I'll raise it with you next week.",
        "I'll raise it when the invoice arrives.", "I'll raise it tomorrow.",
        "I'll raise it next week.", "I'll raise it 15 oct.", "I'll flag it when they reply.",
        "once they reply I'll update the document.", "I'll check back next week.",
        "I'll follow up tomorrow.", "The job is running in the background. I'll remind you tomorrow.",
        "First paragraph.\n\nI'll remind you tomorrow.\n\nThird paragraph.\n\nFourth.\n\nFifth.",
    ]):
        test("future fire " + str(i), text, 2, expect_future=True)

    for i, text in enumerate([
        "I'll edit the file.", "I'll run the tests now.", "I'll check back now.",
        "I'll follow up with the source in this turn.", "Tell me and I'll remind you.",
        "Tell me the date and I'll remind you.", "If you reply, I'll follow up.",
        "When you respond, I'll remind you.", "Once you answer, I'll check back.",
        'The phrase was "I\'ll remind you tomorrow".',
        "The phrase was ‘I’ll remind you tomorrow’.",
        "The phrase was 'I'll remind you tomorrow'.", "`I'll remind you tomorrow` is an example.",
        "> I'll remind you tomorrow.\n\nThat's a quotation.",
        "```text\nI'll remind you tomorrow.\n```\nExample only.",
        "~~~text\nI'll remind you tomorrow.\n~~~\nExample only.",
        "I'll remind you tomorrow. Nothing will remind you.",
        "I'll raise the file descriptor limit.", "They'll remind you tomorrow.",
    ]):
        test("future negative " + str(i), text, 0, expect_future=False)
    test("conditional belongs to old ask logic", "Tell me 'go' and I'll remind you.", 2, expect_future=False)
    test("quote does not provide disclaimer", 'I\'ll remind you tomorrow. The phrase is "nothing will remind you".', 2, expect_future=True)
    test("scheduled task create", "I'll remind you tomorrow.", 0, reminder_records("mcp__scheduled-tasks__create_scheduled_task"))
    test("cron create", "I'll follow up tomorrow.", 0, reminder_records("CronCreate"))
    test("wakeup create", "I'll check back next week.", 0, reminder_records("ScheduleWakeup"))
    test("calendar MCP create", "I'll remind you tomorrow.", 0, reminder_records("mcp__gcal__create_event"))
    test("failed create", "I'll remind you tomorrow.", 2, reminder_records(error=True), expect_future=True)
    test("pending create", "I'll remind you tomorrow.", 2, reminder_records(pending=True), expect_future=True)
    test("json error result", "I'll remind you tomorrow.", 2, reminder_records(result='{"error": "denied"}'))
    test("calendar list is not create", "I'll remind you tomorrow.", 2, reminder_records("mcp__gcal__list_events"))
    test("plain write is not create", "I'll remind you tomorrow.", 2, reminder_records("Write"))
    prior = reminder_records() + [{"type": "user", "message": {"content": "another request"}}]
    test("previous turn create excluded", "I'll remind you tomorrow.", 2, prior)
    prior[-1]["message"]["content"] = [{"type": "text", "text": "another request"}]
    test("text block user boundary", "I'll remind you tomorrow.", 2, prior)
    mixed = reminder_records()
    mixed[-1]["message"]["content"].append({"type": "text", "text": "another request"})
    test("mixed text result user boundary", "I'll remind you tomorrow.", 2, mixed)
    wrong = reminder_records()
    wrong[-1]["message"]["content"][0]["tool_use_id"] = "different-id"
    test("unmatched result excluded", "I'll remind you tomorrow.", 2, wrong)
    test("unreadable transcript fails open", "I'll remind you tomorrow.", 0, path=os.path.join(STATE, "absent.jsonl"))
    malformed = os.path.join(STATE, "malformed.jsonl")
    with open(malformed, "w") as handle:
        handle.write("{bad-json\n")
    test("malformed transcript fails open", "I'll remind you tomorrow.", 0, path=malformed)
    test("failed transcript cannot bypass existing stall", "I'll remind you tomorrow. Want me to apply it?", 2,
         path=os.path.join(STATE, "absent.jsonl"), expect_future=False)
    test("reminder cannot bypass existing stall", "I'll remind you tomorrow. Want me to apply it?", 2,
         reminder_records(), expect_future=False)
    test("disclaimer cannot bypass existing stall", "I'll remind you tomorrow. Nothing will remind you. Want me to apply it?", 2,
         expect_future=False)
    VARIANT_TESTS(test, fixture)


def RUN_FUTURE(text, path, label, env):
    check_relaxation(text)
    global n
    n += 1
    proc = subprocess.run([sys.executable, STALL], input=json.dumps({
        "session_id": f"f{n}", "cwd": "/tmp", "transcript_path": path,
        "last_assistant_message": text}), capture_output=True, text=True,
        env=dict(os.environ, STALL_GUARD_STATE=STATE, **(env or {})))
    return proc.returncode, proc.stderr


def RECORD_FUTURE(ok, label, rc):
    check("future " + label, ok, True)


def VARIANT_TESTS(test, fixture):
    # Repair acceptance: ambiguity needs a later cue in its own clause.
    for i, text in enumerate([
        "Now I'll check back in the log.",
        "I'll follow up on the error by reading the next stack frame.",
        "I'll check back in the log.", "I'll follow up on the error.",
        "Now I'll follow up tomorrow.", "I'll check back next week in this turn.",
        "Tomorrow is the meeting. I'll check back in the log.",
        "I'll follow up on the error; tomorrow is the meeting.",
        "I'll check back in the log; I'll run tests now.",
    ]):
        test("repair immediate or no cue " + str(i), text, 0, expect_future=False)
    for i, text in enumerate([
        "I'll check back next week.", "I'll follow up tomorrow.",
        "I'll check back Friday.", "I'll follow up on 2026-10-12.",
        "I'll check back on 15 oct.", "I'll follow up on October 15.",
        "I'll check back on 10/12.", "I'll follow up later.",
        "I'll check back when they reply.", "I'll follow up once the report arrives.",
        "Tomorrow I'll follow up.", "I'll check back next week; I'll run tests now.",
        "I'll follow up tomorrow. Now I'll check back in the log.",
    ]):
        test("repair later cue " + str(i), text, 2, expect_future=True)
    for i, text in enumerate([
        "Now I'll remind you tomorrow.", "Now I'll raise it with you tomorrow.",
        "Now I'll flag it when they reply.",
    ]):
        test("repair immediacy before explicit pattern " + str(i), text, 0, expect_future=False)
    for i, result in enumerate(["Command running in background with ID: task123", '{"id":"event-123","status":"confirmed"}']):
        recs = reminder_records("Bash", "calendar-create", result=result)
        recs[1]["message"]["content"][0]["input"]["run_in_background"] = True
        recs[-1]["message"]["content"][0].pop("is_error")
        test("repair background Bash never qualifies " + str(i), "I'll remind you tomorrow.", 2, recs,
             env={"STALL_GUARD_REMINDER_TOOLS": '["Bash"]'})
    test("custom reminder create tool", "I'll remind you tomorrow.", 0, reminder_records("custom_create"),
         env={"STALL_GUARD_REMINDER_TOOLS": '["custom_create"]'})
    test("configuration replaces defaults", "I'll remind you tomorrow.", 2, reminder_records("CronCreate"),
         env={"STALL_GUARD_REMINDER_TOOLS": '["custom_create"]'})
    test("empty list disables exemptions", "I'll remind you tomorrow.", 2, reminder_records("CronCreate"),
         env={"STALL_GUARD_REMINDER_TOOLS": '[]'})
    test("bad configuration fails open", "I'll remind you tomorrow.", 0, reminder_records("CronCreate"),
         env={"STALL_GUARD_REMINDER_TOOLS": 'invalid-json'})
    test("invalid configuration type fails open", "I'll remind you tomorrow.", 0, reminder_records("CronCreate"),
         env={"STALL_GUARD_REMINDER_TOOLS": '{}'})
    test("shell is not exempt by default", "I'll remind you tomorrow.", 2, reminder_records("Bash", "calendar-create"))
    path = fixture([{"type": "user", "message": {"content": "remind me"}}])
    codes = [run(STALL, {"session_id": "future-cap", "cwd": "/tmp", "transcript_path": path,
                       "last_assistant_message": "I'll remind you tomorrow."}) for _ in range(6)]
    check("future shares 4-block cap", codes, [2, 2, 2, 2, 0, 0])
    check("future stop_hook_active allows", stall("I'll remind you tomorrow.", transcript_path=path, stop_hook_active=True), 0)


future_tests()
print(f"{total - fails}/{total} passed")
sys.exit(1 if fails else 0)
