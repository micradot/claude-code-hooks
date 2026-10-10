#!/usr/bin/env python3
"""
reversible-ask-guard.py -- Claude Code Stop hook: the stall / fake-gate catcher.

WHAT IT CATCHES
Claude ending a turn by parking work it could do right now, or by asking you for
a "go" it doesn't actually need:

  PARK  "I'll do that next"  "filed as mine to fix"  "I'll pick this up in a
        fresh session"  "unless you want steps 4-7"
  ASK   "say 'restart it' and I will"  "I'll wait for your word"  "if it's go"
        "want me to ..."  "shall I"  "your call"  "tell me and I'll"  "go?"
  RELAY "tell codex: ..." -- handing you words to carry to another agent that
        Claude could message itself.

If one of those appears in the final message AND the same paragraph names no real
gate (a missing fact, an external send, something irreversible, money, sensitive
data, your taste or authority, a permission/platform wall, or a background job it
is genuinely waiting on), the stop is blocked and Claude is sent back with one
line: the phrase it used, and "do the work, or name the real gate".

A block does not reshape the message; Claude goes back and does the work, so the
second reply carries the thing you actually wanted.

LATER PROMISES: first-person reminders/check-backs need a successful reminder
create this turn, or the explicit disclaimer "nothing will remind you".
Code, quotations, immediate work and user-conditioned promises are excluded.
Transcript read errors fail open; the existing cap and log are shared.

WHAT IT MUST NOT DO
  - fire on a genuine question only you can answer, a draft held for your
    sign-off before it is sent, a permission wall, or a finished turn.
  - loop: it honours `stop_hook_active` and a per-session block cap.

CONFIG (environment variables, all optional)
  STALL_GUARD_SCOPE   colon-separated directories. If set, the guard only runs
                      when the session's cwd is inside one of them. Unset = runs
                      everywhere.
  STALL_GUARD_STATE   where the log and per-session counters live
                      (default ~/.claude/state/stall-guard).

CAP: MAX_BLOCKS per session. At ALERT_AT (75% of the cap) the block message also
tells Claude to warn you the guard may be misfiring. At the cap it stops blocking
for that session.

LOG: every block and every allow-with-a-phrase goes to <state>/log.jsonl, so you
can count false positives. Blocks carry a <=160-char snippet around the phrase.

REGISTER IT with "async": false (a Stop hook that runs async cannot block).

WEDGE-SAFETY: fail-open on ANY exception; `stop_hook_active` -> exit 0; cap.
"""
import datetime
import json
import os
import re
import sys
from pathlib import Path

MAX_BLOCKS = 4
ALERT_AT = 3  # 75% of MAX_BLOCKS
SCOPE = [p for p in os.environ.get("STALL_GUARD_SCOPE", "").split(os.pathsep) if p]
STATE = Path(os.environ.get("STALL_GUARD_STATE") or Path.home() / ".claude" / "state" / "stall-guard")
LOG = STATE / "log.jsonl"

# ---- triggers -------------------------------------------------------------
Q = r"[\"'‘’“”`]"
PARK = [
    ("i'll do that next", r"\bi(?:'|’)?ll (?:do|start|run|build|take|tackle|handle|pick up|get to|fire|kick off|send|file|finish)\b[^.\n]{0,40}\bnext\b"),
    ("next, i'll", r"\bnext,? i(?:'|’)?ll\b"),
    ("mine to fix", r"\b(?:filed|logged|parked|noted) as mine\b|\bmine to fix\b"),
    ("pick it up later", r"\bi(?:'|’)?ll (?:pick (?:this|it|that) (?:back )?up|come back to (?:this|it)|do (?:this|it|that) (?:later|tomorrow))\b"),
    ("in a later session", r"\b(?:in|from) a (?:fresh|new|later|daytime|separate) (?:session|seat)\b"),
    ("unless you want", r"\bunless you want\b"),
    ("i can do it on your word", r"\bi can (?:do|run|start|build|fix|take) (?:that|this|it|them)\b[^.\n]{0,60}\b(?:later|tomorrow|next|on your word|if you (?:want|like|say))\b"),
    ("hand it to a seat", r"\bhand it to (?:whatever|any|a fresh) seat\b"),
]
# A phrase the author banned outright: it was false in most of the endings it
# appeared in. No gate excuses it. Say the result, or name what needs the user.
BANNED = re.compile(r"(?<![\"'‘“`])\bnothing (?:else )?(?:needs|is needed from|needed from) you\b|\b(?:it|this|that) doesn'?t need you\b", re.I)
# RELAY: Claude handing the user words to carry to another agent it can reach
# itself. Ordinary gates do NOT excuse it; only saying the agent is unreachable does.
RELAY = re.compile(
    r"\b(?:tell|ask|ping|message|say to|paste (?:this|that|it) (?:to|into))\s+"
    r"(?:codex|grok|it|the (?:other |codex )?(?:seat|session|agent))\b", re.I)
