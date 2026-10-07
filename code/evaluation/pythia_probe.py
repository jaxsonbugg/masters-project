"""
pythia_probe.py - watch how the four Pythia models behave before we design data for them.

WHY THIS EXISTS
The students in this project (Pythia 70M, 160M, 410M, 1B) are "base" language models.
A base model was trained only to continue text (predict the next token). It was never taught
to follow instructions, answer questions politely, or stop talking. Before we spend money on
a benchmark and training data, we want to SEE what these models do with ordinary questions,
so the data we design fits how they really behave.

WHAT THE SCRIPT DOES (in plain steps)
1. Loads each Pythia model from the pinned local copy (never from the internet).
2. Checks the model: counts its parameters, checks the number type (dtype) of its weights,
   and reads the number type stored in the file. This closes open checks in docs/model_versions.md.
3. Checks the tokenizers (the part that cuts text into tokens). The 1B tokenizer files differ
   from the smaller ones, so we test whether the same text becomes the same tokens.
4. Gives each model 16 questions (general knowledge, arithmetic, statistics, R code, ...) in 3
   different prompt formats, and records exactly what the model writes back.
5. Writes three small files to results/pythia_probe/: one record per generation (.jsonl),
   a per-model summary (.csv), and the model/tokenizer facts (.json).

This script never calls the Claude API, so it costs $0. It does not train or change any model.
Run it with the virtual environment's Python (see recovery/python_env.md), for example:
    C:\\masters_project_large\\envs\\probe\\Scripts\\python.exe code\\evaluation\\pythia_probe.py
Useful flags: --models 70m 160m   --dtype float32   --limit-prompts 2   --sampling
"""

import argparse
import csv
import json
import platform
import struct
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch
import transformers
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

# ---------------------------------------------------------------------------------------
# Fixed facts about the models (copied from docs/model_versions.md; do not edit casually).
# "sha" is the pinned Hugging Face commit, "official_params" is the model card's count.
# ---------------------------------------------------------------------------------------
MODELS = {
    "70m": {"repo": "EleutherAI/pythia-70m-deduped", "sha": "9a7c847e93250c8f24d4b7e7134dbf369e8fc9cb", "official_params": 70_426_624},
    "160m": {"repo": "EleutherAI/pythia-160m-deduped", "sha": "c54a0e0b28cc667b6f278803024438d57f847b5d", "official_params": 162_322_944},
    "410m": {"repo": "EleutherAI/pythia-410m-deduped", "sha": "c66f7467608ffee8fca0d28cf1f46a7574b53cec", "official_params": 405_334_016},
    "1b": {"repo": "EleutherAI/pythia-1b-deduped", "sha": "d1988145ec1cf1e76d786cd05af9f53e8b1c95cc", "official_params": 1_011_781_632},
}

# ---------------------------------------------------------------------------------------
# The 16 questions. They are deliberately NOT all about statistics: we want to learn how the
# models behave in general. "reference" is a short correct answer so we can judge outputs by eye.
# ---------------------------------------------------------------------------------------
PROMPTS = [
    {"id": "gk1", "category": "general", "question": "What is the capital of France?", "reference": "Paris"},
    {"id": "gk2", "category": "general", "question": "Who wrote the play Romeo and Juliet?", "reference": "William Shakespeare"},
    {"id": "ar1", "category": "arithmetic", "question": "What is 17 + 25?", "reference": "42"},
    {"id": "ar2", "category": "arithmetic", "question": "What is 12 times 8?", "reference": "96"},
    {"id": "ar3", "category": "arithmetic", "question": "What is 144 divided by 12?", "reference": "12"},
    {"id": "wp1", "category": "word_problem", "question": "A train travels 60 miles per hour for 3 hours. How far does it travel?", "reference": "180 miles"},
    {"id": "lg1", "category": "logic", "question": "If all cats are animals and Tom is a cat, is Tom an animal? Answer yes or no.", "reference": "yes"},
    {"id": "df1", "category": "definition", "question": "What is photosynthesis?", "reference": "Plants turn light, water and carbon dioxide into sugar and oxygen."},
    {"id": "df2", "category": "definition", "question": "What is a prime number?", "reference": "A whole number greater than 1 whose only divisors are 1 and itself."},
    {"id": "st1", "category": "statistics", "question": "What is a p-value?", "reference": "The probability of results at least as extreme as observed if the null hypothesis is true."},
    {"id": "st2", "category": "statistics", "question": "What is the difference between standard deviation and standard error?", "reference": "SD measures spread of the data; SE measures uncertainty of an estimate (SD / sqrt(n))."},
    {"id": "st3", "category": "statistics", "question": "What does a 95% confidence interval mean?", "reference": "A procedure that captures the true value in about 95% of repeated samples."},
    {"id": "r1", "category": "r_code", "question": "Write R code to compute the mean of the vector c(4, 8, 15, 16, 23, 42).", "reference": "mean(c(4, 8, 15, 16, 23, 42)) which equals 18"},
    {"id": "r2", "category": "r_code", "question": "Write R code to fit a linear regression of y on x using a data frame called df.", "reference": "lm(y ~ x, data = df)"},
    {"id": "r3", "category": "r_code", "question": "This R code gives an error: mena(c(1, 2, 3)). Fix it.", "reference": "mean(c(1, 2, 3))"},
    {"id": "fm1", "category": "format", "question": "Answer with only a number: how many days are in a week?", "reference": "7"},
]

