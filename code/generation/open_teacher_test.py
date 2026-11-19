"""
open_teacher_test.py - run the benchmark-generation prompt on an OPEN-WEIGHT teacher (Qwen3.6-27B) and score it.

WHAT THIS IS AND WHY
The project's teacher is the open-weight model Qwen3.6-27B (docs/methodology/workflow.md Section 2.1). This script sends the
benchmark-generation prompt to a running Qwen server on one of Miami's clusters, saves every reply, and scores the
replies with the same checks used for every generated question. It is used to test a deployment on 100 fixed
question "slots" (BM0021 to BM0120) before the real benchmark run. Two backends exist:
  talon   - BF16 (full precision) weights served by vLLM on Miami's Talon cluster (H100, free). The primary cluster;
            its settings stay drafts until reviewed (configs/talon, docs/clusters/talon_setup.md).
  redhawk - a 4-bit file (Unsloth Q4_K_M GGUF) served by llama.cpp on Miami's Redhawk cluster (2x V100, free). The
            fallback.
The teacher runs at BF16 for all generation (decided 2026-11-18 without a precision test; docs/methodology/workflow.md
Section 2.1). `compare` gives paired statistics for any two scored runs on the same slots.

THE THINKING ON/OFF CHECK (set K, decided 2026-11-18; workflow.md Section 2.1). `run --smoke-set K --thinking on|off` writes
BM8001-BM8060 in one mode (40 primary slots plus a 20-slot reserve block). `answer-set` builds the FIXED shared question set
from the two writing runs: positions 1-20 from thinking on, 21-40 from thinking off, a failed primary replaced by the reserve
slot at the same pattern position in the same origin mode, and every outcome recorded. `answer` has the teacher answer that
set N times per question in one mode (prompt data/prompts/teacher_answer_v1.md). code/generation/answer_check.py grades it.

The outputs are TEST MATERIAL ONLY. They are never part of the benchmark and never training data; every saved row
carries "use": "dev_test_only". Only slot descriptions (category, subtopic, difficulty, answer type) are sent, never a
benchmark question.

TWO KINDS OF SLOTS, KEPT APART ON PURPOSE
  main slots  BM0021-BM0120 : the real experiment. ONE attempt per slot, no re-asking for a better answer.
  smoke slots BM9001-BM9004 : development slots used only to test the plumbing (GPU memory, saving, parsing).
                              Set A = BM9001-BM9002, set B = BM9003-BM9004. They are never mixed with main slots.
  throughput set T          : BM9101-BM9132, 32 development slots for the Talon throughput benchmark (configs/talon).
  thinking-check set K      : BM8001-BM8060 (40 primary + 20 reserve development slots; see below).
A run is either a smoke run (--smoke-set A|B|T|K) or a main run; the script refuses to mix them.

WHAT IS REUSED UNCHANGED FROM generate_benchmark.py (so the prompt and the checks cannot drift)
  load_prompt + build_request  - the exact v6 prompt text for each slot (the prompt file is not edited);
  select_slots                 - the fixed, repeatable question slots;
  ITEM_SCHEMA                  - the same output fields;
  process_reply                - the same checks and the same "key from R" step used for every generated question.

WHY THE SCHEMA IS SENT AS TEXT
These servers do not enforce a JSON output schema, and forcing JSON while the model is "thinking" is unreliable on
both engines (llama.cpp issues #20345 and #29006). So the schema TEXT is appended to the system message, identically
for both backends, and replies are parsed and checked instead of forced. A reply that is not valid JSON counts as a
format failure.

HOW A RESUME STAYS SAFE (both backends)
  - responses.jsonl is append-only and each row is flushed to disk as it is written; nothing is ever rewritten.
  - A slot with a saved HTTP-200 reply is never sent again. A slot whose earlier call errored is NOT re-sent unless
    --retry-errors is given (its row is then marked attempt 2, 3, ...).
  - The run folder has a lock file, so two jobs cannot write to the same folder at once.
  - A resume must use exactly the same settings as the original run (model, prompt hash, sampling, max_tokens,
    slots); otherwise it refuses. The prior rows are checked first and a damaged file stops the run.
  - Starting a NEW main run when a main run folder already exists is refused unless --new-run is given.

EXAMPLES (on the clusters the sbatch scripts call `run` themselves)
  python open_teacher_test.py run --backend redhawk --dry-run                             (shows the first request; sends nothing)
  python open_teacher_test.py run --backend redhawk --smoke-cap-check                     (smoke test, 1 call)
  python open_teacher_test.py run --backend redhawk --smoke-set A                         (smoke test, 2 calls)
  python open_teacher_test.py run --backend redhawk --concurrency 2                       (main run, 100 slots)
  python open_teacher_test.py run --backend redhawk --resume <folder>                     (continue after a stop)
  python open_teacher_test.py validate --run <folder>                                     (free; no R needed)
  python open_teacher_test.py score --run <folder>                                        (free; needs R)
  python open_teacher_test.py compare --a <scored items A> --b <scored items B> [--ref <reference items>]
"""

import argparse
import json
import math
import os
import random
import re
import signal
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_benchmark as gb  # noqa: E402  (shared prompt, slots, schema and checks)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------------------------
# Settings that define the test. Every one of these is written into run_log.json.
# ---------------------------------------------------------------------------------------------
N_SLOTS, START = 100, 21                 # BM0021 to BM0120, the fixed deployment-test slots
MAIN_FIRST, MAIN_LAST = 21, 120          # the only slot numbers a main run may contain
# (first slot number, how many): BM9001-2, BM9003-4, BM9101-9132 (T = throughput), BM8001-8060 (K = the thinking on/off
# check: BM8001-8040 are the 40 primary slots, BM8041-8060 a reserve block used only for pre-specified replacements)
SMOKE_SETS = {"A": (9001, 2), "B": (9003, 2), "T": (9101, 32), "K": (8001, 60)}
K_PRIMARY, K_HALF = 40, 20               # the thinking check: 40 primary slots; positions 1-20 come from thinking on, 21-40 from off
MAX_TOKENS = 16384                       # output ceiling per call, INCLUDING thinking tokens (both backends)
# Qwen3.6-27B model card, thinking mode (https://huggingface.co/Qwen/Qwen3.6-27B, read 2026-11-04)
SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0}
# Qwen3.6-27B model card, non-thinking (Instruct) mode (read 2026-11-18): the card gives this one set for that mode.
SAMPLING_NO_THINK = {"temperature": 0.7, "top_p": 0.80, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5}
ANSWER_PROMPT_FILE = gb.REPO / "data" / "prompts" / "teacher_answer_v1.md"

BACKENDS = {
    "redhawk": {
        "base_url": "http://127.0.0.1:8080/v1", "model": "qwen3.6-27b-q4_k_m",
        "precision": "4-bit Q4_K_M GGUF (Unsloth), weights SHA-256 checked by the job script",
        "weights": "unsloth/Qwen3.6-27B-GGUF @ 82d411acf4a06cfb8d9b073a5211bf410bfc29bf, Qwen3.6-27B-Q4_K_M.gguf, "
                   "sha256 5ed60d0af4650a854b1755bd392f9aef4872643dc25a254bc68043fa638392a0",
        "engine": "llama.cpp llama-server (exact tag and commit recorded by the job script in meta)",
        "extra": {"chat_template_kwargs": {"enable_thinking": True}},
        "timeout_s": 3600, "label": "redhawk-q4km",
    },
    # Talon (Miami's H100 cluster): BF16 weights served by vLLM. DRAFT entry, written before any Talon login: the engine
    # version and the exact weights revision are UNVERIFIED and are replaced from the probe output (configs/talon). The
    # model alias must equal --served-model-name in configs/talon/serve_and_run.sh. Free to run.
    "talon": {
        "base_url": "http://127.0.0.1:8000/v1", "model": "qwen3.6-27b-bf16",
        "precision": "BF16 safetensors (Qwen/Qwen3.6-27B), UNVERIFIED until the probe pins the revision",
        "weights": "Qwen/Qwen3.6-27B @ UNVERIFIED-revision (resolved to a commit hash at probe time)",
        "engine": "vLLM (exact version recorded by the job script in meta; UNVERIFIED until the probe)",
        "extra": {"chat_template_kwargs": {"enable_thinking": True}},
        "timeout_s": 3600, "label": "talon-bf16",
    },
}

