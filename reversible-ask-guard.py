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


def judge(text):
    """Return (decision, phrase, gate, snippet). decision in {block, allow-gate, allow-none}."""
    if text.lstrip().startswith("API Error"):
        return "allow-none", None, None, None
    body = clean(text)
    allp = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    # the ask usually sits in the OPENING, the stall shows at the END
    paras = allp if len(allp) <= ENDING_PARAS + 1 else [allp[0]] + allp[-ENDING_PARAS:]
    first_gate = None
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
        for name, rx in PARK + ASK:
            m = re.search(rx, flat, re.IGNORECASE | re.M)
            if not m:
                continue
            g = GATES.search(flat)
            if g:
                if first_gate is None:
                    first_gate = (name, g.group(0))
                continue
            s = max(0, m.start() - 70)
            return "block", name, None, flat[s:m.end() + 70].replace("\n", " ")[:160]
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
    if decision == "allow-none":
        sys.exit(0)
    if decision == "allow-gate":
        log({**base, "decision": "allow-gate", "phrase": phrase, "gate": gate})
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
