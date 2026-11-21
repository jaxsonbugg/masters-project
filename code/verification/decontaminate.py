"""
decontaminate.py - find training examples that copy a benchmark or development question, and near-copies inside the
training data, then (with an approved rule only) list the training examples to remove.

WHAT THIS IS AND WHY (docs/methodology/workflow.md Section 4, safeguard 5; labeling: docs/guides/decontamination_labeling_guide.md)
If a student trains on a copy of a benchmark question, a right answer on the benchmark may be memory, not skill. So every
training example (and every held-out TV example) is compared with every benchmark and development question, and the
development set with the benchmark. Inside the training data, near-copies of one problem are found the same way, so the
students see more different problems. The benchmark itself is NEVER changed: an overlap is always resolved by removing
the training example.

TWO STAGES, MEASURED SEPARATELY
  1. RETRIEVAL (`pairs`, `train-pairs`): cheap checks only NOMINATE candidate pairs. Nothing is removed here.
       (a) an exact copy after normalizing case and spaces;
       (b) a shared run of 8 or more words, as written or with every number replaced by #, found through an index of the
           reference questions' 8-word runs (no pair-by-pair comparison);
       (c) a template score (0 to 1, how much of the wording is the same once numbers are masked), computed only for
           pairs that share at least 3 masked 5-word runs;
       (d) the embedding cosine similarity (0 to 1, "says the same thing in other words") from all-MiniLM-L6-v2, computed
           in blocks of training rows against all references, keeping only each row's closest few matches.
     Inside the training data the comparison uses MinHash: each text becomes 128 numbers summarizing its masked 5-word
     runs, and texts that agree on a whole band of those numbers land in the same bucket, so only bucket-mates are
     compared (never all pairs of 200,000 texts).
  2. CLASSIFICATION (`apply`): a rule chosen from hand-labeled pairs (`sheet`, `calibrate`) and approved by Jaxson
     decides which nominated pairs are copies. The rule file must carry the approval, or nothing is removed.
  Retrieval recall (how many real copies the checks find at all) is estimated separately, with a synthetic set of hard
  pairs (`retrieval-test`) and an audit of the nearest NON-nominated pairs (`audit-sheet`). Decontamination reduces
  leakage; it cannot prove that none remains.

WORKED EXAMPLE
  Benchmark: "A fair die is rolled 4 times. What is the probability of getting exactly two sixes?"
  Training:  "A fair die is rolled 7 times. What is the probability of getting exactly three sixes?"
  (a) no; (b) the 8-word run "what is the probability of getting exactly" ... is shared -> nominated; (c) template 0.96;
  (d) cosine 0.73. A rule such as "template >= t2" (t2 from the labels) would call it a template variant and, against
  the benchmark, remove the training example. Measured on 2026-11-20 with the pinned model, the same benchmark question
  against "In four rolls of a fair six-sided die, find P(two sixes exactly)." (a reworded DUPLICATE) gives template 0.36
  and cosine 0.86, nominated by the embedding only; against "A fair die is rolled 4 times. What is the expected number
  of sixes?" (a DISTINCT problem) it gives template 0.72 and cosine 0.83. No single score separates the three, which is
  why the rule is chosen from hand-labeled pairs.

COMMANDS (all on the PC; no model calls, no R)
  pairs        --refs <benchmark/dev items> --cands <training items> --out pairs.jsonl     candidates against references
  train-pairs  --cands <training items> --out tpairs.jsonl                                  candidates inside training
  sheet        --pairs pairs.jsonl --n 200 --out-dir <dir> [--seed S]                       blind labeling sheet + key
  calibrate    --sheet labeled.csv --key key.jsonl [--rule rule.json]                      label table, precision/recall
  audit-sheet  --refs ... --cands ... --pairs pairs.jsonl --n 100 --out-dir <dir>          nearest non-nominated pairs
  retrieval-test --synthetic hard_pairs.jsonl [--rule rule.json]                           recall on planted pairs
  apply        --pairs pairs.jsonl [--tpairs tpairs.jsonl] --rule rule.json --order <items> --out rejections.jsonl
"""

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DECONTAM_VERSION = "decontaminate-1"
# Retrieval (nomination) settings: generous on purpose, because a nominated pair is only looked at, never removed here.
NGRAM = 8                 # (b) shared word run length
SHINGLE = 5               # (c) and MinHash: masked 5-word runs
MIN_SHARED_SHINGLES = 3   # (c) template score only for pairs sharing at least this many masked 5-word runs
# Boilerplate filter (added 2026-11-20 after the stage G smoke test): a word run that appears in more than this many
# REFERENCE questions is a stock phrase, not a copy, and is not used to nominate. Example: "give your answer to # decimal
# places ." is exactly 8 tokens and sits in nearly every number question; without this filter, 49 of 400 smoke-test pairs
# were nominated (most with cosine below 0.5), which at full scale would be about 130 million pairs.
MAX_REF_DF_8 = 3          # (b) an 8-word run shared by more than 3 reference questions is ignored
MAX_REF_DF_5 = 10         # (c) a masked 5-word run shared by more than 10 reference questions is ignored
TEMPLATE_NOMINATE = 0.60  # (c) nominate at or above this template score
COSINE_NOMINATE = 0.75    # (d) nominate a top-k neighbor at or above this cosine
TOP_K = 3                 # (d) neighbors kept per row
BLOCK = 10000             # (d) training rows per block (memory: BLOCK x references floats, never all rows at once)
MINHASH_PERM = 128
MINHASH_BANDS = 32        # 32 bands x 4 rows: texts sharing about 40% or more of their 5-word runs usually collide
MAX_BUCKET = 1000         # a larger bucket is reported and only its first MAX_BUCKET members are compared
LABELS = ("duplicate", "template", "distinct")
_P32 = (1 << 32) + 15      # a prime just above 2^32 (MinHash modulus)