SCHEMA_BLOCK_HEADER = "Output schema (JSON Schema):"
OUT_ROOT_OVERRIDE = None                 # set by --out-root (used by tests); normally the folder from paths.yaml
FINGERPRINT_KEYS = ["backend", "model", "precision", "weights", "extra_params", "sampling", "max_tokens",
                    "prompt_sha256", "prompt_version", "adapter_change", "attempts_per_slot", "slot_set", "slot_ids"]


def utc_now():
    return datetime.now(timezone.utc)


def paths():
    return yaml.safe_load((gb.REPO / "configs" / "paths.yaml").read_text())


CLUSTER_BACKENDS = {"redhawk": "redhawk", "talon": "talon"}   # backend -> the cluster whose paths.yaml keys it uses


def outputs_root(backend=None):
    """Teacher outputs live outside the repository. On Windows the PC path from paths.yaml. On Linux the path of the
    cluster the backend belongs to: a talon run uses talon_outputs, a redhawk run redhawk_outputs, and the two can never
    be swapped (so Talon results can never land in the Redhawk folder, or the reverse). A command that has no backend
    keeps the Redhawk path as before. The key is UNSET until a storage check on the
    cluster picks an approved location."""
    if OUT_ROOT_OVERRIDE:
        return Path(OUT_ROOT_OVERRIDE)
    cluster = CLUSTER_BACKENDS.get(backend, "redhawk")
    key = "teacher_outputs" if os.name == "nt" else f"{cluster}_outputs"
    value = paths().get(key)
    if not value or str(value).strip().upper() == "UNSET":
        sys.exit(f"{key} is UNSET in configs/paths.yaml. Run the storage check (configs/{cluster}/probe_*.sh), "
                 f"choose an approved project or scratch location, and set {cluster}_root and {cluster}_outputs.")
    return Path(value)


def atomic_write(path, text):
    """Write a file so a crash can never leave it half-written: write a temp file, then rename over the old one."""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def slots_for_ids(ids):
    """Slot descriptions for item ids such as BM0021 or BM9001 (the blueprint is deterministic)."""
    nums = [int(re.sub(r"\D", "", i)) for i in ids]
    table = {s["item_id"]: s for s in gb.blueprint(max(nums))}
    return {i: table[i] for i in ids}


# ---------------------------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------------------------
def build_messages(slot, prompt):
    """The v6 system and user text exactly as generate_benchmark.build_request makes them, plus the
    schema block appended to the system message (the one adapter change, explained at the top)."""
    req = gb.build_request(slot, prompt)
    system = req["system"] + "\n\n" + SCHEMA_BLOCK_HEADER + "\n" + json.dumps(gb.schema_for(gb.PROMPT_VERSION))
    return [{"role": "system", "content": system}, {"role": "user", "content": req["messages"][0]["content"]}]


def mode_params(backend, thinking="on"):
    """(sampling, extra request fields) for a thinking mode. The request keeps vLLM's existing
    chat_template_kwargs: {"enable_thinking": ...} structure; only its value changes (the model card's way to switch
    thinking off), and each mode uses the model card's sampling for that mode."""
    if thinking not in ("on", "off"):
        sys.exit(f"thinking must be 'on' or 'off', not {thinking!r}")
    extra = json.loads(json.dumps(BACKENDS[backend]["extra"]))
    extra.setdefault("chat_template_kwargs", {})["enable_thinking"] = thinking == "on"
    return (SAMPLING if thinking == "on" else SAMPLING_NO_THINK), extra


def build_body(backend, slot, prompt, max_tokens, thinking="on"):
    cfg = BACKENDS[backend]
    sampling, extra = mode_params(backend, thinking)
    return {"model": cfg["model"], "messages": build_messages(slot, prompt), "max_tokens": max_tokens,
            "stream": False, **sampling, **extra}


def est_input_tokens(body):
    """Deliberately generous: one token per 3 characters (the same rule generate_benchmark uses)."""
    return math.ceil(sum(len(m["content"]) for m in body["messages"]) / 3.0)


# ---------------------------------------------------------------------------------------------
# Run folders, the lock and reading saved rows
# ---------------------------------------------------------------------------------------------
def new_run_dir(backend, label):
    root = outputs_root(backend)
    date = utc_now().strftime("%Y-%m-%d")
    nn = 1
    while True:
        d = root / f"{date}_qwen3-6-27b-{BACKENDS[backend]['label']}_{label}{nn:02d}"
        if not d.exists():
            d.mkdir(parents=True)
            return d
        nn += 1


def existing_main_runs(backend):
    root = outputs_root(backend)
    pattern = f"*_qwen3-6-27b-{BACKENDS[backend]['label']}_test[0-9][0-9]"
    return [d for d in sorted(root.glob(pattern)) if (d / "responses.jsonl").exists()]


def acquire_lock(run_dir, break_lock):
    lock = run_dir / "run.lock"
    if lock.exists():
        if not break_lock:
            sys.exit(f"{run_dir} is locked ({lock.read_text(encoding='utf-8').strip()}).\n"
                     f"Another job may still be writing to it. If you are SURE nothing is running (check squeue), "
                     f"delete {lock} or pass --break-lock. Nothing was sent.")
        print(f"Breaking the old lock: {lock.read_text(encoding='utf-8').strip()}")
        lock.unlink()
    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps({"host": socket.gethostname(), "pid": os.getpid(), "slurm_job": os.environ.get("SLURM_JOB_ID"),
                            "utc": utc_now().isoformat(timespec="seconds")}))
    return lock


class RunFolderError(Exception):
    """The run folder is damaged or inconsistent. Run and score stop on it; validate reports it as an
    INFRASTRUCTURE failure."""


def read_rows(run_dir):
    """All rows of responses.jsonl. Raises RunFolderError with a clear message if the file is damaged (never edits it)."""
    f = Path(run_dir) / "responses.jsonl"
    if not f.exists():
        return []
    raw = f.read_text(encoding="utf-8")
    lines = raw.split("\n")
    rows = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            last = n == len(lines) or (n == len(lines) - 1 and not lines[-1].strip())
            hint = (f" It is the LAST line, probably cut off by an interrupted write. Copy it somewhere safe, remove "
                    f"just that line from the file, and resume." if last else " It is not the last line, so the file "
                    f"needs a careful manual look.")
            raise RunFolderError(f"{f} line {n} is not valid JSON.{hint} Nothing was sent.")
    return rows


def summarize_rows(rows):
    ok, errors = {}, {}
    for r in rows:
        if r.get("http_status") == 200:
            ok.setdefault(r["item_id"], []).append(r)
        else:
            errors[r["item_id"]] = errors.get(r["item_id"], 0) + 1
    return ok, errors


# ---------------------------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------------------------
def choose_slots(args):
    """Return (slots, kind, label). Smoke sets and main slots are never mixed."""
    if args.smoke_cap_check or args.smoke_set:
        first, count = SMOKE_SETS[args.smoke_set or "A"]
        slots = gb.select_slots(count, first)
        if args.smoke_cap_check:
            return slots[:1], "smoke", "capcheck"
        return slots, "smoke", f"smoke{args.smoke_set}"
    slots = gb.select_slots(args.n, args.start)
    nums = [int(s["item_id"][2:]) for s in slots]
    if min(nums) < MAIN_FIRST or max(nums) > MAIN_LAST:
        sys.exit(f"A main run may only contain BM{MAIN_FIRST:04d}-BM{MAIN_LAST:04d}; got {slots[0]['item_id']}-"
                 f"{slots[-1]['item_id']}. Use --smoke-set for development slots.")
    return slots, "main", "test"


