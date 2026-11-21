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
  FAKE_ANSWER_FAIL     on | off: every ANSWERING request (stage K) in that thinking mode answers HTTP 500
  FAKE_FLAKY=1         (generator tests, added 2026-11-19) the FIRST request for every item gets a reply that is not JSON,
                       so the generator must ask again; later requests are answered normally
  FAKE_BAD_ITEMS       comma-separated item ids that always get a reply that is not JSON (they fail all attempts)
  FAKE_LONG_ITEMS      comma-separated training ids whose worked answer is far over 2,048 Pythia tokens
The generator's requests (benchmark prompt v7 for BM/DV/SM ids, training prompt v1 for TR/TRR/TV/SM ids) are answered
with a well-formed reply of the right kind; the training reply echoes the slot's context.
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


def make_training_item(cat, sub, diff, atype, context, iid):
    it = {"question": f"Training question {iid} about {sub} in the setting {context}. Give your answer to 3 decimal places.",
          "choices": [], "answer_type": atype, "worked_answer": "Step 1: set up the calculation.\nStep 2: compute it.",
          "final_answer": "0.313", "category": cat, "subtopic": sub, "difficulty": diff, "context": context,
          "r_solution": "cat(dbinom(2, 5, 0.5))" if atype == "number" else ""}
    if atype == "multiple_choice":
        it.update(question=f"Training question {iid}: which statement about {sub} is true?",
                  choices=["The first statement", "The second statement", "The third statement", "The fourth statement"],
                  final_answer="B")
    elif atype == "r_expression":
        it.update(question=f"Training question {iid}: write one line of R for {sub}.", final_answer="sum(1:10)")
    elif atype == "short_text":
        it.update(question=f"Training question {iid}: name the statistic for {sub}.", final_answer="variance")
    if iid in LONG_ITEMS:
        it["worked_answer"] = " ".join(["The sample mean of the measured values is computed step by step."] * 400)
    return it


SEEN = {}
BAD_ITEMS = set(filter(None, os.environ.get("FAKE_BAD_ITEMS", "").split(",")))
LONG_ITEMS = set(filter(None, os.environ.get("FAKE_LONG_ITEMS", "").split(",")))


def generator_reply(body, user, think):
    m = re.search(r"^Write (benchmark item|training example) (\S+)\.$", user, re.M)
    iid = m.group(2)
    g = lambda k: re.search(rf"^{k}: (\S+)", user, re.M).group(1)
    cat, diff, atype = g("Category"), g("Difficulty"), g("Answer type")
    sub = re.search(r"^Subtopic: (.+)$", user, re.M).group(1)
    SEEN[iid] = SEEN.get(iid, 0) + 1
    if m.group(1) == "training example":
        context = re.search(r'context "([^"]*)"', user).group(1)
        item = make_training_item(cat, sub, diff, atype, context, iid)
    else:
        item = make_item(cat, sub, diff, atype)
    content = json.dumps(item)
    if iid in BAD_ITEMS or (os.environ.get("FAKE_FLAKY") == "1" and SEEN[iid] == 1):
        content = "I believe the answer is 42."
    msg = {"role": "assistant", "content": content}
    if think:
        msg[FIELD] = "thinking about it"
    return {"model": body["model"], "choices": [{"message": msg, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 700}}


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
        # chat_template_kwargs.enable_thinking false (the thinking check): no reasoning field, far fewer tokens
        think = (body.get("chat_template_kwargs") or {}).get("enable_thinking", True)
        if "Answer format:" in user:   # an ANSWERING request (stage K): working, then one final line
            if os.environ.get("FAKE_ANSWER_FAIL") == ("on" if think else "off"):   # every answering call in that mode fails
                self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
            msg = {"role": "assistant", "content": "Working it out.\nFinal answer: 0.313"}
            if think:
                msg[FIELD] = "thinking about it"
            return self.send(200, {"model": body["model"], "choices": [{"message": msg, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 300, "completion_tokens": 900 if think else 60}})
        if re.search(r"^Write (benchmark item|training example) (?!BM\d{4}\.)", user, re.M):   # generate_set.py
            return self.send(200, generator_reply(body, user, think))
        iid = re.search(r"item (BM\d{4})", user).group(1)
        g = lambda k: re.search(rf"^{k}: (\S+)", user, re.M).group(1)
        cat, diff, atype = g("Category"), g("Difficulty"), g("Answer type")
        sub = re.search(r"^Subtopic: (.+)$", user, re.M).group(1)
        if FAIL_ITEM == iid and STATE and not os.path.exists(STATE + "." + iid):
            open(STATE + "." + iid, "w").write("failed once")
            self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
        content, finish, completion = json.dumps(make_item(cat, sub, diff, atype)), "stop", 800
        cut = MODE == "truncate" or (MODE == "mixed" and int(iid[2:]) % 4 == 0)
        if MODE == "badjson" or iid in BAD_ITEMS:   # FAKE_BAD_ITEMS also for BM ids (replacement-loop tests, 2026-11-21)
            content = "I believe the answer is 42."
        elif cut:
            content, finish, completion = "", "length", body.get("max_tokens", 16384)
        elif MODE == "reasoning_only":
            content = ""
        msg = {"role": "assistant", "content": content}
        if think:
            msg[FIELD] = "thinking about it"
        out = {"model": body["model"], "choices": [{"message": msg, "finish_reason": finish}],
               "usage": {"prompt_tokens": 500, "completion_tokens": completion}}
        self.send(200, out)


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
