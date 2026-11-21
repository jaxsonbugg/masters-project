"""
generate_set.py - the full-size generator: turn a frozen slot file into teacher replies (on Talon), check them, and
collect them into the benchmark, development, held-out and training sets (on the PC).

WHAT THIS IS AND WHY
open_teacher_test.py was built to test a deployment on 100 fixed slots: one attempt per slot, everything marked as
test material, one job at a time. The real data need more: about 1,400 benchmark-style questions and up to about
260,000 training generations, written by 4 GPUs at once over several 1-day jobs, with failed replies asked again and
nothing lost or repeated. This script does that. It reuses the client's tested parts unchanged (the request settings
for thinking mode, the lock, append-and-fsync saving, reply parsing) and the prompts and checks of set_prompts.py.
docs/methodology/workflow.md (Section 4, safeguards 2, 4 and 5; Phase 4) is the plan this implements.

THE STEPS (plain language)
  run       (Talon) Send every slot of one SHARD (a quarter of the slot file: slots 1, 5, 9, ... for shard 1 of 4)
            to the teacher. A reply that fails the format checks is asked again, with exactly the same request (no
            hints), up to 3 attempts in all; every attempt is saved. Resuming is automatic: the job finds its own
            folder by name and continues where it stopped, and refuses if any setting changed.
  validate  (Talon, free) Separate INFRASTRUCTURE failures (damaged files, wrong settings, foreign or out-of-order rows)
            from MODEL-QUALITY findings (a reply that failed the checks) and from an UNFINISHED run (a job that reached
            its time limit; the next job resumes it).
  collect   (PC) One row per slot: the first usable reply, or "failed" after 3 attempts. For benchmark-style sets with
            --r-keys, R (in the sandbox) writes the key of every number question, as for v6.
  fill-bench (PC) The benchmark, development set or smoke set: each failed primary slot is replaced by the next unused
            spare with the same category, difficulty and answer type. If no spare is left it says which slots need
            new spares (variety.py replace).
  collect-train (PC) The training stream: each position (TR000001, TR000002, ...) gets its first ACCEPTED example
            (usable, at most 2,048 Pythia tokens, not removed by decontamination), else its like-for-like replacements
            (TRR...) in order, else it is UNFILLED after 5 replacements. The published sets are exactly the first
            1,000, 10,000, ... accepted examples, written as compact files apart from the raw replies, with a balance
            report and tolerance checks. A set that was published once can never change (checked on every run).

WHERE THINGS GO
  raw replies   <outputs root>/<date>_qwen3-6-27b-talon-bf16_<set>_<prompt>_<selection>_shard<k>of<K>/  (never edited)
                responses.jsonl (append-only, one row per attempt, thinking text included), done_index.jsonl (a small
                index so a resume starts at once), run_log.json (settings and sessions).
  compact sets  <training_data>/<version>/train_<N>.jsonl + manifest.json  (the only files training reads)

EXAMPLES
  python generate_set.py run --backend talon --slots data/slots/smoke_slots.jsonl --prompt benchmark --first 1 --count 20 --dry-run
  python generate_set.py run --backend talon --slots <large>/slots/train_slots.jsonl --prompt training --shard 2/4
  python generate_set.py validate --run <folder>
  python generate_set.py collect --runs <folder> [<folder> ...] --out items.jsonl [--r-keys]
  python generate_set.py fill-bench --items items.jsonl --manifest data/slots/benchmark_slots.manifest.json --primary 1000 --out bm.jsonl
  python generate_set.py collect-train --items items.jsonl --manifest <large>/slots/train_slots.manifest.json \
         --decontam <rejections.jsonl> --version 2026-12-01_train-v1 --sizes 1000,10000
"""

import argparse
import hashlib
import json
import os
import re
import signal
import socket
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_benchmark as gb  # noqa: E402
import open_teacher_test as ott  # noqa: E402  (client parts reused unchanged)
import set_prompts as sp  # noqa: E402
import variety  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GENERATOR_VERSION = "generate_set-2"      # 2 (2026-11-20): prompt versions in run names; plain-text and printout checks
MAX_ATTEMPTS = 3                 # per slot, re-asked without hints (approved plan, Step 5)
MAX_REPLACEMENTS = 5             # per training position (Step 6)
HTTP_RETRIES = 3                 # transport errors per slot per session before it is left for the next session
CIRCUIT_BREAKER = 25             # this many failed calls in a row = the server is down: stop the session
SET_USE = {"benchmark": "benchmark", "dev": "development", "tv": "heldout_training_style", "train": "training",
           "smoke": "dev_test_only"}
SET_PROMPTS = {"benchmark": ("benchmark",), "dev": ("benchmark",), "tv": ("training",), "train": ("training",),
               "smoke": ("benchmark", "training")}
SET_IDS = {"benchmark": ("BM",), "dev": ("DV",), "tv": ("TV",), "train": ("TR", "TRR"), "smoke": ("SM",)}
FINGERPRINT = ["kind", "set", "use", "prompt_kind", "prompt_version", "prompt_sha256", "selection_sha256", "slot_ids",
               "slots_file", "slots_file_sha256", "taxonomy_sha256", "contexts_sha256", "slot_scheme", "shard",
               "backend", "model", "precision", "weights", "extra_params", "sampling", "max_tokens", "thinking",
               "max_attempts", "generator_version"]
# Sizes of the nested training sets (approved plan; every smaller set is exactly the start of every larger one).
DEFAULT_SIZES = (1000, 10000, 50000, 100000, 200000)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------------------------
# Slot sources: a frozen slot file (or its replacements file) and its manifest
# ---------------------------------------------------------------------------------------------
def load_source(slots_path):
    """(slots, manifest, file_sha256) for a slot file or a replacements file, after checking it against its manifest.
    Refuses a file whose bytes no longer match the manifest (a slot file is frozen once dealt)."""
    slots_path = Path(slots_path)
    m = re.fullmatch(r"(benchmark|dev|tv|train|smoke)_(slots|replacements)\.jsonl", slots_path.name)
    if not m:
        sys.exit(f"{slots_path.name}: expected <set>_slots.jsonl or <set>_replacements.jsonl from variety.py")
    man_path = slots_path.parent / f"{m.group(1)}_slots.manifest.json"
    if not man_path.exists():
        sys.exit(f"{man_path} is missing; a slot file is only used together with its manifest.")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    file_sha = variety.sha256_file(slots_path)
    want = man["slots_sha256"] if m.group(2) == "slots" else man.get("replacements_sha256")
    if file_sha != want:
        sys.exit(f"{slots_path} does not match its manifest (sha256 {file_sha[:12]}..., manifest {str(want)[:12]}...). "
                 f"Slot files are frozen; nothing was sent.")
    slots = variety.read_slots(slots_path)
    for s in slots:
        if s.get("slot_scheme") != variety.SLOT_SCHEME or sp.id_kind(s["item_id"]) not in SET_IDS[man["set"]]:
            sys.exit(f"{s.get('item_id')}: not a {variety.SLOT_SCHEME} slot of set {man['set']}")
    return slots, man, file_sha


def select(slots, first, count, shard):
    """The slots of one run: positions first..first+count-1 of the file (1-based), then every K-th of those for shard
    k/K (k = 1..K). Interleaving keeps each shard's category and difficulty mix the same as the whole file's."""
    part = slots[first - 1: first - 1 + count] if count else slots[first - 1:]
    k, K = shard
    return [s for i, s in enumerate(part) if i % K == k - 1]