# ---------------------------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------------------------
def question_text(item):
    """The text compared: question plus choices (the answer is never compared; only the question can leak)."""
    return (item.get("question") or "") + " " + " ".join(item.get("choices") or [])


def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def mask(text):
    return re.sub(r"\d+(?:[.,]\d+)*", "#", normalize(text))


def words(text):
    """Tokens: words, whole numbers (0.05 is one token), # (a masked number), or single punctuation marks."""
    return re.findall(r"[a-z#]+|\d+(?:[.,]\d+)*|[^\sa-z0-9#]", text)


def ngrams(tokens, n):
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def template_score(a_masked, b_masked):
    return SequenceMatcher(None, a_masked, b_masked, autojunk=False).ratio()


def stable_hash(s):
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little")


# ---------------------------------------------------------------------------------------------
# Loading items (collect output rows, fill-bench rows, compact training rows or plain items)
# ---------------------------------------------------------------------------------------------
def load_items(paths, role):
    import separation   # Codex output must never reach training-side material (workflow.md Section 2.3)
    out = []
    for p in paths:
        separation.refuse_codex_path(p, "decontaminate")
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            separation.refuse_codex_rows([r], "decontaminate", p)
            if r.get("status") not in (None, "usable"):
                continue
            item = r.get("item") or r
            iid = r.get("item_id") or item.get("item_id")
            if not iid or "question" not in item:
                continue
            r_role = role
            if role == "reference":
                r_role = {"BM": "benchmark", "DV": "dev"}.get(iid[:2], "reference")
            out.append({"id": iid, "role": r_role, "text": question_text(item)})
    ids = [o["id"] for o in out]
    if len(set(ids)) != len(ids):
        sys.exit(f"repeated ids in the {role} files")
    return out


