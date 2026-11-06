"""
throughput_report.py - turn the throughput runs (stage T on Talon) into one table and a projection for 200,000 examples.

WHAT THIS IS AND WHY
Before anyone decides how to generate 200,000 training examples, the project needs MEASURED speed instead of guesses.
Stage T (configs/talon/talon_throughput.sbatch) sends the same 32 development prompts (slot set T, BM9101-BM9132) to the
model under different GPU layouts, for example 1 GPU or 2 GPUs, and different numbers of requests in flight. Each such
run leaves a run folder. This script reads those folders and answers: for each layout, how many SUCCESSFUL examples came
back per hour, and how many GPU-hours did 1,000 successful examples cost? It then scales that to 200,000 examples.
It makes no server calls, needs no GPU and writes nothing; it only reads run folders.

WHAT THE TERMS MEAN
  successful example   HTTP 200, the model stopped by itself (finish reason "stop", not cut off), and the answer is
                       a parseable JSON object. A reply that fails any of these is counted but is not an example.
  examples per hour    successes / (wall-clock seconds the client spent sending requests / 3600). The time the server
                       needed to LOAD the model is reported separately because it is paid once per job, not per example.
  GPU-hours per 1,000  GPUs used x hours / successes x 1,000. Example: 32 successes in 0.5 h on 2 GPUs -> 2 x 0.5 / 32
                       x 1000 = 31.25 GPU-hours per 1,000 examples. GPU-hours (not hours) is what a cluster allocation
                       is normally charged in, and it makes 1 GPU and 2 GPUs comparable.
  truncation           the reply hit a length limit (finish reason "length"), or prompt + output tokens reached the
                       server's context limit. A truncated reply is usually an unusable example.
  reasoning exhaustion the model produced reasoning but no usable answer: the content is empty or is not a JSON object.
                       Most often the thinking used up the output budget.
  projection           GPU-hours for 200,000 = GPU-hours per 1,000 x 200. Shown for the best and the worst measured
                       layout. It is a PLANNING ESTIMATE from 32 prompts of one prompt family, not a quote: the real
                       200,000 questions may be longer or shorter, and 32 samples is small.

HOW EACH RUN FOLDER DESCRIBES ITS LAYOUT
The Talon job script records these in run_log.json under "meta" (all are --meta KEY=VALUE arguments of
open_teacher_test.py): gpu_count (required), tensor_parallel, replicas, max_num_seqs, max_model_len, load_seconds. If the
job script wrote gpu_peak.txt (the peak GPU memory lines) into the run folder, it is shown too. A layout that could not even
start (for example BF16 weights plus cache do not fit on 1 GPU) has no run folder: pass it with --failed "label=reason"
and it is listed as a result, because "does not fit" is information.

USAGE
  python throughput_report.py --run <run folder> [--run <run folder> ...] [--failed "1gpu-tp1=out of memory at load"]
                              [--threshold 0.05] [--gpus-available 4 8 16]
Exit code: 0 = report printed, no layout over the threshold; 2 = at least one layout has truncation or reasoning
exhaustion above the threshold (printed as a finding, never hidden); 1 = a run folder could not be read.

Talon's pricing, allocation and GPU quota are UNVERIFIED (ask Miami Research Computing); the "if N GPUs were available"
lines below only show how the arithmetic scales and are not a statement about what the account will be given.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import open_teacher_test as ott  # noqa: E402  (same folder; reused for reading rows and parsing replies)

DEFAULT_THRESHOLD = 0.05      # a truncation or reasoning-exhaustion rate above 5% blocks "comparable" (editable: --threshold)
TARGET_EXAMPLES = 200_000
CONTEXT_NOTE = (
    "CONTEXT NOTE: these runs use 20,480 tokens per sequence (3,000 input cap + 16,384 output cap + headroom). That is far\n"
    "below Qwen's native 262,144 tokens and below the 128K its model card advises for keeping thinking quality. It was chosen\n"
    "only so the Talon run matches the Redhawk run. Treat every number here as valid for THAT setting only."
)
UNVERIFIED_NOTE = (
    "UNVERIFIED (ask Miami Research Computing): Talon pricing, allocation, GPU quota and access limits. The scaling lines\n"
    "show arithmetic only."
)


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def analyse_run(run_dir):
    """Numbers for one run folder. Raises ValueError with a plain message if the folder cannot be used."""
    run_dir = Path(run_dir)
    try:
        meta = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{run_dir}: run_log.json is missing or unreadable ({e})")
    try:
        rows = ott.read_rows(run_dir)
    except ott.RunFolderError as e:
        raise ValueError(str(e))
    m = meta.get("meta") or {}
    gpus = _int(m.get("gpu_count"))
    if not gpus or gpus < 1:
        raise ValueError(f"{run_dir}: run_log.json meta has no gpu_count, so GPU-hours cannot be computed. "
                         f"The Talon job script records it with --meta gpu_count=N.")
    wall = sum(float(s.get("wall_seconds") or 0) for s in meta.get("sessions", []))
    if wall <= 0:
        raise ValueError(f"{run_dir}: no finished client session with wall_seconds in run_log.json (was the run interrupted?)")
    max_len = _int(m.get("max_model_len"))
    n_ok_http = successes = truncated = exhausted = errors = out_tokens = 0
    for rec in rows:
        if rec.get("http_status") != 200:
            errors += 1
            continue
        n_ok_http += 1
        content, reasoning, finish, usage = ott.reply_parts(rec)
        out_tokens += int(usage.get("completion_tokens") or 0)
        used = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
        cut = finish == "length" or bool(max_len and used >= max_len)
        text, _ = ott.extract_json(content)
        try:
            is_object = isinstance(json.loads(text), dict) if content.strip() else False
        except ValueError:
            is_object = False
        if cut:
            truncated += 1
        if reasoning.strip() and not is_object:
            exhausted += 1
        if finish == "stop" and not cut and is_object:
            successes += 1
    replies = n_ok_http + errors
    hours = wall / 3600.0
    peak = ""
    pk = run_dir / "gpu_peak.txt"
    if pk.exists():
        peak = "; ".join(l.strip() for l in pk.read_text(encoding="utf-8").splitlines() if l.strip().startswith("gpu"))
    sess = meta.get("sessions", [{}])
    return {
        "run": run_dir.name, "gpus": gpus, "tp": m.get("tensor_parallel", "?"), "replicas": m.get("replicas", "?"),
        "max_num_seqs": m.get("max_num_seqs", "?"), "client_concurrency": sess[-1].get("concurrency", "?"),
        "max_model_len": max_len, "load_seconds": m.get("load_seconds", "?"),
        "replies": replies, "http_errors": errors, "successes": successes, "truncated": truncated, "exhausted": exhausted,
        "wall_seconds": wall, "out_tokens": out_tokens, "tok_per_s": out_tokens / wall,
        "examples_per_hour": successes / hours,
        "gpu_hours_per_1000": (gpus * hours / successes * 1000) if successes else None,
        "trunc_rate": truncated / n_ok_http if n_ok_http else 0.0,
        "exhaust_rate": exhausted / n_ok_http if n_ok_http else 0.0,
        "peak": peak,
    }


def label(r):
    return f"{r['gpus']} GPU(s), TP={r['tp']}, replicas={r['replicas']}, seqs={r['max_num_seqs']}, client concurrency={r['client_concurrency']}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Throughput table and 200,000-example projection from stage T run folders.")
    ap.add_argument("--run", action="append", default=[], help="a run folder (repeat for each layout)")
    ap.add_argument("--failed", action="append", default=[], help='a layout that could not run, as "label=reason"')
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="truncation / reasoning-exhaustion rate above which a layout is flagged (default 0.05)")
    ap.add_argument("--gpus-available", type=int, nargs="*", default=[4, 8, 16],
                    help="GPU counts used only for the 'if N GPUs were available' arithmetic (UNVERIFIED quota)")
    args = ap.parse_args(argv)
    if not args.run and not args.failed:
        ap.error("give at least one --run or --failed")

    results, problems = [], []
    for d in args.run:
        try:
            results.append(analyse_run(d))
        except ValueError as e:
            problems.append(str(e))
    if problems:
        for p in problems:
            print("CANNOT READ:", p)
        return 1

    print("THROUGHPUT REPORT (stage T, development slots BM9101-BM9132; test material only, never training data)")
    print(CONTEXT_NOTE)
    print()
    flagged = []
    for r in results:
        gph = "n/a (no successful example)" if r["gpu_hours_per_1000"] is None else f"{r['gpu_hours_per_1000']:.2f}"
        print(f"Layout: {label(r)}   [{r['run']}]")
        print(f"  replies {r['replies']} (HTTP errors {r['http_errors']}), successful examples {r['successes']}, "
              f"truncated {r['truncated']} ({r['trunc_rate']:.1%}), reasoning without a usable answer {r['exhausted']} ({r['exhaust_rate']:.1%})")
        print(f"  client wall-clock {r['wall_seconds']:.0f} s (model load {r['load_seconds']} s, not included), "
              f"output {r['out_tokens']} tokens = {r['tok_per_s']:.1f} tok/s")
        print(f"  successful examples per hour: {r['examples_per_hour']:.1f}   GPU-hours per 1,000 successful examples: {gph}")
        if r["peak"]:
            print(f"  peak GPU memory: {r['peak']}")
        if r["trunc_rate"] > args.threshold:
            flagged.append(f"{label(r)}: truncation {r['trunc_rate']:.1%} is above {args.threshold:.0%}")
        if r["exhaust_rate"] > args.threshold:
            flagged.append(f"{label(r)}: reasoning without a usable answer {r['exhaust_rate']:.1%} is above {args.threshold:.0%}")
        print()
    for f in args.failed:
        name, _, why = f.partition("=")
        print(f"Layout: {name.strip()}   NO THROUGHPUT (it did not run): {why.strip() or 'reason not given'}")
        print("  This is a result: this layout cannot be used with these settings.\n")

    usable = [r for r in results if r["gpu_hours_per_1000"] is not None]
    print(f"PROJECTION for {TARGET_EXAMPLES:,} successful examples (planning estimate from {sum(r['replies'] for r in results)} "
          f"replies of one prompt family; the real questions may differ)")
    if usable:
        best = min(usable, key=lambda r: r["gpu_hours_per_1000"])
        worst = max(usable, key=lambda r: r["gpu_hours_per_1000"])
        for tag, r in (("best measured layout ", best), ("worst measured layout", worst)):
            total = r["gpu_hours_per_1000"] * TARGET_EXAMPLES / 1000
            print(f"  {tag}: {r['gpu_hours_per_1000']:.2f} GPU-hours per 1,000 -> {total:,.0f} GPU-hours for {TARGET_EXAMPLES:,}  ({label(r)})")
            for n in args.gpus_available:
                print(f"      if {n} GPUs were available at once: about {total / n / 24:.1f} days of running time")
        print("  Not included: loading the model once per job, jobs lost to time limits or queue waits, failed examples that")
        print("  must be re-asked (only the successes above count), and checking the answers afterwards.")
    else:
        print("  No layout produced a successful example, so no projection can be made.")
    print(UNVERIFIED_NOTE)
    if flagged:
        print("\nFINDINGS (not hidden):")
        for f in flagged:
            print("  -", f)
        print("A layout with findings above the threshold should not be called comparable to the Redhawk run.")
        return 2
    print("\nNo layout is above the truncation / reasoning-exhaustion threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
