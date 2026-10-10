"""Actual pre-opt-out decision oracle, synthetic regression use only.
Source SHA-256: ebe21d4bfc57f2f3e83e8ce416124865e9d5d11ff2ae58c29a5858427b619d11
This module contains no runtime or private data.
"""

import re

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

BANNED = re.compile(r"(?<![\"'‘“`])\bnothing (?:else )?(?:needs|is needed from|needed from) you\b|\b(?:it|this|that) doesn'?t need you\b", re.I)

RELAY = re.compile(
    r"\b(?:tell|ask|ping|message|say to|paste (?:this|that|it) (?:to|into))\s+"
    r"(?:codex|grok|it|the (?:other |codex )?(?:seat|session|agent))\b", re.I)

RELAY_WALL = re.compile(
    r"\bcan(?:'|no)?t (?:reach|dispatch|message|call|launch|start) (?:codex|grok|it|that (?:seat|agent|session))"
    r"|\b(?:codex|grok|that seat) is (?:unreachable|not reachable)\b", re.I)

IMP = r"(?:^|[.;:!?,→*(◆]\s*|\bneeds you:?\s*\**\s*|\b(?:just|then|so:?|and|or)\s+)"

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
    # sends to a person (drafts for sign-off); a handoff to codex is not a send
    r"|\b(?:send|sends|sending|sent|email|emails|emailed|slack|dm|imessage)\b(?! (?:it |this |the \w+ )?to codex)"
    r"|\bgoes (?:out|to (?:her|him|them|[A-Z]\w+))\b|\bleaves tonight\b"
    r"|\bcontract\b|\bsignature\b|\bsign(?:s|ed|ing)? it\b|\baccount(?:'s)? settings?\b"
    r"|\bmount\b|\bplug(?:ged)? in\b|\barriv(?:es|ed)\b|\bon your (?:phone|mac|device|laptop)\b"
    r"|\breads better\b|\bwhich (?:reads|looks|sounds)\b|\blogged as a gate\b"
    r"|\bcommit\b|\bpush\b|\b(?:deny|allow) ?list\b|\bsign\b|\bmedical\b",
    re.IGNORECASE,
)

ENDING_PARAS = 2

FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)

RECEIPT = re.compile(r"^\s*\**(?:FILED TO|REMOVED FROM)\b.*?(?:^\s*\**END (?:FILED TO|REMOVED FROM)\**\s*$|\Z)", re.S | re.M | re.I)

QUOTE_LINE = re.compile(r"^\s*>.*$", re.M)

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
    # the register puts the ask in the OPENING, the stall shows at the END
    paras = allp if len(allp) <= ENDING_PARAS + 1 else [allp[0]] + allp[-ENDING_PARAS:]
    first_gate = None
    for para in paras:
        flat = para.replace("’", "'")
        b = BANNED.search(flat)
        if b:  # no gate escape: Tim banned the phrase itself (26-09-28)
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
