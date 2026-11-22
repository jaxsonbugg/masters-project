"""
replacement_loop.py - the resumable controller that replaces flagged benchmark questions with same-subtopic Qwen candidates.

WHAT THIS IS AND WHY (owner's decisions and approved plan "resolve the Codex flags", revision 2, 2026-11-21)
The Codex screen flagged benchmark questions with serious problems, and 26 positions hold spares whose subtopic differs from
the slot that was dealt there. Each such position needs a new question with EXACTLY the dealt subtopic, difficulty, answer
type, setting and preferred letter, written by Qwen (Claude writes no benchmark text), checked by R, and passed by the Codex
screen and the Codex alignment check before it enters the benchmark. This controller runs that loop on its own, under hard
limits, and stops before anything only Jaxson does (hand corrections, the audit, the freeze).

HOW ONE ROUND WORKS (the "phase" in the ledger)
  deal      3 same-subtopic candidate slots per open position (variety.deal_replacements, same_subtopic=True), appended to
            data/slots/benchmark_replacements.jsonl. No deck card is drawn.
  upload    copy that file and the slot manifest to the Talon repository copy, then compare SHA-256 on both sides.
  submit    stage G jobs of at most 200 slots each, 1 GPU, Slurm wall-time limit 01:00:00 (the 1 GPU-hour cap is enforced by
            Slurm itself), GEN_MARGIN_SECONDS=600. Intent is written to the ledger BEFORE sbatch (see "idempotent" below).
  wait      read the queue; when a job has ended, read its result file: complete, unfinished (resumed under the same identifier
            in a new job), or an infrastructure failure (retried at most once).
  download  copy the run folders, job logs and result files to the PC (read-only on Talon); re-validate on the PC.
  collect   one row per candidate; R writes the number keys and verify tests every R check (R sandbox). Broken ones drop out.
  codex     Codex screen (screen_v1) and alignment (align_v1) of every usable candidate, in the safeguarded codex_batch.py.
  fill      generate_set.fill_match_subtopic: each open position takes the first candidate that is usable, passed by the
            screen, subtopic-"aligned" and difficulty-"matches", with metadata equal to the dealt slot.
After round 3, positions still open get an owner-review packet (every candidate of every round) and the controller stops.

THE LIMITS (configs/replacement_loop.yaml; the standing approval is hard-coded in ALLOWED_* below and cannot be widened there)
  * per job: 1 GPU, TIME_GENERATE=01:00:00, at most 200 slots; the estimate (slots x rate + loading) must be under 1 GPU-hour.
  * total: 4.0 GPU-hours, a hard stop. Before each submission: hours already used (measured) + 1.0 for every job still
    running or unmeasured + 1.0 for the new job must stay within the budget.
  * Codex: at most 40 batch runs in total; a rejected batch or a failed job is retried at most once.
  * allowed actions only: the fixed command shapes in ALLOWED_SSH, ALLOWED_SCP_TO, ALLOWED_SCP_FROM. Anything else stops the
    controller (StopLoop "action not allowed"). No refresh of the Talon copy, no other stage, no other Codex use.

IDEMPOTENT SUBMISSION (correction 2)
  The identifier of a job is its round, shard and slot selection: the stage G tag benchmark-benchmark-p<first>n<count>-<k>of<K>
  (the selection is fixed by first and count in the append-only replacements file, and the run folder name carries the
  selection's SHA-256). Before sbatch the ledger records {"state": "submitting"} atomically. If the answer never arrives, the
  next start reconciles: squeue by job name, the Talon submit_log.txt, the job logs and the result files. A job number found
  there that the ledger does not know is adopted; if every source was read and none shows a new job, it was not submitted;
  if any source cannot be read, the controller STOPS rather than risk a duplicate. (sacct is disabled on Talon: Slurm
  accounting storage is off, observed 2026-11-20.)

THE LEDGER: <benchmark_work>/<loop_id>/ledger.json, written to a temporary file and renamed (atomic on one disk), so a crash
leaves either the old or the new ledger, never half of one. Every start resumes from it.

Commands:  plan | run | status | packet       (python replacement_loop.py run --config configs/replacement_loop.yaml)
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
sys.path.insert(0, str(REPO / "code" / "verification"))
import generate_set as gs  # noqa: E402
import variety  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LEDGER_VERSION = 1
PY = sys.executable
GEN = str(REPO / "code" / "generation" / "generate_set.py")
CODEX = str(REPO / "code" / "verification" / "codex_batch.py")

# The standing approval (owner, 2026-11-21), fixed in code. The config may restate these values but never change them.
APPROVED_ENV = {"GPU_COUNT": "1", "TENSOR_PARALLEL": "1", "REPLICAS": "1", "MAX_NUM_SEQS": "16", "CLIENT_CONCURRENCY": "16",
                "TIME_GENERATE": "01:00:00", "GEN_MARGIN_SECONDS": "600"}
GEN_SLOTS = "data/slots/benchmark_replacements.jsonl"
MAX_GPU_HOURS_PER_JOB = 1.0
MAX_CANDIDATES = 6         # raised from 3 by the owner on 2026-11-22 ("a few options") for the 2-position loop
MAX_TOTAL_GPU_HOURS = 5.3   # raised from 4.0 to 5.0 (round 3), then to 5.3 (the 2 unfinished round-3 slots) by the owner on 2026-11-22
MAX_SLOTS_PER_JOB = 200
TAG_RE = r"benchmark-benchmark-p[1-9]\d*n[1-9]\d*-[1-9]\d*of[1-9]\d*"
RUN_RE = r"\d{4}-\d{2}-\d{2}_qwen3-6-27b-talon-bf16_benchmark_benchmark-v8_[0-9a-f]{8}_shard[1-9]\d*of[1-9]\d*"


class StopLoop(Exception):
    """A stop condition: the controller writes a stop report and exits. condition is one of the plan's six."""
    def __init__(self, condition, detail):
        super().__init__(f"{condition}: {detail}")
        self.condition, self.detail = condition, detail