# Three unrelated worked examples used in the "fewshot" format. They show the model the
# pattern "Question ... Answer: <short answer>" without giving away any test answer.
FEWSHOT_EXAMPLES = [
    ("What is the capital of Italy?", "Rome"),
    ("What is 9 + 6?", "15"),
    ("What color is the sky on a clear day?", "Blue"),
]


def build_prompt(fmt, question):
    """Turn one question into the text the model actually sees, in one of three formats."""
    if fmt == "raw":
        # Just the bare question. Shows pure continuation behavior.
        return question
    if fmt == "qa":
        # A light template that signals where the answer should start.
        return f"Question: {question}\nAnswer:"
    if fmt == "fewshot":
        # Three solved examples first, then our question, so the model can copy the pattern.
        shots = "".join(f"Question: {q}\nAnswer: {a}\n\n" for q, a in FEWSHOT_EXAMPLES)
        return shots + f"Question: {question}\nAnswer:"
    raise ValueError(f"unknown format {fmt}")


# Strings used to compare tokenizers. If the 1B tokenizer splits any of these differently
# from the others, the same training text would turn into different tokens for different students.
TOKENIZER_TEST_STRINGS = [
    "The quick brown fox jumps over the lazy dog.",
    "A p-value of 0.034 is below alpha = 0.05.",
    "model <- lm(y ~ x1 + x2, data = df)\nsummary(model)",
    "for (i in 1:10) {\n    print(i^2)\n}",
    "mean(c(4, 8, 15, 16, 23, 42))  # 18",
    "123456789 3.14159 -0.5e-3",
    "<|endoftext|>",
    "   indented    spaces\t and a tab",
]


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%MZ")


def read_safetensors_dtypes(path):
    """Read the number types stored INSIDE the weights file, without loading the weights.
    A .safetensors file starts with 8 bytes giving the length of a JSON header, and the header
    lists every tensor with its dtype. This tells us how the checkpoint was saved on disk,
    which is separate from the dtype we choose when loading it."""
    with open(path, "rb") as f:
        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len))
    return dict(Counter(v["dtype"] for k, v in header.items() if k != "__metadata__"))


def has_repetition(token_ids, n=4, times=3):
    """Flag text that loops: any run of n tokens that appears at least `times` times."""
    if len(token_ids) < n * times:
        return False
    grams = Counter(tuple(token_ids[i:i + n]) for i in range(len(token_ids) - n + 1))
    return max(grams.values()) >= times