RELAY_WALL = re.compile(
    r"\bcan(?:'|no)?t (?:reach|dispatch|message|call|launch|start) (?:codex|grok|it|that (?:seat|agent|session))"
    r"|\b(?:codex|grok|that seat) is (?:unreachable|not reachable)\b", re.I)
IMP = r"(?:^|[.;:!?,→*(◆]\s*|\bneeds you:?\s*\**\s*|\b(?:just|then|so:?|and|or)\s+)"
# "say X" only as an imperative handed to the user, and not when X is the user
# reporting a step only they can do ("say done", "tell me 'mounted'").
NOT_REPORT = r"(?!(?:done|saved|installed|mounted|plugged in|it'?s in|ready|back|finished|signed in|in)\b)"
ASK = [
    ("say '<x>' and i'll", IMP + r"say " + Q + r"?" + NOT_REPORT + r"[\w' -]{1,24}" + Q + r"?,? and i(?:'|’)?(?:ll| will)\b"),
    ("say go", IMP + r"say (?:" + Q + r")?go\b"),
    ("wait for your word", r"\b(?:wait|waiting|held|hold(?:ing)?) (?:for|on) your (?:word|go|ok|say[- ]so)\b"),
    ("on your word", r"\bon your (?:word|go|say[- ]so)\b"),
    ("if it's go", r"\bif (?:it(?:'|’)?s|that(?:'|’)?s) (?:a )?go\b"),
    ("want me to", r"\bwant me to\b"),
    ("shall i", r"\bshall i\b"),
    ("should i go ahead", r"\bshould i (?:go ahead|proceed|do (?:it|that|this)|run (?:it|that|this))\b"),
    ("your call", r"(?:\bit(?:'|’)?s|\bthat(?:'|’)?s|\bis|[,:(])\s*your call\b"),
    ("tell me and i'll", IMP + r"tell me " + Q + NOT_REPORT + r"[\w' -]{1,24}" + Q + r",? and i(?:'|’)?(?:ll| will)\b"),
    ("if you want, i'll", r"\bif you(?:'d)? (?:want|like)(?: me to)?,? i(?:'|’)?(?:ll| will| can)\b"),
    ("let me know if you want", r"\blet me know if you(?:'d)? (?:want|like)\b"),
    ("when you're ready", r"\b(?:when|whenever) you(?:'|’)?re ready\b|\bready when you are\b"),
    ("go?", r"(?:^|[\s(])go\?(?:\s|$)"),
]

