"""A stand-in for the Claude CLI, used ONLY by code/tests/key_check_test/test_key_check.py. It never contacts any service.

It imitates the parts of `claude` that key_check.py uses: `--version`, `auth status --json`, and `-p ...` (prompt on stdin,
stream-json events on stdout). PLACEHOLDER, NOT A MODEL OF THE REAL CLI: the real event format is checked in the
owner-approved pilot, and the fake is updated from it.

Switches (environment):
  FAKE_CLAUDE_MODE     good (default) | tool_use | api_source | no_source | malformed | error_result
  FAKE_CLAUDE_AUTH     subscription (default) | api_key | logged_out
  FAKE_CLAUDE_ANSWERS  a JSON file {anonymous id: entry} that replaces the default entries
  FAKE_CLAUDE_LOG      a file to which every call appends {"argv", "anthropic_env": [names], "stdin"}
"""
import json
import os
import re
import sys

argv = sys.argv[1:]
stdin = sys.stdin.read() if "-p" in argv else ""
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": argv, "anthropic_env": sorted(k for k in os.environ if k.upper().startswith("ANTHROPIC")),
                            "claude_env": sorted(k for k in os.environ if k.upper().startswith("CLAUDE")),
                            "cwd": os.getcwd(), "stdin": stdin}) + "\n")

if argv[:1] == ["--version"]:
    print("9.9.9 (Claude Code, fake)")
    sys.exit(0)
if argv[:2] == ["auth", "status"]:
    a = os.environ.get("FAKE_CLAUDE_AUTH", "subscription")
    st = {"subscription": {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "team",
                           "consoleProfileSignInOffered": True, "email": "x@example.org"},
          "api_key": {"loggedIn": True, "authMethod": "api_key", "apiKeySource": "ANTHROPIC_API_KEY"},
          "logged_out": {"loggedIn": False}}[a]
    print(json.dumps(st))
    sys.exit(0)
if "-p" not in argv:
    print("fake claude: unsupported call", argv, file=sys.stderr)
    sys.exit(64)

mode = os.environ.get("FAKE_CLAUDE_MODE", "good")
if mode == "usage_limit":
    print(json.dumps({"type": "system", "subtype": "init", "model": "fake-claude-1", "tools": [], "mcp_servers": [],
                      "apiKeySource": "none"}))
    # the shape of the real event stream when the five-hour window is full (2026-11-25): a rejected rate_limit_event, a
    # synthetic reply, and a result whose text does NOT name the limit
    print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour",
                      "unifiedWindows": {"five_hour": {"utilization": 1, "status": "rejected"}}}}))
    print(json.dumps({"type": "assistant", "message": {"model": "<synthetic>", "content": [
        {"type": "text", "text": "You've hit your 5-hour limit · resets 4:10am (America/New_York)"}]}}))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "", "usage": {}}))
    sys.exit(1)
schema = json.loads(argv[argv.index("--json-schema") + 1])
top = list(schema["properties"])[0]
item_props = schema["properties"][top]["items"]["properties"]
m = re.search(r"<<<BATCH START>>>\n(.*)<<<BATCH END>>>", stdin, re.S)
rows = [json.loads(l) for l in (m.group(1).splitlines() if m else []) if l.strip()]
override = json.load(open(os.environ["FAKE_CLAUDE_ANSWERS"], encoding="utf-8")) if os.environ.get("FAKE_CLAUDE_ANSWERS") else {}


def default(r):
    at = r.get("answer_type")
    if top == "verdicts":
        return {"verdict": "pass", "issue_type": "none", "reason": "clear and answerable"}
    if top == "variants":
        return {"key_concern": "", "variants": [{"expression": "1", "what_is_wrong": "constant", "counterexample": "x <- 1"}] * 3}
    if top == "briefs":
        return {"brief": "the key looks right", "reading": "key_likely_correct", "confidence": "medium"}
    if "status" in item_props:
        return {"status": "not_applicable", "r_code": "", "answer_expression": "", "test_inputs": [],
                "correct_options": ["A"] if at == "multiple_choice" else [], "note": "conceptual"}
    return {"answer": "A" if at == "multiple_choice" else "1", "correct_options": ["A"] if at == "multiple_choice" else [],
            "working": "reasoned", "confidence": "high"}


out = {top: [{"id": r["id"], **override.get(r["id"], default(r))} for r in rows]}
events = [{"type": "system", "subtype": "init", "model": "fake-claude-1",
           "tools": ["Bash"] if mode == "tool_use" else [], "mcp_servers": [],
           **({} if mode == "no_source" else {"apiKeySource": "ANTHROPIC_API_KEY" if mode == "api_source" else "none"})},
          {"type": "assistant", "message": {"model": "fake-claude-1", "content": [{"type": "thinking", "thinking": "..."},
           {"type": "tool_use", "id": "t1", "name": "StructuredOutput", "input": out}]}},
          {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}]
result = {"type": "result", "subtype": "error_during_execution" if mode == "error_result" else "success",
          "is_error": mode == "error_result", "num_turns": 2, "result": "",
          "usage": {"input_tokens": 1500, "output_tokens": 700}, "total_cost_usd": 0.05}
if mode == "malformed":
    events[1]["message"]["content"] = [{"type": "text", "text": "Here you go: {"}]
    result["result"] = "Here you go: {"
else:
    result["structured_output"] = out
events.append(result)
for e in events:
    print(json.dumps(e))
sys.exit(1 if mode == "error_result" else 0)