class Uncertain(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def crash_point(name):
    """Test hook: RL_CRASH_AT=<name> makes the controller die here, as a power cut would (the ledger stays as last saved)."""
    if os.environ.get("RL_CRASH_AT") == name:
        print(f"[test] simulated crash at {name}")
        os._exit(99)


# ------------------------------------------------------------------------------------------------------------------
# configuration
# ------------------------------------------------------------------------------------------------------------------
def load_paths():
    return yaml.safe_load((REPO / "configs" / "paths.yaml").read_text(encoding="utf-8"))


def expand(value, paths):
    """'{benchmark_work}/x' -> the paths.yaml location + '/x'. Storage locations always come from configs/paths.yaml."""
    if not isinstance(value, str):
        return value
    return re.sub(r"\{(\w+)\}", lambda m: str(paths[m.group(1)]), value)


def load_config(path):
    raw_text = Path(path).read_text(encoding="utf-8")
    cfg = yaml.safe_load(raw_text)
    paths = load_paths()
    cfg["_sha256"] = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    cfg["_path"] = str(path)
    for sect in ("inputs", "talon", "codex", "local"):
        for k, v in list((cfg.get(sect) or {}).items()):
            cfg[sect][k] = expand(v, paths) if not isinstance(v, list) else [expand(x, paths) for x in v]
    t = cfg["talon"]
    t.setdefault("root", paths["talon_root"])
    t.setdefault("repo", paths["talon_repo"])
    t.setdefault("outputs", paths["talon_outputs"])
    # the standing approval cannot be widened from the config file
    problems = []
    if cfg.get("max_gpu_hours_per_job", 1.0) > MAX_GPU_HOURS_PER_JOB:
        problems.append("max_gpu_hours_per_job above 1.0")
    if cfg.get("slots_per_job_max", 200) > MAX_SLOTS_PER_JOB:
        problems.append("slots_per_job_max above 200")
    for k, v in (t.get("env") or {}).items():
        if APPROVED_ENV.get(k) != str(v):
            problems.append(f"talon env {k}={v} is not the approved {APPROVED_ENV.get(k)!r}")
    if cfg["max_total_gpu_hours"] > MAX_TOTAL_GPU_HOURS or cfg["max_codex_batches"] > 40 or cfg["max_retries_per_step"] > 1 \
            or cfg["rounds"] > 3 or cfg["candidates_per_position"] > MAX_CANDIDATES:
        problems.append(f"a limit is above the approved value ({MAX_TOTAL_GPU_HOURS} GPU-hours, 40 Codex batches, 1 retry, "
                        f"3 rounds, {MAX_CANDIDATES} candidates)")
    if problems:
        sys.exit("configuration refused (it would widen the standing approval): " + "; ".join(problems))
    return cfg


def state_dir(cfg):
    return Path(cfg["local"]["state_root"]) / cfg["loop_id"]


# ------------------------------------------------------------------------------------------------------------------
# the ledger (atomic)
# ------------------------------------------------------------------------------------------------------------------
def save_ledger(cfg, led):
    d = state_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    led["updated_utc"] = utc_now()
    tmp = d / "ledger.json.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(led, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, d / "ledger.json")          # atomic: the old or the new ledger, never half of one


def load_ledger(cfg):
    f = state_dir(cfg) / "ledger.json"
    if not f.exists():
        return None
    led = json.loads(f.read_text(encoding="utf-8"))
    if led.get("version") != LEDGER_VERSION:
        raise StopLoop("ledger mismatch", f"ledger version {led.get('version')} is not {LEDGER_VERSION}")
    if led["config_sha256"] != cfg["_sha256"]:
        raise StopLoop("ledger mismatch", "the configuration changed since this loop started; start a new loop_id instead")
    return led


def log_event(led, text):
    led.setdefault("history", []).append({"utc": utc_now(), "event": text})
    print(f"[{led['history'][-1]['utc']}] {text}")


# ------------------------------------------------------------------------------------------------------------------
# allowed remote actions (everything else stops the controller)
# ------------------------------------------------------------------------------------------------------------------
class Talon:
    def __init__(self, cfg):
        t = cfg["talon"]
        self.host, self.ssh_cmd, self.scp_cmd = t["host"], list(t["ssh"]), list(t["scp"])
        self.root, self.repo, self.outputs = t["root"].rstrip("/"), t["repo"].rstrip("/"), t["outputs"].rstrip("/")
        R, O, P = re.escape(self.repo), re.escape(self.outputs), re.escape(self.root)
        env = " ".join(f"{k}={v}" for k, v in APPROVED_ENV.items())
        self.allowed_ssh = [
            # submit one stage G shard of the replacements file, with exactly the approved settings
            rf"cd {R} && QT_SUBMIT=yes {re.escape(env)} GEN_SLOTS={re.escape(GEN_SLOTS)} GEN_PROMPT=benchmark "
            rf"GEN_SHARD=[1-9]\d*/[1-9]\d* GEN_FIRST=[1-9]\d* GEN_COUNT=[1-9]\d* bash configs/talon/submit_pipeline.sh generate",
            rf"squeue -h -u \$\(id -un\) -n qt_talon_G_{TAG_RE} -o %i,%T",
            rf"sha256sum {R}/data/slots/benchmark_slots\.jsonl {R}/data/slots/benchmark_slots\.manifest\.json "
            rf"{R}/data/prompts/benchmark_generation_v8\.md; sha256sum {R}/data/slots/benchmark_replacements\.jsonl; true",
            rf"cat {P}/submit_log\.txt",
            rf"ls -1 {R} {O}/stage_results",
            rf"cat {O}/stage_results/stageG_{TAG_RE}_job\d+\.txt",
            rf"head -n 40 {R}/qt_talon_G_{TAG_RE}_\d+\.log",
        ]
        self.allowed_scp_to = {f"{self.repo}/data/slots/benchmark_replacements.jsonl",
                               f"{self.repo}/data/slots/benchmark_slots.manifest.json"}
        self.allowed_scp_from = [rf"{O}/{RUN_RE}", rf"{O}/stage_results/stageG_{TAG_RE}_job\d+\.txt",
                                 rf"{R}/qt_talon_G_{TAG_RE}_\d+\.log"]

    def ssh(self, cmd, timeout=600):
        if not any(re.fullmatch(p, cmd) for p in self.allowed_ssh):
            raise StopLoop("action not allowed", f"remote command refused: {cmd}")
        r = subprocess.run(self.ssh_cmd + [self.host, cmd], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, r.stdout, r.stderr

    def scp_to(self, local, remote):
        if remote not in self.allowed_scp_to:
            raise StopLoop("action not allowed", f"copy to Talon refused: {remote}")
        r = subprocess.run(self.scp_cmd + [str(local), f"{self.host}:{remote}"], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise StopLoop("repeated failure", f"scp to {remote} failed: {r.stderr[-300:]}")

    def scp_from(self, remote, local, recursive=False):
        if not any(re.fullmatch(p, remote) for p in self.allowed_scp_from):
            raise StopLoop("action not allowed", f"copy from Talon refused: {remote}")
        r = subprocess.run(self.scp_cmd + (["-r"] if recursive else []) + [f"{self.host}:{remote}", str(local)],
                           capture_output=True, text=True, timeout=3600)
        return r.returncode == 0, r.stderr

    def submit_cmd(self, first, count, k, K):
        env = " ".join(f"{a}={b}" for a, b in APPROVED_ENV.items())
        return (f"cd {self.repo} && QT_SUBMIT=yes {env} GEN_SLOTS={GEN_SLOTS} GEN_PROMPT=benchmark GEN_SHARD={k}/{K} "
                f"GEN_FIRST={first} GEN_COUNT={count} bash configs/talon/submit_pipeline.sh generate")


def tag_of(first, count, k, K):
    return f"benchmark-benchmark-p{first}n{count}-{k}of{K}"


# ------------------------------------------------------------------------------------------------------------------
# plan: the round-1 open positions, with reasons, and the GPU estimate
# ------------------------------------------------------------------------------------------------------------------
def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def screen_flags(folder):
    out = {}
    for f in sorted(Path(folder).glob("*/screen_results.jsonl")):
        for r in read_jsonl(f):
            if r["verdict"] == "flag":
                out[r["item_id"]] = r
    return out


def open_positions(cfg):
    """{position: [reasons]} for round 1 (plan revision 2, 'Each round', step 1)."""
    inp = cfg["inputs"]
    if inp.get("only_extra_open"):
        # a follow-up loop for owner-listed positions only (owner's decision, 2026-11-22): the screen flags and earlier
        # substitutions of the main loop are not re-opened
        reasons = {}
        for f in inp.get("extra_open") or []:
            for line in Path(f).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    reasons.setdefault(int(line.split()[0]), []).append(f"owner-listed ({Path(f).name})")
        return reasons
    positions = read_jsonl(inp["positions"])
    prefix, width = variety.SETS["benchmark"]
    fixc = json.loads(Path(inp["fix_classification"]).read_text(encoding="utf-8"))
    flags = screen_flags(inp["screen_results"])
    import codex_batch
    reasons = {}
    for p in positions:
        k, iid = p["position"], p["item_id"]
        r = []
        if iid in flags:
            grp = codex_batch.review_group({"issue_type": flags[iid]["issue_type"], "reason": flags[iid]["reason"]})
            if grp.startswith("1"):
                cls = (fixc.get(iid) or {}).get("class")
                if cls in ("substantive", "not_computable"):
                    r.append(f"small printed-number flag, {cls} (replaced, owner's rule)")
                elif cls is None:
                    r.append("small printed-number flag without a fix classification (replaced)")
            else:
                r.append(f"serious Codex flag: {flags[iid]['issue_type']}")
        if iid != f"{prefix}{k:0{width}d}":
            r.append(f"earlier substitution ({iid} holds the position; its subtopic is not the dealt one)")
        if r:
            reasons[k] = r
    for f in inp.get("extra_open") or []:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if line.strip():
                k = int(line.split()[0])
                reasons.setdefault(k, []).append(f"owner-listed ({Path(f).name})")
    return reasons


def estimate(cfg, n_slots):
    K = max(1, math.ceil(n_slots / cfg["slots_per_job_max"]))
    per_job_slots = math.ceil(n_slots / K) if n_slots else 0
    per_job = per_job_slots * cfg["gpu_hours_per_1000_slots"] / 1000 + cfg["load_hours_per_job"]
    return {"slots": n_slots, "jobs": K, "slots_per_job": per_job_slots, "est_gpu_hours_per_job": round(per_job, 3),
            "est_gpu_hours_total": round(K * per_job, 3)}


def cmd_plan(cfg, args):
    reasons = open_positions(cfg)
    n = len(reasons) * cfg["candidates_per_position"]
    est = estimate(cfg, n)
    by = {}
    for rs in reasons.values():
        for r in rs:
            key = r.split(":")[0].split("(")[0].strip()
            by[key] = by.get(key, 0) + 1
    out = {"open_positions": len(reasons), "reasons": by, "candidates": n, **est,
           "budget_gpu_hours": cfg["max_total_gpu_hours"], "positions": {str(k): v for k, v in sorted(reasons.items())}}
    d = state_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan_round1.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in out.items() if k != "positions"}, indent=1))
    print(f"-> {d / 'plan_round1.json'}")
    return out