# ---- real gates (checked in the SAME paragraph as the trigger) -------------
GATES = re.compile(
    r"🔒"
    r"|\birreversib|\bnot reversible\b|can(?:'|no)t be undone|\bone-way\b"
    r"|\bexternal\b|\bsign[- ]?off\b|\bfor (?:your )?(?:approval|review) before (?:it|i) send"
    r"|\bsends? (?:it )?(?:to|as)\b|\bemail(?:s|ed)? (?:to|as)\b|\bpublish|\bpost (?:it|this) (?:to|on)\b"
    r"|\bmoney\b|\bspend\b|\bpayment\b|\bpurchase\b|\bcharges? (?:your|the) card\b|\$\d"
    r"|\bsensitive\b|\bprivate\b|\bhealth\b|\blegal\b|\bcounsel\b"
    r"|\bdelet(?:e|es|ed|ion)\b|\bdestructive\b|\bpermanent(?:ly)?\b"
    r"|\btaste\b|\bpreference\b|\bprefer\b|\byour decision\b|\bdecide\b|\bwhich (?:one|of|version|option)\b"
    r"|\bmissing fact\b|\bfact[- ]stop\b|\bonly you (?:know|can|have)\b|\bi can(?:'|no)t (?:see|tell|know)\b"
    r"|\bemotional\b|\bupset\b|\bunattended\b|\bblast radius is (?:high|large|wide)\b"
    r"|\bpassword\b|\btouch id\b|\b2fa\b|\bsign(?:ed)? in\b|\blog(?:ged)? in\b|\btoken\b"
    r"|\b(?:isn(?:'|’)t|not|never) allowed\b|\bcan(?:'|’|no)t (?:add|change|edit|widen|grant|fire|trigger|run|reach|access|approve|click|type)\b"
    r"|\bpermission|\bclassifier\b|\bdenied\b|\bharness\b|\bplatform\b|\bsandbox\b|\byour hands\b"
    r"|\b(?:is|are|it(?:'|’)s) (?:running|in flight)\b|\bin the background\b|\bwhen it (?:lands|finishes|completes|returns|comes back)\b"
    # sends to a person (drafts for sign-off); a handoff to another agent is not a send
    r"|\b(?:send|sends|sending|sent|email|emails|emailed|slack|dm|imessage)\b(?! (?:it |this |the \w+ )?to codex)"
    r"|\bgoes (?:out|to (?:her|him|them|[A-Z]\w+))\b|\bleaves tonight\b"
    r"|\bcontract\b|\bsignature\b|\bsign(?:s|ed|ing)? it\b|\baccount(?:'s)? settings?\b"
    r"|\bmount\b|\bplug(?:ged)? in\b|\barriv(?:es|ed)\b|\bon your (?:phone|mac|device|laptop)\b"
    r"|\breads better\b|\bwhich (?:reads|looks|sounds)\b|\blogged as a gate\b"
    r"|\bcommit\b|\bpush\b|\b(?:deny|allow) ?list\b|\bsign\b|\bmedical\b",
    re.IGNORECASE,
)
ENDING_PARAS = 2  # judged: the opening paragraph plus the last two

FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
RECEIPT = re.compile(r"^\s*\**(?:FILED TO|REMOVED FROM)\b.*?(?:^\s*\**END (?:FILED TO|REMOVED FROM)\**\s*$|\Z)", re.S | re.M | re.I)
QUOTE_LINE = re.compile(r"^\s*>.*$", re.M)