def parse_shard(text):
    m = re.fullmatch(r"(\d+)/(\d+)", text or "1/1")
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        sys.exit(f"--shard must look like 2/4, not {text!r}")
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------------------------
# Checking one saved reply (the same test in run, validate and collect)
# ---------------------------------------------------------------------------------------------
def parse_reply(rec):
    """(item or None, finish_reason, problems) of one saved row, with no R and no tokenizer."""
    if rec.get("http_status") != 200:
        return None, None, [f"no reply (HTTP {rec.get('http_status')})"]
    content, _, finish, _ = ott.reply_parts(rec)
    if not content.strip():
        return None, finish, ["content is empty" + (" (cut off while thinking)" if finish == "length" else "")]
    text, _ = ott.extract_json(content)
    try:
        item = json.loads(text)
    except ValueError:
        return None, finish, ["content is not parseable JSON"] + (["cut off at max_tokens"] if finish == "length" else [])
    if not isinstance(item, dict):
        return None, finish, ["the JSON is not an object"]
    return item, finish, None


def check_reply(rec, slot, prompt_kind, version):
    """(item, problems) for a saved row; problems == [] means usable. `version` is the prompt version the reply was
    written with (for example benchmark-v8): each version is checked exactly as designed."""
    item, finish, problems = parse_reply(rec)
    if problems is not None:
        return item, problems
    if prompt_kind == "benchmark":
        return item, sp.check_benchmark_item(item, slot, finish, version=version)
    return item, sp.check_training_item(item, slot, finish, version=version)


# ---------------------------------------------------------------------------------------------
# Run folders and the done-index
# ---------------------------------------------------------------------------------------------
def run_name(man_set, prompt_version, selection_sha, shard):
    """For example smoke_benchmark-v8_bfa35577_shard1of1. (Runs before 2026-11-20 carry only the kind, smoke_benchmark_...)"""
    return f"{man_set}_{prompt_version}_{selection_sha[:8]}_shard{shard[0]}of{shard[1]}"


def find_run_dir(backend, name):
    """The existing folder of this exact run (any date), or None. Two folders for one run is an error."""
    root = ott.outputs_root(backend)
    hits = sorted(d for d in root.glob(f"*_qwen3-6-27b-{ott.BACKENDS[backend]['label']}_{name}") if d.is_dir())
    if len(hits) > 1:
        sys.exit(f"more than one folder for the run {name}: {[str(h) for h in hits]}. Look at them; nothing was sent.")
    return hits[0] if hits else None


def count_lines(path):
    if not Path(path).exists():
        return 0
    n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            n += chunk.count(b"\n")
    return n