# ------------------------------------------------------------------------------------------------------------------
# the phases
# ------------------------------------------------------------------------------------------------------------------
def manifest_path(cfg):
    return Path(cfg["local"]["slots_dir"]) / "benchmark_slots.manifest.json"


def replacements_path(cfg):
    return Path(cfg["local"]["slots_dir"]) / "benchmark_replacements.jsonl"


def original_slots(cfg):
    m = json.loads(manifest_path(cfg).read_text(encoding="utf-8"))
    return {s["item_id"]: s for s in variety.read_slots(manifest_path(cfg).parent / m["slots_file"])}


def cur(led):
    return led["rounds"][str(led["round"])]


def phase_deal(cfg, led, T):
    rd = cur(led)
    tag = f"{cfg['loop_id']}-r{led['round']}"
    m = json.loads(manifest_path(cfg).read_text(encoding="utf-8"))
    done = [e for e in m.get("replacements", []) if e.get("tag") == tag]
    if done:                                  # dealt before a crash, ledger not yet saved: adopt, never deal twice
        ids = done[-1]["ids"]
    else:
        orig = original_slots(cfg)
        prefix, width = variety.SETS["benchmark"]
        likes = [orig[f"{prefix}{k:0{width}d}"] for k in rd["positions"]]
        new = variety.deal_replacements(manifest_path(cfg), likes, same_subtopic=True,
                                        copies=cfg["candidates_per_position"], tag=tag)
        ids = [s["item_id"] for s in new]
        crash_point("after_deal")
    allrep = [s["item_id"] for s in variety.read_slots(replacements_path(cfg))]
    first = allrep.index(ids[0]) + 1
    if allrep[first - 1: first - 1 + len(ids)] != ids:
        raise StopLoop("ledger mismatch", "the round's candidates are not one contiguous block of the replacements file")
    est = estimate(cfg, len(ids))
    if est["est_gpu_hours_per_job"] > MAX_GPU_HOURS_PER_JOB:
        raise StopLoop("budget", f"estimated {est['est_gpu_hours_per_job']} GPU-hours per job is above the 1.0 cap")
    rd.update({"candidate_ids": ids, "first": first, "count": len(ids), "K": est["jobs"], "estimate": est,
               "shards": {str(k): {"tag": tag_of(first, len(ids), k, est["jobs"]), "attempts": [], "complete": False}
                          for k in range(1, est["jobs"] + 1)}})
    rd["replacements_sha256"] = sha256_file(replacements_path(cfg))
    led["phase"] = "upload"
    log_event(led, f"round {led['round']}: dealt {len(ids)} candidates ({ids[0]}-{ids[-1]}) for {len(rd['positions'])} "
                   f"positions; {est['jobs']} job(s) of about {est['slots_per_job']} slots")


