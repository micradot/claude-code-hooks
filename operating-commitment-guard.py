#!/usr/bin/env python3
"""
operating-commitment-guard.py -- Claude Code Stop hook: "saying a rule is not filing it".

THE PROBLEM
Claude says "from now on I'll always check X" or "that won't happen again". Next
session it has no memory of saying it, because nothing was written down. The
promise was real in the moment and gone by morning.

WHAT IT DOES
When Claude's final message contains an operating self-commitment ("going forward
I'll...", "from now on...", "I'll always/never...", "I'll make sure I...", "won't
happen again", "my default is now...") OR the marker `WILCO:`, the hook requires
BOTH:
  (a) a SUCCESSFUL write this turn to a place a future session will read
      (CLAUDE.md, AGENTS.md, SKILL.md, MEMORY.md, a memory/ folder, or any path
      you list in OPCOMMIT_FILING_PATHS), and
  (b) a `WILCO: <change> -> <path>` line in the message, so you can spot it.
If either is missing it blocks the stop and tells Claude exactly which half.

WILCO = "will comply". Change MARKER below if you want another word.

"SUCCESSFUL" MEANS SUCCESSFUL: a write counts only if its tool result exists and
is not an error. A write blocked by another hook or that failed does not count.

DELIBERATELY NARROW. The trigger phrases are first-person and about how Claude
operates, not task talk ("I'll edit the file" never fires). "default" on its own
is NOT a trigger: in ops and config work it names settings ("the default will be
20%"), and an earlier version that matched it blocked ordinary turns. A missed
commitment is the cheaper failure for a blocking hook.

KNOWN LIMIT: Claude Code writes the transcript asynchronously, so a write that
really succeeded may not be in the transcript yet when the hook runs. The guard
may then nag once; the retry passes. Bounded by MAX_BLOCKS, never a wedge.

CONFIG (environment variables, all optional)
  OPCOMMIT_MODE           "block" (default) or "warn" (prints to stderr, exit 0)
  OPCOMMIT_FILING_PATHS   extra files or directories that count as filing,
                          colon-separated (e.g. your changelog or rules folder)
  OPCOMMIT_KNOWN_ROOTS    roots a memory-folder write must sit under
                          (default: ~/.claude plus the session cwd)

REGISTER IT with "async": false.

WEDGE-SAFETY: fail-open on any exception; honours `stop_hook_active`; per-session
cap of MAX_BLOCKS, after which it lets the turn end.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

MARKER = "WILCO"
MAX_BLOCKS = 2
MODE = os.environ.get("OPCOMMIT_MODE", "block").strip().lower()

# High-precision FIRST-PERSON operating-self-commitment phrases. Err toward NOT firing.
COMMIT = re.compile(
    r"going\s+forward[,\s]+i['’]?ll"
    r"|from\s+now\s+on\b"
    r"|from\s+here\s+on\b"
    r"|i['’]?ll\s+make\s+sure\s+i\b"
    r"|i['’]?ll\s+always\b"
    r"|i['’]?ll\s+never\b"
    r"|i\s+won['’]?t\s+(?:do\s+that|let\s+that\s+happen)\s+again\b"
    r"|won['’]?t\s+happen\s+again\b"
    r"|i['’]?ll\s+change\s+how\s+i\b"
    r"|change\s+how\s+i\s+(?:operate|work)\b"
    r"|i['’]?ll\s+(?:start|stop)\s+(?:doing|always|ever)\b"
    r"|i['’]?ll\s+remember\s+to\b"
    r"|the\s+(?:rule|test|check)\s+i['’]?ll\s+(?:run|apply|use|follow)\b"
    r"|my\s+default\s+(?:is\s+now|will\s+be|becomes)\b"
    r"|that\s+becomes\s+my\s+default\b"
    r"|going\s+forward[,\s]+(?:the|my)\s+(?:rule|habit|approach)\b",
    re.IGNORECASE,
)
# DELIBERATELY NOT MATCHED (each produced real false positives):
#   i'll ... from here          ("I'll grab the config from here")
#   i'll default to / defaulting to / treat that as default
#   "going forward, the default ..."  ("going forward, the default will be 20%")

MARKER_RE = re.compile(r"\b" + re.escape(MARKER) + r"\s*:", re.IGNORECASE)
MUTATING_TOOLS = {"Write", "Edit", "MultiEdit"}
FILING_DIR_HINTS = ("/memory/", "/_memory/")
FILING_BASENAMES = {"claude.md", "agents.md", "skill.md", "memory.md"}


def _norm(p):
    try:
        return os.path.realpath(os.path.expanduser(p)).casefold()
    except Exception:
        return ""


def _under(path_n, root):
    r = _norm(root)
    if not r:
        return False
    return path_n == r or path_n.startswith(r.rstrip("/") + "/")


def _extra_paths():
    return [p for p in os.environ.get("OPCOMMIT_FILING_PATHS", "").split(os.pathsep) if p]


def _known_roots(cwd=None):
    env = os.environ.get("OPCOMMIT_KNOWN_ROOTS")
    raw = env.split(os.pathsep) if env else ["~/.claude"]
    if cwd:
        raw.append(cwd)
    return [r for r in raw if r]


def is_filing_path(fp, cwd=None):
    """A path that, if written SUCCESSFULLY, counts as filing the commitment."""
    if not fp:
        return False
    n = _norm(fp)
    if not n:
        return False
    if any(_under(n, extra) for extra in _extra_paths()):
        return True
    if not any(_under(n, r) for r in _known_roots(cwd)):
        return False  # rejects writes to /tmp lookalikes
    if any(h in n for h in FILING_DIR_HINTS):
        return True
    return n.rsplit("/", 1)[-1] in FILING_BASENAMES


def turn_filed(transcript_path, cwd=None):
    """True iff a mutating write to a filing surface SUCCEEDED this turn.
    The current turn runs back to the last genuine user message."""
    with open(transcript_path, errors="replace") as f:
        lines = f.readlines()
    qualifying_ids = set()
    result_is_error = {}
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        etype = entry.get("type")
        content = (entry.get("message") or {}).get("content", [])
        if etype == "user" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tid = b.get("tool_use_id")
                    if tid is not None:
                        result_is_error[tid] = bool(b.get("is_error"))
        if etype == "user":
            if isinstance(content, str):
                break
            if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "text" for b in content):
                break
            continue
        if etype == "assistant" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in MUTATING_TOOLS:
                    if is_filing_path((b.get("input") or {}).get("file_path", ""), cwd):
                        if b.get("id") is not None:
                            qualifying_ids.add(b["id"])
    return any(tid in result_is_error and not result_is_error[tid] for tid in qualifying_ids)


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


def counter_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    return Path(tempfile.gettempdir()) / f"operating-commitment-guard-{safe}.count"


def read_count(p):
    try:
        return int(p.read_text().strip())
    except Exception:
        return 0


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        sys.exit(0)
    final_text = extract_final_text(payload.get("last_assistant_message"))
    if not final_text:
        sys.exit(0)
    committed = bool(COMMIT.search(final_text))
    marked = bool(MARKER_RE.search(final_text))
    if not (committed or marked):
        sys.exit(0)
    transcript_path = payload.get("transcript_path")
    try:
        filed = turn_filed(transcript_path, payload.get("cwd")) if transcript_path else False
    except Exception:
        sys.exit(0)
    missing = []
    if not filed:
        missing.append("FILE it: write the change this turn to a file a future session reads "
                       "(CLAUDE.md, AGENTS.md, a SKILL.md, MEMORY.md or a memory folder). "
                       "A blocked or failed write does not count.")
    if not marked:
        missing.append(f'MARK it: add a "{MARKER}: <change> -> <path>" line so the user can spot it.')
    if not missing:
        sys.exit(0)
    msg = ("OPERATING-COMMITMENT GUARD: your message commits to a change in how you operate, "
           "but " + " ".join(missing))
    if MODE == "warn":
        sys.stderr.write(msg + "\n")
        sys.exit(0)
    cpath = counter_path(payload.get("session_id", ""))
    n = read_count(cpath)
    if n >= MAX_BLOCKS:
        try:
            cpath.unlink()
        except Exception:
            pass
        sys.exit(0)
    try:
        cpath.write_text(str(n + 1))
    except Exception:
        pass
    sys.stderr.write(msg + "\n")
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