def rebuild_index(run_dir, slots_by_id, prompt_kind, version):
    """Rebuild done_index.jsonl from responses.jsonl (slow; only after a crash between the two writes)."""
    rows = []
    for n, rec in enumerate(ott.read_rows(run_dir), 1):
        slot = slots_by_id.get(rec.get("item_id"))
        usable = None
        if rec.get("http_status") == 200 and slot is not None:
            usable = not check_reply(rec, slot, prompt_kind, version)[1]
        rows.append({"item_id": rec.get("item_id"), "attempt": rec.get("attempt"), "http_status": rec.get("http_status"),
                     "usable": usable, "line": n})
    ott.atomic_write(run_dir / "done_index.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
    return rows


def load_index(run_dir, slots_by_id, prompt_kind, version):
    """The done-index, rebuilt if it disagrees with responses.jsonl (a crash between the two appends)."""
    idx_path, resp_path = run_dir / "done_index.jsonl", run_dir / "responses.jsonl"
    n_resp = count_lines(resp_path)
    if n_resp == 0 and not idx_path.exists():
        return [], False                    # a brand-new run: nothing to rebuild
    if idx_path.exists():
        rows = [json.loads(l) for l in idx_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(rows) == n_resp:
            return rows, False
    return rebuild_index(run_dir, slots_by_id, prompt_kind, version), True


def slot_states(index_rows):
    """{item_id: {"attempts": HTTP-200 replies, "usable": bool, "errors": transport errors}} from the index."""
    st = defaultdict(lambda: {"attempts": 0, "usable": False, "errors": 0})
    for r in index_rows:
        s = st[r["item_id"]]
        if r["http_status"] == 200:
            s["attempts"] += 1
            s["usable"] = s["usable"] or bool(r["usable"])
        else:
            s["errors"] += 1
    return st


# ---------------------------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------------------------
def cmd_run(args):
    backend = args.backend
    cfg = dict(ott.BACKENDS[backend])
    if args.base_url:
        cfg["base_url"] = args.base_url
    if args.out_root:
        ott.OUT_ROOT_OVERRIDE = args.out_root
    slots_all, man, file_sha = load_source(args.slots)
    if args.prompt not in SET_PROMPTS[man["set"]]:
        sys.exit(f"the {args.prompt} prompt is not used for the {man['set']} set (allowed: {SET_PROMPTS[man['set']]})")
    shard = parse_shard(args.shard)
    slots = select(slots_all, args.first, args.count, shard)
    if not slots:
        sys.exit("the selection is empty")
    prompt, prompt_sha, prompt_version = sp.load_prompt(args.prompt)
    for s in slots:
        if sp.id_kind(s["item_id"]) not in sp.PROMPTS[args.prompt][2]:
            sys.exit(f"{s['item_id']}: the {args.prompt} prompt may not be used for this id")
    slots_by_id = {s["item_id"]: s for s in slots}
    selection_sha = sha256_text("".join(canonical(s) + "\n" for s in slots))
    sampling, extra = ott.mode_params(backend, "on")
    max_tokens = args.max_tokens

    def body(slot):
        return {"model": cfg["model"], "messages": sp.build_messages(slot, prompt, args.prompt), "max_tokens": max_tokens,
                "stream": False, **sampling, **extra}

    print(f"Backend {backend}: model {cfg['model']} at {cfg['base_url']} ({cfg['precision']})")
    print(f"Set {man['set']} ({SET_USE[man['set']]}), prompt {prompt_version} sha256 {prompt_sha[:12]}..., slot file "
          f"{Path(args.slots).name} sha256 {file_sha[:12]}..., shard {shard[0]}/{shard[1]}: {len(slots)} slots "
          f"({slots[0]['item_id']} ... {slots[-1]['item_id']})")
    print(f"Thinking on, sampling {sampling}, max_tokens {max_tokens}, up to {MAX_ATTEMPTS} attempts per slot, "
          f"concurrency {args.concurrency}")
    if args.dry_run:
        b = body(slots[0])
        print("\n--- First request body exactly as it would be sent (dry run: nothing was sent) ---")
        print(json.dumps({k: v for k, v in b.items() if k != "messages"}, indent=2))
        print("\nSYSTEM:\n" + b["messages"][0]["content"] + "\n\nUSER:\n" + b["messages"][1]["content"])
        return 0

    name = run_name(man["set"], prompt_version, selection_sha, shard)
    run_dir = find_run_dir(backend, name)
    if run_dir is None:
        root = ott.outputs_root(backend)
        run_dir = root / f"{ott.utc_now().strftime('%Y-%m-%d')}_qwen3-6-27b-{cfg['label']}_{name}"
        run_dir.mkdir(parents=True)
    lock = ott.acquire_lock(run_dir, args.break_lock)
    meta_path = run_dir / "run_log.json"
    new_meta = {
        "kind": "generate", "set": man["set"], "use": SET_USE[man["set"]], "prompt_kind": args.prompt,
        "prompt_version": prompt_version, "prompt_file": str(sp.PROMPTS[args.prompt][0].relative_to(gb.REPO).as_posix()),
        "prompt_sha256": prompt_sha, "selection": {"first": args.first, "count": args.count},
        "selection_sha256": selection_sha, "slot_ids": [s["item_id"] for s in slots], "n_slots": len(slots),
        "slots_file": Path(args.slots).name, "slots_file_sha256": file_sha, "taxonomy_sha256": man["taxonomy_sha256"],
        "contexts_sha256": man["contexts_sha256"], "slot_scheme": variety.SLOT_SCHEME, "shard": list(shard),
        "backend": backend, "model": cfg["model"], "precision": cfg["precision"], "weights": cfg["weights"],
        "engine": cfg["engine"], "extra_params": extra, "sampling": sampling, "max_tokens": max_tokens, "thinking": "on",
        "max_attempts": MAX_ATTEMPTS, "generator_version": GENERATOR_VERSION,
        "adapter_change": "output schema JSON appended to the system message after '" + sp.SCHEMA_BLOCK_HEADER + "'",
        "meta": dict(kv.split("=", 1) for kv in args.meta), "sessions": [],
    }

    def refuse(msg):
        lock.unlink()
        sys.exit(msg)

    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        bad = [k for k in FINGERPRINT if meta.get(k) != new_meta.get(k)]
        old_engine, new_engine = (meta.get("meta") or {}).get("engine_version"), new_meta["meta"].get("engine_version")
        if old_engine and new_engine and old_engine != new_engine:
            bad.append("meta.engine_version")
        if bad:
            refuse("This resume does not match the original run, so it was refused (nothing was sent). Different: " +
                   ", ".join(f"{k} (was {meta.get(k)!r}, now {new_meta.get(k)!r})" if not k.startswith("meta.")
                             else f"{k} (was {old_engine!r}, now {new_engine!r})" for k in bad))
        meta["meta"].update(new_meta["meta"])
    else:
        meta = new_meta
    try:
        index_rows, rebuilt = load_index(run_dir, slots_by_id, args.prompt, prompt_version)
    except ott.RunFolderError as e:
        refuse(str(e))
    states = slot_states(index_rows)
    foreign = sorted(set(states) - set(slots_by_id))
    if foreign:
        refuse(f"{run_dir} has rows for slots outside this run: {foreign[:5]}. Nothing was sent.")
    todo = [s for s in slots if not states[s["item_id"]]["usable"] and states[s["item_id"]]["attempts"] < MAX_ATTEMPTS]
    if args.limit:
        todo = todo[: args.limit]
    session = {"started_utc": ott.utc_now().isoformat(timespec="seconds"), "base_url": cfg["base_url"],
               "todo": len(todo), "index_rebuilt": rebuilt, "concurrency": args.concurrency,
               "host": socket.gethostname(), "slurm_job": os.environ.get("SLURM_JOB_ID")}
    meta["sessions"].append(session)
    ott.atomic_write(meta_path, json.dumps(meta, indent=2))
    n_done = sum(1 for s in slots if states[s["item_id"]]["usable"])
    n_failed = sum(1 for s in slots if not states[s["item_id"]]["usable"] and states[s["item_id"]]["attempts"] >= MAX_ATTEMPTS)
    print(f"\nOutput folder: {run_dir}\n{n_done} slot(s) already usable, {n_failed} failed all {MAX_ATTEMPTS} attempts, "
          f"{len(todo)} to work on" + (" (done-index rebuilt)" if rebuilt else ""))
    print(f"RUN_DIR={run_dir}\n", flush=True)

    import httpx
    write_lock, stop = threading.Lock(), threading.Event()
    stats = {"calls": 0, "ok": 0, "errors": 0, "usable": 0, "unusable": 0, "out_tokens": 0, "in_tokens": 0,
             "consecutive_errors": 0}
    client = httpx.Client(timeout=httpx.Timeout(cfg["timeout_s"], connect=30.0))
    t0_all = time.time()
    line_no = [count_lines(run_dir / "responses.jsonl")]

    def finish(note=None):
        wall = time.time() - t0_all
        session.update({"finished_utc": ott.utc_now().isoformat(timespec="seconds"), "wall_seconds": round(wall, 1),
                        **{k: v for k, v in stats.items() if k != "consecutive_errors"},
                        "aggregate_output_tok_per_s": round(stats["out_tokens"] / max(wall, 1), 2)})
        if note:
            session["ended_by"] = note
        ott.atomic_write(meta_path, json.dumps(meta, indent=2))
        return wall

    def on_term(signum, frame):   # Slurm sends SIGTERM at the time limit: leave a clean, resumable folder
        stop.set()
        with write_lock:
            finish(f"signal {signum}")
            try:
                lock.unlink()
            except OSError:
                pass
        print(f"Received signal {signum}: stopping. Saved replies are kept; the next job resumes {run_dir}", flush=True)
        os._exit(143)

    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError):
        pass

    # The job's own deadline (stage G passes it): at --stop-after seconds no NEW request starts; requests already running
    # may finish for --grace seconds more; after that the session is saved, the lock released and the process ends (exit
    # 143), abandoning any call still running (it is simply asked again by the next job). Works on Linux and Windows alike.
    def hard_stop():
        with write_lock:
            finish("deadline: calls still running after the grace period were abandoned")
            try:
                lock.unlink()
            except OSError:
                pass
        print(f"Deadline plus grace reached: stopping. Saved replies are kept; the next job resumes {run_dir}", flush=True)
        os._exit(143)

    if args.stop_after > 0:
        for t in (threading.Timer(args.stop_after, stop.set), threading.Timer(args.stop_after + args.grace, hard_stop)):
            t.daemon = True
            t.start()

    def save(row, usable):
        with write_lock:
            with open(run_dir / "responses.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            line_no[0] += 1
            with open(run_dir / "done_index.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"item_id": row["item_id"], "attempt": row["attempt"], "http_status": row["http_status"],
                                    "usable": usable, "line": line_no[0]}) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def work(slot):
        iid = slot["item_id"]
        st = states[iid]
        errors_now = 0
        req = body(slot)
        while not stop.is_set() and not st["usable"] and st["attempts"] < MAX_ATTEMPTS:
            started, t0 = ott.utc_now().isoformat(timespec="seconds"), time.time()
            row = {"item_id": iid, "set": man["set"], "use": SET_USE[man["set"]], "slot_scheme": variety.SLOT_SCHEME,
                   "slots_file_sha256": file_sha, "prompt_version": prompt_version, "slot": slot,
                   "attempt": st["attempts"] + 1, "call_id": f"{run_dir.name}/{iid}/{ott.utc_now().strftime('%H%M%S%f')}",
                   "request_started_utc": started}
            try:
                r = client.post(cfg["base_url"].rstrip("/") + "/chat/completions", json=req)
                row["http_status"] = r.status_code
                try:
                    row["response"] = r.json()
                except ValueError:
                    row["response"], row["error"] = None, r.text[:2000]
            except Exception as e:   # timeout or lost connection
                row.update({"http_status": None, "response": None, "error": f"{type(e).__name__}: {e}"})
            row["seconds"] = round(time.time() - t0, 1)
            usable, problems = None, []
            if row["http_status"] == 200:
                _, problems = check_reply(row, slot, args.prompt, prompt_version)
                usable = not problems
                row["problems"] = problems
            else:
                row["attempt"] = None          # a transport error is not an attempt by the model
            save(row, usable)
            usage = (row.get("response") or {}).get("usage") or {}
            with write_lock:
                stats["calls"] += 1
                stats["in_tokens"] += usage.get("prompt_tokens", 0) or 0
                stats["out_tokens"] += usage.get("completion_tokens", 0) or 0
                if row["http_status"] == 200:
                    stats["ok"] += 1
                    stats["consecutive_errors"] = 0
                    stats["usable" if usable else "unusable"] += 1
                else:
                    stats["errors"] += 1
                    stats["consecutive_errors"] += 1
                    if stats["consecutive_errors"] >= CIRCUIT_BREAKER:
                        stop.set()
                print(f"{iid}: attempt {row['attempt']} HTTP {row['http_status']} "
                      f"{'usable' if usable else ('UNUSABLE: ' + '; '.join(problems)[:140] if usable is False else row.get('error', '')[:140])} "
                      f"out {usage.get('completion_tokens')} {row['seconds']}s", flush=True)
                if stats["calls"] % 50 == 0:
                    el = time.time() - t0_all
                    print(f"  -- {stats['calls']} calls, {stats['usable']} usable, {stats['out_tokens']} output tokens in "
                          f"{el:.0f}s = {stats['out_tokens'] / max(el, 1):.1f} tok/s", flush=True)
            if row["http_status"] == 200:
                st["attempts"] += 1
                st["usable"] = bool(usable)
            else:
                st["errors"] += 1
                errors_now += 1
                if errors_now >= HTTP_RETRIES:
                    return
                time.sleep(args.retry_wait)

    note = None
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for fu in as_completed([pool.submit(work, s) for s in todo]):
                fu.result()
    except KeyboardInterrupt:
        stop.set()
        note = "keyboard interrupt"
    finally:
        if stop.is_set() and note is None and stats["consecutive_errors"] >= CIRCUIT_BREAKER:
            note = f"circuit breaker: {CIRCUIT_BREAKER} failed calls in a row (server unreachable?)"
        elif stop.is_set() and note is None:
            note = "deadline: no new requests after --stop-after; running calls finished"
        wall = finish(note)
        try:
            lock.unlink()
        except OSError:
            pass
    usable_now = sum(1 for s in slots if states[s["item_id"]]["usable"])
    failed_now = sum(1 for s in slots if not states[s["item_id"]]["usable"] and states[s["item_id"]]["attempts"] >= MAX_ATTEMPTS)
    print(f"\nSession done in {wall:.0f}s: {stats['calls']} calls ({stats['errors']} transport errors), "
          f"{stats['out_tokens']} output tokens. Run so far: {usable_now} usable, {failed_now} failed, "
          f"{len(slots) - usable_now - failed_now} unfinished of {len(slots)}.")
    if note and note.startswith("circuit breaker"):
        print("GENERATE_STOP: " + note)
        return 4
    return 0


# ---------------------------------------------------------------------------------------------
# validate (free, no R, no tokenizer)
# ---------------------------------------------------------------------------------------------
def validate_run(run_dir, slots_path=None):
    """(report dict). Separates infrastructure failures, model-quality findings and an unfinished run."""
    run_dir = Path(run_dir)
    infra, quality, notes = [], [], []
    rep = {"infra": infra, "quality": quality, "notes": notes, "usable": 0, "failed": 0, "unfinished": 0, "replies": 0,
           "quality_replies": 0, "slots": 0}
    try:
        meta = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        infra.append(f"run_log.json is missing or not valid JSON ({e})")
        return rep
    absent = [k for k in FINGERPRINT + ["sessions"] if k not in meta]
    if absent or meta.get("kind") != "generate":
        infra.append(f"run_log.json is not a generate run log (missing {absent})")
        return rep
    ids = meta["slot_ids"]
    rep["slots"] = len(ids)
    kinds = {sp.id_kind(i) for i in ids}
    if None in kinds or not kinds <= set(SET_IDS.get(meta["set"], ())):
        infra.append(f"slot_ids contain ids that do not belong to set {meta['set']!r}")
    if meta.get("prompt_version") not in sp.PROMPT_FILES:
        infra.append(f"prompt_version {meta.get('prompt_version')!r} is not a known prompt version")
        return rep
    if not kinds <= set(sp.PROMPT_FILES[meta["prompt_version"]][2]):
        infra.append(f"the {meta['prompt_kind']} prompt was used for ids it may not be used for")
    if len(set(ids)) != len(ids):
        infra.append("slot_ids contains duplicates")
    if meta["use"] != SET_USE.get(meta["set"]):
        infra.append(f"use {meta['use']!r} does not match set {meta['set']!r}")
    if meta["backend"] not in ott.BACKENDS or meta["model"] != ott.BACKENDS[meta["backend"]]["model"]:
        infra.append("backend/model do not match the design")
        return rep
    designed_sampling, designed_extra = ott.mode_params(meta["backend"], "on")
    if meta["thinking"] != "on" or meta["sampling"] != designed_sampling or meta["extra_params"] != designed_extra:
        infra.append("thinking, sampling or extra_params differ from the design (thinking on, model-card sampling)")
    if meta["max_tokens"] != ott.MAX_TOKENS:
        infra.append(f"max_tokens {meta['max_tokens']} is not the designed {ott.MAX_TOKENS}")
    if meta["max_attempts"] != MAX_ATTEMPTS:
        infra.append(f"max_attempts {meta['max_attempts']} is not {MAX_ATTEMPTS}")
    _, cur_sha, cur_version = sp.load_prompt(meta["prompt_version"])
    if (meta["prompt_sha256"], meta["prompt_version"]) != (cur_sha, cur_version):
        infra.append("prompt_sha256 differs from the prompt file in this repository copy")
    slots_by_id = None
    if slots_path:
        slots, _, file_sha = load_source(slots_path)
        if file_sha != meta["slots_file_sha256"]:
            infra.append("the given slot file is not the one this run used")
        sel = select(slots, meta["selection"]["first"], meta["selection"]["count"], tuple(meta["shard"]))
        if sha256_text("".join(canonical(s) + "\n" for s in sel)) != meta["selection_sha256"]:
            infra.append("the slot selection rebuilt from the slot file differs from the run's selection_sha256")
        slots_by_id = {s["item_id"]: s for s in sel}
    if infra:
        return rep
    try:
        rows = ott.read_rows(run_dir)
    except ott.RunFolderError as e:
        infra.append(str(e))
        return rep
    n_index = count_lines(run_dir / "done_index.jsonl")
    if n_index != len(rows):
        notes.append(f"done_index.jsonl has {n_index} rows for {len(rows)} saved replies (rebuilt automatically on resume)")
    per = defaultdict(list)
    for n, r in enumerate(rows, 1):
        per[r.get("item_id")].append((n, r))
    foreign = sorted(set(per) - set(ids), key=str)
    if foreign:
        infra.append(f"rows for slots that are not part of this run: {foreign[:5]}")
    for iid in ids:
        rs = per.get(iid, [])
        slot = None
        attempts = usable = 0
        for n, r in rs:
            if not isinstance(r.get("slot"), dict):
                infra.append(f"{iid} line {n}: the row carries no slot")
                continue
            for k, want in (("use", meta["use"]), ("set", meta["set"]), ("slot_scheme", variety.SLOT_SCHEME),
                            ("slots_file_sha256", meta["slots_file_sha256"]), ("prompt_version", meta["prompt_version"])):
                if r.get(k) != want:
                    infra.append(f"{iid} line {n}: {k} is {r.get(k)!r}, expected {want!r}")
            slot = r.get("slot")
            if slots_by_id is not None and slot != slots_by_id[iid]:
                infra.append(f"{iid} line {n}: the saved slot differs from the slot file")
            if r.get("http_status") != 200:
                continue
            if usable:
                infra.append(f"{iid} line {n}: an attempt after a usable reply (the slot was asked again)")
            attempts += 1
            if r.get("attempt") != attempts:
                infra.append(f"{iid} line {n}: attempt number {r.get('attempt')} out of order (expected {attempts})")
            resp = r.get("response") if isinstance(r.get("response"), dict) else {}
            ch = resp.get("choices")
            if not (isinstance(ch, list) and ch and isinstance(ch[0], dict) and isinstance(ch[0].get("message"), dict)
                    and ch[0].get("finish_reason")):
                infra.append(f"{iid} line {n}: the saved reply has no choices[0].message or finish_reason")
                continue
            u = resp.get("usage") or {}
            if not (isinstance(u.get("prompt_tokens"), int) and isinstance(u.get("completion_tokens"), int)):
                infra.append(f"{iid} line {n}: the saved reply has no integer token counts")
            rep["replies"] += 1
            _, problems = check_reply(r, slot, meta["prompt_kind"], meta["prompt_version"])
            if problems:
                rep["quality_replies"] += 1
                quality.append(f"{iid} attempt {attempts}: " + "; ".join(problems))
            else:
                usable += 1
        if attempts > MAX_ATTEMPTS:
            infra.append(f"{iid}: {attempts} attempts (at most {MAX_ATTEMPTS})")
        if usable:
            rep["usable"] += 1
        elif attempts >= MAX_ATTEMPTS:
            rep["failed"] += 1
        else:
            rep["unfinished"] += 1
    return rep


def cmd_validate(args):
    rep = validate_run(args.run, args.slots)
    for n in rep["notes"]:
        print("  NOTE", n)
    for f in rep["infra"][:200]:
        print("  INFRASTRUCTURE FAIL:", f)
    for q in rep["quality"][: args.show]:
        print("  MODEL-QUALITY:", q)
    if len(rep["quality"]) > args.show:
        print(f"  ... {len(rep['quality']) - args.show} more model-quality finding(s)")
    print(f"  {rep['slots']} slot(s): {rep['usable']} usable, {rep['failed']} failed all {MAX_ATTEMPTS} attempts, "
          f"{rep['unfinished']} unfinished; {rep['replies']} repl(ies), {rep['quality_replies']} with findings")
    infra_ok = not rep["infra"]
    print("VALIDATE_INFRA: " + ("PASS" if infra_ok else "FAIL (%d problem(s))" % len(rep["infra"])))
    print(f"VALIDATE_COMPLETE: {'yes' if rep['unfinished'] == 0 else 'no'}")
    print(f"VALIDATE_RESULT infra={'PASS' if infra_ok else 'FAIL'} usable={rep['usable']} failed={rep['failed']} "
          f"unfinished={rep['unfinished']} replies={rep['replies']} quality_replies={rep['quality_replies']}")
    # 0 complete and clean; 1 infrastructure failure; 2 complete, some replies had findings; 3 unfinished (resume it)
    sys.exit(1 if not infra_ok else (3 if rep["unfinished"] else (2 if rep["quality_replies"] else 0)))


# ---------------------------------------------------------------------------------------------
# collect (PC): one row per slot from one or more run folders
# ---------------------------------------------------------------------------------------------
def collect_rows(run_dirs, rscript=None):
    """[row] per slot over all given runs. A row: item_id, slot, status (usable | failed | unfinished | r_failed),
    the chosen reply's item and where it is (run folder, line), the attempts, and every fingerprint.
    `rscript` (the R sandbox) turns on the R key step for benchmark-style number items."""
    out, prompt_kind, set_name = {}, None, None
    for d in run_dirs:
        d = Path(d)
        rep = validate_run(d)
        if rep["infra"]:
            sys.exit(f"{d.name}: infrastructure failure, not collected: {rep['infra'][:3]}")
        meta = json.loads((d / "run_log.json").read_text(encoding="utf-8"))
        if prompt_kind not in (None, meta["prompt_kind"]) or set_name not in (None, meta["set"]):
            sys.exit("all collected runs must share one set and one prompt")
        prompt_kind, set_name = meta["prompt_kind"], meta["set"]
        rows = ott.read_rows(d)
        per = defaultdict(list)
        for n, r in enumerate(rows, 1):
            per[r["item_id"]].append((n, r))
        for iid in meta["slot_ids"]:
            if iid in out:
                sys.exit(f"{iid} appears in two collected runs")
            attempts, chosen, last_problems, slot = 0, None, [], None
            for n, r in per.get(iid, []):
                slot = r["slot"]
                if r.get("http_status") != 200:
                    continue
                attempts += 1
                item, problems = check_reply(r, slot, prompt_kind, meta["prompt_version"])
                if not problems:
                    chosen = (n, item, r)
                    break
                last_problems = problems
            row = {"item_id": iid, "set": set_name, "prompt_kind": prompt_kind, "prompt_version": meta["prompt_version"],
                   "prompt_sha256": meta["prompt_sha256"], "slot_scheme": variety.SLOT_SCHEME,
                   "slots_file": meta["slots_file"], "slots_file_sha256": meta["slots_file_sha256"],
                   "slot": slot, "attempts": attempts, "run": d.name}
            if chosen:
                n, item, r = chosen
                row.update(status="usable", item=item, line=n, finish_reason=ott.reply_parts(r)[2],
                           completion_tokens=((r.get("response") or {}).get("usage") or {}).get("completion_tokens"))
                if rscript is not None and prompt_kind == "benchmark":
                    msg = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(item))])
                    keyed, hard, soft = gb.process_reply(msg, slot, rscript)
                    row["item"], row["soft_flags"] = keyed, soft
                    if hard:
                        row.update(status="r_failed", problems=hard)
            else:
                row.update(status="failed" if attempts >= MAX_ATTEMPTS else "unfinished", problems=last_problems)
            out[iid] = row
    return list(out.values())