def prompt_pin():
    """The approved benchmark prompt's SHA-256, read from configs/talon/common.sh (the same pin the Talon job checks)."""
    text = (REPO / "configs" / "talon" / "common.sh").read_text(encoding="utf-8")
    m = re.search(r'^PROMPT_BENCH_FILE="benchmark_generation_v8\.md"', text, re.M)
    pin = re.search(r'^PROMPT_BENCH_SHA256="([0-9a-f]{64})"', text, re.M)
    if not m or not pin:
        raise StopLoop("ledger mismatch", "configs/talon/common.sh does not pin benchmark_generation_v8.md")
    if hashlib.sha256((REPO / "data" / "prompts" / "benchmark_generation_v8.md").read_bytes()).hexdigest() != pin.group(1):
        raise StopLoop("ledger mismatch", "the PC's prompt v8 does not match its pin in common.sh")
    return pin.group(1)


def remote_shas(T):
    rc, out, err = T.ssh(f"sha256sum {T.repo}/data/slots/benchmark_slots.jsonl {T.repo}/data/slots/benchmark_slots.manifest.json "
                         f"{T.repo}/data/prompts/benchmark_generation_v8.md; sha256sum {T.repo}/data/slots/benchmark_replacements.jsonl; true")
    if rc != 0:
        raise StopLoop("repeated failure", f"could not read SHA-256 values on Talon: {err[-300:]}")
    shas = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            shas[parts[1].rsplit("/", 1)[-1]] = parts[0]
    return shas


def phase_upload(cfg, led, T):
    rd = cur(led)
    man = json.loads(manifest_path(cfg).read_text(encoding="utf-8"))
    local = {"benchmark_replacements.jsonl": sha256_file(replacements_path(cfg)),
             "benchmark_slots.manifest.json": sha256_file(manifest_path(cfg))}
    if local["benchmark_replacements.jsonl"] != rd["replacements_sha256"] or man["replacements_sha256"] != rd["replacements_sha256"]:
        raise StopLoop("ledger mismatch", "the replacements file changed since this round was dealt")
    shas = remote_shas(T)
    if shas.get("benchmark_slots.jsonl") != man["slots_sha256"]:
        raise StopLoop("ledger mismatch", "the Talon copy's benchmark_slots.jsonl is not the dealt slot file")
    if shas.get("benchmark_generation_v8.md") != prompt_pin():
        raise StopLoop("ledger mismatch", "the Talon copy's prompt v8 is not the pinned version")
    if any(shas.get(n) != s for n, s in local.items()):
        T.scp_to(replacements_path(cfg), f"{T.repo}/data/slots/benchmark_replacements.jsonl")
        T.scp_to(manifest_path(cfg), f"{T.repo}/data/slots/benchmark_slots.manifest.json")
        crash_point("after_upload")
        shas = remote_shas(T)
        if any(shas.get(n) != s for n, s in local.items()):
            raise StopLoop("ledger mismatch", f"after the copy the Talon SHA-256 values differ: {shas} vs {local}")
    led["phase"] = "submit"
    log_event(led, f"round {led['round']}: slot files on Talon match the PC (replacements {local['benchmark_replacements.jsonl'][:12]})")


def known_jobs(led, tag):
    return {a["job"] for rd in led["rounds"].values() for sh in rd.get("shards", {}).values() if sh["tag"] == tag
            for a in sh["attempts"] if a.get("job")}


def reconcile(T, led, sh):
    """For an attempt left in 'submitting': its job number, or None when it was certainly not submitted. Raises Uncertain."""
    tag, known = sh["tag"], known_jobs(led, sh["tag"])
    name = f"qt_talon_G_{tag}"
    found = set()
    rc, out, err = T.ssh(f"squeue -h -u $(id -un) -n {name} -o %i,%T")
    if rc != 0:
        raise Uncertain(f"squeue could not be read: {err[-200:]}")
    found |= {l.split(",")[0].strip() for l in out.splitlines() if l.strip()}
    rc, out, err = T.ssh(f"cat {T.root}/submit_log.txt")
    if rc != 0:
        raise Uncertain(f"submit_log.txt could not be read: {err[-200:]}")
    found |= set(re.findall(rf"JOB=(\d+) KIND=generate .*GEN={re.escape(tag)}(?:\s|$)", out))
    rc, out, err = T.ssh(f"ls -1 {T.repo} {T.outputs}/stage_results")
    if rc != 0:
        raise Uncertain(f"the job logs and result files could not be listed: {err[-200:]}")
    found |= set(re.findall(rf"^{re.escape(name)}_(\d+)\.log$", out, re.M))
    found |= set(re.findall(rf"^stageG_{re.escape(tag)}_job(\d+)\.txt$", out, re.M))
    new = sorted(found - known, key=int)
    if len(new) > 1:
        raise Uncertain(f"more than one unknown job for {tag}: {new}")
    return new[0] if new else None


def gpu_committed(led):
    used = unmeasured = 0.0
    for rd in led["rounds"].values():
        for sh in rd.get("shards", {}).values():
            for a in sh["attempts"]:
                if a["state"] in ("submitting", "submitted"):
                    unmeasured += MAX_GPU_HOURS_PER_JOB
                elif a.get("gpu_hours") is not None:
                    used += a["gpu_hours"]
                elif a["state"] not in ("not_submitted", "refused"):
                    unmeasured += MAX_GPU_HOURS_PER_JOB            # ended without a measurement: charge the full cap
    return used, unmeasured


