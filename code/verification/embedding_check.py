"""
embedding_check.py - check that our embedding code gives the same vectors as the reference library, and measure its
speed on this PC's CPU, before decontamination uses it on real data (approved plan, Step 7, item 4).

WHAT THIS IS AND WHY
decontaminate.py turns each question into 384 numbers with the model all-MiniLM-L6-v2 (pinned revision, see
recovery/embedding_model.md). It does this with the `transformers` library already in the project environment, by
copying the model card's recipe: cut the text at 256 word pieces, average the model's output over the real (not padding)
tokens ("mean pooling"), and scale the result to length 1 ("L2 normalization"). The official way to run this model is
the `sentence-transformers` package. If our copy of the recipe were slightly wrong (for example pooling over padding),
every similarity score would be off, so the two are compared on the same texts:

  texts      (project environment) writes about 100 sample texts to a file.
  reference  (THROWAWAY environment with sentence-transformers) embeds those texts the official way and saves the
             vectors. sentence-transformers is never installed in the project environment; the throwaway virtual
             environment is deleted afterwards.
  verify     (project environment) embeds the same texts with our code; the cosine between our vector and the reference
             vector must be at least 0.9999 for every text (1.0 = identical direction).
  bench   embeds 5,000 to 10,000 training-like texts and records texts per second, peak memory and the projected time
          for about 260,000 texts. If the CPU is too slow, the fallback is a short Talon GPU job (owner's approval).

EXAMPLE
  python embedding_check.py texts --out texts.json                                  (project environment)
  <throwaway>/python embedding_check.py reference --texts texts.json --model-folder <model> --out ref.npy
  python embedding_check.py verify --texts texts.json --reference ref.npy          -> min cosine, PASS or FAIL
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
THRESHOLD = 0.9999


def sample_texts(n, seed=20261120):
    """Deterministic statistics-and-R texts built from the taxonomy and the context deck, with some long texts so the
    256-word-piece truncation is exercised."""
    sys.path.insert(0, str(REPO / "code" / "generation"))
    import variety
    blocks, _ = variety.load_taxonomy()
    ctx, _ = variety.load_contexts()
    subs = [s for b in blocks.values() for a in b["areas"].values() for s in a]
    names = [c["description"] for c in ctx["contexts"]]
    rng = random.Random(seed)
    stems = ["A study records {c}. Using the data below, answer a question about {s}. The values are {v}. Give your answer to 3 decimal places.",
             "Which statement about {s} is correct?",
             "Write one line of R that performs {s} on the vector x <- c({v}).",
             "x <- c({v})\nWhat does R print for a calculation involving {s}?",
             "In a setting with {c}, a researcher is interested in {s}. Explain what the output below shows.\n{t}"]
    table = "Coefficients:\n            Estimate Std. Error t value Pr(>|t|)\n(Intercept)   2.1043     0.4410   4.772  1.2e-05\nx             0.5521     0.0874   6.317  3.9e-08"
    out = []
    for i in range(n):
        v = ", ".join(str(round(rng.uniform(0, 100), rng.choice([0, 1, 2]))) for _ in range(rng.randint(3, 12)))
        t = rng.choice(stems).format(c=rng.choice(names), s=rng.choice(subs), v=v, t=table)
        if i % 25 == 0:   # a long text (more than 256 word pieces)
            t = t + " " + " ".join(f"Observation {k} had value {rng.uniform(0, 50):.2f} in group {rng.choice('ABC')}." for k in range(60))
        out.append(t)
    return out


def cmd_texts(args):
    texts = sample_texts(args.n)
    Path(args.out).write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
    print(f"{len(texts)} texts -> {args.out}")


def cmd_reference(args):
    """Runs in the THROWAWAY environment: imports only sentence-transformers and numpy."""
    import sentence_transformers
    from sentence_transformers import SentenceTransformer
    texts = json.loads(Path(args.texts).read_text(encoding="utf-8"))
    ref = SentenceTransformer(args.model_folder, device="cpu")
    v = ref.encode(texts, batch_size=32, convert_to_numpy=True)
    np.save(args.out, v.astype(np.float32))
    Path(args.out + ".json").write_text(json.dumps({"sentence_transformers_version": sentence_transformers.__version__,
                                                    "max_seq_length": ref.max_seq_length, "modules": [type(m).__name__ for m in ref]}),
                                        encoding="utf-8")
    print(f"{len(texts)} reference vectors -> {args.out} (sentence-transformers {sentence_transformers.__version__}, "
          f"max_seq_length {ref.max_seq_length}, modules {[type(m).__name__ for m in ref]})")


def cmd_verify(args):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import decontaminate as dc
    texts = json.loads(Path(args.texts).read_text(encoding="utf-8"))
    b = np.load(args.reference)
    info = json.loads(Path(args.reference + ".json").read_text(encoding="utf-8"))
    ours = dc.Embedder(args.model)
    a = ours.encode(texts)
    bn = b / np.linalg.norm(b, axis=1, keepdims=True)
    cos = (a * bn).sum(axis=1)
    res = {"texts": len(texts), "min_cosine": float(cos.min()), "mean_cosine": float(cos.mean()),
           "max_abs_difference": float(np.abs(a - b).max()), "reference_norm_range": [float(np.linalg.norm(b, axis=1).min()),
                                                                                    float(np.linalg.norm(b, axis=1).max())],
           "truncated_at_256": ours.truncated, "truncated_share": round(ours.truncated / len(texts), 4),
           "reference": info, "weights_sha256": ours.weights_sha256, "threshold": THRESHOLD,
           "pass": bool(cos.min() >= THRESHOLD and info["max_seq_length"] == dc.Embedder.MAX_LEN)}
    print(json.dumps(res, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    sys.exit(0 if res["pass"] else 1)


def cmd_bench(args):
    import psutil
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import decontaminate as dc
    texts = sample_texts(args.n, seed=7)
    if args.texts:
        for f in args.texts:
            texts += [it["text"] for it in dc.load_items([f], "x")]
    proc = psutil.Process()
    rss0 = proc.memory_info().rss
    emb = dc.Embedder(args.model, batch=args.batch)
    emb.encode(texts[:64])   # warm-up, not timed
    t0 = time.time()
    v = emb.encode(texts)
    secs = time.time() - t0
    mi = proc.memory_info()
    peak = getattr(mi, "peak_wset", None) or mi.rss
    rate = len(texts) / secs
    res = {"texts": len(texts), "seconds": round(secs, 1), "texts_per_second": round(rate, 1),
           "batch": args.batch, "threads": __import__("torch").get_num_threads(),
           "peak_memory_mb": round(peak / 2**20), "start_memory_mb": round(rss0 / 2**20),
           "vectors_mb": round(v.nbytes / 2**20, 1), "projected_minutes_for_260000": round(260000 / rate / 60, 1),
           "projected_vectors_mb_for_260000": round(260000 * 384 * 4 / 2**20)}
    print(json.dumps(res, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("texts")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_texts)
    p = sub.add_parser("reference")
    p.add_argument("--texts", required=True)
    p.add_argument("--model-folder", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_reference)
    p = sub.add_parser("verify")
    p.add_argument("--texts", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("bench")
    p.add_argument("--n", type=int, default=5000)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--texts", nargs="*", help="also embed these item files (for example the smoke run's texts)")
    p.add_argument("--model", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_bench)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