def verify_rows(rows, rscript):
    """Run generate_benchmark.verify_item (R in the sandbox) on every usable benchmark-style row: a number key is
    recomputed by R, and an R check must accept the key and reject deliberately wrong answers. A row whose check is
    broken or vacuous becomes status "verify_flagged" (with the issues), so fill-bench replaces it with a spare like any
    other failed slot (added 2026-11-21). Rows that R cannot check (multiple choice, plain short text) keep status
    "usable" and are marked "not_machine_checkable": the Codex screen and the audit cover them."""
    for r in rows:
        if r["status"] != "usable" or r["prompt_kind"] != "benchmark":
            continue
        status, issues, r_value = gb.verify_item(r["item"], rscript)
        r["verify_status"], r["verify_issues"] = status, issues
        if status == "FLAGGED":
            r["status"], r["problems"] = "verify_flagged", issues
    return rows


def apply_repairs(rows, decisions, rscript):
    """Owner-reviewed decisions for verify-flagged questions (added 2026-11-21). Each decision is
      {"item_id", "action": "repair_check" | "replace", "new_r_check", "reason"}.
    repair_check: the question and its key are right and only the R check is broken (wrong object names, the random seed
      not reset, a hard-coded wrong value). The check is replaced (the original is kept as r_check_original) and verify is
      run again in the R sandbox; the question becomes usable ONLY if the repaired check now accepts the key and rejects
      the wrong answers. The key itself is never changed here.
    replace: the key or the question is doubtful; the slot stays failed and fill-bench gives its position to a spare.
    Returns a report {"repaired", "repair_failed", "replace", "undecided"}."""
    by_id = {r["item_id"]: r for r in rows}
    rep = {"repaired": [], "repair_failed": [], "replace": [], "undecided": []}
    decided = set()
    for d in decisions:
        r = by_id.get(d["item_id"])
        if r is None or r["status"] != "verify_flagged":
            sys.exit(f"{d['item_id']}: a decision for a slot that is not verify-flagged ({r and r['status']}); nothing applied")
        decided.add(d["item_id"])
        r["decision"] = {"action": d["action"], "reason": d["reason"]}
        if d["action"] == "replace":
            rep["replace"].append(d["item_id"])
            continue
        item = r["item"]
        item["r_check_original"], item["r_check"] = item["r_check"], d["new_r_check"]
        status, issues, _ = gb.verify_item(item, rscript)
        r["verify_status"], r["verify_issues"] = status, issues
        if status == "FLAGGED":
            rep["repair_failed"].append((d["item_id"], issues))
        else:
            r["status"], r["problems"] = "usable", []
            r["repaired"] = True
            rep["repaired"].append(d["item_id"])
    rep["undecided"] = sorted(r["item_id"] for r in rows if r["status"] == "verify_flagged" and r["item_id"] not in decided)
    return rep