def cmd_run(args):
    import httpx

    backend, cfg = args.backend, BACKENDS[args.backend]
    if args.base_url:
        cfg = {**cfg, "base_url": args.base_url}
    prompt, sha = gb.load_prompt()
    if gb.PROMPT_VERSION != "v6":
        sys.exit("This test uses prompt v6 only.")
    slots, kind, label = choose_slots(args)
    thinking = args.thinking
    sampling, extra = mode_params(backend, thinking)
    if thinking == "off":
        label += "-thinkoff"
    max_tokens = 512 if args.smoke_cap_check else args.max_tokens
    if kind == "smoke" and args.resume:
        sys.exit("Smoke runs are not resumed; start a new one.")
    bodies = {s["item_id"]: build_body(backend, s, prompt, max_tokens, thinking) for s in slots}
    longest = max(est_input_tokens(b) for b in bodies.values())

    print(f"Backend {backend}: model {cfg['model']} at {cfg['base_url']}")
    print(f"Precision: {cfg['precision']}")
    print(f"Thinking: {thinking} (chat_template_kwargs {extra.get('chat_template_kwargs')})")
    print(f"Slots: {len(slots)} {[s['item_id'] for s in slots] if kind == 'smoke' else (slots[0]['item_id'] + ' to ' + slots[-1]['item_id'])} "
          f"({kind}), max_tokens {max_tokens}, concurrency {args.concurrency}, sampling {sampling}")
    print(f"Prompt v6 sha256 {sha}; longest prompt about {longest} tokens (generous estimate)")
    if args.dry_run:
        first = bodies[slots[0]["item_id"]]
        print("\n--- First request body exactly as it would be sent (dry run: nothing was sent) ---")
        print(json.dumps({k: v for k, v in first.items() if k != "messages"}, indent=2))
        print("\nSYSTEM:\n" + first["messages"][0]["content"])
        print("\nUSER:\n" + first["messages"][1]["content"])
        return
    headers = {"Content-Type": "application/json"}   # the servers run on the cluster node itself and need no key

    # --- choose the run folder, with the guards that keep a resume from overwriting or repeating anything ---
    if args.resume:
        run_dir = Path(args.resume)
        if not (run_dir / "run_log.json").exists():
            sys.exit(f"{run_dir} has no run_log.json, so it is not a run folder. Nothing was sent.")
    else:
        old = existing_main_runs(backend) if kind == "main" else []
        if old and not args.new_run:
            sys.exit("A main run folder already exists:\n  " + "\n  ".join(str(d) for d in old) +
                     "\nResume it with --resume <folder> (finished slots are skipped), or pass --new-run only if you "
                     "really want a second, separate main run. Nothing was sent.")
        run_dir = new_run_dir(backend, label)
    lock = acquire_lock(run_dir, args.break_lock)

    meta_path = run_dir / "run_log.json"
    new_meta = {
        "use": "dev_test_only", "test": "Qwen3.6-27B deployment test (docs/methodology/workflow.md Section 2.1)",
        "backend": backend, "model": cfg["model"], "precision": cfg["precision"], "weights": cfg["weights"],
        "engine": cfg["engine"], "extra_params": extra, "sampling": sampling, "max_tokens": max_tokens, "thinking": thinking,
        "slot_set": "dev_smoke" if kind == "smoke" else "main", "slot_ids": [s["item_id"] for s in slots],
        "n_slots": len(slots), "prompt_file": str(gb.PROMPT_FILE.relative_to(gb.REPO)),
        "prompt_version": gb.PROMPT_VERSION, "prompt_sha256": sha,
        "adapter_change": "ITEM_SCHEMA JSON appended to the system message after '" + SCHEMA_BLOCK_HEADER + "'; "
                          "no constrained decoding (response_format not sent)",
        "attempts_per_slot": 1,
        "meta": dict(kv.split("=", 1) for kv in args.meta), "sessions": [],
    }
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        bad = [k for k in FINGERPRINT_KEYS if meta.get(k) != new_meta.get(k)]
        if bad:
            lock.unlink()
            sys.exit("This resume does not match the original run, so it was refused. Different: " +
                     ", ".join(f"{k} (was {meta.get(k)!r}, now {new_meta.get(k)!r})" for k in bad))
        meta["meta"].update(new_meta["meta"])
    else:
        meta = new_meta

    try:
        rows = read_rows(run_dir)
    except RunFolderError as e:
        lock.unlink()
        sys.exit(str(e))
    ok_by_id, err_by_id = summarize_rows(rows)
    dup = [i for i, v in ok_by_id.items() if len(v) > 1]
    if dup:
        lock.unlink()
        sys.exit(f"{run_dir} already has more than one saved reply for {dup}. Not continuing; look at the file.")
    todo, skipped_err = [], []
    for s in slots:
        iid = s["item_id"]
        if iid in ok_by_id:
            continue
        if err_by_id.get(iid) and not args.retry_errors:
            skipped_err.append(iid)
            continue
        todo.append(s)
    session = {"started_utc": utc_now().isoformat(timespec="seconds"), "base_url": cfg["base_url"],
               "todo": len(todo), "already_done": len(ok_by_id), "errored_not_retried": skipped_err,
               "retry_errors": args.retry_errors, "concurrency": args.concurrency,
               "host": socket.gethostname(), "slurm_job": os.environ.get("SLURM_JOB_ID")}
    meta["sessions"].append(session)
    atomic_write(meta_path, json.dumps(meta, indent=2))
    print(f"\nOutput folder: {run_dir}")
    print(f"{len(ok_by_id)} slot(s) already have a reply (skipped), {len(skipped_err)} errored earlier and are NOT "
          f"re-sent (use --retry-errors), {len(todo)} to send.")
    print(f"RUN_DIR={run_dir}\n")

    write_lock, stop = threading.Lock(), threading.Event()
    stats = {"calls": 0, "ok": 0, "errors": 0, "out_tokens": 0, "in_tokens": 0}
    client = httpx.Client(timeout=httpx.Timeout(cfg["timeout_s"], connect=30.0))
    t_start = time.time()

    def finish(note=None):
        wall = time.time() - t_start
        session.update({"finished_utc": utc_now().isoformat(timespec="seconds"), "wall_seconds": round(wall, 1),
                        **stats, "aggregate_output_tok_per_s": round(stats["out_tokens"] / max(wall, 1), 2)})
        if note:
            session["ended_by"] = note
        atomic_write(meta_path, json.dumps(meta, indent=2))
        return wall

    def on_term(signum, frame):  # Slurm sends SIGTERM at the time limit: leave a clean, resumable folder
        stop.set()
        with write_lock:
            finish(f"signal {signum}")
            try:
                lock.unlink()
            except OSError:
                pass
        print(f"Received signal {signum}: stopping. Completed replies are saved; resume with --resume {run_dir}")
        os._exit(143)

    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError):
        pass

    def one(slot):
        if stop.is_set():
            return
        iid = slot["item_id"]
        call_id = f"{run_dir.name}/{iid}/{utc_now().strftime('%H%M%S%f')}"
        started, t0 = utc_now().isoformat(timespec="seconds"), time.time()
        row = {"item_id": iid, "use": "dev_test_only", "backend": backend, "attempt": err_by_id.get(iid, 0) + 1,
               "call_id": call_id, "request_started_utc": started}
        try:
            r = client.post(cfg["base_url"].rstrip("/") + "/chat/completions", headers=headers, json=bodies[iid])
            row["http_status"] = r.status_code
            row["seconds"] = round(time.time() - t0, 1)
            try:
                row["response"] = r.json()
            except ValueError:
                row["response"], row["error"] = None, r.text[:2000]
        except Exception as e:  # timeout or lost connection
            row.update({"http_status": None, "seconds": round(time.time() - t0, 1), "response": None,
                        "error": f"{type(e).__name__}: {e}"})
        usage = (row.get("response") or {}).get("usage") or {}
        with write_lock:
            with open(run_dir / "responses.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            stats["calls"] += 1
            stats["in_tokens"] += usage.get("prompt_tokens", 0)
            stats["out_tokens"] += usage.get("completion_tokens", 0)
            ch = ((row.get("response") or {}).get("choices") or [{}])[0]
            if row["http_status"] == 200:
                stats["ok"] += 1
            else:
                stats["errors"] += 1
            print(f"{iid}: HTTP {row['http_status']} finish {ch.get('finish_reason')} in {usage.get('prompt_tokens')} "
                  f"out {usage.get('completion_tokens')} {row['seconds']}s"
                  + (f" ERROR {row['error'][:120]}" if row.get("error") else ""),
                  flush=True)
            if stats["calls"] % 10 == 0:
                el = time.time() - t_start
                print(f"  -- {stats['calls']} calls, {stats['out_tokens']} output tokens in {el:.0f}s "
                      f"= {stats['out_tokens'] / max(el, 1):.1f} tok/s aggregate", flush=True)

    note = None
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(one, s) for s in todo]
            for fu in as_completed(futures):
                fu.result()
    except KeyboardInterrupt:
        stop.set()
        note = "keyboard interrupt"
        print("Interrupted. Completed replies are saved; resume with --resume.")
    finally:
        wall = finish(note)
        try:
            lock.unlink()
        except OSError:
            pass
    print(f"\nDone: {stats['ok']} ok, {stats['errors']} errors. "
          f"Output tokens {stats['out_tokens']} in {wall:.0f}s ({session['aggregate_output_tok_per_s']} tok/s).")
    print(f"Saved in {run_dir}")