def phase_submit(cfg, led, T):
    rd = cur(led)
    for k, sh in sorted(rd["shards"].items(), key=lambda x: int(x[0])):
        if sh["complete"]:
            continue
        last = sh["attempts"][-1] if sh["attempts"] else None
        if last and last["state"] == "submitting":
            try:
                job = reconcile(T, led, sh)
            except Uncertain as e:
                raise StopLoop("submission uncertain", f"{sh['tag']}: {e}. Look at the queue and submit_log.txt by hand; "
                                                       "nothing was resubmitted.")
            if job:
                last.update({"state": "submitted", "job": job, "reconciled": True})
                log_event(led, f"{sh['tag']}: reconciled, job {job} had been submitted")
            else:
                last["state"] = "not_submitted"
                log_event(led, f"{sh['tag']}: reconciled, the earlier submission did not happen")
            save_ledger(cfg, led)
            last = sh["attempts"][-1]
        if last and last["state"] == "submitted":
            continue
        n_fail = sum(a["state"] == "failed" for a in sh["attempts"])
        n_unf = sum(a["state"] == "unfinished" for a in sh["attempts"])
        if n_fail > cfg["max_retries_per_step"]:
            raise StopLoop("repeated failure", f"{sh['tag']} failed {n_fail} times")
        if n_unf > cfg["max_resumes_per_shard"]:
            raise StopLoop("repeated failure", f"{sh['tag']} was unfinished {n_unf} times")
        used, unmeasured = gpu_committed(led)
        if used + unmeasured + MAX_GPU_HOURS_PER_JOB > cfg["max_total_gpu_hours"] + 1e-9:
            running = [a["job"] for s in rd["shards"].values() for a in s["attempts"] if a["state"] == "submitted"]
            if running:
                # (owner-approved fix, 2026-11-21) a running job is charged the full 1.0 until it is measured: wait for
                # it to end and be measured, then check the budget again, instead of stopping on a pessimistic charge
                led["phase"] = "wait"
                log_event(led, f"{sh['tag']}: not submitted yet: {used:.2f} used + {unmeasured:.1f} charged for running "
                               f"job(s) {running} + 1.0 would pass {cfg['max_total_gpu_hours']}; waiting for them to be measured")
                return
            raise StopLoop("budget", f"GPU budget: {used:.2f} used + {unmeasured:.1f} committed + 1.0 for the next job "
                                     f"would pass {cfg['max_total_gpu_hours']}")
        sh["attempts"].append({"state": "submitting", "intent_utc": utc_now()})
        save_ledger(cfg, led)                                    # intent first, then sbatch
        crash_point("after_intent")
        cmd = T.submit_cmd(rd["first"], rd["count"], int(k), rd["K"])
        try:
            rc, out, err = T.ssh(cmd)
        except subprocess.TimeoutExpired:
            raise StopLoop("submission uncertain", f"{sh['tag']}: ssh timed out; the next start reconciles")
        crash_point("after_sbatch")
        m = re.search(r"Submitted batch job (\d+)", out)
        if m:
            sh["attempts"][-1].update({"state": "submitted", "job": m.group(1), "submitted_utc": utc_now()})
            log_event(led, f"{sh['tag']}: submitted job {m.group(1)}")
            save_ledger(cfg, led)
        elif rc not in (0, 255):
            # submit_pipeline.sh stopped with `die` (exit 2, "STOP: ..."): either a check failed before sbatch, or sbatch
            # reported no job number ("the generate job was NOT submitted"). Either way no job exists.
            sh["attempts"][-1].update({"state": "refused", "detail": (out + err)[-500:]})
            save_ledger(cfg, led)
            raise StopLoop("repeated failure", f"{sh['tag']}: submit_pipeline.sh refused the job: {(out + err)[-300:]}")
        else:
            raise StopLoop("submission uncertain", f"{sh['tag']}: no job number in the answer (rc {rc}); the next start "
                                                   "reconciles before anything is resubmitted")
    led["phase"] = "wait"


def parse_kv(text):
    return dict(l.split("=", 1) for l in text.splitlines() if "=" in l and re.match(r"^[A-Z_]+=", l))


CONN_TOLERANCE_SECONDS = float(os.environ.get("RL_CONN_TOLERANCE_SECONDS", 1800))   # env override: tests only


def connection_down(cfg, led, rc, err):
    """While WAITING on a job (owner-approved, 2026-11-21): ssh exit 255 means the connection failed (VPN or Wi-Fi), not
    Talon. Tolerated for up to 30 minutes, then the loop stops. Submissions never use this: there, an unanswered ssh still
    stops the loop and the next start reconciles before anything is resubmitted."""
    if rc != 255:
        return False
    now = time.time()
    since = led.setdefault("conn_down_since", now)
    if now - since > CONN_TOLERANCE_SECONDS:
        return False
    if since == now:
        log_event(led, f"Talon unreachable ({err.strip()[-120:]}); retrying while waiting, for up to "
                       f"{CONN_TOLERANCE_SECONDS / 60:.0f} minutes")
    return True