def cmd_apply_repairs(args):
    rows = [json.loads(l) for l in Path(args.items).read_text(encoding="utf-8").splitlines() if l.strip()]
    decisions = [d for d in json.loads(Path(args.decisions).read_text(encoding="utf-8"))
                 if d["item_id"] in {r["item_id"] for r in rows}]
    rep = apply_repairs(rows, decisions, gb.rscript_path())
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"repaired {len(rep['repaired'])}, repair FAILED {len(rep['repair_failed'])}, replace {len(rep['replace'])}, "
          f"undecided {len(rep['undecided'])} -> {args.out}")
    for iid, issues in rep["repair_failed"]:
        print(f"  REPAIR FAILED {iid}: {'; '.join(issues)}")
    if rep["undecided"]:
        print("  undecided (still flagged, will be replaced unless decided):", ", ".join(rep["undecided"]))
    print("statuses:", dict(Counter(r["status"] for r in rows)))
    sys.exit(1 if rep["repair_failed"] else 0)


def cmd_collect(args):
    rscript = gb.rscript_path() if args.r_keys else None    # the R sandbox, after its self-test (fails closed)
    rows = collect_rows(args.runs, rscript)
    if rscript is not None:
        verify_rows(rows, rscript)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    c = Counter(r["status"] for r in rows)
    print(f"{len(rows)} slot(s): {dict(c)} -> {args.out} (sha256 {sha256_text(text)[:12]}...)")