def extract_final_text(lam):
    if lam is None:
        return ""
    if isinstance(lam, str):
        return lam
    if isinstance(lam, dict):
        content = lam.get("content")
        if content is None:
            content = (lam.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        lam = content
    if isinstance(lam, list):
        return "\n".join(b.get("text", "") for b in lam
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def clean(text):
    """Drop what Claude is quoting or handing to someone else, not saying itself."""
    text = FENCE.sub("\n\n", text)
    text = RECEIPT.sub("\n\n", text)
    text = QUOTE_LINE.sub("", text)
    return text



# Exact names only. Set to [] to disable create-tool exemptions.
# JSON avoids ambiguity with tool names containing punctuation.
DEFAULT_REMINDER_TOOLS = [
    "mcp__scheduled-tasks__create_scheduled_task", "CronCreate", "ScheduleWakeup",
    "mcp__calendar__create_event", "mcp__google_calendar__create_event",
    "mcp__gcal__create_event",
]


def reminder_tool(block):
    if block.get("name") == "Bash" and (block.get("input") or {}).get("run_in_background"):
        return False
    names = json.loads(os.environ.get("STALL_GUARD_REMINDER_TOOLS", json.dumps(DEFAULT_REMINDER_TOOLS)))
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("STALL_GUARD_REMINDER_TOOLS must be a JSON list of tool names")
    return block.get("name") in names


# ---- later promises: a successful reminder must exist in this turn --------
FIRST_PERSON = r"\bi(?:['’]ll|\s+will)\s+"
FUTURE = re.compile(
    FIRST_PERSON + r"(?:remind you\b"
    r"|raise (?:it|this|that) (?:on\b|with you\b|when\b|tomorrow\b|next week\b|\d{1,2}\b)"
    r"|flag (?:it|this|that) when\b|check back\b|follow up\b)"
    r"|\bonce they reply[,\s]+" + FIRST_PERSON,
    re.I,
)
# The old ask check still owns a promise conditional on the user's next reply.
USER_CONDITION = re.compile(
    r"\b(?:tell me|let me know|say\b[^.!?\n]{0,40}\band|"
    r"(?:if|when|once) you (?:reply|respond|answer|tell|say|confirm|want|like|ask))\b",
    re.I,
)
NOW = re.compile(r"\b(?:now|right now|this turn|in this reply|before i finish this turn)\b", re.I)
AMBIGUOUS_FOLLOWUP = re.compile(FIRST_PERSON + r"(?:check back|follow up)\b", re.I)
LATER = re.compile(
    r"\b(?:tomorrow|next (?:week|month|year)|later|when they reply|once\b"
    r"|(?:mon|tues|wednes|thurs|fri|satur|sun)day|mon|tue|wed|thu|fri|sat|sun)\b"
    r"|\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"
    r"|\b(?:\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2})\b",
    re.I,
)
INLINE_QUOTE = re.compile(
    r'"[^"\n]*(?:"|$)|“[^”\n]*(?:”|$)|‘[^’\n]*(?:’|$)'
    r"|(?<!\w)'[^\n]*?(?:'(?!\w)|$)|`[^`\n]*(?:`|$)", re.M,
)
TILDE_FENCE = re.compile(r"~~~.*?(?:~~~|\Z)", re.S)
DISCLAIMER = re.compile(r"\bnothing will remind you\b", re.I)
FUTURE_PHRASE = "future promise without reminder"


def future_body(text):
    return INLINE_QUOTE.sub(" ", TILDE_FENCE.sub("\n\n", clean(text)))


def future_promise(text):
    """Scan the whole reply, ignoring quotations and immediate/conditional work."""
    if text.lstrip().startswith("API Error"):
        return None
    body = future_body(text)
    for match in FUTURE.finditer(body):
        start = max(body.rfind(mark, 0, match.start()) for mark in ".!?;\n") + 1
        ends = [body.find(mark, match.end()) for mark in ".!?;\n"]
        end = min((p for p in ends if p >= 0), default=len(body))
        if USER_CONDITION.search(body[start:match.start()]):
            continue
        clause = body[start:end]
        if NOW.search(clause):
            continue
        if AMBIGUOUS_FOLLOWUP.match(match.group()) and not LATER.search(clause):
            continue
        return body[max(0, match.start() - 70):match.end() + 70].replace("\n", " ")[:160]
    return None


def result_succeeded(block):
    """Use the sibling guard's tool-result contract; reject explicit failures too."""
    if block.get("is_error"):
        return False
    content = block.get("content", "")
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
    if isinstance(content, str):
        if re.search(r"(?:exit code:|exited with (?:exit )?code)\s*[1-9]\d*", content, re.I):
            return False
        try:
            content = json.loads(content)
        except (ValueError, TypeError):
            return True
    if isinstance(content, dict):
        if content.get("error") or content.get("isError") or content.get("success") is False:
            return False
        if content.get("exit_code", 0) != 0:
            return False
    return True


def turn_reminded(transcript_path):
    """Reuse the sibling's reverse scan and id-matched successful results.

    Only entries after the last genuine user message count. Tool-result-only
    user entries stay in the turn; mixed user text starts a new turn.
    Read errors propagate to the caller, which allows this check to fail open.
    """
    if not transcript_path:
        return False
    with open(transcript_path) as handle:
        lines = handle.readlines()
    qualifying_ids, results = set(), {}
    for line in reversed(lines):
        if not line.strip():
            continue
        # A malformed entry could hide a user boundary: fail open, don't accept
        # a reminder from a previous turn by skipping that boundary.
        entry = json.loads(line)
        if not isinstance(entry, dict):
            raise ValueError("invalid transcript entry")
        content = (entry.get("message") or {}).get("content", [])
        if entry.get("type") == "user":
            if isinstance(content, str) or (isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "text" for b in content)):
                break
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tid = block.get("tool_use_id")
                        if tid is not None:
                            results.setdefault(tid, result_succeeded(block))
            continue
        if entry.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "tool_use"
                        and reminder_tool(block) and block.get("id") is not None):
                    qualifying_ids.add(block["id"])
    return any(results.get(tid, False) for tid in qualifying_ids)