def phase_wait(cfg, led, T):
    """Returns True when every shard is complete; False while jobs are still queued or running."""
    rd = cur(led)
    waiting = False
    for k, sh in sorted(rd["shards"].items(), key=lambda x: int(x[0])):
        if sh["complete"]:
            continue
        if not sh["attempts"] or sh["attempts"][-1]["state"] != "submitted":
            continue                             # not running: handled by submit once nothing is left to wait for
        a = sh["attempts"][-1]
        rc, out, err = T.ssh(f"squeue -h -u $(id -un) -n qt_talon_G_{sh['tag']} -o %i,%T")
        if rc != 0:
            if connection_down(cfg, led, rc, err):
                waiting = True
                continue
            raise StopLoop("repeated failure", f"squeue failed: {err[-200:]}")
        if any(l.split(",")[0].strip() == a["job"] for l in out.splitlines()):
            led.pop("conn_down_since", None)
            waiting = True
            continue
        rc, out, err = T.ssh(f"cat {T.outputs}/stage_results/stageG_{sh['tag']}_job{a['job']}.txt")
        rc2, log, err2 = T.ssh(f"head -n 40 {T.repo}/qt_talon_G_{sh['tag']}_{a['job']}.log")
        if rc == 255 or rc2 == 255:                # the connection dropped: never mistake that for a failed job
            if connection_down(cfg, led, 255, err or err2):
                waiting = True
                continue
            raise StopLoop("repeated failure", f"Talon unreachable while reading job {a['job']}'s results: {(err or err2)[-200:]}")
        led.pop("conn_down_since", None)
        res = parse_kv(out) if rc == 0 else {}
        start = re.search(r"=== node \S+, job \d+, stage G, (\S+Z) ===", log or "")
        if res.get("UTC") and start:
            t0 = datetime.fromisoformat(start.group(1).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(res["UTC"].replace("Z", "+00:00"))
            a["gpu_hours"] = round((t1 - t0).total_seconds() / 3600 * int(APPROVED_ENV["GPU_COUNT"]), 3)
        a.update({"ended_seen_utc": utc_now(), "result": {k_: res.get(k_) for k_ in
                  ("RESULT", "INFRA", "GEN_COMPLETE", "GEN_RESULT", "RUN_DIR", "UTC", "NODE")}})
        if res and res.get("INFRA") == "PASS" and res.get("GEN_COMPLETE") == "yes":
            a["state"], sh["complete"], sh["run_dir"] = "finished", True, res["RUN_DIR"]
            log_event(led, f"{sh['tag']}: job {a['job']} complete ({res.get('GEN_RESULT')}; {a.get('gpu_hours')} GPU-hours)")
        elif res and res.get("INFRA") == "PASS":
            a["state"] = "unfinished"
            log_event(led, f"{sh['tag']}: job {a['job']} reached its time limit unfinished; it resumes in a new job")
        else:
            a["state"] = "failed"
            log_event(led, f"{sh['tag']}: job {a['job']} failed (result file: {res.get('RESULT', 'missing')})")
        save_ledger(cfg, led)
    if waiting:
        return False
    if all(sh["complete"] for sh in rd["shards"].values()):
        led["phase"] = "download"
        return True
    led["phase"] = "submit"                      # an unfinished or failed shard goes back to submit (bounded there)
    return False


def phase_download(cfg, led, T):
    rd = cur(led)
    dest = Path(cfg["local"]["teacher_outputs"])
    logs = dest / f"{cfg['loop_id']}_stageG_r{led['round']}_logs"
    logs.mkdir(parents=True, exist_ok=True)
    local_dirs = []
    for k, sh in sorted(rd["shards"].items(), key=lambda x: int(x[0])):
        name = sh["run_dir"].rsplit("/", 1)[-1]
        target = dest / name
        if not (target / "done_index.jsonl").exists():
            part = dest / (name + ".partial")
            if part.exists():
                import shutil
                shutil.rmtree(part)
            part.mkdir(parents=True)
            ok, err = T.scp_from(sh["run_dir"], part, recursive=True)
            if not ok:
                raise StopLoop("repeated failure", f"copying {name} failed: {err[-300:]}")
            inner = part / name
            os.replace(inner if inner.exists() else part, target)
            if part.exists():
                part.rmdir()
        for a in sh["attempts"]:
            if a.get("job") and a["state"] in ("finished", "unfinished", "failed"):
                T.scp_from(f"{T.outputs}/stage_results/stageG_{sh['tag']}_job{a['job']}.txt", logs)
                T.scp_from(f"{T.repo}/qt_talon_G_{sh['tag']}_{a['job']}.log", logs)
        r = subprocess.run([PY, GEN, "validate", "--run", str(target), "--slots", str(replacements_path(cfg))],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode not in (0, 2):            # validate: 0 clean, 2 model-quality findings only; 1 infrastructure, 3 unfinished
            raise StopLoop("repeated failure", f"{name} does not validate on the PC (exit {r.returncode}): {r.stdout[-300:]}")
        local_dirs.append(str(target))
    rd["local_dirs"] = local_dirs
    led["phase"] = "collect"
    log_event(led, f"round {led['round']}: {len(local_dirs)} run folder(s) copied and re-validated on the PC")


def phase_collect(cfg, led, T):
    rd = cur(led)
    out = state_dir(cfg) / f"r{led['round']}_candidates.jsonl"
    cmd = [PY, GEN, "collect", "--runs", *rd["local_dirs"], "--out", str(out)] + (["--r-keys"] if cfg["collect_r_keys"] else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise StopLoop("repeated failure", f"collect failed: {(r.stdout + r.stderr)[-400:]}")
    rows = [x for x in read_jsonl(out) if x["item_id"] in set(rd["candidate_ids"])]
    if sorted(x["item_id"] for x in rows) != sorted(rd["candidate_ids"]):
        raise StopLoop("ledger mismatch", "the collected rows are not exactly the round's candidates")
    usable = [x["item_id"] for x in rows if x["status"] == "usable"]
    rd.update({"collected": str(out), "usable_ids": usable,
               "status_counts": {s: sum(x["status"] == s for x in rows) for s in sorted({x["status"] for x in rows})}})
    (state_dir(cfg) / f"r{led['round']}_usable_ids.txt").write_text("".join(i + "\n" for i in usable), encoding="utf-8", newline="\n")
    led["phase"] = "codex"
    log_event(led, f"round {led['round']}: collected {len(rows)} candidates: {rd['status_counts']}")


def codex_args(cfg):
    c = cfg["codex"]
    extra = []
    if c.get("workspace"):
        extra += ["--workspace", c["workspace"]]
    if c.get("keys"):
        extra += ["--keys", c["keys"]]
    return extra


def keys_for(cfg, label, date):
    keys_dir = Path(cfg["codex"].get("keys") or load_paths()["codex_keys"])
    return sorted(keys_dir.glob(f"{date}_{label}_*_key.json"))


def build(cfg, led, kind, label, ids_file, date):
    existing = keys_for(cfg, label, date)
    if not existing:
        r = subprocess.run([PY, CODEX, f"build-{kind}", "--items", cur(led)["collected"], "--manifest", str(manifest_path(cfg)),
                            "--only", str(ids_file), "--label", label, "--date", date,
                            "--batch-size", str(cfg["codex"]["batch_size"])] + codex_args(cfg),
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            raise StopLoop("repeated failure", f"build-{kind} failed: {(r.stdout + r.stderr)[-400:]}")
        crash_point("after_build")
        existing = keys_for(cfg, label, date)
    return {json.loads(k.read_text(encoding="utf-8"))["batch"]: {"state": "built", "key": str(k)} for k in existing}


def workspace(cfg):
    return Path(cfg["codex"].get("workspace") or load_paths()["codex_workspace"])


def run_batch(cfg, led, name):
    if led["codex_batches_run"] >= cfg["max_codex_batches"]:
        raise StopLoop("budget", f"Codex budget: {led['codex_batches_run']} of {cfg['max_codex_batches']} batches used")
    led["codex_batches_run"] += 1
    save_ledger(cfg, led)                          # counted before the call, so a crash cannot hide a run
    crash_point("before_codex_run")
    c = cfg["codex"]
    cmd = [PY, CODEX, "run", "--batch", str(workspace(cfg) / name), "--real", "--model", c["model"], "--effort", c["effort"],
           "--timeout", str(c["timeout_seconds"])] + (["--codex", c["cli"]] if c.get("cli") else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    run_json = workspace(cfg) / name / "run.json"
    accepted = run_json.exists() and json.loads(run_json.read_text(encoding="utf-8")).get("accepted_run")
    return bool(accepted and r.returncode == 0)


def import_batch(cfg, name):
    cmd = [PY, CODEX, "import", "--batch", str(workspace(cfg) / name)]
    if cfg["codex"].get("keys"):
        cmd += ["--keys", cfg["codex"]["keys"]]
    if cfg["codex"].get("out_root"):
        cmd += ["--out-root", cfg["codex"]["out_root"]]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return r.returncode == 0, (r.stdout + r.stderr)[-400:]


def results_dir(cfg):
    return Path(cfg["codex"].get("out_root") or (REPO / "data" / "verification_logs"))


def phase_codex(cfg, led, T):
    rd = cur(led)
    date = rd.setdefault("codex_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ids_file = state_dir(cfg) / f"r{led['round']}_usable_ids.txt"
    rd.setdefault("codex", {})
    if not rd["usable_ids"]:
        led["phase"] = "fill"
        return
    for kind in ("screen", "align"):
        label = f"loop-r{led['round']}-cand-{kind}"
        ck = rd["codex"].setdefault(kind, {"label": label, "batches": {}})
        if not ck["batches"]:
            ck["batches"] = build(cfg, led, kind, label, ids_file, date)
            save_ledger(cfg, led)
        for name in sorted(ck["batches"]):
            b = ck["batches"][name]
            if b["state"] == "imported":
                continue
            if b["state"] == "running":            # a crash during the call: the folder is no longer clean; retry path
                b["state"] = "rejected"
            if b["state"] == "built":
                b["state"] = "running"
                save_ledger(cfg, led)
                ok = run_batch(cfg, led, name)
                b["state"] = "accepted" if ok else "rejected"
                save_ledger(cfg, led)
            if b["state"] == "accepted":
                ok, msg = import_batch(cfg, name)
                b["state"] = "imported" if ok else "rejected"
                b["import_note"] = msg if not ok else None
                save_ledger(cfg, led)
            if b["state"] == "rejected":
                tries = b.get("retries", 0)
                if tries >= cfg["max_retries_per_step"]:
                    raise StopLoop("repeated failure", f"Codex batch {name} was rejected again after {tries} retry")
                key = json.loads(Path(b["key"]).read_text(encoding="utf-8"))
                retry_ids = state_dir(cfg) / f"{name}_retry_ids.txt"
                retry_ids.write_text("".join(v["item_id"] + "\n" for v in key["ids"].values()), encoding="utf-8", newline="\n")
                new = build(cfg, led, kind, f"{label}-retry{tries + 1}-{name.rsplit('_', 1)[-1]}", retry_ids, date)
                b["state"], b["replaced_by"] = "superseded", sorted(new)
                for n2, v2 in new.items():
                    v2["retries"] = tries + 1
                ck["batches"].update(new)
                save_ledger(cfg, led)
                log_event(led, f"Codex batch {name} rejected; retrying once as {sorted(new)}")
                return                                   # the next step runs the retry batch
    led["phase"] = "fill"
    log_event(led, f"round {led['round']}: Codex screen and alignment imported ({led['codex_batches_run']} batch runs so far)")


def all_results(cfg, led, kind):
    out = {}
    fname = "align_results.jsonl" if kind == "align" else "screen_results.jsonl"
    for rd in led["rounds"].values():
        ck = (rd.get("codex") or {}).get(kind)
        if not ck:
            continue
        for name, b in ck["batches"].items():
            if b["state"] != "imported":
                continue
            key = json.loads(Path(b["key"]).read_text(encoding="utf-8"))
            f = results_dir(cfg) / f"{key['date']}_codex_{key['label']}" / name / fname
            for r in read_jsonl(f):
                out[r["item_id"]] = {**r, "batch": name}
    return out


def all_candidates(led):
    rows = []
    for rd in led["rounds"].values():
        if rd.get("collected"):
            ids = set(rd["candidate_ids"])
            rows += [x for x in read_jsonl(rd["collected"]) if x["item_id"] in ids]
    return rows


def phase_fill(cfg, led, T):
    rd = cur(led)
    positions = read_jsonl(led["positions_current"])
    m = json.loads(manifest_path(cfg).read_text(encoding="utf-8"))
    out, still = gs.fill_match_subtopic(positions, rd["positions"], all_candidates(led), all_results(cfg, led, "screen"),
                                        all_results(cfg, led, "align"), m, original_slots(cfg), gs.excluded_spares(manifest_path(cfg)))
    f = state_dir(cfg) / f"positions_r{led['round']}.jsonl"
    f.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in out), encoding="utf-8", newline="\n")
    rd.update({"filled": sorted(set(rd["positions"]) - set(still)), "still_open": still, "positions_out": str(f)})
    led["positions_current"] = str(f)
    log_event(led, f"round {led['round']}: {len(rd['filled'])} of {len(rd['positions'])} open position(s) filled; "
                   f"{len(still)} still open")
    if not still:
        raise StopLoop("all filled", f"every open position has a screened, aligned same-subtopic question ({f})")
    if led["round"] >= cfg["rounds"]:
        write_packet(cfg, led)
        raise StopLoop("round limit", f"round {led['round']} finished with {len(still)} position(s) open; owner-review "
                                      f"packet written")
    led["round"] += 1
    led["rounds"][str(led["round"])] = {"positions": still, "started_utc": utc_now()}
    led["phase"] = "deal"


PHASES = {"deal": phase_deal, "upload": phase_upload, "submit": phase_submit, "wait": phase_wait,
          "download": phase_download, "collect": phase_collect, "codex": phase_codex, "fill": phase_fill}


# ------------------------------------------------------------------------------------------------------------------
# owner packet, stop report, run, status
# ------------------------------------------------------------------------------------------------------------------
def write_packet(cfg, led):
    rd = cur(led)
    scr, ali = all_results(cfg, led, "screen"), all_results(cfg, led, "align")
    orig = original_slots(cfg)
    prefix, width = variety.SETS["benchmark"]
    rows = []
    for k in rd["still_open"]:
        oid = f"{prefix}{k:0{width}d}"
        for c in sorted((c for c in all_candidates(led) if c["slot"].get("replaces") == oid), key=lambda c: c["item_id"]):
            it = c.get("item") or {}
            s, a = scr.get(c["item_id"], {}), ali.get(c["item_id"], {})
            rows.append({"position": k, "original_slot": oid, "subtopic": orig[oid]["subtopic"], "difficulty": orig[oid]["difficulty"],
                         "candidate": c["item_id"], "status": c["status"], "problems": "; ".join(c.get("problems") or []),
                         "verify": c.get("verify_status"), "question": it.get("question", ""),
                         "choices": " | ".join(it.get("choices") or []), "key": it.get("canonical_answer", ""),
                         "screen": s.get("verdict", "not screened"), "screen_reason": s.get("reason", ""),
                         "subtopic_verdict": a.get("subtopic_verdict", ""), "subtopic_reason": a.get("subtopic_reason", ""),
                         "difficulty_verdict": a.get("difficulty_verdict", ""), "difficulty_reason": a.get("difficulty_reason", ""),
                         "owner_choice (pick one per position)": ""})
    f = state_dir(cfg) / "owner_review_packet.csv"
    with open(f, "w", encoding="utf-8-sig", newline="") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    log_event(led, f"owner-review packet: {len(rows)} candidate(s) for {len(rd['still_open'])} position(s) -> {f}")


def write_stop(cfg, led, stop):
    used, unmeasured = gpu_committed(led)
    led["stopped"] = {"utc": utc_now(), "condition": stop.condition, "detail": stop.detail}
    rep = {"loop_id": cfg["loop_id"], **led["stopped"], "round": led["round"], "phase": led["phase"],
           "gpu_hours_measured": round(used, 3), "gpu_hours_unmeasured_charged": unmeasured,
           "codex_batch_runs": led["codex_batches_run"], "positions_current": led.get("positions_current"),
           "rounds": {n: {k: rd.get(k) for k in ("positions", "count", "status_counts", "filled", "still_open")}
                      for n, rd in led["rounds"].items()},
           "note": "The controller stops before the owner's hand corrections, the manual audit and the benchmark freeze."}
    (state_dir(cfg) / f"stop_report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json").write_text(
        json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    save_ledger(cfg, led)
    print(f"STOPPED ({stop.condition}): {stop.detail}")
    print(f"GPU-hours measured {used:.2f} (+{unmeasured:.1f} charged for unmeasured jobs) of {cfg['max_total_gpu_hours']}; "
          f"Codex batch runs {led['codex_batches_run']} of {cfg['max_codex_batches']}.")
    print(rep["note"])


def new_ledger(cfg):
    plan = open_positions(cfg)
    if not plan:
        sys.exit("no open positions; nothing to do")
    return {"version": LEDGER_VERSION, "loop_id": cfg["loop_id"], "config_sha256": cfg["_sha256"], "created_utc": utc_now(),
            "baseline_positions": cfg["inputs"]["positions"], "positions_current": cfg["inputs"]["positions"],
            "open_reasons": {str(k): v for k, v in sorted(plan.items())}, "round": 1, "phase": "deal",
            "rounds": {"1": {"positions": sorted(plan), "started_utc": utc_now()}}, "codex_batches_run": 0,
            "stopped": None, "history": []}


def cmd_run(cfg, args):
    T = Talon(cfg)
    led = None
    try:
        led = load_ledger(cfg)
        if led is None:
            led = new_ledger(cfg)
            log_event(led, f"loop {cfg['loop_id']} started: {len(led['rounds']['1']['positions'])} open position(s)")
            save_ledger(cfg, led)
        elif led.get("stopped") and led["stopped"]["condition"] in ("all filled", "round limit"):
            print(f"this loop already ended ({led['stopped']['condition']}); nothing to do")
            return 0
        led["stopped"] = None
        steps = 0
        while True:
            if args.max_steps and steps >= args.max_steps:
                save_ledger(cfg, led)
                print(f"paused after {steps} step(s) (--max-steps); run again to continue")
                return 0
            ph = led["phase"]
            result = PHASES[ph](cfg, led, T)
            save_ledger(cfg, led)
            steps += 1
            if ph == "wait" and result is False and led["phase"] == "wait":
                if args.once:
                    print("jobs still running; run again later")
                    return 0
                time.sleep(args.poll_seconds)
    except StopLoop as stop:
        if led is None:                       # stopped while reading the ledger: report without overwriting it
            print(f"STOPPED ({stop.condition}): {stop.detail}")
            return 3
        write_stop(cfg, led, stop)
        return 3


def cmd_status(cfg, args):
    led = load_ledger(cfg)
    if led is None:
        print("no ledger yet")
        return 0
    used, unmeasured = gpu_committed(led)
    print(json.dumps({"round": led["round"], "phase": led["phase"], "stopped": led.get("stopped"),
                      "gpu_hours_measured": round(used, 3), "gpu_hours_unmeasured": unmeasured,
                      "codex_batch_runs": led["codex_batches_run"],
                      "rounds": {n: {k: rd.get(k) for k in ("count", "status_counts", "filled", "still_open")}
                                 for n, rd in led["rounds"].items()}}, indent=1))
    return 0


def cmd_amend_budget(cfg, args):
    """Accept a configuration whose ONLY change is max_total_gpu_hours (owner-approved amendment, logged in the ledger).
    --old-config is the previous version (for example `git show HEAD:configs/replacement_loop.yaml`); its SHA-256 must be
    the one the ledger recorded, and every other setting must be identical."""
    led = json.loads((state_dir(cfg) / "ledger.json").read_text(encoding="utf-8"))
    old_text = Path(args.old_config).read_text(encoding="utf-8")
    old_sha = hashlib.sha256(old_text.encode("utf-8")).hexdigest()
    if old_sha != led["config_sha256"]:
        sys.exit("--old-config is not the configuration this loop started with (SHA-256 differs); nothing changed")
    old, new = yaml.safe_load(old_text), yaml.safe_load(Path(cfg["_path"]).read_text(encoding="utf-8"))
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    if changed != ["max_total_gpu_hours"]:
        sys.exit(f"only max_total_gpu_hours may change in an amendment; changed: {changed}. Nothing changed.")
    if new["max_total_gpu_hours"] < old["max_total_gpu_hours"] - 1e-9 and gpu_committed(led)[0] > new["max_total_gpu_hours"]:
        sys.exit("the new budget is below the hours already used; nothing changed")
    led.setdefault("amendments", []).append({"utc": utc_now(), "field": "max_total_gpu_hours",
                                             "old": old["max_total_gpu_hours"], "new": new["max_total_gpu_hours"],
                                             "old_config_sha256": old_sha, "new_config_sha256": cfg["_sha256"],
                                             "reason": args.reason})
    led["config_sha256"] = cfg["_sha256"]
    log_event(led, f"configuration amended: max_total_gpu_hours {old['max_total_gpu_hours']} -> "
                   f"{new['max_total_gpu_hours']} ({args.reason})")
    save_ledger(cfg, led)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "run", "status", "amend-budget"])
    ap.add_argument("--old-config", help="amend-budget: the configuration version the loop started with")
    ap.add_argument("--reason", default="", help="amend-budget: why (recorded in the ledger)")
    ap.add_argument("--config", default=str(REPO / "configs" / "replacement_loop.yaml"))
    ap.add_argument("--poll-seconds", type=float, default=300)
    ap.add_argument("--once", action="store_true", help="return instead of sleeping while jobs run")
    ap.add_argument("--max-steps", type=int, default=0)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    return {"plan": lambda: cmd_plan(cfg, args) and 0, "run": lambda: cmd_run(cfg, args),
            "status": lambda: cmd_status(cfg, args), "amend-budget": lambda: cmd_amend_budget(cfg, args)}[args.cmd]()


if __name__ == "__main__":
    sys.exit(main() or 0)
