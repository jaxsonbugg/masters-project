"""A stand-in for llama-server used ONLY by the local shell tests: /health (503 while 'loading'), and a slot-aware
chat endpoint. Exits by itself after 150 s so it can never linger."""
import json, os, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[1]); t0 = time.time()
if os.environ.get("FAKE_DIE") == "1":
    print("fake: dying while loading (test)", flush=True); sys.exit(1)
threading.Timer(150, os._exit, [0]).start()
MODE = os.environ.get("FAKE_MODE", "good")
FAIL_ITEM = os.environ.get("FAKE_FAIL_ITEM", "")
STATE = os.environ.get("FAKE_STATE", "")

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
    def do_GET(self):
        loading = time.time() - t0 < 2
        self.send_response(503 if loading else 200); self.end_headers()
        self.wfile.write(b'{"error":{"message":"Loading model"}}' if loading else b'{"status":"ok"}')
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = body["messages"][1]["content"]
        iid = re.search(r"item (BM\d{4})", user).group(1)
        g = lambda k: re.search(rf"^{k}: (\S+)", user, re.M).group(1)
        cat, diff, atype = g("Category"), g("Difficulty"), g("Answer type")
        sub = re.search(r"^Subtopic: (.+)$", user, re.M).group(1)
        if FAIL_ITEM == iid and STATE and not os.path.exists(STATE + "." + iid):
            open(STATE + "." + iid, "w").write("failed once")
            self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
        content = "I believe the answer is 42." if MODE == "badjson" else json.dumps(make_item(cat, sub, diff, atype))
        out = {"model": body["model"], "choices": [{"message": {"content": content, "reasoning_content": "thinking"}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 500, "completion_tokens": 800}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)

ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
