"""A stand-in for the Codex CLI, used ONLY by code/tests/codex_test/test_codex_batch.py. It never contacts any service.

It imitates the parts of `codex` that codex_batch.py uses: `--version`, `features list`, and `exec ... -` (prompt on stdin,
verdicts written to the -o file, JSONL events on stdout). PLACEHOLDER, NOT A MODEL OF THE REAL CLI: the real event format is
checked during the owner-approved integration batch, and the fake is updated from it.

Switches (environment):
  FAKE_CODEX_MODE      good (default; the first id is flagged, the rest pass) | malformed | missing | extra | duplicate |
                       bad_enum | empty | nonzero | timeout | tool_use
  FAKE_CODEX_LOG       a file to which every call appends {"argv": [...], "stdin": "..."} (to check what the tool sent)
  FAKE_CODEX_NO_FEATURE  a feature name to leave out of `features list`
"""
import json
import os
import re
import sys
import time

argv = sys.argv[1:]
stdin = sys.stdin.read() if "exec" in argv else ""
log = os.environ.get("FAKE_CODEX_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": argv, "stdin": stdin}) + "\n")

if argv[:1] in (["--version"], ["-V"]):
    print("codex-cli 9.9.9-fake")
    sys.exit(0)
if argv[:2] == ["features", "list"]:
    names = ["apps", "plugins", "remote_plugin", "browser_use", "browser_use_external", "browser_use_full_cdp_access",
             "in_app_browser", "computer_use", "image_generation", "view_image", "multi_agent", "hooks", "goals",
             "tool_suggest", "unified_exec", "fast_mode"]
    for n in names:
        if n != os.environ.get("FAKE_CODEX_NO_FEATURE"):
            print(f"{n:<40} stable             true")
    sys.exit(0)
if argv[:1] != ["exec"]:
    print("fake codex: unsupported call", argv, file=sys.stderr)
    sys.exit(64)

mode = os.environ.get("FAKE_CODEX_MODE", "good")
out = argv[argv.index("-o") + 1]
m = re.search(r"^Batch ids \(\d+\): (.*)$", stdin, re.M)
ids = [i.strip() for i in m.group(1).split(",")] if m else []
if mode == "timeout":
    time.sleep(30)
# FAKE_CODEX_FAIL_FIRST=<n> with FAKE_CODEX_COUNTER=<file>: the first n calls answer malformed (tests a bounded retry)
counter = os.environ.get("FAKE_CODEX_COUNTER")
if counter:
    n_calls = int(open(counter).read()) + 1 if os.path.exists(counter) else 1
    open(counter, "w").write(str(n_calls))
    if n_calls <= int(os.environ.get("FAKE_CODEX_FAIL_FIRST", "0")):
        mode = "malformed"
flag_first = os.environ.get("FAKE_CODEX_PASS_ALL") != "1"
if ids and ids[0].startswith("A-"):          # an alignment batch (align_v1): the first id is only "partly" aligned
    verdicts = [{"id": i, "subtopic_verdict": "partly" if (k == 0 and flag_first) else "aligned",
                 "subtopic_reason": "tests the subtopic", "difficulty_verdict": "matches",
                 "difficulty_reason": "fits the level"} for k, i in enumerate(ids)]
else:
    verdicts = [{"id": i, "verdict": "flag" if (k == 0 and flag_first) else "pass",
                 "issue_type": "missing_information" if (k == 0 and flag_first) else "none",
                 "reason": "a needed value is not given" if (k == 0 and flag_first) else "clear and answerable"}
                for k, i in enumerate(ids)]
if mode == "missing":
    verdicts = verdicts[1:]
elif mode == "extra":
    verdicts.append({"id": "S-99-999", "verdict": "pass", "issue_type": "none", "reason": "x"})
elif mode == "duplicate":
    verdicts.append(dict(verdicts[0]))
elif mode == "bad_enum":
    verdicts[0]["verdict"] = "maybe"
text = json.dumps({"verdicts": verdicts})
if mode == "malformed":
    text = "Here are my verdicts: " + text[:40]
if mode != "empty":
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
events = [{"type": "thread.started", "thread_id": "fake-thread"},
          {"type": "session.configured", "model": "fake-model-1", "reasoning_effort": "medium"},
          {"type": "item.completed", "item": {"id": "i0", "type": "reasoning", "text": "thinking"}}]
if mode == "tool_use":
    events.append({"type": "item.started", "item": {"id": "i1", "type": "command_execution", "command": "ls"}})
events += [{"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": text}},
           {"type": "turn.completed", "usage": {"input_tokens": 1200, "cached_input_tokens": 0, "output_tokens": 300}}]
for e in events:
    print(json.dumps(e))
sys.exit(3 if mode == "nonzero" else 0)