def judge_future(text, transcript_path):
    snippet = future_promise(text)
    if snippet is None:
        return "allow-none", None, None, None
    if DISCLAIMER.search(future_body(text)):
        return "allow-gate", FUTURE_PHRASE, "explicit no-reminder disclaimer", None
    try:
        reminded = turn_reminded(transcript_path)
    except Exception:
        return "allow-gate", FUTURE_PHRASE, "transcript unavailable (fail-open)", None
    if reminded:
        return "allow-gate", FUTURE_PHRASE, "successful reminder create this turn", None
    return "block", FUTURE_PHRASE, None, snippet



# An opt-out is a reversal of a default already applied in this paragraph.
# Match the whole offer clause, and exempt only trigger spans inside it.
OPTOUT_APPLIED = re.compile(
    r"\bi(?:'ve| have) (?:already )?(?:applied|set|kept|left|spelled|done|dropped|renamed)\b"
    r"|\bi (?:already )?(?:kept|left|went with|spelled|set|applied|dropped|renamed)\s+(?=[\w\"'`])"
    r"|\bi took it to mean\b|\bwhich i took to be\b"
    r"|(?:^|[.!;\n]\s*)(?:already )?(?:done|kept|left it as|applied|spelled it|set it to)\b"
    r"|\bstays as it is\b", re.I | re.M,
)
OPTOUT_NOT_APPLIED = re.compile(
    r"\b(?:not|never|haven't|hasn't|wasn't|isn't|didn't|hadn't|won't|can't)\b"
    r"|\b(?:will|would|could|should|plan to|need to|going to|nothing|no changes?)\b", re.I,
)
# Explicit noncompletion after the evidence invalidates the earlier default.
OPTOUT_INTERVENING = re.compile(
    r"\bnothing\b[^.!?;\n]{0,60}\b(?:applied|changed|done|set|renamed)\b"
    r"|\bno changes?\b"
    r"|\b(?:not|never|haven't|hasn't|wasn't|isn't|didn't|hadn't)\b"
    r"[^.!?;\n]{0,60}\b(?:applied|changed|done|set|renamed)\b", re.I,
)
OPTOUT_REVERSE = (
    r"(?:(?:swap|change|switch)(?: [^.!?;\n]{1,60})? back"
    r"|(?:undo|drop|revert)(?: [^.!?;\n]{1,60})?"
    r"|put [^.!?;\n]{1,60} back|rename(?: [^.!?;\n]{1,60})? back)"
)
OPTOUT_CONDITION = r"if you(?: would rather|'d rather| prefer| did mean) [^.!?;\n]{1,120}?"
OPTOUT_OFFER = re.compile(
    r"\b(?:" + OPTOUT_CONDITION + r",?\s+)?say so and i(?:'ll| will) "
    + OPTOUT_REVERSE + r"\s*(?=[.!?;\n]|$)"
    r"|\b" + OPTOUT_CONDITION + r",?\s+say so\s*(?=[.!?;\n]|$)"
    r"|\bunless you want (?:it|this|that|them) changed\s*(?=[.!?;\n]|$)", re.I,
)


def optout_spans(para):
    # A quoted word may be the alternative; a quoted completion is not evidence.
    quotes = [m.span() for m in INLINE_QUOTE.finditer(para)]
    def quoted(position):
        return any(a <= position < b for a, b in quotes)
    spans = []
    for offer in OPTOUT_OFFER.finditer(para):
        if quoted(offer.start()):
            continue
        # An alternative that asks to create or extend something is new work.
        if re.search(r"\b(?:add|build|create|install|start|run|extend|update|do|make)\b",
                     offer.group(0), re.I):
            continue
        for applied in OPTOUT_APPLIED.finditer(para, 0, offer.start()):
            if quoted(applied.start()):
                continue
            start = max(para.rfind(mark, 0, applied.start()) for mark in '.!;\n') + 1
            end = min((p for mark in '.!;\n'
                       if (p := para.find(mark, applied.end(), offer.start())) >= 0),
                      default=offer.start())
            if (not OPTOUT_NOT_APPLIED.search(para[start:end])
                    and not OPTOUT_INTERVENING.search(para[applied.end():offer.start()])):
                spans.append(offer.span())
                break
    return spans