# ---------------------------------------------------------------------------------------------
# Embeddings (all-MiniLM-L6-v2, implemented with transformers; verified against sentence-transformers separately)
# ---------------------------------------------------------------------------------------------
class Embedder:
    """Mean pooling over the attention mask, then L2 normalization, maximum 256 word pieces (truncated), float32 -
    the model card's sentence-transformers configuration (modules.json, 1_Pooling/config.json, sentence_bert_config.json)."""

    MAX_LEN = 256

    def __init__(self, folder=None, batch=64):
        import torch
        import yaml
        from transformers import AutoModel, AutoTokenizer
        folder = Path(folder or yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())["models_embedding"])
        self.folder, self.batch, self.torch = folder, batch, torch
        self.tok = AutoTokenizer.from_pretrained(str(folder))
        self.model = AutoModel.from_pretrained(str(folder), dtype=torch.float32).eval()
        self.weights_sha256 = hashlib.sha256((folder / "model.safetensors").read_bytes()).hexdigest()
        self.truncated = 0
        self.count = 0

    def encode(self, texts):
        torch = self.torch
        out = np.zeros((len(texts), 384), dtype=np.float32)
        with torch.inference_mode():
            for i in range(0, len(texts), self.batch):
                chunk = texts[i:i + self.batch]
                full = self.tok(chunk, add_special_tokens=True, truncation=False, verbose=False)["input_ids"]
                self.truncated += sum(1 for ids in full if len(ids) > self.MAX_LEN)
                self.count += len(chunk)
                enc = self.tok(chunk, padding=True, truncation=True, max_length=self.MAX_LEN, return_tensors="pt")
                hidden = self.model(**enc).last_hidden_state
                m = enc["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * m).sum(1) / m.sum(1).clamp(min=1e-9)
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                out[i:i + len(chunk)] = pooled.numpy()
        return out


def top_k_blocked(cand_vecs, ref_vecs, k=TOP_K, block=BLOCK):
    """(indices, scores) of each candidate row's k most similar references, computed block by block so memory stays at
    block x n_refs floats. Vectors are L2-normalized, so the dot product is the cosine."""
    n = cand_vecs.shape[0]
    k = min(k, ref_vecs.shape[0])
    idx = np.zeros((n, k), dtype=np.int64)
    sc = np.zeros((n, k), dtype=np.float32)
    for s in range(0, n, block):
        sims = cand_vecs[s:s + block] @ ref_vecs.T
        part = np.argpartition(-sims, kth=k - 1, axis=1)[:, :k]
        ps = np.take_along_axis(sims, part, axis=1)
        order = np.argsort(-ps, axis=1)
        idx[s:s + block] = np.take_along_axis(part, order, axis=1)
        sc[s:s + block] = np.take_along_axis(ps, order, axis=1)
    return idx, sc


# ---------------------------------------------------------------------------------------------
# Retrieval against references
# ---------------------------------------------------------------------------------------------
def nominate(refs, cands, cand_vecs=None, ref_vecs=None):
    """Candidate pairs (candidate, reference) with every score. A pair is nominated by any check; each pair records
    which checks nominated it."""
    ref_norm = {}
    idx8 = defaultdict(set)
    idx8m = defaultdict(set)
    idx5m = defaultdict(set)
    rinfo = []
    for j, r in enumerate(refs):
        n, m = normalize(r["text"]), mask(r["text"])
        ref_norm.setdefault(n, []).append(j)
        wn, wm = words(n), words(m)
        for g in ngrams(wn, NGRAM):
            idx8[g].add(j)
        for g in ngrams(wm, NGRAM):
            idx8m[g].add(j)
        for g in ngrams(wm, SHINGLE):
            idx5m[g].add(j)
        rinfo.append((n, m))
    # drop stock phrases (see MAX_REF_DF_8 / MAX_REF_DF_5)
    for idx, cap in ((idx8, MAX_REF_DF_8), (idx8m, MAX_REF_DF_8), (idx5m, MAX_REF_DF_5)):
        for g in [g for g, js in idx.items() if len(js) > cap]:
            del idx[g]
    pairs = {}

    def pair(i, j):
        key = (i, j)
        if key not in pairs:
            pairs[key] = {"cand": cands[i]["id"], "ref": refs[j]["id"], "ref_role": refs[j]["role"], "nominated_by": [],
                          "exact": False, "shared8": 0, "shared8_masked": 0, "shared5_masked": 0}
        return pairs[key]

    for i, c in enumerate(cands):
        n, m = normalize(c["text"]), mask(c["text"])
        wn, wm = words(n), words(m)
        for j in ref_norm.get(n, []):
            p = pair(i, j)
            p["exact"] = True
            p["nominated_by"].append("exact")
        hits = Counter(j for g in ngrams(wn, NGRAM) for j in idx8.get(g, ()))
        for j, k in hits.items():
            p = pair(i, j)
            p["shared8"] = k
            p["nominated_by"].append("ngram8")
        hits = Counter(j for g in ngrams(wm, NGRAM) for j in idx8m.get(g, ()))
        for j, k in hits.items():
            p = pair(i, j)
            p["shared8_masked"] = k
            if "ngram8" not in p["nominated_by"]:
                p["nominated_by"].append("ngram8_masked")
        hits = Counter(j for g in ngrams(wm, SHINGLE) for j in idx5m.get(g, ()))
        for j, k in hits.items():
            if k < MIN_SHARED_SHINGLES:
                continue
            t = template_score(m, rinfo[j][1])
            if t >= TEMPLATE_NOMINATE or (i, j) in pairs:
                p = pair(i, j)
                p["shared5_masked"] = k
                p["template"] = round(t, 4)
                if t >= TEMPLATE_NOMINATE:
                    p["nominated_by"].append("template")
    if cand_vecs is not None:
        idx, sc = top_k_blocked(cand_vecs, ref_vecs)
        for i in range(len(cands)):
            for j, s in zip(idx[i], sc[i]):
                if s >= COSINE_NOMINATE:
                    pair(i, int(j))["nominated_by"].append("embedding")
    # every nominated pair gets every score
    for (i, j), p in pairs.items():
        if "template" not in p:
            p["template"] = round(template_score(mask(cands[i]["text"]), rinfo[j][1]), 4)
        if cand_vecs is not None:
            p["cosine"] = round(float(cand_vecs[i] @ ref_vecs[j]), 4)
    return list(pairs.values())


# ---------------------------------------------------------------------------------------------
# Retrieval inside the training data (MinHash with banding)
# ---------------------------------------------------------------------------------------------
def minhash_signatures(texts, perm=MINHASH_PERM, seed=20261119):
    """MinHash: for each of `perm` random hash functions h_k(x) = (a_k x + b_k) mod p, keep the smallest value over the
    text's masked 5-word runs. Two texts agree on one position with probability equal to their Jaccard similarity (the
    share of 5-word runs they have in common). Shingle hashes are 32-bit and p = 2^32 + 15 (a prime), so a_k x + b_k
    stays below 2^64 and the arithmetic is exact in unsigned 64-bit integers."""
    rng = np.random.default_rng(seed)
    a = rng.integers(1, _P32, size=perm, dtype=np.uint64)
    b = rng.integers(0, _P32, size=perm, dtype=np.uint64)
    hashed = []
    for t in texts:
        sh = ngrams(words(mask(t)), SHINGLE) or {mask(t)}
        hashed.append(np.unique(np.fromiter((stable_hash(s) & 0xFFFFFFFF for s in sh), dtype=np.uint64, count=len(sh))))
    # Stock phrases ("give your answer to # decimal places") would make unrelated questions look alike, so a 5-word run
    # found in more than 1% of the texts (and at least 50 of them) is left out; a text made only of such runs keeps them.
    df = {}
    for h in hashed:
        for x in h.tolist():
            df[x] = df.get(x, 0) + 1
    cap = max(50, int(0.01 * len(texts)))
    common = np.array(sorted(x for x, k in df.items() if k > cap), dtype=np.uint64)
    sigs = np.zeros((len(texts), perm), dtype=np.uint64)
    for i, h in enumerate(hashed):
        keep = h[~np.isin(h, common)] if common.size else h
        if keep.size == 0:
            keep = h
        sigs[i] = ((np.outer(keep, a) + b) % _P32).min(axis=0)
    return sigs


def lsh_pairs(sigs, bands=MINHASH_BANDS):
    rows = sigs.shape[1] // bands
    found, big = set(), []
    for bnd in range(bands):
        buckets = defaultdict(list)
        part = sigs[:, bnd * rows:(bnd + 1) * rows]
        for i in range(sigs.shape[0]):
            buckets[part[i].tobytes()].append(i)
        for members in buckets.values():
            if len(members) < 2:
                continue
            if len(members) > MAX_BUCKET:
                big.append(len(members))
                members = members[:MAX_BUCKET]
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    found.add((members[x], members[y]))
    return found, big


def train_pairs(cands, vecs=None):
    sigs = minhash_signatures([c["text"] for c in cands])
    found, big = lsh_pairs(sigs)
    out = []
    for i, j in sorted(found):
        p = {"a": cands[i]["id"], "b": cands[j]["id"], "nominated_by": ["minhash"],
             "minhash_jaccard": round(float(np.mean(sigs[i] == sigs[j])), 4),
             "template": round(template_score(mask(cands[i]["text"]), mask(cands[j]["text"])), 4)}
        if vecs is not None:
            p["cosine"] = round(float(vecs[i] @ vecs[j]), 4)
        out.append(p)
    return out, big


# ---------------------------------------------------------------------------------------------
# The removal rule (only an approved rule file is ever applied)
# ---------------------------------------------------------------------------------------------
def rule_says_copy(scores, clauses):
    """True if any clause holds. A clause is a dict of minimums, for example {"cosine": 0.95} or
    {"shared8": 1, "template": 0.8}; "exact": true means an exact copy."""
    for cl in clauses:
        ok = True
        for k, v in cl.items():
            if k == "exact":
                ok = ok and bool(scores.get("exact")) == bool(v)
            else:
                ok = ok and scores.get(k) is not None and scores.get(k) >= v
        if ok:
            return True
    return False


def load_rule(path):
    rule = json.loads(Path(path).read_text(encoding="utf-8"))
    if not rule.get("approved_by") or not rule.get("approved_utc"):
        sys.exit(f"{path} is not approved (approved_by and approved_utc are required). Nothing was removed.")
    for k in ("against_reference", "within_training"):
        if not isinstance(rule.get(k), list):
            sys.exit(f"{path}: {k} must be a list of clauses")
    return rule


def stream_order(rows):
    """Order of training candidates in the accepted stream: primary position, then replacements in id order."""
    import generate_set as gs
    prim = [r for r in rows if not (r.get("slot") or {}).get("replaces")]
    reps = [r["slot"] for r in rows if (r.get("slot") or {}).get("replaces")]
    chains = gs.replacement_chains([r["item_id"] for r in sorted(prim, key=lambda r: r["item_id"])], reps)
    order, k = {}, 0
    for pid in sorted(chains):
        for cid in [pid] + chains[pid]:
            order[cid] = k
            k += 1
    return order


def apply_rule(pairs, tpairs, rule, order, keep_first=()):
    """Rejections. Against the benchmark and dev set: any pair the rule calls a copy removes the training example.
    Inside training: walk the stream in order; an example is removed if the rule calls it a copy of an earlier KEPT
    example. Examples already published (keep_first) are always kept and are processed first."""
    rejections = {}
    keep = set(keep_first)
    for p in pairs:
        if p["cand"] in rejections:
            continue
        if rule_says_copy(p, rule["against_reference"]):
            if p["cand"] in keep:
                sys.exit(f"{p['cand']} is in a published set but the rule calls it a copy of {p['ref']}. Published sets are "
                         f"frozen; stop and review.")
            rejections[p["cand"]] = {"item_id": p["cand"], "reason": "decontamination", "match": p["ref"],
                                     "match_role": p.get("ref_role"), "scores": {k: p.get(k) for k in
                                     ("exact", "shared8", "shared8_masked", "template", "cosine")}}
    partners = defaultdict(list)
    for p in tpairs:
        if rule_says_copy(p, rule["within_training"]):
            partners[p["a"]].append(p)
            partners[p["b"]].append(p)
    rank = lambda i: (0 if i in keep else 1, order.get(i, math.inf), i)
    kept = set()
    for cid in sorted(set(order) | set(partners), key=rank):
        if cid in rejections:
            continue
        dup = next((p for p in partners.get(cid, []) if (p["b"] if p["a"] == cid else p["a"]) in kept), None)
        if dup and cid not in keep:
            other = dup["b"] if dup["a"] == cid else dup["a"]
            rejections[cid] = {"item_id": cid, "reason": "near_duplicate", "match": other, "match_role": "training",
                               "scores": {k: dup.get(k) for k in ("minhash_jaccard", "template", "cosine")}}
        else:
            kept.add(cid)
    return list(rejections.values())


# ---------------------------------------------------------------------------------------------
# Labeling: blind sheet, calibration, audit of non-nominated pairs, synthetic retrieval test
# ---------------------------------------------------------------------------------------------
def band(p):
    c = p.get("cosine")
    if p.get("exact"):
        return "exact"
    top = max(c or 0, p.get("template") or 0)
    for lo in (0.95, 0.9, 0.8, 0.7):
        if top >= lo:
            return f">={lo}"
    return "<0.7"


def make_sheet(pairs, texts, n, seed, out_dir, kind="calibration"):
    """A blind sheet: random order, random sides, no scores or ids. Pairs are drawn stratified by score band and by the
    check that nominated them, so clear and borderline cases are both seen."""
    rng = random.Random(seed)
    strata = defaultdict(list)
    for p in pairs:
        strata[(band(p), (p.get("nominated_by") or ["none"])[0])].append(p)
    keys = sorted(strata)
    for k in keys:
        rng.shuffle(strata[k])
    chosen = []
    while len(chosen) < n and any(strata[k] for k in keys):
        for k in keys:
            if strata[k] and len(chosen) < n:
                chosen.append(strata[k].pop())
    rng.shuffle(chosen)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    key_rows = []
    with open(out_dir / f"{kind}_sheet.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pair", "question_1", "question_2", "label", "unsure", "note"])
        for k, p in enumerate(chosen, 1):
            a, b = (p.get("cand") or p.get("a")), (p.get("ref") or p.get("b"))
            if rng.random() < 0.5:
                a, b = b, a
            w.writerow([k, texts[a], texts[b], "", "", ""])
            key_rows.append({"pair": k, "q1": a, "q2": b, **p})
    (out_dir / f"{kind}_key.jsonl").write_text("".join(json.dumps(r) + "\n" for r in key_rows), encoding="utf-8")
    return len(chosen)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def calibrate(sheet_rows, key_rows, rule_clauses=None, copy_labels=("duplicate", "template")):
    """The label table by score band, and (given a rule) its CLASSIFICATION precision and recall on the labeled,
    nominated pairs, with 95% Wilson intervals. These say nothing about pairs retrieval never nominated."""
    key = {int(r["pair"]): r for r in key_rows}
    table = defaultdict(Counter)
    tp = fp = fn = tn = 0
    unsure = 0
    for s in sheet_rows:
        lab = (s.get("label") or "").strip().lower()
        if lab not in LABELS:
            sys.exit(f"pair {s.get('pair')}: label {lab!r} is not one of {LABELS}")
        unsure += (s.get("unsure") or "").strip().lower() == "yes"
        p = key[int(s["pair"])]
        table[band(p)][lab] += 1
        if rule_clauses is not None:
            says, truth = rule_says_copy(p, rule_clauses), lab in copy_labels
            tp += says and truth
            fp += says and not truth
            fn += (not says) and truth
            tn += (not says) and not truth
    out = {"by_band": {b: dict(c) for b, c in sorted(table.items())}, "labeled": len(sheet_rows), "unsure": unsure}
    if rule_clauses is not None:
        out["rule"] = rule_clauses
        out["confusion"] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn}
        out["precision"] = {"value": round(tp / (tp + fp), 4) if tp + fp else None, "ci95": wilson(tp, tp + fp)}
        out["recall_among_nominated"] = {"value": round(tp / (tp + fn), 4) if tp + fn else None, "ci95": wilson(tp, tp + fn)}
        out["note"] = ("precision and recall are for CLASSIFICATION of nominated pairs only; retrieval recall comes from "
                       "retrieval-test and the audit sheet")
    return out