# ---------------------------------------------------------------------------------------------
# fill-bench (PC): benchmark, development and smoke sets, failed primaries replaced by spares
# ---------------------------------------------------------------------------------------------
def require_fingerprint(row, manifest):
    """A benchmark-style item must carry the slot file's fingerprint, so a new BM id can never be confused with an
    archived Claude-era or deployment-test BM id (approved plan, Step 3)."""
    if row.get("slot_scheme") != variety.SLOT_SCHEME or not row.get("slots_file_sha256"):
        sys.exit(f"{row.get('item_id')}: no slot-file fingerprint; refused (old-scheme ids are never used here)")
    if row["slots_file_sha256"] not in [manifest["slots_sha256"]] + manifest.get("replacements_sha256_history", []):
        sys.exit(f"{row['item_id']}: its slot-file fingerprint does not belong to this manifest; refused")


def excluded_spares(manifest_path):
    """Spares permanently excluded from the benchmark: those later used for Codex calibration answers
    (<set>_excluded_spares.json beside the slot manifest: {"ids": [...], "reason": ...}). Never used as replacements."""
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    f = Path(manifest_path).parent / f"{m['set']}_excluded_spares.json"
    return set(json.loads(f.read_text(encoding="utf-8"))["ids"]) if f.exists() else set()


def fill_bench(rows, manifest, primary, excluded=()):
    """(positions, needs): position k (1..primary) gets primary slot k if usable, else the next unused usable spare with
    the same category, difficulty and answer type (spares are the slots after the primary block and any replacements
    dealt later, taken in id order). `needs` lists the primary slots with no matching spare left. Spares in `excluded`
    (permanently excluded, for example Codex calibration spares) are never used, and a primary slot in it is refused."""
    for r in rows:
        require_fingerprint(r, manifest)
    by_id = {r["item_id"]: r for r in rows}
    prefix, width = variety.SETS[manifest["set"]]
    ids = [f"{prefix}{k:0{width}d}" for k in range(1, primary + 1)]
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit(f"primary slots not collected yet: {missing[:5]} ... ({len(missing)})")
    bad = sorted(set(ids) & set(excluded))
    if bad:
        sys.exit(f"primary slots {bad[:5]} are in the permanently excluded list; refused")
    spares = sorted((r for r in rows if r["item_id"] not in set(ids) and r["item_id"] not in set(excluded)),
                    key=lambda r: r["item_id"])
    used, positions, needs = set(), [], []
    for k, iid in enumerate(ids, 1):
        r = by_id[iid]
        if r["status"] == "usable":
            positions.append({"position": k, **r, "replaces": None})
            continue
        key = (r["slot"]["category"], r["slot"]["difficulty"], r["slot"]["answer_type"])
        pick = next((s for s in spares if s["item_id"] not in used and s["status"] == "usable" and
                     (s["slot"]["category"], s["slot"]["difficulty"], s["slot"]["answer_type"]) == key), None)
        if pick is None:
            needs.append(iid)
            positions.append({"position": k, "item_id": iid, "status": "needs_spare", "slot": r["slot"]})
            continue
        used.add(pick["item_id"])
        positions.append({"position": k, **pick, "replaces": iid, "replaced_status": r["status"]})
    return positions, needs


def cmd_fill_bench(args):
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in Path(args.items).read_text(encoding="utf-8").splitlines() if l.strip()]
    positions, needs = fill_bench(rows, manifest, args.primary, excluded_spares(args.manifest))
    text = "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in positions)
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    n_rep = sum(1 for p in positions if p.get("replaces"))
    print(f"{len(positions)} position(s), {n_rep} filled from spares, {len(needs)} still need a spare -> {args.out}")
    if needs:
        print("No usable spare with the same category, difficulty and answer type is left for: " + ", ".join(needs))
        print("Deal like-for-like spares with: python code/generation/variety.py replace --manifest "
              f"{args.manifest} --like <id>, generate them, collect again and re-run fill-bench.")
        sys.exit(3)


# ---------------------------------------------------------------------------------------------
# collect-train (PC): accepted stream, replacements, exact nested sets, balance report
# ---------------------------------------------------------------------------------------------
def replacement_chains(primary_ids, replacement_slots, outside=()):
    """{primary id: [replacement ids in order]}; a replacement may replace a primary or an earlier replacement.
    `outside` holds slot ids of the same file that are not part of this stream (the smoke file's benchmark half);
    replacements of those are skipped."""
    root = {i: i for i in primary_ids}
    chains = {i: [] for i in primary_ids}
    skip = set(outside)
    for s in sorted(replacement_slots, key=lambda s: s["item_id"]):
        if s.get("replaces") in skip:
            skip.add(s["item_id"])
            continue
        r = root.get(s.get("replaces"))
        if r is None:
            sys.exit(f"{s['item_id']} replaces {s.get('replaces')!r}, which is not a slot of this training stream")
        root[s["item_id"]] = r
        chains[r].append(s["item_id"])
    return chains


def judge_candidate(row, length, decontam):
    """(accepted, reason, n_tokens). reason is None when accepted; 'pending' when not generated yet."""
    if row is None or row["status"] == "unfinished":
        return False, "pending", None
    if row["status"] != "usable":
        return False, "failed_attempts", None
    n, problem = length(row)
    if problem:
        return False, "length", n
    if row["item_id"] in decontam:
        return False, decontam[row["item_id"]], n
    return True, None, n


def accepted_stream(primary_slots, replacement_slots, rows_by_id, length, decontam, outside=()):
    """Walk the positions in order. Returns (positions, needs) where each position is accepted (with its example),
    unfilled (MAX_REPLACEMENTS replacements all rejected), needs_replacement, or pending."""
    chains = replacement_chains([s["item_id"] for s in primary_slots], replacement_slots, outside)
    positions, needs = [], []
    for k, slot in enumerate(primary_slots, 1):
        cands = [slot["item_id"]] + chains[slot["item_id"]]
        rejections, state = [], None
        for cid in cands:
            ok, reason, n = judge_candidate(rows_by_id.get(cid), length, decontam)
            if ok:
                state = {"position": k, "state": "accepted", "item_id": cid, "n_tokens": n}
                break
            if reason == "pending":
                state = {"position": k, "state": "pending", "item_id": cid}
                break
            rejections.append({"item_id": cid, "reason": reason, "n_tokens": n})
        if state is None:
            if len(cands) - 1 >= MAX_REPLACEMENTS:
                state = {"position": k, "state": "unfilled"}
            else:
                state = {"position": k, "state": "needs_replacement"}
                needs.append(cands[-1])
        state["primary"] = slot["item_id"]
        state["rejections"] = rejections
        positions.append(state)
    return positions, needs