# ---------------------------------------------------------------------------------------------
# validate (free, no R: runs on Redhawk right after a smoke test) and score (on the PC, needs R)
# ---------------------------------------------------------------------------------------------
THINK = re.compile(r"<think>.*?</think>", re.S)
FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


def extract_json(content):
    """Return (text_to_parse, strict). strict=True means the content was exactly one JSON object (after removing a
    thinking block, whitespace or a ```json fence). Otherwise the outermost {...} is cut out (lenient)."""
    text = THINK.sub("", content or "").strip()
    m = FENCE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        json.loads(text)
        return text, True
    except ValueError:
        pass
    a, b = text.find("{"), text.rfind("}")
    return (text[a:b + 1], False) if a != -1 and b > a else (text, False)


def reply_parts(rec):
    """(content, reasoning, finish_reason, usage) of one saved row."""
    resp = rec.get("response") or {}
    ch = (resp.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    content = msg.get("content") or ""
    # llama.cpp and older vLLM name the field reasoning_content; newer vLLM versions name it reasoning. Both are
    # accepted so a server upgrade cannot silently make the reasoning disappear from the saved analysis.
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or "".join(THINK.findall(content))
    return content, reasoning, ch.get("finish_reason"), resp.get("usage") or {}


def thinking_evidence(rec):
    """'' if a saved reply shows no sign of thinking; otherwise what was found. Used to CONFIRM that thinking-off
    requests really ran without thinking: a reasoning field, <think> text, or reasoning tokens in the usage."""
    content, reasoning, _, usage = reply_parts(rec)
    found = []
    if reasoning.strip():
        found.append(f"{len(reasoning)} characters of reasoning")
    if "<think>" in (content or ""):
        found.append("<think> text in the content")
    rt = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    if rt:
        found.append(f"{rt} reasoning tokens")
    return "; ".join(found)


FINAL_LINE = re.compile(r"^\W*final\s+answer\W*:\s*(.*?)\s*$", re.I)


def final_answer(content):
    """The answer on the LAST line that starts with "Final answer:" (markdown stars, backticks and $ removed), or None
    when there is no such line. Example: '... so p = 0.2304.\nFinal answer: **0.230**' gives '0.230'."""
    text = THINK.sub("", content or "")
    for line in reversed(text.strip().splitlines()):
        m = FINAL_LINE.match(line)
        if m:
            return m.group(1).strip().strip("*`$ ").strip() or None
    return None


def usable_reply(rec, slot):
    """(item or None, problems) for one saved WRITING reply, with no R. Usable means problems == []: an HTTP-200 reply,
    not cut off, a JSON object, and no problem from gb.check_item. It is the same test `validate` applies."""
    if rec is None:
        return None, ["no saved reply"]
    if rec.get("http_status") != 200:
        return None, [f"no reply (HTTP {rec.get('http_status')})"]
    content, _, finish, _ = reply_parts(rec)
    if finish == "length":
        return None, ["reply cut off at max_tokens"]
    if not content.strip():
        return None, ["content is empty"]
    text, _ = extract_json(content)
    try:
        item = json.loads(text)
    except ValueError:
        return None, ["content is not parseable JSON"]
    if not isinstance(item, dict):
        return None, ["the JSON is not an object"]
    return item, gb.check_item(item, slot, "end_turn", r_keyed=True)


def load_answer_prompt():
    """(sections, sha256) of the answering prompt. Sections start with '=== NAME ==='; '#' lines before the first one are a
    human-only header. The SHA-256 is taken over the text with line endings normalized to LF, so a Windows checkout and the
    cluster copy give the same fingerprint."""
    raw = ANSWER_PROMPT_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    sha = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()
    sections, name = {}, None
    for line in raw.split("\n"):
        m = re.match(r"^=== (.+) ===$", line)
        if m:
            name = m.group(1).strip()
            sections[name] = []
        elif name:
            sections[name].append(line)
    sections = {k: "\n".join(v).strip() for k, v in sections.items()}
    for need in ("SYSTEM", "USER", "FORMAT number", "FORMAT multiple_choice", "FORMAT r_expression", "FORMAT short_text"):
        if need not in sections:
            sys.exit(f"{ANSWER_PROMPT_FILE} has no section '=== {need} ==='")
    return sections, sha


def answer_messages(q, sections):
    choices = ""
    if q.get("choices"):
        choices = "Options:\n" + "\n".join(f"{'ABCD'[i]}. {c}" for i, c in enumerate(q["choices"]))
    user = sections["USER"].format(question=q["question"].strip(), choices=choices,
                                   answer_format=sections["FORMAT " + q["answer_type"]])
    return [{"role": "system", "content": sections["SYSTEM"]}, {"role": "user", "content": user}]


def cmd_validate(args):
    """Check a run folder after any run (smoke stage or main). Needs no R, so it runs on Redhawk right after the
    client finishes. It keeps two kinds of problem strictly apart:

      INFRASTRUCTURE failure = something is wrong with the plumbing, so the run cannot be trusted or used:
        missing or damaged files, invalid metadata or settings that differ from the design, smoke and main slots
        mixed, replies for slots that are not part of the run, a slot with no saved reply (an INCOMPLETE run), a slot
        with more than one reply, rows not marked dev_test_only, or a reply whose envelope is malformed (no choices,
        no finish_reason, no integer token counts).
      MODEL-QUALITY finding = the plumbing worked and the MODEL's reply is poor, which is a RESULT, not a fault:
        content that is empty or not valid JSON, a reply cut off at max_tokens, missing schema fields, fields that
        disagree with the slot, or any hard problem the usual checks find (thinking aloud and so on).
        (Whether the answers are CORRECT is judged later by `score` and `verify` on the PC, where R is installed.)

    Exit code: 0 = no problem of either kind; 1 = at least one infrastructure failure; 2 = infrastructure is fine but
    at least one reply has a model-quality finding. The last lines are machine-readable for serve_and_run.sh."""
    run_dir = Path(args.run)
    infra, quality, notes, per_slot = [], [], [], []
    n_replies = quality_replies = 0

    VALIDATE_COUNTS.clear()

    def conclude():
        nonlocal n_replies, quality_replies
        n_replies = VALIDATE_COUNTS.get("replies", n_replies)            # an answer run reports its counts here
        quality_replies = VALIDATE_COUNTS.get("quality_replies", quality_replies)
        for iid, status in per_slot:
            print(f"  {iid}: {status}")
        for n in notes:
            print("  NOTE", n)
        for f in infra:
            print("  INFRASTRUCTURE FAIL:", f)
        for q in quality:
            print("  MODEL-QUALITY:", q)
        print(f"VALIDATE_INFRA: {'PASS' if not infra else f'FAIL ({len(infra)} problem(s))'}")
        print(f"VALIDATE_QUALITY: {len(quality)} finding(s) in {quality_replies} of {n_replies} repl(ies)")
        print(f"VALIDATE_RESULT infra={'PASS' if not infra else 'FAIL'} quality_replies={quality_replies} replies={n_replies}")
        sys.exit(1 if infra else (2 if quality_replies else 0))

    # ---- infrastructure: the run folder and its metadata ----
    print(f"validate {run_dir.name}")
    try:
        meta = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        infra.append(f"run_log.json is missing or not valid JSON ({e})")
        conclude()
    if meta.get("kind") == "answers":
        validate_answers(run_dir, meta, infra, quality, notes, per_slot, conclude)
    required = ["backend", "model", "slot_set", "slot_ids", "sampling", "max_tokens", "prompt_sha256",
                "attempts_per_slot", "sessions", "use"]
    absent = [k for k in required if k not in meta]
    if absent:
        infra.append(f"run_log.json lacks required field(s): {absent}")
        conclude()
    expected = meta["slot_ids"]
    if not (isinstance(expected, list) and expected and all(isinstance(i, str) and re.fullmatch(r"BM\d{4}", i) for i in expected)):
        infra.append(f"slot_ids in run_log.json is not a list of BM#### ids: {expected!r}")
        conclude()
    if len(set(expected)) != len(expected):
        infra.append("slot_ids in run_log.json contains duplicates")
    nums = [int(i[2:]) for i in expected]
    if meta["slot_set"] == "main":
        if min(nums) < MAIN_FIRST or max(nums) > MAIN_LAST:
            infra.append(f"a main run lists slots outside BM{MAIN_FIRST:04d}-BM{MAIN_LAST:04d}")
    elif meta["slot_set"] == "dev_smoke":
        smoke_ids = {n for first, count in SMOKE_SETS.values() for n in range(first, first + count)}
        if not set(nums) <= smoke_ids:
            infra.append("a smoke run lists slots that are not in a development set (BM9001-BM9004, BM9101-BM9132 or BM8001-BM8060); smoke and main slots must never mix")
    else:
        infra.append(f"slot_set {meta['slot_set']!r} is neither 'main' nor 'dev_smoke'")
    if meta["backend"] not in BACKENDS or meta["model"] != BACKENDS[meta["backend"]]["model"]:
        infra.append(f"backend/model in run_log.json ({meta['backend']!r}, {meta['model']!r}) do not match the design")
        conclude()
    thinking = meta.get("thinking", "on")   # runs from before 2026-11-18 have no field and were all thinking on
    designed_sampling, designed_extra = mode_params(meta["backend"], thinking if thinking in ("on", "off") else "on")
    if thinking not in ("on", "off"):
        infra.append(f"thinking in run_log.json is {thinking!r}, not 'on' or 'off'")
    if meta["sampling"] != designed_sampling:
        infra.append(f"sampling in run_log.json {meta['sampling']} differs from the designed {designed_sampling} (thinking {thinking})")
    if "extra_params" in meta and meta["extra_params"] != designed_extra:
        infra.append(f"extra_params in run_log.json {meta['extra_params']} differ from the designed {designed_extra} (thinking {thinking})")
    if meta["max_tokens"] not in (MAX_TOKENS, 512) or (meta["max_tokens"] == 512 and expected != ["BM9001"]):
        infra.append(f"max_tokens {meta['max_tokens']} is not the designed {MAX_TOKENS} (512 is allowed only for the cap check)")
    if meta["attempts_per_slot"] != 1:
        infra.append("attempts_per_slot is not 1")
    if meta["use"] != "dev_test_only":
        infra.append("run_log.json is not marked dev_test_only")
    _, current_sha = gb.load_prompt()
    if meta["prompt_sha256"] != current_sha:
        infra.append("prompt_sha256 in run_log.json differs from the prompt file in this repository copy")
    if infra:
        conclude()   # without trustworthy metadata the replies cannot be interpreted

    # ---- infrastructure: the saved replies ----
    try:
        slots = slots_for_ids(expected)
    except (KeyError, ValueError) as e:
        infra.append(f"cannot rebuild the slot descriptions ({e!r})")
        conclude()
    if not (run_dir / "responses.jsonl").exists():
        infra.append("responses.jsonl is missing")
        conclude()
    try:
        rows = read_rows(run_dir)
    except RunFolderError as e:
        infra.append(str(e))
        conclude()
    ok_by_id, err_by_id = summarize_rows(rows)
    foreign = sorted({r.get("item_id") for r in rows} - set(expected))
    if foreign:
        infra.append(f"replies saved for slots that are not part of this run: {foreign}")
    if any(r.get("use") != "dev_test_only" for r in rows):
        infra.append("a saved row is not marked dev_test_only")
    models = set()
    reasoning_seen = strict_ok = 0
    for iid in expected:
        got = ok_by_id.get(iid, [])
        if not got:
            infra.append(f"{iid}: INCOMPLETE, no saved HTTP-200 reply" + (f" ({err_by_id[iid]} errored call(s))" if iid in err_by_id else ""))
            per_slot.append((iid, "MISSING"))
            continue
        if len(got) > 1:
            infra.append(f"{iid}: {len(got)} saved replies (a slot must have exactly one)")
        rec = got[0]
        resp = rec.get("response")
        choices = resp.get("choices") if isinstance(resp, dict) else None
        usage = (resp or {}).get("usage") if isinstance(resp, dict) else None
        if not (isinstance(choices, list) and choices and isinstance(choices[0], dict) and isinstance(choices[0].get("message"), dict)):
            infra.append(f"{iid}: the saved reply has no choices[0].message")
            per_slot.append((iid, "MALFORMED REPLY"))
            continue
        if not choices[0].get("finish_reason"):
            infra.append(f"{iid}: the saved reply has no finish_reason")
        if not (isinstance(usage, dict) and isinstance(usage.get("prompt_tokens"), int) and isinstance(usage.get("completion_tokens"), int)):
            infra.append(f"{iid}: the saved reply has no integer token counts")
        n_replies += 1
        models.add(resp.get("model"))
        content, reasoning, finish, _ = reply_parts(rec)
        if reasoning.strip():
            reasoning_seen += 1
        if thinking == "off" and thinking_evidence(rec):
            infra.append(f"{iid}: thinking was requested OFF but the reply shows thinking ({thinking_evidence(rec)})")
        # ---- model quality: what the model produced ----
        found = []
        if finish == "length":
            found.append("reply cut off at max_tokens")
        if not content.strip():
            found.append("content is empty" + (" (the whole budget went to reasoning)" if finish == "length" else ""))
        text, strict = extract_json(content)
        item = None
        try:
            item = json.loads(text)
            strict_ok += strict
        except ValueError:
            if content.strip():
                found.append(f"content is not parseable JSON (starts {content[:80]!r})")
        if isinstance(item, dict):
            for p in gb.check_item(item, slots[iid], "max_tokens" if finish == "length" else "end_turn", r_keyed=True):
                if p != "cut off at max_tokens":
                    found.append(p)
        elif item is not None:
            found.append("the JSON is not an object")
        if found:
            quality_replies += 1
            quality.extend(f"{iid}: {f}" for f in found)
        per_slot.append((iid, "OK" if not found else "QUALITY FINDING(S)"))
    if thinking == "off" and n_replies:
        notes.append(f"thinking off confirmed from the records: {n_replies - reasoning_seen} of {n_replies} repl(ies) have no "
                     f"reasoning field, no <think> text and no reasoning tokens" if reasoning_seen == 0 else
                     f"thinking off NOT confirmed: {reasoning_seen} repl(ies) carry reasoning")
    elif reasoning_seen == 0 and n_replies:
        notes.append("no reply carried a separate reasoning field or <think> block, so reasoning could not be separated "
                     "(check --reasoning-format / separate_reasoning); content-only scoring still works")
    print(f"  {len(expected)} expected slot(s), {len(ok_by_id)} with a reply, {strict_ok} strictly valid JSON, "
          f"{reasoning_seen} with separate reasoning; model field(s) seen: {sorted(m for m in models if m)}")
    conclude()


# ---------------------------------------------------------------------------------------------
# The thinking on/off check (docs/methodology/workflow.md Section 2.1): answer-set, answer, and the answer-run checks
# ---------------------------------------------------------------------------------------------
def k_positions():
    """The fixed plan of the shared answer set: position -> (origin mode, primary slot, reserve slot).
    Positions 1-20 come from the thinking-ON writing run, 21-40 from the thinking-OFF run; each half is a 20-slot block,
    so it has the benchmark's exact category and difficulty mix. A failed primary question is replaced by the reserve
    slot at the same pattern position (same category and difficulty), written in the SAME origin mode."""
    first = SMOKE_SETS["K"][0]
    plan = []
    for pos in range(1, K_PRIMARY + 1):
        origin = "on" if pos <= K_HALF else "off"
        primary = f"BM{first + pos - 1:04d}"
        reserve = f"BM{first + K_PRIMARY + (pos - 1) % K_HALF:04d}"
        plan.append((pos, origin, primary, reserve))
    return plan


def writing_run(path, want_mode):
    """(meta, {item_id: first HTTP-200 row or the last row}) of a thinking-check WRITING run, after checking that it is one."""
    run_dir = Path(path)
    meta = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
    first, count = SMOKE_SETS["K"]
    if meta.get("slot_ids") != [f"BM{n:04d}" for n in range(first, first + count)]:
        sys.exit(f"{run_dir} is not a thinking-check writing run (it must hold BM{first:04d}-BM{first + count - 1:04d}).")
    if meta.get("thinking", "on") != want_mode:
        sys.exit(f"{run_dir} was written with thinking {meta.get('thinking', 'on')!r}, but it was given as the thinking-{want_mode} run.")
    rows = {}
    for r in read_rows(run_dir):
        if r["item_id"] not in rows or (r.get("http_status") == 200 and rows[r["item_id"]].get("http_status") != 200):
            rows[r["item_id"]] = r
    return meta, rows


def cmd_answer_set(args):
    """Build the FIXED shared question set for the thinking check from the two writing runs (no R needed, so it runs on
    Talon). Every slot's outcome is recorded; nothing is dropped silently."""
    runs = {}
    for mode in ("on", "off"):
        try:
            runs[mode] = writing_run(getattr(args, mode), mode)
        except RunFolderError as e:
            sys.exit(str(e))
    backend = runs["on"][0]["backend"]
    first, count = SMOKE_SETS["K"]
    slots = slots_for_ids([f"BM{n:04d}" for n in range(first, first + count)])
    usable = {}   # (mode, item_id) -> (item, problems)
    for mode, (_, rows) in runs.items():
        for iid, slot in slots.items():
            usable[(mode, iid)] = usable_reply(rows.get(iid), slot)
    questions, composition = [], {"positions": [], "replacements": [], "unfilled": [], "by_origin_and_category": {},
                                  "writing_outcomes": {}}
    for pos, origin, primary, reserve in k_positions():
        chosen, replaced = None, False
        for iid in (primary, reserve):
            item, problems = usable[(origin, iid)]
            if item is not None and not problems:
                chosen, replaced = iid, iid != primary
                break
        rec = {"position": pos, "origin": origin, "primary_slot": primary, "reserve_slot": reserve,
               "used_slot": chosen, "replacement": replaced}
        composition["positions"].append(rec)
        if chosen is None:
            composition["unfilled"].append(rec)
            continue
        if replaced:
            composition["replacements"].append(rec)
        item = usable[(origin, chosen)][0]
        slot = slots[chosen]
        questions.append({"qid": f"Q{pos:02d}", "position": pos, "origin": origin, "item_id": chosen,
                          "replacement": replaced, "category": slot["category"], "subtopic": slot["subtopic"],
                          "difficulty": slot["difficulty"], "answer_type": slot["answer_type"],
                          "question": item["question"], "choices": item.get("choices") or []})
        key = f"{origin} | {slot['category']}"
        composition["by_origin_and_category"][key] = composition["by_origin_and_category"].get(key, 0) + 1
    for mode in ("on", "off"):
        composition["writing_outcomes"][mode] = [
            {"item_id": iid, "block": "primary" if int(iid[2:]) < first + K_PRIMARY else "reserve",
             "category": slots[iid]["category"], "usable": usable[(mode, iid)][0] is not None and not usable[(mode, iid)][1],
             "problems": usable[(mode, iid)][1]} for iid in slots]
    out = new_run_dir(backend, "answersetK")
    text = "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions)
    atomic_write(out / "answer_set.jsonl", text)
    composition.update({"source_runs": {m: str(Path(getattr(args, m)).resolve()) for m in ("on", "off")},
                        "answer_set_sha256": __import__("hashlib").sha256(text.encode("utf-8")).hexdigest(),
                        "n_questions": len(questions), "built_utc": utc_now().isoformat(timespec="seconds")})
    atomic_write(out / "composition.json", json.dumps(composition, indent=2, ensure_ascii=False))
    print(f"Shared answer set: {len(questions)} of {K_PRIMARY} positions filled; {len(composition['replacements'])} "
          f"replacement(s) from the reserve; {len(composition['unfilled'])} unfilled")
    for k, v in sorted(composition["by_origin_and_category"].items()):
        print(f"  {k}: {v}")
    for r in composition["replacements"]:
        print(f"  REPLACED position {r['position']} ({r['origin']}): {r['primary_slot']} failed, used {r['reserve_slot']}")
    for r in composition["unfilled"]:
        print(f"  UNFILLED position {r['position']} ({r['origin']}): {r['primary_slot']} and {r['reserve_slot']} both failed")
    print(f"ANSWER_SET={out / 'answer_set.jsonl'}")


ANSWER_FINGERPRINT = ["kind", "backend", "model", "extra_params", "sampling", "max_tokens", "thinking", "samples",
                      "answer_set_sha256", "question_ids", "answer_prompt_sha256"]


def cmd_answer(args):
    """Have the teacher ANSWER every question of a fixed answer set, `--samples` times each, in one thinking mode.
    Same safety rules as `run`: append-only replies, a lock, and a resume that must match the original settings."""
    import httpx

    backend, cfg = args.backend, BACKENDS[args.backend]
    if args.base_url:
        cfg = {**cfg, "base_url": args.base_url}
    sampling, extra = mode_params(backend, args.thinking)
    sections, prompt_sha = load_answer_prompt()
    set_path = Path(args.set)
    set_text = set_path.read_text(encoding="utf-8")
    questions = [json.loads(line) for line in set_text.splitlines() if line.strip()]
    if not questions:
        sys.exit(f"{set_path} holds no questions.")
    jobs = [(q, n) for q in questions for n in range(1, args.samples + 1)]
    bodies = {f"{q['qid']}-s{n}": {"model": cfg["model"], "messages": answer_messages(q, sections),
                                   "max_tokens": args.max_tokens, "stream": False, **sampling, **extra} for q, n in jobs}
    print(f"Answering {len(questions)} question(s) x {args.samples} sample(s) = {len(jobs)} call(s); thinking {args.thinking}; "
          f"sampling {sampling}; answer prompt sha256 {prompt_sha}")
    if args.dry_run:
        first = bodies[f"{questions[0]['qid']}-s1"]
        print(json.dumps({k: v for k, v in first.items() if k != "messages"}, indent=2))
        print("\nSYSTEM:\n" + first["messages"][0]["content"] + "\n\nUSER:\n" + first["messages"][1]["content"])
        return
    run_dir = Path(args.resume) if args.resume else new_run_dir(backend, "answersK" + ("-thinkoff" if args.thinking == "off" else ""))
    lock = acquire_lock(run_dir, args.break_lock)
    meta_path = run_dir / "run_log.json"
    new_meta = {"kind": "answers", "use": "dev_test_only", "test": "thinking on/off check (docs/methodology/workflow.md Section 2.1)",
                "backend": backend, "model": cfg["model"], "precision": cfg["precision"], "engine": cfg["engine"],
                "extra_params": extra, "sampling": sampling, "max_tokens": args.max_tokens, "thinking": args.thinking,
                "samples": args.samples, "answer_set": str(set_path.resolve()),
                "answer_set_sha256": __import__("hashlib").sha256(set_text.encode("utf-8")).hexdigest(),
                "question_ids": [q["qid"] for q in questions],
                "answer_prompt_file": str(ANSWER_PROMPT_FILE.relative_to(gb.REPO)), "answer_prompt_sha256": prompt_sha,
                "meta": dict(kv.split("=", 1) for kv in args.meta), "sessions": []}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        bad = [k for k in ANSWER_FINGERPRINT if meta.get(k) != new_meta.get(k)]
        if bad:
            lock.unlink()
            sys.exit("This resume does not match the original run, so it was refused. Different: " + ", ".join(bad))
        meta["meta"].update(new_meta["meta"])
    else:
        meta = new_meta
    try:
        done = {r["answer_id"] for r in read_rows(run_dir) if r.get("http_status") == 200}
    except RunFolderError as e:
        lock.unlink()
        sys.exit(str(e))
    todo = [(q, n) for q, n in jobs if f"{q['qid']}-s{n}" not in done]
    session = {"started_utc": utc_now().isoformat(timespec="seconds"), "base_url": cfg["base_url"], "todo": len(todo),
               "already_done": len(done), "concurrency": args.concurrency, "host": socket.gethostname(),
               "slurm_job": os.environ.get("SLURM_JOB_ID")}
    meta["sessions"].append(session)
    atomic_write(meta_path, json.dumps(meta, indent=2))
    print(f"Output folder: {run_dir}\n{len(done)} answer(s) already saved, {len(todo)} to send.\nRUN_DIR={run_dir}\n")
    write_lock = threading.Lock()
    stats = {"calls": 0, "ok": 0, "errors": 0, "out_tokens": 0, "in_tokens": 0}
    client = httpx.Client(timeout=httpx.Timeout(cfg["timeout_s"], connect=30.0))
    t_start = time.time()

    def one(job):
        q, n = job
        aid = f"{q['qid']}-s{n}"
        t0 = time.time()
        row = {"answer_id": aid, "qid": q["qid"], "item_id": q["item_id"], "sample": n, "use": "dev_test_only",
               "backend": backend, "request_started_utc": utc_now().isoformat(timespec="seconds")}
        try:
            r = client.post(cfg["base_url"].rstrip("/") + "/chat/completions", json=bodies[aid])
            row["http_status"], row["seconds"] = r.status_code, round(time.time() - t0, 1)
            try:
                row["response"] = r.json()
            except ValueError:
                row["response"], row["error"] = None, r.text[:2000]
        except Exception as e:  # timeout or lost connection
            row.update({"http_status": None, "seconds": round(time.time() - t0, 1), "response": None,
                        "error": f"{type(e).__name__}: {e}"})
        usage = (row.get("response") or {}).get("usage") or {}
        with write_lock:
            with open(run_dir / "responses.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            stats["calls"] += 1
            stats["ok" if row["http_status"] == 200 else "errors"] += 1
            stats["in_tokens"] += usage.get("prompt_tokens", 0)
            stats["out_tokens"] += usage.get("completion_tokens", 0)
            print(f"{aid}: HTTP {row['http_status']} out {usage.get('completion_tokens')} {row['seconds']}s", flush=True)

    note = None
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for fu in as_completed([pool.submit(one, j) for j in todo]):
                fu.result()
    except KeyboardInterrupt:
        note = "keyboard interrupt"
    finally:
        wall = time.time() - t_start
        session.update({"finished_utc": utc_now().isoformat(timespec="seconds"), "wall_seconds": round(wall, 1), **stats,
                        "aggregate_output_tok_per_s": round(stats["out_tokens"] / max(wall, 1), 2)})
        if note:
            session["ended_by"] = note
        atomic_write(meta_path, json.dumps(meta, indent=2))
        try:
            lock.unlink()
        except OSError:
            pass
    print(f"\nDone: {stats['ok']} ok, {stats['errors']} errors in {wall:.0f}s. Saved in {run_dir}")


def validate_answers(run_dir, meta, infra, quality, notes, per_slot, conclude):
    """`validate` for an ANSWER run: every (question, sample) has exactly one saved reply; the settings match the design;
    a thinking-off run shows no thinking anywhere (INFRASTRUCTURE if it does: the mode did not work); a reply that is cut
    off or has no "Final answer:" line is a MODEL-QUALITY finding."""
    for k in ("backend", "model", "sampling", "extra_params", "thinking", "samples", "question_ids", "answer_prompt_sha256", "sessions"):
        if k not in meta:
            infra.append(f"run_log.json lacks {k}")
    if infra:
        conclude()
    if meta["backend"] not in BACKENDS or meta["model"] != BACKENDS[meta["backend"]]["model"]:
        infra.append("backend/model in run_log.json do not match the design")
        conclude()
    sampling, extra = mode_params(meta["backend"], meta["thinking"])
    if meta["sampling"] != sampling or meta["extra_params"] != extra:
        infra.append(f"sampling or extra_params differ from the designed thinking-{meta['thinking']} settings")
    if meta["answer_prompt_sha256"] != load_answer_prompt()[1]:
        infra.append("answer_prompt_sha256 differs from the answering prompt in this repository copy")
    if meta.get("use") != "dev_test_only":
        infra.append("run_log.json is not marked dev_test_only")
    try:
        rows = read_rows(run_dir)
    except RunFolderError as e:
        infra.append(str(e))
        conclude()
    expected = [f"{q}-s{n}" for q in meta["question_ids"] for n in range(1, meta["samples"] + 1)]
    ok = {}
    for r in rows:
        if r.get("http_status") == 200:
            ok.setdefault(r.get("answer_id"), []).append(r)
    foreign = sorted(set(ok) - set(expected))
    if foreign:
        infra.append(f"replies saved for answers that are not part of this run: {foreign[:5]}")
    n_replies = n_quality = thinking_seen = 0
    for aid in expected:
        got = ok.get(aid, [])
        if not got:
            infra.append(f"{aid}: INCOMPLETE, no saved HTTP-200 reply")
            per_slot.append((aid, "MISSING"))
            continue
        if len(got) > 1:
            infra.append(f"{aid}: {len(got)} saved replies (exactly one expected)")
        rec = got[0]
        n_replies += 1
        ev = thinking_evidence(rec)
        if ev:
            thinking_seen += 1
            if meta["thinking"] == "off":
                infra.append(f"{aid}: thinking was requested OFF but the reply shows thinking ({ev})")
        content, _, finish, _ = reply_parts(rec)
        found = []
        if finish == "length":
            found.append("reply cut off at max_tokens")
        if final_answer(content) is None:
            found.append("no 'Final answer:' line")
        if found:
            n_quality += 1
            quality.extend(f"{aid}: {f}" for f in found)
        per_slot.append((aid, "OK" if not found else "QUALITY FINDING(S)"))
    if meta["thinking"] == "off":
        notes.append(f"thinking off {'confirmed' if not thinking_seen else 'NOT confirmed'}: {thinking_seen} of {n_replies} "
                     f"repl(ies) show a reasoning field, <think> text or reasoning tokens")
    print(f"  {len(expected)} expected answer(s), {n_replies} with a reply; thinking {meta['thinking']}")
    # conclude() prints and exits; the counters it reads are passed through these two module-level slots
    VALIDATE_COUNTS.update(replies=n_replies, quality_replies=n_quality)
    conclude()


VALIDATE_COUNTS = {}


def cmd_score(args):
    run_dir = Path(args.run)
    meta = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
    rscript = gb.rscript_path()
    try:
        rows_all = read_rows(run_dir)
    except RunFolderError as e:
        sys.exit(str(e))
    ok_by_id, err_by_id = summarize_rows(rows_all)
    dup = [i for i, v in ok_by_id.items() if len(v) > 1]
    if dup and not args.allow_duplicates:
        sys.exit(f"More than one saved reply for {dup}: a slot must have exactly one (one attempt per slot). "
                 f"Resolve it, or pass --allow-duplicates to score the FIRST reply of each.")
    rows = {}
    for iid in meta["slot_ids"]:
        if iid in ok_by_id:
            rows[iid] = ok_by_id[iid][0]
        elif iid in err_by_id:
            last = [r for r in rows_all if r["item_id"] == iid][-1]
            rows[iid] = last
    slots = slots_for_ids(list(rows))
    items = []
    for iid, rec in sorted(rows.items()):
        slot = slots[iid]
        content, reasoning, finish, usage = reply_parts(rec)
        base = {**slot, "use": "dev_test_only", "backend": meta["backend"], "attempts": rec.get("attempt", 1),
                "finish_reason": finish, "http_status": rec.get("http_status"),
                "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                "reasoning_chars": len(reasoning), "content_chars": len(content), "seconds": rec.get("seconds"),
                "cost_usd": rec.get("cost_usd", 0.0)}
        if rec.get("http_status") != 200:
            items.append({**base, "format_valid": False, "json_strict": False,
                          "problems": [f"no reply (HTTP {rec.get('http_status')}): {str(rec.get('error', ''))[:200]}"],
                          "soft_flags": [], "final_status": "failed"})
            continue
        text, strict = extract_json(content)
        stop_reason = "max_tokens" if finish == "length" else "end_turn"
        shim = SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])
        item, hard, soft = gb.process_reply(shim, slot, rscript)  # the same checks and R-key step as every generated question
        fmt_ok = item is not None and stop_reason != "max_tokens" and not any(
            p.startswith(("missing field", "reply is not valid JSON", "cut off")) or "differs from the slot" in p
            for p in hard)
        items.append({**base, **(item or {}), "format_valid": fmt_ok, "json_strict": strict and item is not None,
                      "problems": hard, "soft_flags": soft, "final_status": "ok" if not hard else "failed"})
    out = run_dir / "items.jsonl"
    atomic_write(out, "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items))
    review = gb.REPO / "results" / "open_teacher_test"
    review.mkdir(parents=True, exist_ok=True)
    (review / f"{run_dir.name}_items.jsonl").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    (review / f"{run_dir.name}_log.json").write_text((run_dir / "run_log.json").read_text(encoding="utf-8"),
                                                     encoding="utf-8")
    n = len(items)
    ok = sum(i["final_status"] == "ok" for i in items)
    fmt = sum(i["format_valid"] for i in items)
    strict = sum(i["json_strict"] for i in items)
    cut = sum(i["finish_reason"] == "length" for i in items)
    outs = sorted(i["output_tokens"] or 0 for i in items)
    cost = sum(i["cost_usd"] or 0 for i in items)
    print(f"{n} slots scored ({run_dir.name})")
    print(f"  format valid {fmt}/{n} (strict JSON with nothing around it: {strict}); cut off at max_tokens {cut}")
    print(f"  passed every automatic check on the first attempt {ok}/{n}")
    print(f"  output tokens per item: median {outs[n // 2] if n else 0}, mean {sum(outs) / max(n, 1):.0f}, max {outs[-1] if n else 0}")
    print(f"  cost ${cost:.4f} (${cost / max(ok, 1):.4f} per usable item)")
    for i in items:
        if i["problems"] or i["soft_flags"]:
            print(f"  {i['item_id']} [{i['category']}]" + ("  HARD: " + "; ".join(i["problems"]) if i["problems"] else "")
                  + ("  SOFT: " + "; ".join(i["soft_flags"]) if i["soft_flags"] else ""))
    print(f"Wrote {out} and a copy in {review}. Next: generate_benchmark.py verify --items {out}")


# ---------------------------------------------------------------------------------------------
# compare (paired statistics on the same slots)
# ---------------------------------------------------------------------------------------------
def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value: binomial test of b successes in b+c trials at p = 0.5."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load_items(path):
    return {r["item_id"]: r for r in (json.loads(l) for l in open(path, encoding="utf-8") if l.strip())}


def outcomes(items, hand):
    """Per slot: format, checks, correct. `hand` holds hand-check verdicts {item_id: True/False} (multiple choice,
    and any R item a person judged). Correct needs: passed the checks, R agreed with the typed key (no soft flag
    saying they differ) and no hand verdict of False; for items R cannot check, a hand verdict of True is required."""
    res = {}
    for iid, it in items.items():
        fmt = bool(it.get("format_valid"))
        checks = it.get("final_status") == "ok"
        verdict = hand.get(iid)
        if not checks:
            correct = False
        elif it.get("answer_type") == "number":
            correct = not any("differs from R" in s for s in it.get("soft_flags") or []) and verdict is not False
        else:
            v = it.get("verify_status")
            correct = verdict is True or (verdict is None and v == "ok")
        res[iid] = {"format": fmt, "checks": checks, "correct": correct}
    return res


def cmd_compare(args):
    a, b = load_items(args.a), load_items(args.b)
    ha = load_items(args.hand_a) if args.hand_a else {}
    hb = load_items(args.hand_b) if args.hand_b else {}
    ha = {k: v.get("correct") for k, v in ha.items()}
    hb = {k: v.get("correct") for k, v in hb.items()}
    oa, ob = outcomes(a, ha), outcomes(b, hb)
    ids = sorted(set(oa) & set(ob))
    rng = random.Random(20261104)
    print(f"Paired slots: {len(ids)}  (A = {Path(args.a).name}, B = {Path(args.b).name})")
    for metric in ("correct", "checks", "format"):
        xa = [oa[i][metric] for i in ids]
        xb = [ob[i][metric] for i in ids]
        n = len(ids)
        ka, kb = sum(xa), sum(xb)
        both = sum(p and q for p, q in zip(xa, xb))
        only_a = [i for i, p, q in zip(ids, xa, xb) if p and not q]
        only_b = [i for i, p, q in zip(ids, xa, xb) if q and not p]
        diffs = []
        for _ in range(10000):
            s = [rng.randrange(n) for _ in range(n)]
            diffs.append((sum(xa[j] for j in s) - sum(xb[j] for j in s)) / n)
        diffs.sort()
        lo, hi = diffs[249], diffs[9749]
        wa, wb = wilson(ka, n), wilson(kb, n)
        print(f"\n[{metric}] A {ka}/{n} ({ka / n:.0%}, 95% CI {wa[0]:.0%}-{wa[1]:.0%})   "
              f"B {kb}/{n} ({kb / n:.0%}, 95% CI {wb[0]:.0%}-{wb[1]:.0%})")
        print(f"  both {both}, only A {len(only_a)}, only B {len(only_b)}, neither {n - both - len(only_a) - len(only_b)}")
        print(f"  A minus B = {(ka - kb) / n:+.1%}, bootstrap 95% CI {lo:+.1%} to {hi:+.1%}; "
              f"exact McNemar p = {mcnemar_exact(len(only_a), len(only_b)):.3f} (descriptive)")
        print(f"  only A: {', '.join(only_a) or '-'}")
        print(f"  only B: {', '.join(only_b) or '-'}")
    if args.ref:
        ref = load_items(args.ref)
        k = sum(1 for i in ids if i in ref and ref[i].get("final_status") == "ok" and ref[i].get("attempts") == 1)
        print(f"\nReference ({Path(args.ref).name}): passed every automatic check on the first attempt in {k}/{len(ids)} "
              f"of these slots (descriptive only; a reference produced with a different setup is not a paired comparison).")


def main():
    global OUT_ROOT_OVERRIDE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-root", default=None, help="override the output folder from paths.yaml (used by tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="send the slots to a backend (both run on Miami's clusters and are free)")
    p.add_argument("--backend", required=True, choices=list(BACKENDS))
    p.add_argument("--base-url", default=None, help="override the backend URL (Redhawk jobs pick a free port)")
    p.add_argument("--n", type=int, default=N_SLOTS)
    p.add_argument("--start", type=int, default=START)
    p.add_argument("--smoke-set", choices=list(SMOKE_SETS), default=None,
                   help="send a development set (A = BM9001-2, B = BM9003-4, T = BM9101-9132 throughput, "
                        "K = BM8001-8060 thinking check) instead of the main slots")
    p.add_argument("--smoke-cap-check", action="store_true", help="one call (BM9001) with max_tokens 512")
    p.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--thinking", choices=["on", "off"], default="on",
                   help="thinking mode (default on); off uses the model card's non-thinking sampling")
    p.add_argument("--resume", default=None, help="an existing run folder to continue (skips finished slots)")
    p.add_argument("--new-run", action="store_true", help="allow a second, separate main run folder")
    p.add_argument("--retry-errors", action="store_true", help="re-send slots whose earlier call errored (attempt 2, 3, ...)")
    p.add_argument("--break-lock", action="store_true", help="remove a stale run.lock (only if no job is running)")
    p.add_argument("--meta", action="append", default=[], help="KEY=VALUE recorded in run_log.json (engine commit etc.)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("answer-set", help="thinking check: build the fixed shared question set from the two writing runs (no R)")
    p.add_argument("--on", required=True, help="the thinking-ON writing run folder (set K)")
    p.add_argument("--off", required=True, help="the thinking-OFF writing run folder (set K)")
    p.set_defaults(fn=cmd_answer_set)
    p = sub.add_parser("answer", help="thinking check: the teacher answers every question of an answer set, N times each")
    p.add_argument("--backend", required=True, choices=list(BACKENDS))
    p.add_argument("--base-url", default=None)
    p.add_argument("--set", required=True, help="answer_set.jsonl written by answer-set")
    p.add_argument("--samples", type=int, default=3)
    p.add_argument("--thinking", choices=["on", "off"], required=True)
    p.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--resume", default=None)
    p.add_argument("--break-lock", action="store_true")
    p.add_argument("--meta", action="append", default=[])
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_answer)
    p = sub.add_parser("validate", help="check saved replies are complete, tied to their slots and parseable (free; no R)")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("score", help="parse and check a run's replies (free; needs R)")
    p.add_argument("--run", required=True)
    p.add_argument("--allow-duplicates", action="store_true")
    p.set_defaults(fn=cmd_score)
    p = sub.add_parser("compare", help="paired statistics for two scored runs on the same slots")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--hand-a", default=None, help="jsonl of {item_id, correct, note} hand verdicts for A")
    p.add_argument("--hand-b", default=None)
    p.add_argument("--ref", default=None, help="another items file on the same slots (reference only, not tested)")
    p.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    OUT_ROOT_OVERRIDE = args.out_root
    if args.cmd in ("run", "answer") and args.concurrency < 1:
        sys.exit("--concurrency must be at least 1")
    args.fn(args)


if __name__ == "__main__":
    main()