def judge(text):
    """Return (decision, phrase, gate, snippet). decision in {block, allow-gate, allow-optout, allow-none}."""
    if text.lstrip().startswith("API Error"):
        return "allow-none", None, None, None
    body = clean(text)
    allp = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    # the ask usually sits in the OPENING, the stall shows at the END
    paras = allp if len(allp) <= ENDING_PARAS + 1 else [allp[0]] + allp[-ENDING_PARAS:]
    first_gate = None
    first_optout = None
    for para in paras:
        flat = para.replace("’", "'")
        b = BANNED.search(flat)
        if b:
            s = max(0, b.start() - 70)
            return "block", "nothing needs you (banned)", None, flat[s:b.end() + 70].replace("\n", " ")[:160]
        r = RELAY.search(flat)
        if r and not RELAY_WALL.search(flat):
            s = max(0, r.start() - 70)
            return "block", "relay to another agent", None, flat[s:r.end() + 70].replace("\n", " ")[:160]
        optouts = optout_spans(flat)
        if optouts and first_optout is None:
            first_optout = flat[optouts[0][0]:optouts[0][1]]
        for name, rx in PARK + ASK:
            for m in re.finditer(rx, flat, re.IGNORECASE | re.M):
                # Imperative patterns may include the preceding punctuation.
                start = m.start() + len(m.group(0)) - len(m.group(0).lstrip(" .;:!?,→*(◆\n"))
                if any(a <= start and m.end() <= b for a, b in optouts):
                    continue
                g = GATES.search(flat)
                if g:
                    if first_gate is None:
                        first_gate = (name, g.group(0))
                    continue
                s = max(0, m.start() - 70)
                return "block", name, None, flat[s:m.end() + 70].replace("\n", " ")[:160]
    if first_optout:
        return "allow-optout", first_optout, "default already applied; reversal only", None
    if first_gate:
        return "allow-gate", first_gate[0], first_gate[1], None
    return "allow-none", None, None, None


def in_scope(cwd):
    if not SCOPE:
        return True
    try:
        c = os.path.abspath(cwd or "")
        for root in SCOPE:
            r = os.path.abspath(os.path.expanduser(root))
            if os.path.commonpath([c, r]) == r:
                return True
    except Exception:
        return False
    return False


def count_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    return STATE / f"blocks-{safe}.count"


def read_count(p):
    try:
        return int(p.read_text().strip())
    except Exception:
        return 0


def log(rec):
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        rec["ts"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        with open(LOG, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    sid = payload.get("session_id", "")
    base = {"session": sid[:8], "cwd": payload.get("cwd", "")}
    if payload.get("stop_hook_active"):
        sys.exit(0)
    if not in_scope(payload.get("cwd")):
        sys.exit(0)
    text = extract_final_text(payload.get("last_assistant_message"))
    if not text.strip():
        sys.exit(0)
    decision, phrase, gate, snippet = judge(text)
    # Keep the ordinary stall/ask verdict independent. A reminder only excuses
    # the later promise, never an unrelated stall or banned ending.
    if decision != "block":
        future = judge_future(text, payload.get("transcript_path"))
        if future[0] == "block" or (future[0] != "allow-none" and decision != "allow-optout"):
            decision, phrase, gate, snippet = future
    if decision == "allow-none":
        sys.exit(0)
    if decision in {"allow-gate", "allow-optout"}:
        log({**base, "decision": decision, "phrase": phrase, "gate": gate})
        sys.exit(0)
    cpath = count_path(sid)
    n = read_count(cpath)
    if n >= MAX_BLOCKS:
        log({**base, "decision": "allow-cap", "phrase": phrase, "blocks": n})
        sys.exit(0)
    n += 1
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        cpath.write_text(str(n))
    except Exception:
        pass
    rec = {**base, "decision": "block", "phrase": phrase, "snippet": snippet, "blocks": n}
    msg = (f"STALL GUARD: your last message parks work or asks for a go (\"{phrase}\"). "
           "Do the work now, or name the real gate in that same paragraph "
           "(missing fact, external send, irreversible, money, sensitive, the user's taste, "
           "a permission/platform wall, or a background job you are waiting on).")
    if phrase == FUTURE_PHRASE:
        msg = ("you promised to come back later but nothing will fire. "
               "make the calendar block (date + the exact text you will need) now, "
               "or say 'nothing will remind you'.")
    if n >= ALERT_AT:
        rec["alert"] = f"{n}/{MAX_BLOCKS} blocks this session"
        msg += (f" CAP ALERT: this is block {n} of {MAX_BLOCKS} this session; tell the user in one "
                "line that the stall guard is near its cap, in case it is misfiring.")
    log(rec)
    sys.stderr.write(msg + "\n")
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
