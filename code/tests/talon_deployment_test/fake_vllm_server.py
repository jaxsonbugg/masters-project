"""A stand-in for `vllm serve`, used ONLY by the local Talon shell tests (shtest_talon.sh).

PLACEHOLDER, NOT A MODEL OF THE REAL vLLM. Nothing here was copied from a real vLLM run on Talon (there has been none). The
Talon scripts are written so that no pass/fail depends on the wording of the server log, only on HTTP answers, exit codes and
nvidia-smi readings, so this fake cannot make a wrong log check look right (the mistake of Redhawk job 2510690). After the first
real Talon run, its real log and one real reply replace the placeholders here.

Endpoints: /health (503 for the first second, like a server still loading), /v1/models (lists --served-model-name), and a
slot-aware /v1/chat/completions. Behaviour switches (environment):
  FAKE_MODE            good | badjson | truncate (cut off, reasoning only) | reasoning_only (stop, empty content) | mixed (every
                       4th item cut off)
  FAKE_REASONING_FIELD reasoning (newer vLLM, default) or reasoning_content (older vLLM, llama.cpp)
  FAKE_WRONG_NAME=1    /v1/models lists another model name
  FAKE_DIE=1           exit while "loading"
  FAKE_FAIL_ITEM       that item id answers HTTP 500 once (FAKE_STATE marks it)
  FAKE_DELAY           seconds per request (default 0.05) so the client's wall-clock time is never zero
Exits by itself after 300 s so it can never linger."""
import json, os, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[1]); t0 = time.time()
if os.environ.get("FAKE_DIE") == "1":
    print("fake vllm: dying while loading (test)", flush=True); sys.exit(1)
threading.Timer(300, os._exit, [0]).start()
MODE = os.environ.get("FAKE_MODE", "good")
FIELD = os.environ.get("FAKE_REASONING_FIELD", "reasoning")
ARGS = os.environ.get("FAKE_SERVER_ARGS", "")
m = re.search(r"--served-model-name (\S+)", ARGS)
SERVED = "some-other-model" if os.environ.get("FAKE_WRONG_NAME") == "1" else (m.group(1) if m else "unknown")
FAIL_ITEM = os.environ.get("FAKE_FAIL_ITEM", ""); STATE = os.environ.get("FAKE_STATE", "")
DELAY = float(os.environ.get("FAKE_DELAY", "0.05"))


def make_item(cat, sub, diff, atype):
    it = {"question": "x", "answer_type": atype, "choices": [], "working": "w", "r_solution": "", "canonical_answer": "",
          "answer_tolerance": 0, "r_check": "", "explanation": "A short explanation sentence.", "difficulty": diff,
          "category": cat, "subtopic": sub}
    if atype == "number":
        it.update(question="A fair coin is tossed 5 times. What is the probability of exactly 2 heads? Give your answer to 3 decimal places.",
                  r_solution="cat(dbinom(2, 5, 0.5))", canonical_answer="0.313", answer_tolerance=0.0005)
    elif atype == "multiple_choice":
        it.update(question="Which statement about the sample mean is true?",
                  choices=["It is unbiased for the population mean", "It is always equal to the median", "It ignores outliers", "It has zero variance"],
                  canonical_answer="A")
    elif atype == "r_expression":
        it.update(question="Write one line of R that returns the sum of the integers from 1 to 10.", canonical_answer="sum(1:10)",
                  r_check="isTRUE(all.equal(eval(parse(text = candidate)), 55))")
    elif atype == "short_text":
        it.update(question="What is the name of the statistic that measures the average squared deviation from the mean?", canonical_answer="variance")
    return it


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if time.time() - t0 < 1:
            return self.send(503, {"error": "loading"})
        if self.path.startswith("/v1/models"):
            return self.send(200, {"object": "list", "data": [{"id": SERVED, "object": "model", "owned_by": "vllm"}]})
        return self.send(200, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        time.sleep(DELAY)
        user = body["messages"][1]["content"]
        iid = re.search(r"item (BM\d{4})", user).group(1)
        g = lambda k: re.search(rf"^{k}: (\S+)", user, re.M).group(1)
        cat, diff, atype = g("Category"), g("Difficulty"), g("Answer type")
        sub = re.search(r"^Subtopic: (.+)$", user, re.M).group(1)
        if FAIL_ITEM == iid and STATE and not os.path.exists(STATE + "." + iid):
            open(STATE + "." + iid, "w").write("failed once")
            self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
        content, finish, completion = json.dumps(make_item(cat, sub, diff, atype)), "stop", 800
        cut = MODE == "truncate" or (MODE == "mixed" and int(iid[2:]) % 4 == 0)
        if MODE == "badjson":
            content = "I believe the answer is 42."
        elif cut:
            content, finish, completion = "", "length", body.get("max_tokens", 16384)
        elif MODE == "reasoning_only":
            content = ""
        out = {"model": body["model"], "choices": [{"message": {"role": "assistant", "content": content, FIELD: "thinking about it"},
                                                    "finish_reason": finish}],
               "usage": {"prompt_tokens": 500, "completion_tokens": completion}}
        self.send(200, out)


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
