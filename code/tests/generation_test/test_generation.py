"""Tests for the full-size generation and decontamination code (approved plan of 2026-11-19, Step 8):
code/generation/variety.py, set_prompts.py, generate_set.py and code/verification/decontaminate.py.

Everything is local and synthetic: slot files are dealt into a temporary folder, the teacher is the fake vLLM server of the
Talon tests (code/tests/talon_deployment_test/fake_vllm_server.py), and no Talon job, internet call or paid service is used.
The embedding test uses the pinned all-MiniLM-L6-v2 files on this PC (configs/paths.yaml models_embedding) and the training
length test the pinned Pythia tokenizer; both are skipped with a note if the files are missing. No R is run here.
Usage: python test_generation.py"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

CODE = Path(__file__).resolve().parents[2]
REPO = CODE.parent
sys.path.insert(0, str(CODE / "generation"))
sys.path.insert(0, str(CODE / "verification"))
import generate_benchmark as gb  # noqa: E402
import set_prompts as sp  # noqa: E402
import variety  # noqa: E402
import generate_set as gs  # noqa: E402
import decontaminate as dc  # noqa: E402

PY = sys.executable
FAKE = str(CODE / "tests" / "talon_deployment_test" / "fake_vllm_server.py")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {str(detail)[:400]}")


def raises(fn):
    try:
        fn()
    except (SystemExit, variety.TaxonomyError, ValueError) as e:
        return str(e) or True
    return False


T = Path(tempfile.mkdtemp(prefix="gen_test_"))


def deal(set_name, n, seed, out):
    return variety.cmd_deal(SimpleNamespace(set=set_name, n=n, seed=seed, out=str(out), overwrite=False,
                                            taxonomy=str(variety.TAXONOMY_FILE), contexts=str(variety.CONTEXTS_FILE)))


# ------------------------------------------------------------------ 1. the taxonomy and the dealer
print("[1] taxonomy checks and the dealer")
bad = T / "dup.yaml"
bad.write_text("categories:\n  numerical:\n    answer_type: number\n    areas:\n      a: [x]\n      a: [y]\n", encoding="utf-8")
check("a key repeated in one block (two areas with the same name) is refused, not silently dropped",
      "appears twice" in str(raises(lambda: variety.load_taxonomy(bad))))
rep = T / "rep.yaml"
rep.write_text("categories:\n  numerical:\n    answer_type: number\n    areas:\n      a: [x, y]\n      b: [x]\n", encoding="utf-8")
check("a subtopic listed twice in one category is refused", "more than once" in str(raises(lambda: variety.load_taxonomy(rep))))
blocks, tax_sha = variety.load_taxonomy()
ctx, ctx_sha = variety.load_contexts()
check("the repository taxonomy loads: 673 subtopics, both R-interpretation blocks",
      sum(len(s) for b in blocks.values() for s in b["areas"].values()) == 673)
need = variety.requirement(1150)
short = [k for k, v in need.items()
         if v > sum(len(s) for b in blocks.values() if (b["category"], b["answer_type"]) == k[:2] for s in b["areas"].values())]
check("the size rule holds for the 1,150-slot benchmark (enough subtopics in every category, answer type and difficulty)", not short, short)
s1, m1 = deal("benchmark", 1150, "seed-A", T / "a")
s2, m2 = deal("benchmark", 1150, "seed-A", T / "b")
s3, m3 = deal("benchmark", 1150, "seed-B", T / "c")
check("dealing is deterministic: the same seed gives byte-identical slot files", s1.read_bytes() == s2.read_bytes())
check("a different seed gives a different deal", s1.read_bytes() != s3.read_bytes())
bm = variety.read_slots(s1)
pairs = Counter((s["category"], s["answer_type"], s["subtopic"], s["difficulty"]) for s in bm)
check("no (subtopic, difficulty) pair repeats within the 1,150 benchmark slots", max(pairs.values()) == 1, pairs.most_common(2))
check("every slot carries slot_scheme taxonomy-v2 and the ids run BM0001-BM1150",
      all(s["slot_scheme"] == "taxonomy-v2" for s in bm) and bm[0]["item_id"] == "BM0001" and bm[-1]["item_id"] == "BM1150")
mix = Counter(s["category"] for s in bm[:1000])
check("the first 1,000 slots have the target category mix 30/20/20/15/15",
      mix == Counter({"numerical": 300, "conceptual": 200, "r_generation": 200, "r_interpretation": 150, "output_interpretation": 150}), mix)
st, _ = deal("train", 6000, "seed-T", T / "t")
tr = variety.read_slots(st)
for cat, share in ctx["shares"].items():
    cs = [s for s in tr if s["category"] == cat]
    got = sum(1 for s in cs if s["context"] == "none") / len(cs)
    check(f"no-context share for {cat} is {share:.2f} (got {got:.3f} over 6,000 slots)", abs(got - share) < 0.02)
rint = Counter((s["answer_type"], s["difficulty"]) for s in tr if s["category"] == "r_interpretation")
check("R interpretation is 2:1 number to short text and each answer type meets both difficulties",
      all(rint[(a, d)] > 0 for a in ("number", "short_text") for d in ("intro", "intermediate"))
      and abs(sum(v for (a, _), v in rint.items() if a == "number") / sum(rint.values()) - 2 / 3) < 0.02, rint)
# continued decks: a replacement continues the deck where the deal stopped and never re-deals a card of the current cycle
man = json.loads(m3.read_text(encoding="utf-8"))
like = bm[0]
d = variety.Dealer(blocks, ctx, man["seed"], state=man["deck_state"])
block = d.block_of[(like["category"], like["answer_type"])]
deck = d.sub_decks[(block, like["difficulty"])]
start = deck.dealt
n_cycle = len(deck._cycle(0))
cycle_start = start - start % n_cycle
already = {deck.card(i)[1] for i in range(cycle_start, start)}
new = variety.deal_replacements(m3, [variety.read_slots(s3)[0]] * 3)
check("replacement slots keep category, difficulty, answer type, context and letter, and say what they replace",
      all((n["category"], n["difficulty"], n["answer_type"], n["context"], n["preferred_letter"], n["replaces"]) ==
          (variety.read_slots(s3)[0]["category"], variety.read_slots(s3)[0]["difficulty"], variety.read_slots(s3)[0]["answer_type"],
           variety.read_slots(s3)[0]["context"], variety.read_slots(s3)[0]["preferred_letter"], "BM0001") for n in new))
check("benchmark spares continue the set's numbering (BM1151, BM1152, BM1153)", [n["item_id"] for n in new] == ["BM1151", "BM1152", "BM1153"])
d2 = variety.Dealer(blocks, ctx, man["seed"], state=man["deck_state"])
deck2 = d2.sub_decks[(d2.block_of[(new[0]["category"], new[0]["answer_type"])], new[0]["difficulty"])]
check("the replacement subtopics are the next cards of the continued deck, none dealt earlier in this cycle",
      [n["subtopic"] for n in new] == [deck2.card(start + k)[1] for k in range(3)]
      and (start + 3 > cycle_start + n_cycle or not ({n["subtopic"] for n in new} & already)))
man3 = json.loads(m3.read_text(encoding="utf-8"))
check("the manifest records the new deck state and every version of the replacements file's fingerprint",
      man3["deck_state"] != man["deck_state"] and man3["replacements_sha256"] in man3["replacements_sha256_history"])
tr_rep = variety.deal_replacements(T / "t" / "train_slots.manifest.json", [tr[4]])
check("training replacements are numbered TRR000001 on", tr_rep[0]["item_id"] == "TRR000001" and tr_rep[0]["replaces"] == "TR000005")

# ------------------------------------------------------------------ 2. prompts and reply checks
print("[2] prompts v7 and training v1, and the reply checks")
p6, _ = gb.load_prompt()
p7, sha7, v7 = sp.load_prompt("benchmark-v7")
ptr1, shatr1, vtr1 = sp.load_prompt("training-v1")
p8, sha8, v8 = sp.load_prompt("benchmark")
ptr, shatr, vtr = sp.load_prompt("training")
check("the v6 prompt is unchanged (pinned SHA-256 348db6ff...)",
      gb.load_prompt()[1] == "348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4")
check("the earlier prompt files are unchanged (v7 980f5570..., training v1 db9ca660...)",
      sha7.startswith("980f5570") and shatr1.startswith("db9ca660"))
check("new runs use benchmark-v8 and training-v2", (v8, vtr) == ("benchmark-v8", "training-v2"))
s7, s8 = p7[("SYSTEM", None)].split("\n"), p8[("SYSTEM", None)].split("\n")
check("v8's system text is v7's plus exactly one rule, 2b 'Plain text only'",
      [l for l in s8 if l not in s7] == [l for l in s8 if l.startswith("2b. Plain text only")] and len(s8) == len(s7) + 1
      and all(p7[k] == p8[k] for k in p7 if k != ("SYSTEM", None)))
t1, t2 = ptr1[("SYSTEM", None)].split("\n"), ptr[("SYSTEM", None)].split("\n")
check("training v2 is v1 plus rule 2a 'Plain text only', with LaTeX named in rule 3; nothing else changed",
      [l for l in t2 if l not in t1 and not l.startswith(("2a. Plain text only", "3. The worked_answer"))] == []
      and len(t2) == len(t1) + 1 and all(ptr1[k] == ptr[k] for k in ptr1 if k != ("SYSTEM", None)))
slot = dict(bm[0])
slot_v6 = {k: slot[k] for k in ("item_id", "category", "subtopic", "difficulty", "answer_type", "preferred_letter")}
u6 = gb.build_request(slot_v6, p6)["messages"][0]["content"].split("\n")
u7 = sp.build_request(slot, p7, "benchmark-v7")["messages"][0]["content"].split("\n")
extra = [l for l in u7 if l not in u6]
check("the v7 user message is v6's plus exactly one line, the Setting line (v8 keeps the same user message)", len(u7) == len(u6) + 1 and len(extra) == 1
      and sp.build_request(slot, p8, "benchmark")["messages"] == sp.build_request(slot, p7, "benchmark-v7")["messages"]
      and extra[0].startswith("Setting: "), extra)
sys6, sys7 = p6[("SYSTEM", None)].split("\n"), p7[("SYSTEM", None)].split("\n")
check("the v7 system text differs from v6 in exactly one line (the corrected grading sentence)",
      len(sys6) == len(sys7) and sum(a != b for a, b in zip(sys6, sys7)) == 1 and "final-answer line" in p7[("SYSTEM", None)])
none_slot = {**slot, "context": "none", "context_text": ""}
check("a 'none' card asks for a question with no real-world story",
      "Setting: none. Write a purely statistical or R question" in sp.build_request(none_slot, p7, "benchmark")["messages"][0]["content"])
check("a v1-blueprint slot (no slot_scheme) is refused by the new prompts", bool(raises(lambda: sp.build_request(slot_v6, p7, "benchmark"))))
check("the training prompt is refused for a benchmark id", bool(raises(lambda: sp.build_request(slot, ptr, "training"))))
check("'No:' as a table row label is NOT thinking aloud (the Stage T false alarm, BM9115)",
      sp.thinking_aloud("Smoker | Yes: 14 | total 40\nNo: 26 | total 40") is None)
check("a lowercase 'no:' in mid-sentence still is", sp.thinking_aloud("the count must be 3... no: exactly 2 statisticians") is not None)
check("'Wait, ...' and 'Actually, ...' still are", sp.thinking_aloud("Wait, use 5 trials.") and sp.thinking_aloud("Ok. Actually, use 4."))
good_bm = {"question": "A fair coin is tossed 5 times. What is the probability of exactly 2 heads? Give your answer to 3 decimal places.",
           "answer_type": "number", "choices": [], "working": "C(5,2)/32", "r_solution": "cat(dbinom(2, 5, 0.5))",
           "canonical_answer": "0.313", "answer_tolerance": 0.0005, "r_check": "", "explanation": "Binomial with n = 5, p = 0.5.",
           "difficulty": "intro", "category": "numerical", "subtopic": "s"}
nslot = {"item_id": "DV0001", "category": "numerical", "subtopic": "s", "difficulty": "intro", "answer_type": "number"}
check("a good v7 benchmark reply passes", sp.check_benchmark_item(good_bm, nslot) == [], sp.check_benchmark_item(good_bm, nslot))
check("v7 requires the working field", "missing field working" in sp.check_benchmark_item({k: v for k, v in good_bm.items() if k != "working"}, nslot))
check("v7 requires the r_solution field", "missing field r_solution" in sp.check_benchmark_item({k: v for k, v in good_bm.items() if k != "r_solution"}, nslot))
check("a reply cut off at max_tokens is unusable", "cut off at max_tokens" in sp.check_benchmark_item(good_bm, nslot, "length"))
tslot = {"category": "numerical", "subtopic": "s", "difficulty": "intro", "answer_type": "number", "context": "sports"}
good_tr = {"question": "A player makes 70% of free throws. What is P(exactly 4 of 5)? Give your answer to 3 decimal places.",
           "choices": [], "answer_type": "number", "worked_answer": "X is binomial with n = 5, p = 0.7.\nP(X = 4) = 5 x 0.7^4 x 0.3 = 0.36015.",
           "final_answer": "0.360", "category": "numerical", "subtopic": "s", "difficulty": "intro", "context": "sports",
           "r_solution": "cat(dbinom(4, 5, 0.7))"}
check("a good training reply passes the format checks", sp.check_training_item(good_tr, tslot) == [], sp.check_training_item(good_tr, tslot))
check("'Final answer' inside the worked answer is refused (exactly one final answer line)",
      any("final answer" in p for p in sp.check_training_item({**good_tr, "worked_answer": "... Final answer: 0.36"}, tslot)))
check("a worked answer that corrects itself is refused",
      any("thinks aloud" in p for p in sp.check_training_item({**good_tr, "worked_answer": "P = 0.4. Wait, P = 0.36."}, tslot)))
check("'Let me define X' is ordinary tutoring language in a worked answer",
      sp.check_training_item({**good_tr, "worked_answer": "Let me define X as the number made. P(X = 4) = 0.36015."}, tslot) == [])
check("a context different from the slot's is refused", any("context differs" in p for p in sp.check_training_item({**good_tr, "context": "finance"}, tslot)))
check("decimals that disagree with the question are refused", any("decimal" in p for p in sp.check_training_item({**good_tr, "final_answer": "0.36"}, tslot)))
mc_slot = {**tslot, "answer_type": "multiple_choice"}
mc = {**good_tr, "answer_type": "multiple_choice", "question": "Which is true?", "final_answer": "B",
      "choices": ["A. one", "B. two", "C. three", "D. four"]}
check("multiple-choice choices with letter labels are refused (the code adds A. to D.)",
      any("letter label" in p for p in sp.check_training_item(mc, mc_slot)))
mc_ok = {**mc, "choices": ["one", "two", "three", "four"]}
text = sp.training_text(mc_ok)
check("the student text is Question / A.-D. / Answer / Final answer, in that order",
      text.split("\n")[:5] == ["Question: Which is true?", "A. one", "B. two", "C. three", "D. four"] and text.split("\n")[-1] == "Final answer: B"
      and text.split("\n")[5].startswith("Answer: "))
try:
    tl = sp.TrainingLength()
    long_item = {**good_tr, "worked_answer": " ".join(["The mean of the sample is computed step by step."] * 300)}
    lt = sp.training_text(long_item)
    n, prob = tl.check(lt)
    check("an over-long example (> 2,048 Pythia tokens) is rejected, not truncated (the text is unchanged)",
          prob is not None and n > 2048 and sp.training_text(long_item) == lt, (n, prob))
    n2, prob2 = tl.check(sp.training_text(good_tr))
    check("a short example fits, and the count includes the end-of-text token", prob2 is None and n2 == len(tl.tok.encode(sp.training_text(good_tr), add_special_tokens=False).ids) + 1)
except (OSError, Exception) as e:   # the pinned tokenizer is outside the repository
    print(f"  NOTE  Pythia tokenizer not available, length tests skipped ({e})")

# ------------------------------------------------------------------ 3. the generator against the fake server
print("[3] generate_set.py run/validate/collect against the fake vLLM server")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


port = free_port()
env = {**os.environ, "FAKE_FLAKY": "1", "FAKE_BAD_ITEMS": "SM0004", "FAKE_DELAY": "0.01",
       "FAKE_SERVER_ARGS": "--served-model-name qwen3.6-27b-bf16"}
srv = subprocess.Popen([PY, FAKE, str(port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
sm_path, sm_man = deal("smoke", 24, "seed-S", T / "slots")
OUT = T / "outputs"
OUT.mkdir()


def run(*extra):
    r = subprocess.run([PY, str(CODE / "generation" / "generate_set.py"), "run", "--slots", str(sm_path), "--base-url",
                        f"http://127.0.0.1:{port}/v1", "--out-root", str(OUT), "--retry-wait", "0.1", *extra],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


try:
    rc1, o1 = run("--prompt", "benchmark", "--first", "1", "--count", "12", "--shard", "1/2")
    rc2, o2 = run("--prompt", "benchmark", "--first", "1", "--count", "12", "--shard", "2/2")
    dirs = sorted(OUT.glob("*_smoke_benchmark-v8_*"))
    ids = [json.loads(l)["item_id"] for d_ in dirs for l in (d_ / "done_index.jsonl").read_text().splitlines()]
    check("two shards together cover SM0001-SM0012 exactly, each slot in one shard only",
          rc1 == 0 and rc2 == 0 and len(dirs) == 2 and sorted(set(ids)) == [f"SM{k:04d}" for k in range(1, 13)]
          and not (set(json.loads(l)["item_id"] for l in (dirs[0] / "done_index.jsonl").read_text().splitlines()) &
                   set(json.loads(l)["item_id"] for l in (dirs[1] / "done_index.jsonl").read_text().splitlines())), (o1[-300:], o2[-300:]))
    rows = [json.loads(l) for d_ in dirs for l in (d_ / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
    att = Counter(r["item_id"] for r in rows)
    check("a bad first reply is asked again (attempt 2); a slot bad every time stops after exactly 3 attempts",
          att["SM0004"] == 3 and all(v == 2 for k, v in att.items() if k != "SM0004"), att)
    check("every saved row carries the slot-file fingerprint, slot_scheme and the slot itself",
          all(r["slots_file_sha256"] == variety.sha256_file(sm_path) and r["slot_scheme"] == "taxonomy-v2" and r["slot"]["item_id"] == r["item_id"] for r in rows))
    before = (dirs[0] / "responses.jsonl").read_bytes()
    rc3, o3 = run("--prompt", "benchmark", "--first", "1", "--count", "12", "--shard", "1/2")
    check("a resume of a complete shard sends nothing and changes nothing", rc3 == 0 and "0 to work on" in o3 and (dirs[0] / "responses.jsonl").read_bytes() == before, o3[-300:])
    rc4, o4 = run("--prompt", "benchmark", "--first", "1", "--count", "12", "--shard", "1/2", "--max-tokens", "8000")
    check("a resume with a changed setting is refused and sends nothing", rc4 != 0 and "refused" in o4 and (dirs[0] / "responses.jsonl").read_bytes() == before, o4[-300:])
    (dirs[0] / "done_index.jsonl").write_text("", encoding="utf-8")
    rc5, o5 = run("--prompt", "benchmark", "--first", "1", "--count", "12", "--shard", "1/2")
    check("a damaged done-index is rebuilt from the replies, and still nothing is re-sent", rc5 == 0 and "done-index rebuilt" in o5 and "0 to work on" in o5, o5[-300:])
    reps_ = [gs.validate_run(d_, sm_path) for d_ in dirs]     # SM0004 (even position) is in shard 2
    check("validate: infrastructure clean, complete, the 3-times-bad slot counted as failed (a result, not a fault)",
          all(not r["infra"] and r["unfinished"] == 0 for r in reps_) and [r["failed"] for r in reps_] == [0, 1],
          [(r["infra"][:2], r["failed"]) for r in reps_])
    # tampering: a row with another slot file's fingerprint is an infrastructure failure
    tam = T / "tampered"
    shutil.copytree(dirs[0], tam)
    lines = (tam / "responses.jsonl").read_text(encoding="utf-8").splitlines()
    r0 = json.loads(lines[0])
    r0["slots_file_sha256"] = "0" * 64
    lines[0] = json.dumps(r0)
    (tam / "responses.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    check("validate: a row from another slot file is an INFRASTRUCTURE failure", any("slots_file_sha256" in f for f in gs.validate_run(tam)["infra"]))
    lines = (dirs[0] / "responses.jsonl").read_text(encoding="utf-8").splitlines()
    good_row = next(json.loads(l) for l in lines if json.loads(l)["item_id"] != "SM0004" and not json.loads(l)["problems"])
    extra_row = dict(good_row)
    shutil.rmtree(tam)
    shutil.copytree(dirs[0], tam)
    with open(tam / "responses.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({**extra_row, "attempt": 3}) + "\n")
    check("validate: a slot asked again after a usable reply is an INFRASTRUCTURE failure",
          any("after a usable reply" in f for f in gs.validate_run(tam)["infra"]))
    items = gs.collect_rows(dirs)
    st_ = Counter(r["status"] for r in items)
    check("collect: one row per slot, 11 usable and SM0004 failed", len(items) == 12 and st_ == Counter({"usable": 11, "failed": 1}), st_)
    rc6, o6 = run("--prompt", "training", "--first", "13", "--count", "12")
    tdir = next(OUT.glob("*_smoke_training-v2_*"))
    check("the training prompt runs on positions 13-24 and its replies pass the training format checks",
          rc6 == 0 and gs.validate_run(tdir, sm_path)["usable"] == 12, o6[-300:])
finally:
    srv.kill()

# ------------------------------------------------------------------ 4. benchmark spares and fingerprints
print("[4] fill-bench: failed primaries replaced like-for-like by spares; fingerprints required")
man_s = json.loads(sm_man.read_text(encoding="utf-8"))
slots12 = variety.read_slots(sm_path)[:12]


def row(slot, status="usable", fp=None):
    return {"item_id": slot["item_id"], "slot": slot, "status": status, "slot_scheme": "taxonomy-v2",
            "slots_file_sha256": fp or man_s["slots_sha256"], "item": {"question": "q"}}


rows8 = [row(s) for s in slots12[:8]]
rows8[2]["status"] = "failed"
spares = [row(s) for s in slots12[8:]]
match = [s for s in spares if (s["slot"]["category"], s["slot"]["difficulty"], s["slot"]["answer_type"]) ==
         (rows8[2]["slot"]["category"], rows8[2]["slot"]["difficulty"], rows8[2]["slot"]["answer_type"])]
positions, needs = gs.fill_bench(rows8 + spares, man_s, 8)
if match:
    check("a failed primary is replaced by the first unused spare with the same category, difficulty and answer type",
          positions[2]["item_id"] == match[0]["item_id"] and positions[2]["replaces"] == rows8[2]["item_id"] and not needs)
else:
    check("with no matching spare, the slot is listed as needing a new spare (variety.py replace)", needs == [rows8[2]["item_id"]])
like = rows8[2]["slot"]
fake_spare = row({**slots12[9], "item_id": "SM0099", "category": like["category"], "difficulty": like["difficulty"],
                  "answer_type": like["answer_type"], "context": like["context"]})
positions, needs = gs.fill_bench(rows8 + [fake_spare], man_s, 8)
check("a spare of the same category, difficulty and answer type fills the failed position",
      positions[2]["item_id"] == "SM0099" and not needs)
wrong = row({**slots12[9], "item_id": "SM0098", "category": "conceptual" if like["category"] != "conceptual" else "numerical",
             "answer_type": "multiple_choice" if like["answer_type"] != "multiple_choice" else "number"})
positions, needs = gs.fill_bench(rows8 + [wrong], man_s, 8)
check("a spare with another category or answer type is NOT used", needs == [rows8[2]["item_id"]])
nofp = [dict(r) for r in rows8]
del nofp[0]["slot_scheme"]
check("an item without the slot-file fingerprint is refused", "fingerprint" in str(raises(lambda: gs.fill_bench(nofp, man_s, 8))))
check("an item with a fingerprint from another slot file is refused",
      "does not belong" in str(raises(lambda: gs.fill_bench([row(slots12[0], fp="f" * 64)] + rows8[1:], man_s, 8))))

# ------------------------------------------------------------------ 5. the training stream: acceptance, replacement, nesting
print("[5] collect-train: accepted stream, like-for-like replacement, exact nested sets, frozen sets")
TD = T / "train"
st_path, st_man = deal("train", 40, "seed-N", TD)
prim = variety.read_slots(st_path)
fp = variety.sha256_file(st_path)


def trow(slot, status="usable"):
    item = {"question": f"Question for {slot['item_id']}?", "choices": ["a", "b", "c", "d"] if slot["answer_type"] == "multiple_choice" else [],
            "answer_type": slot["answer_type"], "worked_answer": "Step one.", "final_answer": "B" if slot["answer_type"] == "multiple_choice" else "1",
            "category": slot["category"], "subtopic": slot["subtopic"], "difficulty": slot["difficulty"], "context": slot["context"], "r_solution": ""}
    return {"item_id": slot["item_id"], "slot": slot, "status": status, "item": item, "prompt_kind": "training",
            "slot_scheme": "taxonomy-v2", "slots_file_sha256": fp, "run": "fake_run", "line": 1}


LONG = {"TR000005"}
FAILED = {"TR000003"}
DECON = {"TR000007": "decontamination"}
ALWAYS_BAD = "TR000010"
items_path = T / "train_items.jsonl"
state = {s["item_id"]: trow(s, "failed" if s["item_id"] in FAILED or s["item_id"] == ALWAYS_BAD else "usable") for s in prim}


def write_items():
    items_path.write_text("".join(json.dumps(r) + "\n" for r in state.values()), encoding="utf-8")
    dec = T / "decontam.jsonl"
    dec.write_text("".join(json.dumps({"item_id": k, "reason": v}) + "\n" for k, v in DECON.items()), encoding="utf-8")
    return dec


def length(r):
    return (3000, "too long") if r["item_id"] in LONG else (100, None)


def collect(sizes="5,10,30"):
    dec = write_items()
    a = SimpleNamespace(manifest=str(st_man), items=str(items_path), decontam=str(dec), version="v-test", out_dir=str(T / "sets"),
                        sizes=sizes, first=1, count=0, tokenizer=None, contexts=None, max_tokens=2048)
    return gs.cmd_collect_train(a, length=length)


rep1 = collect()
check("the stream stops at the first unsettled position (TR000003 needs a replacement): only 2 settled, no set published",
      rep1["settled"] == 2 and not any(s["published"] for s in rep1["sets"].values()), rep1["states"])
needs_ = (T / "sets" / "v-test" / "needs_replacement.txt").read_text().split()
check("the positions needing a like-for-like replacement are listed: the failed, the too-long, the decontaminated and the always-bad",
      set(needs_) == {"TR000003", "TR000005", "TR000007", ALWAYS_BAD}, needs_)
for _ in range(6):     # deal and "generate" replacements until every position is settled
    needs_ = (T / "sets" / "v-test" / "needs_replacement.txt").read_text().split()
    if not needs_:
        break
    new = variety.deal_replacements(st_man, [state[i]["slot"] for i in needs_])
    for s in new:
        root = s["replaces"]
        while root.startswith("TRR"):
            root = state[root]["slot"]["replaces"]
        state[s["item_id"]] = {**trow(s, "failed" if root == ALWAYS_BAD else "usable"),
                               "slots_file_sha256": json.loads(st_man.read_text())["replacements_sha256"]}
    rep2 = collect()
reps = [s for s in variety.read_slots(TD / "train_replacements.jsonl")]
same = all((r["category"], r["difficulty"], r["answer_type"], r["context"]) ==
           (state[r["replaces"]]["slot"]["category"], state[r["replaces"]]["slot"]["difficulty"],
            state[r["replaces"]]["slot"]["answer_type"], state[r["replaces"]]["slot"]["context"]) for r in reps)
check("every replacement keeps category, difficulty, answer type and context; only the subtopic changes", same)
check("a position whose 5 replacements all fail is UNFILLED (and is skipped, not left open)",
      rep2["states"].get("unfilled") == 1 and sum(1 for r in reps if r["item_id"] in state and state[r["item_id"]]["status"] == "failed") == 5, rep2["states"])
f5, f10, f30 = (T / "sets" / "v-test" / f"train_{n}.jsonl" for n in (5, 10, 30))
check("with every position settled (40 positions, 1 unfilled = 39 accepted), the 5, 10 and 30 sets are published",
      all(rep2["sets"][k]["published"] for k in ("5", "10", "30")) and rep2["accepted_settled"] == 39, rep2["states"])
l5, l10 = f5.read_text(encoding="utf-8").splitlines(), f10.read_text(encoding="utf-8").splitlines()
check("exact sizes, and the 5 set is exactly the first 5 lines of the 10 set (nested)", len(l5) == 5 and len(l10) == 10 and l10[:5] == l5)
p3 = json.loads(l5[2])
check("position 3 holds the replacement example, at the SAME position as the rejected primary",
      p3["position"] == 3 and p3["item_id"].startswith("TRR") and p3["primary"] == "TR000003")
check("compact rows hold only what training needs plus a pointer to the raw reply (no thinking text)",
      set(p3) == {"position", "item_id", "primary", "slots_file_sha256", "slot_scheme", "category", "difficulty", "answer_type",
                  "subtopic", "area", "context", "question", "choices", "worked_answer", "final_answer", "text", "n_tokens", "source"})
rej = rep2["sets"]["10"]["rejections"]
check("rejections are counted by reason and broken down by category, difficulty and answer type",
      rej["reason"].get("length") == 1 and rej["reason"].get("decontamination") == 1 and rej["reason"].get("failed_attempts", 0) >= 1
      and "length by difficulty" in rej and "length by answer_type" in rej, rej)
check("each length rejection is listed with its token count, category, difficulty, answer type and area",
      rep2["sets"]["10"]["length_rejections"][0]["n_tokens"] == 3000 and "area" in rep2["sets"]["10"]["length_rejections"][0])
check("the balance report gives target and accepted shares and the no-context share by category",
      "category" in rep2["sets"]["10"]["balance"] and "no_context_share" in rep2["sets"]["10"]["balance"])
before5 = f5.read_bytes()
rep3 = collect()
check("collecting again changes no published file", f5.read_bytes() == before5)
DECON["TR000002"] = "decontamination"
check("a later decontamination result that would change a published set is refused (published sets are frozen)",
      "frozen" in str(raises(collect)))
del DECON["TR000002"]

# ------------------------------------------------------------------ 6. decontamination
print("[6] decontamination: retrieval, scores, rules, MinHash, block-wise similarity")
refs = [{"id": "BM0001", "role": "benchmark", "text": "A fair die is rolled 4 times. What is the probability of getting exactly two sixes?"},
        {"id": "DV0001", "role": "dev", "text": "Write one line of R that returns the mean of mpg for each number of cylinders in mtcars."}]
cands = [{"id": "TR000001", "role": "c", "text": "A fair die is rolled 4 times. What is the probability of getting exactly two sixes?"},
         {"id": "TR000002", "role": "c", "text": "A fair die is rolled 7 times. What is the probability of getting exactly three sixes?"},
         {"id": "TR000003", "role": "c", "text": "The weights of 12 apples have a sample variance of 3.1. Find a 95% interval for sigma."}]
pairs = dc.nominate(refs, cands)
byc = {p["cand"]: p for p in pairs}
check("an exact copy is nominated as exact", byc["TR000001"]["exact"] and "exact" in byc["TR000001"]["nominated_by"])
check("a template variant (numbers changed) is nominated by the masked 8-word run and has a high template score",
      "TR000002" in byc and byc["TR000002"]["shared8_masked"] > 0 and byc["TR000002"]["template"] > 0.9, byc.get("TR000002"))
check("an unrelated question is not nominated", "TR000003" not in byc)
tail = " Give your answer to 3 decimal places."
refs_bp = [{"id": f"BM{k:04d}", "role": "benchmark", "text": t + tail} for k, t in enumerate([
    "The mean of a sample of 9 is 4.", "A coin is tossed 6 times.", "A die is rolled twice.", "The variance of x is 2.",
    "A normal variable has mean 10.", "Twelve plants grew in a plot.", "An urn holds red and blue balls.",
    "A survey asked forty people.", "The rate of arrivals is high.", "Find the standard error of a proportion.",
    "Two groups were compared in a trial.", "A regression slope was estimated."], 1)]   # 12 references, as in a real benchmark the phrase is common
c_bp = [{"id": "TR000009", "role": "c", "text": "The median household income in a town is 52 thousand dollars." + tail}]
check("a stock phrase shared by many reference questions ('Give your answer to 3 decimal places.') does not nominate a pair",
      dc.nominate(refs_bp, c_bp) == [])
check("a number like 0.05 is one token, not four", dc.words("p = 0.05 .") == ["p", "=", "0.05", "."])
rule = {"approved_by": "test", "approved_utc": "2026-11-20", "against_reference": [{"exact": True}, {"template": 0.9}],
        "within_training": [{"template": 0.95}]}
rej = dc.apply_rule(pairs, [], rule, {c["id"]: k for k, c in enumerate(cands)})
check("the rule removes the copy and the template variant, and only TRAINING ids (the benchmark is never touched)",
      sorted(r["item_id"] for r in rej) == ["TR000001", "TR000002"] and all(not r["item_id"].startswith(("BM", "DV")) for r in rej))
(T / "r.json").write_text(json.dumps({**rule, "approved_by": ""}), encoding="utf-8")
check("a rule file without an approval is refused", "not approved" in str(raises(lambda: dc.load_rule(T / "r.json"))))
tp = [{"a": "TR000001", "b": "TR000009", "template": 0.99}, {"a": "TR000009", "b": "TR000020", "template": 0.99}]
order = {"TR000001": 0, "TR000009": 1, "TR000020": 2}
rj = dc.apply_rule([], tp, rule, order)
check("within training, the LATER copy is removed and the earlier kept (TR000009 removed, TR000020 kept: its match was removed)",
      [r["item_id"] for r in rj] == ["TR000009"], rj)
rj2 = dc.apply_rule([], tp, rule, order, keep_first=["TR000009"])
check("an example already in a published set is always kept; the other side of the pair is removed instead",
      sorted(r["item_id"] for r in rj2) == ["TR000001", "TR000020"], rj2)
import numpy as np  # noqa: E402
rng = np.random.default_rng(1)
A = rng.normal(size=(2500, 16)).astype(np.float32)
A /= np.linalg.norm(A, axis=1, keepdims=True)
R = rng.normal(size=(40, 16)).astype(np.float32)
R /= np.linalg.norm(R, axis=1, keepdims=True)
idx, sc = dc.top_k_blocked(A, R, k=3, block=700)
direct = np.argsort(-(A @ R.T), axis=1)[:, :3]
check("block-wise top-3 similarity equals the direct full computation", (idx == direct).all() and np.allclose(sc, np.take_along_axis(A @ R.T, direct, 1)))
base = "The weights in grams of apples from orchard number {} were recorded over a season and the sample mean and standard deviation were computed for a report"
texts = [base.format(k) for k in range(3)] + [f"Unrelated question number {k} about a completely different topic such as R vectors and indexing rules" + " x" * k for k in range(50)]
found, big = dc.lsh_pairs(dc.minhash_signatures(texts))
check("MinHash finds the planted near-duplicates (same text, different number) without comparing all pairs",
      {(0, 1), (0, 2), (1, 2)} <= found, sorted(found)[:10])
check("MinHash does not pair the planted near-duplicates with unrelated texts", not any(a < 3 <= b for a, b in found))
order_rows = [{"item_id": "TR000002", "slot": {"item_id": "TR000002"}},
              {"item_id": "TRR000001", "slot": {"item_id": "TRR000001", "replaces": "TR000001"}},
              {"item_id": "TR000001", "slot": {"item_id": "TR000001"}}]
check("the stream order puts a replacement at its primary's position (TR000001, TRR000001, TR000002)",
      sorted(dc.stream_order(order_rows), key=dc.stream_order(order_rows).get) == ["TR000001", "TRR000001", "TR000002"])
cal_key = [{"pair": 1, "exact": True, "template": 1.0, "cosine": 1.0}, {"pair": 2, "template": 0.95, "cosine": 0.9},
           {"pair": 3, "template": 0.7, "cosine": 0.85}, {"pair": 4, "template": 0.92, "cosine": 0.8}]
sheet = [{"pair": "1", "label": "duplicate"}, {"pair": "2", "label": "template"}, {"pair": "3", "label": "distinct"}, {"pair": "4", "label": "distinct"}]
cal = dc.calibrate(sheet, cal_key, [{"template": 0.9}])
check("calibration: precision and recall of a rule on labeled pairs (2 true copies; the rule removes 3, one wrongly)",
      cal["confusion"] == {"tp": 2, "fp": 1, "fn": 0, "tn": 1} and cal["precision"]["value"] == round(2 / 3, 4), cal)
check("calibration refuses a label outside duplicate / template / distinct",
      bool(raises(lambda: dc.calibrate([{"pair": "1", "label": "maybe"}], cal_key))))
sheet_dir = T / "sheet"
n = dc.make_sheet([{"cand": "TR000001", "ref": "BM0001", "template": 0.9, "nominated_by": ["template"]}],
                  {"TR000001": "q one", "BM0001": "q two"}, 5, 1, sheet_dir)
sh = (sheet_dir / "calibration_sheet.csv").read_text(encoding="utf-8")
check("the labeling sheet is blind: no ids and no scores on it, only the two questions", n == 1 and "BM0001" not in sh and "0.9" not in sh and "q one" in sh)

# ------------------------------------------------------------------ 7. the embedding implementation
print("[7] embeddings: mean pooling over the mask, L2 normalization, truncation at 256")
try:
    emb = dc.Embedder()
    short_t, long_t = "What is a p-value?", "Explain the bootstrap. " * 200
    v_alone = emb.encode([short_t])
    v_batch = emb.encode([short_t, long_t])
    check("padding does not change a vector (pooling uses the attention mask): alone vs in a batch with a long text",
          float(v_alone[0] @ v_batch[0]) > 0.99999, float(v_alone[0] @ v_batch[0]))
    check("vectors have length 1 (L2-normalized), 384 numbers each", v_batch.shape == (2, 384) and np.allclose(np.linalg.norm(v_batch, axis=1), 1, atol=1e-5))
    check("a text longer than 256 word pieces is counted as truncated", emb.truncated >= 1)
except OSError as e:
    print(f"  NOTE  embedding model not available, embedding tests skipped ({e})")

# ------------------------------------------------------------------ 9. printout consistency and plain text (2026-11-20)
print("[9] the printout checker (output_check.py) and the plain-text rule of benchmark-v8 / training-v2")
import output_check as oc  # noqa: E402
grid_t = [(0.5, 3), (2.145, 18), (7.0, 23), (1.96, 1e6), (3.3, 5.7)]
grid_f = [(4.0, 3, 20), (6.0, 2, 27), (25.3, 2, 27), (0.8, 4, 10)]
grid_c = [(6.102, 1), (12.5, 4), (0.3, 2)]
code = ("options(digits = 15)\n"
        + "".join(f"cat(2*pt(-{t}, {d}), '\\n')\n" for t, d in grid_t)
        + "".join(f"cat(pf({f}, {a}, {b}, lower.tail = FALSE), '\\n')\n" for f, a, b in grid_f)
        + "".join(f"cat(pchisq({x}, {k}, lower.tail = FALSE), '\\n')\n" for x, k in grid_c)
        + "cat(qt(0.975, 18), qt(0.975, 25), '\\n')\n")
ok_r, out = gb.run_r(code, gb.rscript_path())      # our own reference code, run in the R sandbox like all R in this project
vals = [float(x) for x in out.split()]
mine = ([oc.p_t_two(t, d) for t, d in grid_t] + [oc.p_f_upper(f, a, b) for f, a, b in grid_f]
        + [oc.p_chisq_upper(x, k) for x, k in grid_c] + [oc.t_crit(0.95, 18), oc.t_crit(0.95, 25)])
check("the t, F and chi-square p-values and t critical values match R to 6 significant digits",
      ok_r and len(vals) == len(mine) and all(abs(a - b) <= 1e-6 * max(abs(b), 1e-300) + 1e-14 for a, b in zip(mine, vals)),
      list(zip(mine, vals)))
sm0010 = ("Coefficients:\n               Estimate Std. Error t value Pr(>|t|)    \n(Intercept)  15.3200    2.8100    5.452   0.0000 ***\n"
          "speed         1.2000    0.2400    5.000   0.0000 ***\ntemp         -0.4000    0.1500   -2.667   0.0131 *  \n---\n"
          "95% confidence intervals:\n               lower    upper\nspeed         0.992    1.408\ntemp         -0.709   -0.091\n")
check("SM0010's impossible interval (0.992 to 1.408 for estimate 1.2 with SE 0.24) is caught, and only that row",
      len(oc.check(sm0010)) == 1 and "interval for speed" in oc.check(sm0010)[0], oc.check(sm0010))
sm0004 = ("\tTwo Sample t-test\n\ndata:  x and y\nt = 2.145, df = 18, p-value = 0.04546\nalternative hypothesis: true difference "
          "in means is not equal to 0\n95 percent confidence interval:\n 0.0288 2.7712\nsample estimates:\nmean of x mean of y \n    5.40      4.00 \n")
check("SM0004 (p 0.04546 where 0.04585 is exact: 0.85%, within the 1% allowance; a correct interval) passes", oc.check(sm0004) == [])
check("a t-test interval with the wrong width is caught", oc.check(sm0004.replace("0.0288 2.7712", "0.4288 2.3712")) != [])
check("a p-value 2.7% off (Claude-era BM0070: F = 4.000 on 3 and 20 DF printed 0.0215, exact 0.0221) is caught",
      oc.check("F-statistic: 4.000 on 3 and 20 DF,  p-value: 0.0215") != [] and oc.check("F-statistic: 4.000 on 3 and 20 DF,  p-value: 0.02208") == [])
check("a regression p-value inconsistent with t and df (Claude-era BM0110: t = 7 on 23 df printed 1.2e-07, exact 3.9e-07) is caught",
      oc.check("            Estimate Std. Error t value Pr(>|t|)\nx             0.70      0.10     7.000  1.2e-07 ***\n---\n"
               "Residual standard error: 2.1 on 23 degrees of freedom\n") != [])
anova = ("            Df Sum Sq Mean Sq F value  Pr(>F)\ngroup        2  120.0   60.00   6.000 0.00698 **\nResiduals   27  270.0   10.00\n")
check("a consistent ANOVA table passes; a wrong Mean Sq or F is caught",
      oc.check(anova) == [] and oc.check(anova.replace("60.00", "65.00")) != [] and oc.check(anova.replace("6.000", "7.000")) != [])
check("chi-square: X-squared = 6.102 on 1 df with p 0.01350 passes, with p 0.0315 is caught",
      oc.check("X-squared = 6.102, df = 1, p-value = 0.01350") == [] and oc.check("X-squared = 6.102, df = 1, p-value = 0.0315") != [])
check("'< 2.2e-16' and '0.0000' are read as bounds: consistent with a huge t, refused for a small one",
      oc.check("t = 25.3, df = 40, p-value < 2.2e-16") == [] and oc.check("t = 1.2, df = 40, p-value < 2.2e-16") != [])
check("text with no recognizable printout is never flagged", oc.check("Which statement about the sample mean is true?") == [])
bm_item = {**good_bm, "answer_type": "multiple_choice", "canonical_answer": "B", "r_solution": "", "answer_tolerance": 0,
           "choices": ["one", "two", "three", "four"], "question": "Here is R output:\n" + sm0010 + "What does the interval mean?",
           "category": "output_interpretation"}
oslot = {**nslot, "category": "output_interpretation", "answer_type": "multiple_choice"}
check("a benchmark-v8 reply with an inconsistent printout is unusable (asked again); the same reply under v7 is checked as before",
      any("printed output is inconsistent" in p for p in sp.check_benchmark_item(bm_item, oslot, version="benchmark-v8"))
      and not any("printed output" in p for p in sp.check_benchmark_item(bm_item, oslot, version="benchmark-v7")))
fenced = {**good_bm, "question": "Consider:\n```r\nx <- c(1, 2)\n```\nWhat is mean(x)? Give your answer to 3 decimal places."}
latex = {**good_bm, "question": "Let \\rho = E|X|^3. Compute it. Give your answer to 3 decimal places."}
rcode = {**good_bm, "question": 'x <- grepl("\\\\d+", s); cat("done\\n"). What is 1+1? Give your answer to 3 decimal places.'}
check("benchmark-v8: a markdown code fence is refused", any("code fence" in p for p in sp.check_benchmark_item(fenced, nslot)))
check("benchmark-v8: a LaTeX command (\\rho) is refused", any("LaTeX" in p for p in sp.check_benchmark_item(latex, nslot)))
check("benchmark-v8: R escapes (\\n, a doubled \\\\d in a regular expression) are NOT mistaken for LaTeX",
      not any("LaTeX" in p for p in sp.check_benchmark_item(rcode, nslot)))
check("benchmark-v7 replies keep their old checks (no plain-text rule)", not any("code fence" in p for p in sp.check_benchmark_item(fenced, nslot, version="benchmark-v7")))
check("training-v2: a code fence in the worked answer is refused; training-v1 is unchanged",
      any("code fence" in p for p in sp.check_training_item({**good_tr, "worked_answer": "```r\nx\n```"}, tslot))
      and any("markdown" in p for p in sp.check_training_item({**good_tr, "worked_answer": "```r\nx\n```"}, tslot, version="training-v1")))

# ------------------------------------------------------------------ 8. the Talon copy keeps the pinned bytes
print("[8] the files as `git archive` (the Talon copy) writes them keep their pinned SHA-256 (line endings)")
import hashlib  # noqa: E402
import io  # noqa: E402
import tarfile  # noqa: E402
pins = {"data/prompts/benchmark_generation_v6.md": "348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4",
        "data/prompts/benchmark_generation_v7.md": sha7, "data/prompts/training_generation_v1.md": shatr1,
        "data/prompts/benchmark_generation_v8.md": sha8, "data/prompts/training_generation_v2.md": shatr,
        "data/taxonomy/subtopics.yaml": tax_sha, "data/taxonomy/contexts.yaml": ctx_sha}
common = (REPO / "configs" / "talon" / "common.sh").read_text(encoding="utf-8")
check("the prompt pins in configs/talon/common.sh equal the prompt files' SHA-256",
      f'PROMPT_BENCH_SHA256="{sha8}"' in common and f'PROMPT_TRAIN_SHA256="{shatr}"' in common
      and 'PROMPT_BENCH_FILE="benchmark_generation_v8.md"' in common and 'PROMPT_TRAIN_FILE="training_generation_v2.md"' in common)
smoke_slots = REPO / "data" / "slots" / "smoke_slots.jsonl"
if smoke_slots.exists():
    pins["data/slots/smoke_slots.jsonl"] = json.loads((REPO / "data" / "slots" / "smoke_slots.manifest.json").read_text())["slots_sha256"]
arc = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", "HEAD", "--", *pins], capture_output=True)
if arc.returncode == 0:
    tf = tarfile.open(fileobj=io.BytesIO(arc.stdout))
    got = {m.name: hashlib.sha256(tf.extractfile(m).read()).hexdigest() for m in tf.getmembers() if m.isfile()}
    bad = {k: got.get(k, "missing")[:12] for k, v in pins.items() if got.get(k) != v}
    check("every pinned file comes out of `git archive HEAD` with its pinned SHA-256 (no Windows line endings added)", not bad, bad)
else:
    print(f"  NOTE  git archive failed ({arc.stderr.decode()[:120]}); check skipped (files not committed yet?)")

shutil.rmtree(T, ignore_errors=True)
print(f"\n==== generation tests: {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