def settled_prefix(positions):
    """The positions up to (not including) the first that is pending or needs a replacement: only these can be published."""
    out = []
    for p in positions:
        if p["state"] not in ("accepted", "unfilled"):
            break
        out.append(p)
    return out


def balance(primary_slots, positions_span, rows_by_id, shares, n_published):
    """Target and accepted mixes over the positions a published set spans, with the tolerance checks."""
    slot_of = {s["item_id"]: s for s in primary_slots}
    target = [slot_of[p["primary"]] for p in positions_span]
    acc = [rows_by_id[p["item_id"]]["slot"] for p in positions_span if p["state"] == "accepted"]
    flags = []
    rep = {"n_published": n_published, "positions_spanned": len(positions_span)}
    for key in ("category", "difficulty", "answer_type"):
        t, a = Counter(s[key] for s in target), Counter(s[key] for s in acc)
        rep[key] = {k: {"target": round(t[k] / len(target), 4), "accepted": round(a[k] / max(1, len(acc)), 4)} for k in t}
    unfilled = Counter(slot_of[p["primary"]]["category"] for p in positions_span if p["state"] == "unfilled")
    per_cat = Counter(s["category"] for s in target)
    rep["unfilled_by_category"] = dict(unfilled)
    for c, k in unfilled.items():
        if k / per_cat[c] > 0.005:
            flags.append(f"category {c}: {k} of {per_cat[c]} positions unfilled (more than 0.5%)")
    ctx_tol = 0.01 if n_published >= 10000 else 0.03
    rep["no_context_share"] = {}
    for c in sorted(per_cat):
        accc = [s for s in acc if s["category"] == c]
        share = sum(1 for s in accc if s["context"] == sp.NONE) / max(1, len(accc))
        rep["no_context_share"][c] = {"design": shares[c], "accepted": round(share, 4)}
        if abs(share - shares[c]) > ctx_tol:
            flags.append(f"category {c}: no-context share {share:.3f} is more than {ctx_tol * 100:.0f} points from {shares[c]}")
    rep["area"] = {}
    for c in sorted(per_cat):
        ta = Counter(s["area"] for s in target if s["category"] == c)
        aa = Counter(s["area"] for s in acc if s["category"] == c)
        nt, na = sum(ta.values()), max(1, sum(aa.values()))
        rep["area"][c] = {a: {"target": round(ta[a] / nt, 4), "accepted": round(aa[a] / na, 4)} for a in ta}
        if n_published >= 10000:
            for a in ta:
                if abs(aa[a] / na - ta[a] / nt) > 0.20 * (ta[a] / nt):
                    flags.append(f"{c} / area {a}: accepted share {aa[a] / na:.4f} is more than 20% (relative) from target {ta[a] / nt:.4f}")
    subs = Counter((s["category"], s["answer_type"], s["difficulty"], s["subtopic"]) for s in acc)
    rep["subtopics_used"] = len(subs)
    if subs:
        uses = sorted(subs.values())
        rep["subtopic_use"] = {"min": uses[0], "median": statistics.median(uses), "max": uses[-1]}
        if n_published >= 50000 and uses[-1] > 2 * statistics.median(uses):
            flags.append(f"the most-used subtopic is used {uses[-1]} times, more than 2 x the median {statistics.median(uses)}")
    rep["flags"] = flags
    return rep


def rejection_table(positions_span, rows_by_id, slot_index):
    """Rejections by reason, and by reason x category / difficulty / answer type; length rejections listed."""
    by = defaultdict(Counter)
    length_list = []
    for p in positions_span:
        for rj in p["rejections"]:
            s = slot_index[rj["item_id"]]
            by["reason"][rj["reason"]] += 1
            for key in ("category", "difficulty", "answer_type"):
                by[f"{rj['reason']} by {key}"][s[key]] += 1
            if rj["reason"] == "length":
                length_list.append({"item_id": rj["item_id"], "n_tokens": rj["n_tokens"], "category": s["category"],
                                    "difficulty": s["difficulty"], "answer_type": s["answer_type"], "area": s["area"]})
    return {k: dict(v) for k, v in by.items()}, length_list


def compact_row(p, row, n_tokens, slot):
    item = row["item"]
    return {"position": p["position"], "item_id": row["item_id"], "primary": p["primary"],
            "slots_file_sha256": row["slots_file_sha256"], "slot_scheme": row["slot_scheme"],
            "category": slot["category"], "difficulty": slot["difficulty"], "answer_type": slot["answer_type"],
            "subtopic": slot["subtopic"], "area": slot["area"], "context": slot["context"],
            "question": item["question"], "choices": item["choices"], "worked_answer": item["worked_answer"],
            "final_answer": item["final_answer"], "text": sp.training_text(item), "n_tokens": n_tokens,
            "source": {"run": row["run"], "line": row["line"]}}