# ---------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------
def write_jsonl(path, rows):
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cmd_pairs(args):
    refs = load_items(args.refs, "reference")
    cands = load_items(args.cands, "candidate")
    t0 = time.time()
    cv = rv = None
    emb = None
    if not args.no_embeddings:
        emb = Embedder(args.model)
        rv = emb.encode([r["text"] for r in refs])
        cv = emb.encode([c["text"] for c in cands])
    pairs = nominate(refs, cands, cv, rv)
    sha = write_jsonl(args.out, pairs)
    by = Counter(k for p in pairs for k in set(p["nominated_by"]))
    log = {"version": DECONTAM_VERSION, "refs": len(refs), "cands": len(cands), "pairs": len(pairs), "by_check": dict(by),
           "settings": {"ngram": NGRAM, "shingle": SHINGLE, "min_shared_shingles": MIN_SHARED_SHINGLES,
                        "max_ref_df_8": MAX_REF_DF_8, "max_ref_df_5": MAX_REF_DF_5,
                        "template_nominate": TEMPLATE_NOMINATE, "cosine_nominate": COSINE_NOMINATE, "top_k": TOP_K},
           "embedding": None if emb is None else {"folder": str(emb.folder), "weights_sha256": emb.weights_sha256,
                                                  "truncated_share": round(emb.truncated / max(1, emb.count), 4)},
           "seconds": round(time.time() - t0, 1), "out_sha256": sha}
    Path(args.out + ".log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps(log, indent=2))


def cmd_train_pairs(args):
    cands = load_items(args.cands, "candidate")
    vecs = None if args.no_embeddings else Embedder(args.model).encode([c["text"] for c in cands])
    pairs, big = train_pairs(cands, vecs)
    sha = write_jsonl(args.out, pairs)
    log = {"version": DECONTAM_VERSION, "cands": len(cands), "pairs": len(pairs), "oversized_buckets": big,
           "settings": {"perm": MINHASH_PERM, "bands": MINHASH_BANDS, "shingle": SHINGLE, "max_bucket": MAX_BUCKET},
           "out_sha256": sha}
    Path(args.out + ".log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps(log, indent=2))


def all_texts(paths):
    t = {}
    for p in paths:
        for it in load_items([p], "x"):
            t[it["id"]] = it["text"]
    return t


def cmd_sheet(args):
    pairs = [json.loads(l) for l in Path(args.pairs).read_text(encoding="utf-8").splitlines() if l.strip()]
    texts = all_texts(args.texts)
    n = make_sheet(pairs, texts, args.n, args.seed, args.out_dir, args.kind)
    print(f"{n} pairs on the blind sheet in {args.out_dir} (the key file stays closed while labeling)")


def cmd_calibrate(args):
    with open(args.sheet, encoding="utf-8", newline="") as f:
        sheet = list(csv.DictReader(f))
    key = [json.loads(l) for l in Path(args.key).read_text(encoding="utf-8").splitlines() if l.strip()]
    clauses = json.loads(Path(args.rule).read_text(encoding="utf-8"))[args.side] if args.rule else None
    print(json.dumps(calibrate(sheet, key, clauses), indent=2))


def cmd_audit_sheet(args):
    """For a random sample of candidates, the nearest reference by embedding that retrieval did NOT nominate."""
    refs = load_items(args.refs, "reference")
    cands = load_items(args.cands, "candidate")
    nominated = {(p["cand"], p["ref"]) for p in
                 (json.loads(l) for l in Path(args.pairs).read_text(encoding="utf-8").splitlines() if l.strip())}
    rng = random.Random(args.seed)
    sample = rng.sample(cands, min(args.n, len(cands)))
    emb = Embedder(args.model)
    rv, sv = emb.encode([r["text"] for r in refs]), emb.encode([c["text"] for c in sample])
    idx, sc = top_k_blocked(sv, rv, k=min(10, len(refs)))
    rows = []
    for i, c in enumerate(sample):
        for j, s in zip(idx[i], sc[i]):
            if (c["id"], refs[int(j)]["id"]) not in nominated:
                rows.append({"cand": c["id"], "ref": refs[int(j)]["id"], "cosine": round(float(s), 4), "nominated_by": ["audit"]})
                break
    texts = {**{r["id"]: r["text"] for r in refs}, **{c["id"]: c["text"] for c in sample}}
    make_sheet(rows, texts, len(rows), args.seed, args.out_dir, "audit")
    print(f"{len(rows)} non-nominated nearest pairs on the blind audit sheet in {args.out_dir}")


def cmd_retrieval_test(args):
    """Synthetic hard pairs: {"id", "kind": "hard_duplicate" | "hard_distinct", "a": {question, choices}, "b": {...}}.
    Retrieval recall = share of hard duplicates nominated; for distinct pairs, how many retrieval nominated and how many
    the rule (if given) would wrongly remove."""
    rows = [json.loads(l) for l in Path(args.synthetic).read_text(encoding="utf-8").splitlines() if l.strip()]
    emb = None if args.no_embeddings else Embedder(args.model)
    clauses = json.loads(Path(args.rule).read_text(encoding="utf-8"))["against_reference"] if args.rule else None
    res = Counter()
    misses = []
    for r in rows:
        ref = [{"id": r["id"] + "_a", "role": "reference", "text": question_text(r["a"])}]
        cand = [{"id": r["id"] + "_b", "role": "candidate", "text": question_text(r["b"])}]
        vecs = (emb.encode([cand[0]["text"]]), emb.encode([ref[0]["text"]])) if emb else (None, None)
        ps = nominate(ref, cand, *vecs)
        nominated = bool(ps)
        res[f"{r['kind']}:nominated"] += nominated
        res[f"{r['kind']}:total"] += 1
        if clauses is not None and ps:
            res[f"{r['kind']}:rule_removes"] += rule_says_copy(ps[0], clauses)
        if r["kind"] == "hard_duplicate" and not nominated:
            misses.append(r["id"])
    k, n = res["hard_duplicate:nominated"], res["hard_duplicate:total"]
    out = {"counts": dict(res), "retrieval_recall": {"value": round(k / n, 4) if n else None, "ci95": wilson(k, n)},
           "missed_duplicates": misses}
    print(json.dumps(out, indent=2))


def cmd_apply(args):
    rule = load_rule(args.rule)
    pairs = [json.loads(l) for l in Path(args.pairs).read_text(encoding="utf-8").splitlines() if l.strip()]
    tpairs = [json.loads(l) for l in Path(args.tpairs).read_text(encoding="utf-8").splitlines() if l.strip()] if args.tpairs else []
    rows = [json.loads(l) for l in Path(args.order).read_text(encoding="utf-8").splitlines() if l.strip()]
    keep = []
    for f in args.keep or []:
        keep += [json.loads(l)["item_id"] for l in Path(f).read_text(encoding="utf-8").splitlines() if l.strip()]
    rej = apply_rule(pairs, tpairs, rule, stream_order(rows), keep)
    sha = write_jsonl(args.out, rej)
    c = Counter(r["reason"] for r in rej)
    log = {"version": DECONTAM_VERSION, "rule_file": args.rule, "rule_sha256": hashlib.sha256(Path(args.rule).read_bytes()).hexdigest(),
           "pairs_sha256": hashlib.sha256(Path(args.pairs).read_bytes()).hexdigest(), "removed": dict(c), "out_sha256": sha}
    Path(args.out + ".log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps(log, indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pairs")
    p.add_argument("--refs", nargs="+", required=True)
    p.add_argument("--cands", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--no-embeddings", action="store_true", help="lexical checks only (tests)")
    p.set_defaults(fn=cmd_pairs)
    p = sub.add_parser("train-pairs")
    p.add_argument("--cands", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--no-embeddings", action="store_true")
    p.set_defaults(fn=cmd_train_pairs)
    p = sub.add_parser("sheet")
    p.add_argument("--pairs", required=True)
    p.add_argument("--texts", nargs="+", required=True, help="the item files the pair ids come from")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=20261119)
    p.add_argument("--kind", default="calibration")
    p.add_argument("--out-dir", required=True)
    p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("calibrate")
    p.add_argument("--sheet", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--rule", default=None)
    p.add_argument("--side", default="against_reference", choices=["against_reference", "within_training"])
    p.set_defaults(fn=cmd_calibrate)
    p = sub.add_parser("audit-sheet")
    p.add_argument("--refs", nargs="+", required=True)
    p.add_argument("--cands", nargs="+", required=True)
    p.add_argument("--pairs", required=True)
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--seed", type=int, default=20261119)
    p.add_argument("--model", default=None)
    p.add_argument("--out-dir", required=True)
    p.set_defaults(fn=cmd_audit_sheet)
    p = sub.add_parser("retrieval-test")
    p.add_argument("--synthetic", required=True)
    p.add_argument("--rule", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--no-embeddings", action="store_true")
    p.set_defaults(fn=cmd_retrieval_test)
    p = sub.add_parser("apply")
    p.add_argument("--pairs", required=True)
    p.add_argument("--tpairs", default=None)
    p.add_argument("--rule", required=True)
    p.add_argument("--order", required=True, help="the collected training items (gives the stream order)")
    p.add_argument("--keep", nargs="*", help="published compact set files: their examples are always kept")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_apply)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