def peak_memory_mb():
    """Peak physical memory this process has used so far (megabytes). Windows exposes a true peak."""
    info = psutil.Process().memory_info()
    return round(getattr(info, "peak_wset", info.rss) / 1e6, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    ap.add_argument("--dtype", default="float16", choices=["float16", "float32", "bfloat16"],
                    help="runtime load dtype. Project rule is float16; use float32 only as a logged deviation.")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--sampling", action="store_true", help="also run a sampled (temp 0.7, top_p 0.9) pass")
    ap.add_argument("--limit-prompts", type=int, default=None, help="only use the first N prompts (for quick tests)")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out-dir", default=None, help="override the output folder (default results/pythia_probe)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    paths = yaml.safe_load((repo_root / "configs" / "paths.yaml").read_text())  # never hardcode paths
    models_dir = Path(paths["models_pythia"])
    out_dir = Path(args.out_dir) if args.out_dir else repo_root / "results" / "pythia_probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    dtype = getattr(torch, args.dtype)
    prompts = PROMPTS[: args.limit_prompts] if args.limit_prompts else PROMPTS
    formats = ["raw", "qa", "fewshot"]
    decodings = [("greedy", {"do_sample": False})]
    if args.sampling:
        decodings.append(("sampled", {"do_sample": True, "temperature": 0.7, "top_p": 0.9}))

    env = {
        "python": sys.version.split()[0], "torch": torch.__version__, "transformers": transformers.__version__,
        "platform": platform.platform(), "device": args.device, "dtype_requested": args.dtype,
        "cpu_threads": torch.get_num_threads(), "ram_total_gb": round(psutil.virtual_memory().total / 1e9, 1),
    }
    print(f"[probe] {stamp}  env={env}")

    model_info = {"environment": env, "models": {}, "tokenizer_comparison": {}}
    records = []
    tokenizers = {}

    for size in args.models:
        meta = MODELS[size]
        folder = models_dir / f"pythia-{size}-deduped" / "step143000"
        print(f"\n[probe] loading {size} from {folder}")
        tok = AutoTokenizer.from_pretrained(folder, local_files_only=True)
        tokenizers[size] = tok
        # The "end of text" token (<|endoftext|>) has id 0 in the shared vocabulary. We look it up by
        # NAME instead of trusting tok.eos_token_id or the model config, because the 1B files disagree:
        # its tokenizer defines no eos token at all (None) and its config says eos id 2, which is the
        # ordinary character "!". Using the same explicit id for all four models keeps them comparable.
        eos_id = tok.convert_tokens_to_ids("<|endoftext|>")
        assert eos_id == 0, f"unexpected <|endoftext|> id {eos_id} for {size}"

        t0 = time.time()
        # The dtype is passed explicitly (project rule): we never trust config.json for this.
        # (transformers 5 calls this argument `dtype`; older versions called it `torch_dtype`.)
        model = AutoModelForCausalLM.from_pretrained(folder, dtype=dtype, local_files_only=True)
        model.to(args.device)
        model.eval()
        load_seconds = round(time.time() - t0, 2)

        # --- model facts (closes the open checks in docs/model_versions.md section 3) ---
        n_params = sum(p.numel() for p in model.parameters())
        loaded_dtypes = sorted({str(p.dtype) for p in model.parameters()})
        info = {
            "repo": meta["repo"], "commit_sha": meta["sha"],
            "official_params": meta["official_params"], "counted_params": n_params,
            "param_difference": n_params - meta["official_params"],
            "loaded_dtypes": loaded_dtypes,
            "file_tensor_dtypes": read_safetensors_dtypes(folder / "model.safetensors"),
            "config_eos_token_id": model.config.eos_token_id, "config_bos_token_id": model.config.bos_token_id,
            "config_eos_token_string": tok.convert_ids_to_tokens(model.config.eos_token_id),
            "tokenizer_eos_token": tok.eos_token, "tokenizer_eos_token_id": tok.eos_token_id,
            "eos_id_used_by_probe": eos_id,
            "tokenizer_vocab_size": len(tok), "model_max_positions": model.config.max_position_embeddings,
            "load_seconds": load_seconds, "peak_ram_mb_after_load": peak_memory_mb(),
        }
        model_info["models"][size] = info
        print(f"[probe] {size}: params={n_params:,} (official {meta['official_params']:,}), loaded dtype={loaded_dtypes}, "
              f"file dtypes={info['file_tensor_dtypes']}, eos id tokenizer={tok.eos_token_id} "
              f"config={model.config.eos_token_id} ({info['config_eos_token_string']!r}) used={eos_id}")

        # --- generations ---
        for p in prompts:
            for fmt in formats:
                text_in = build_prompt(fmt, p["question"])
                enc = tok(text_in, return_tensors="pt").to(args.device)
                n_in = enc["input_ids"].shape[1]
                for dec_name, dec_kwargs in decodings:
                    torch.manual_seed(args.seed)
                    rec = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "model": size, "repo": meta["repo"], "commit_sha": meta["sha"],
                        "dtype": args.dtype, "device": args.device, "decoding": dec_name,
                        "max_new_tokens": args.max_new_tokens, "seed": args.seed,
                        "prompt_id": p["id"], "category": p["category"], "format": fmt,
                        "reference": p["reference"], "prompt_text": text_in, "prompt_tokens": n_in,
                    }
                    try:
                        t1 = time.time()
                        with torch.no_grad():
                            # Every model stops on the same explicit end-of-text id (see eos_id above).
                            out = model.generate(
                                **enc, max_new_tokens=args.max_new_tokens,
                                eos_token_id=eos_id, pad_token_id=eos_id, **dec_kwargs,
                            )
                        secs = time.time() - t1
                        new_ids = out[0, n_in:].tolist()
                        stopped_by_eos = eos_id in new_ids
                        if stopped_by_eos:
                            new_ids = new_ids[: new_ids.index(eos_id)]
                        rec.update({
                            "output_text": tok.decode(new_ids, skip_special_tokens=True),
                            "generated_tokens": len(new_ids),
                            "finish_reason": "eos" if stopped_by_eos else "max_tokens",
                            "repeats": has_repetition(new_ids),
                            "seconds": round(secs, 3),
                            "tokens_per_second": round(len(new_ids) / secs, 2) if secs > 0 else None,
                            "peak_ram_mb": peak_memory_mb(), "error": None,
                        })
                    except Exception as e:  # keep going: an error is itself a result worth recording
                        rec.update({"output_text": None, "generated_tokens": None, "finish_reason": "error",
                                    "repeats": None, "seconds": None, "tokens_per_second": None,
                                    "peak_ram_mb": peak_memory_mb(), "error": f"{type(e).__name__}: {e}"})
                    records.append(rec)
            print(f"[probe] {size}: finished prompt {p['id']}")

        del model  # free memory before the next size loads

    # --- tokenizer comparison across sizes ---
    if len(tokenizers) > 1:
        base = args.models[0]
        for s in TOKENIZER_TEST_STRINGS:
            ids = {size: tokenizers[size](s)["input_ids"] for size in tokenizers}
            model_info["tokenizer_comparison"][s] = {
                "ids_by_model": ids,
                "identical_to_first_model": {size: ids[size] == ids[base] for size in ids},
            }

    # --- write the three output files ---
    prefix = out_dir / f"{stamp}_probe"
    with open(f"{prefix}.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(f"{prefix}_model_info.json", "w", encoding="utf-8") as f:
        json.dump(model_info, f, indent=2, ensure_ascii=False)

    # per (model, format, decoding) summary
    groups = {}
    for r in records:
        groups.setdefault((r["model"], r["format"], r["decoding"]), []).append(r)
    rows = []
    for (m, fmt, dec), rs in groups.items():
        ok = [r for r in rs if r["error"] is None]
        n = len(rs)
        rows.append({
            "model": m, "format": fmt, "decoding": dec, "n": n, "errors": n - len(ok),
            "mean_generated_tokens": round(sum(r["generated_tokens"] for r in ok) / len(ok), 1) if ok else None,
            "eos_rate": round(sum(r["finish_reason"] == "eos" for r in ok) / len(ok), 3) if ok else None,
            "repeat_rate": round(sum(bool(r["repeats"]) for r in ok) / len(ok), 3) if ok else None,
            "mean_tokens_per_second": round(sum(r["tokens_per_second"] or 0 for r in ok) / len(ok), 2) if ok else None,
        })
    with open(f"{prefix}_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n[probe] summary (model, format, decoding: n, errors, mean tokens, eos rate, repeat rate, tok/s)")
    for r in rows:
        print(f"  {r['model']:>5} {r['format']:>8} {r['decoding']:>8}: n={r['n']} err={r['errors']} "
              f"tokens={r['mean_generated_tokens']} eos={r['eos_rate']} repeat={r['repeat_rate']} tps={r['mean_tokens_per_second']}")
    print(f"\n[probe] wrote {prefix}.jsonl, {prefix}_summary.csv, {prefix}_model_info.json")


if __name__ == "__main__":
    main()