def cmd_collect_train(args, length=None):
    import separation   # Codex output must never reach training-side material (workflow.md Section 2.3)
    for pth in (args.manifest, args.items, args.decontam, args.out_dir):
        separation.refuse_codex_path(pth, "collect-train")
    man_path = Path(args.manifest)
    man = json.loads(man_path.read_text(encoding="utf-8"))
    if man["set"] not in ("train", "tv", "smoke"):
        sys.exit("collect-train is for the training stream (set train), the held-out set (tv) or the smoke set")
    all_primary, _, primary_sha = load_source(man_path.parent / man["slots_file"])
    primary = all_primary[args.first - 1: args.first - 1 + args.count] if args.count else all_primary[args.first - 1:]
    outside = {s["item_id"] for s in all_primary} - {s["item_id"] for s in primary}
    rep_path = man_path.parent / f"{man['set']}_replacements.jsonl"
    replacements = load_source(rep_path)[0] if rep_path.exists() else []
    rows = [json.loads(l) for l in Path(args.items).read_text(encoding="utf-8").splitlines() if l.strip()]
    separation.refuse_codex_rows(rows, "collect-train", args.items)
    rows_by_id = {}
    for r in rows:
        if r.get("prompt_kind") != "training":
            sys.exit(f"{r['item_id']}: not written with the training prompt")
        if r.get("slot_scheme") != variety.SLOT_SCHEME or not r.get("slots_file_sha256"):
            sys.exit(f"{r['item_id']}: no slot-file fingerprint; refused")
        rows_by_id[r["item_id"]] = r
    decontam = {}
    if args.decontam:
        for l in Path(args.decontam).read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l)
                decontam[d["item_id"]] = d["reason"]
    if length is None:
        tl = sp.TrainingLength(args.tokenizer)
        cache = {}

        def length(row):
            if row["item_id"] not in cache:
                cache[row["item_id"]] = tl.check(sp.training_text(row["item"]), args.max_tokens)
            return cache[row["item_id"]]
        tokenizer_sha = tl.sha256
    else:
        tokenizer_sha = "test"
    positions, needs = accepted_stream(primary, replacements, rows_by_id, length, decontam, outside)
    settled = settled_prefix(positions)
    accepted = [p for p in settled if p["state"] == "accepted"]
    out_dir = Path(args.out_dir) / args.version
    out_dir.mkdir(parents=True, exist_ok=True)
    pub_path = out_dir / "published.json"
    published = json.loads(pub_path.read_text(encoding="utf-8")) if pub_path.exists() else {}
    # A published set can never change: its ids must come out exactly the same on every later collect.
    for size, rec in published.items():
        now = [p["item_id"] for p in accepted[: int(size)]]
        if sha256_text("\n".join(now)) != rec["ids_sha256"]:
            sys.exit(f"the published {size} set would change (its first {size} accepted ids differ from those published "
                     f"on {rec['utc']}). Published sets are frozen; look at the decontamination or replacement input. "
                     f"Nothing was written.")
    slot_index = {s["item_id"]: s for s in primary + replacements}
    ctx, ctx_sha = variety.load_contexts(Path(args.contexts) if args.contexts else variety.CONTEXTS_FILE)
    if ctx_sha != man["contexts_sha256"]:
        sys.exit("the context deck changed since these slots were dealt, so its design shares cannot be used for the "
                 "balance check. Nothing was written.")
    report = {"version": args.version, "generator_version": GENERATOR_VERSION, "manifest": man_path.name,
              "slots_sha256": primary_sha, "tokenizer_sha256": tokenizer_sha, "max_tokens": args.max_tokens,
              "decontamination_file": args.decontam,
              "decontamination_sha256": variety.sha256_file(args.decontam) if args.decontam else None,
              "positions": len(positions), "settled": len(settled), "accepted_settled": len(accepted),
              "states": dict(Counter(p["state"] for p in positions)), "needs_replacement": len(needs), "sets": {}}
    for size in sorted(int(x) for x in args.sizes.split(",")):
        if len(accepted) < size:
            report["sets"][str(size)] = {"published": False,
                                         "reason": f"only {len(accepted)} accepted examples are settled; a set is never published undersized"}
            continue
        part = accepted[:size]
        span = settled[: settled.index(part[-1]) + 1]
        bal = balance(primary, span, rows_by_id, ctx["shares"], size)
        rej, length_list = rejection_table(span, rows_by_id, slot_index)
        ids_sha = sha256_text("\n".join(p["item_id"] for p in part))
        f = out_dir / f"{man['set']}_{size}.jsonl"
        text = "".join(json.dumps(compact_row(p, rows_by_id[p["item_id"]], p["n_tokens"], rows_by_id[p["item_id"]]["slot"]),
                                  ensure_ascii=False) + "\n" for p in part)
        if str(size) in published and sha256_text(text) != published[str(size)]["file_sha256"]:
            sys.exit(f"the published {size} set's file would change (same ids, different content). Published sets are "
                     f"frozen; nothing was written.")
        if not (f.exists() and variety.sha256_file(f) == sha256_text(text)):
            f.write_text(text, encoding="utf-8", newline="\n")
        if str(size) not in published:
            published[str(size)] = {"utc": ott.utc_now().isoformat(timespec="seconds"), "ids_sha256": ids_sha,
                                    "file": f.name, "file_sha256": sha256_text(text)}
        report["sets"][str(size)] = {"published": True, "file": f.name, "file_sha256": published[str(size)]["file_sha256"],
                                     "ids_sha256": ids_sha, "balance": bal, "rejections": rej,
                                     "length_rejections": length_list, "tolerance_flags": bal["flags"]}
    ott.atomic_write(pub_path, json.dumps(published, indent=2))
    ott.atomic_write(out_dir / "manifest.json", json.dumps(report, indent=2))
    need_path = out_dir / "needs_replacement.txt"
    ott.atomic_write(need_path, "".join(i + "\n" for i in needs))
    print(f"{len(positions)} positions: {report['states']}; settled {len(settled)}, accepted {len(accepted)}")
    for size, s in report["sets"].items():
        if s["published"]:
            print(f"  set {size}: published {s['file']} ({len(s['tolerance_flags'])} tolerance flag(s))")
            for fl in s["tolerance_flags"]:
                print("     FLAG", fl)
        else:
            print(f"  set {size}: not published ({s['reason']})")
    if needs:
        print(f"{len(needs)} position(s) need a like-for-like replacement: ids in {need_path}\n"
              f"  deal them with: python code/generation/variety.py replace --manifest {man_path} --like-file {need_path}")
    return report


# ---------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="send one shard of a slot file to the teacher (Talon)")
    p.add_argument("--backend", default="talon", choices=list(ott.BACKENDS))
    p.add_argument("--base-url", default=None)
    p.add_argument("--slots", required=True, help="<set>_slots.jsonl or <set>_replacements.jsonl (with its manifest beside it)")
    p.add_argument("--prompt", required=True, choices=["benchmark", "training"])
    p.add_argument("--first", type=int, default=1, help="first position of the file to use (1-based)")
    p.add_argument("--count", type=int, default=0, help="how many positions from --first (0 = to the end)")
    p.add_argument("--shard", default="1/1", help="k/K: this job takes every K-th selected slot, starting with the k-th")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--max-tokens", type=int, default=ott.MAX_TOKENS)
    p.add_argument("--limit", type=int, default=0, help="work on at most this many slots in this session (tests)")
    p.add_argument("--retry-wait", type=float, default=10.0, help="seconds to wait after a transport error")
    p.add_argument("--stop-after", type=float, default=0, help="seconds after which no new request starts (0 = no deadline)")
    p.add_argument("--grace", type=float, default=600, help="seconds running calls may still take after --stop-after")
    p.add_argument("--out-root", default=None, help="outputs root (tests only); normally from configs/paths.yaml")
    p.add_argument("--break-lock", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--meta", action="append", default=[], help="key=value recorded in run_log.json (job id, engine_version, ...)")
    p = sub.add_parser("validate", help="infrastructure vs model-quality vs unfinished (free, no R)")
    p.add_argument("--run", required=True)
    p.add_argument("--slots", default=None, help="also rebuild the selection from this slot file and compare")
    p.add_argument("--show", type=int, default=50)
    p = sub.add_parser("collect", help="one row per slot from run folders (PC)")
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--r-keys", action="store_true", help="benchmark-style sets: R writes number keys and verify tests "
                   "every R check (R sandbox); a broken or vacuous check makes the slot 'verify_flagged' (replaced by a spare)")
    p = sub.add_parser("apply-repairs", help="apply owner-reviewed repair/replace decisions to verify-flagged items (R sandbox)")
    p.add_argument("--items", required=True)
    p.add_argument("--decisions", required=True, help="a JSON list of {item_id, action: repair_check | replace, new_r_check, reason}")
    p.add_argument("--out", required=True)
    p = sub.add_parser("fill-bench", help="benchmark/dev/smoke: replace failed primaries with like-for-like spares")
    p.add_argument("--items", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--primary", type=int, required=True, help="size of the primary block (1000 benchmark, 200 dev)")
    p.add_argument("--out", required=True)
    p = sub.add_parser("collect-train", help="training stream: accepted examples, replacements, exact nested sets")
    p.add_argument("--items", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--decontam", default=None, help="rejections from code/verification/decontaminate.py")
    p.add_argument("--version", required=True, help="name of the dataset version folder, for example 2026-12-01_train-v1")
    p.add_argument("--out-dir", default=None, help="default: training_data from configs/paths.yaml")
    p.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES))
    p.add_argument("--first", type=int, default=1, help="first position of the slot file in the stream (smoke: 21)")
    p.add_argument("--count", type=int, default=0, help="how many positions from --first (0 = to the end)")
    p.add_argument("--tokenizer", default=None)
    p.add_argument("--contexts", default=None, help="the context deck the slots were dealt from (default: the repository's)")
    p.add_argument("--max-tokens", type=int, default=sp.MAX_TRAINING_TOKENS)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        sys.exit(cmd_run(args))
    if args.cmd == "validate":
        cmd_validate(args)
    elif args.cmd == "collect":
        cmd_collect(args)
    elif args.cmd == "apply-repairs":
        cmd_apply_repairs(args)
    elif args.cmd == "fill-bench":
        cmd_fill_bench(args)
    elif args.cmd == "collect-train":
        if args.out_dir is None:
            args.out_dir = ott.paths()["training_data"]
        cmd_collect_train(args)


if __name__ == "__main__":
    main()
