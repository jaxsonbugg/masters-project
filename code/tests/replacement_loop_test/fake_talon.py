"""A fake Talon for the replacement-loop tests: stands in for `ssh` and `scp`. NOT A MODEL OF SLURM; it only implements the
exact command shapes replacement_loop.py is allowed to send, over a folder that plays the Talon home directory.

  python fake_talon.py ssh <host> <command>
  python fake_talon.py scp [-o X] [-r] <src> <dst>        (one side is <host>:<path>)

Paths under /fake/talon_project are mapped to $FAKE_TALON_DIR. A submitted stage G job runs at once: the real
code/generation/generate_set.py run is called against the fake vLLM server at $FAKE_VLLM_URL, then a job log and a result file
are written the way serve_and_run.sh writes them. The job is shown as RUNNING by squeue for $FAKE_TALON_RUNNING_POLLS polls (1).
Every command is appended to $FAKE_TALON_DIR/commands.log.

Failure switches (environment):
  FAKE_TALON_FAIL_TAG=<tag>        every job of this tag ends with INFRA=FAIL
  FAKE_TALON_UNFINISHED_ONCE=<tag> the first job of this tag stops after 1 slot (GEN_COMPLETE=no)
  FAKE_TALON_LOSE_ANSWER=<tag>     the first submission of this tag is made, but the connection drops (exit 255, no output)
  FAKE_TALON_UNREADABLE_LOG=1      `cat .../submit_log.txt` fails (exit 1)
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ["FAKE_TALON_DIR"])
PREFIX = "/fake/talon_project"
REPO_CODE = Path(__file__).resolve().parents[3]
STATE = ROOT / "fake_state.json"


def m(path):
    p = path.replace("~/talon_project", PREFIX)
    if not p.startswith(PREFIX):
        sys.exit(f"fake talon: path outside the fake home: {path}")
    return Path(str(ROOT) + p[len(PREFIX):])


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"next_job": 500, "jobs": {}, "tag_jobs": {}, "once": []}


def save(st):
    STATE.write_text(json.dumps(st, indent=1))


def log(line):
    with open(ROOT / "commands.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def once(st, key):
    if key in st["once"]:
        return False
    st["once"].append(key)
    return True


def submit(cmd):
    env = dict(re.findall(r"(\w+)=(\S+)", cmd.split("&&", 1)[1].split("bash", 1)[0]))
    repo = ROOT / "repo"
    first, count = int(env["GEN_FIRST"]), int(env["GEN_COUNT"])
    k, K = env["GEN_SHARD"].split("/")
    tag = f"benchmark-benchmark-p{first}n{count}-{k}of{K}"
    name = f"qt_talon_G_{tag}"
    st = state()
    if any(j["name"] == name and j["polls_left"] > 0 for j in st["jobs"].values()):
        print(f"STOP: a {name} job of yours is already in the queue.", file=sys.stderr)
        sys.exit(2)
    job = str(st["next_job"])
    st["next_job"] += 2
    st["jobs"][job] = {"name": name, "polls_left": int(os.environ.get("FAKE_TALON_RUNNING_POLLS", "1"))}
    with open(ROOT / "submit_log.txt", "a") as fh:
        fh.write(f"JOB={job} KIND=generate SUBMITTED_UTC={utc()} LAYOUT=1/1/1/16/16/20480 GEN={tag}\n")
    start = utc()
    if os.environ.get("FAKE_TALON_HOURS"):           # pretend the job ran this long (budget tests)
        from datetime import timedelta
        start = (datetime.now(timezone.utc) - timedelta(hours=float(os.environ["FAKE_TALON_HOURS"]))).strftime("%Y-%m-%dT%H:%M:%SZ")
    outputs = ROOT / "teacher_outputs"
    before = {d.name for d in outputs.glob("*")}
    extra = ["--limit", "1"] if os.environ.get("FAKE_TALON_UNFINISHED_ONCE") == tag and once(st, "unf:" + tag) else []
    r = subprocess.run([sys.executable, str(REPO_CODE / "code" / "generation" / "generate_set.py"), "run", "--backend", "talon",
                        "--base-url", os.environ["FAKE_VLLM_URL"], "--slots", str(repo / env["GEN_SLOTS"]), "--prompt", "benchmark",
                        "--first", str(first), "--count", str(count), "--shard", f"{k}/{K}", "--out-root", str(outputs),
                        "--retry-wait", "0.05", "--meta", f"job={job}", *extra], capture_output=True, text=True, encoding="utf-8")
    new = sorted({d.name for d in outputs.glob("*") if d.is_dir()} - before)
    run_dir = new[0] if new else st["tag_jobs"].get(tag, {}).get("run_dir")
    if run_dir:
        st["tag_jobs"].setdefault(tag, {})["run_dir"] = run_dir
    v = subprocess.run([sys.executable, str(REPO_CODE / "code" / "generation" / "generate_set.py"), "validate", "--run",
                        str(outputs / run_dir)], capture_output=True, text=True, encoding="utf-8") if run_dir else None
    complete = "yes" if (v and v.returncode in (0, 2)) else "no"     # validate: 0 clean, 1 infra, 2 quality only, 3 unfinished
    infra = "FAIL" if os.environ.get("FAKE_TALON_FAIL_TAG") == tag or r.returncode not in (0, 1, 3) else "PASS"
    (repo / f"{name}_{job}.log").write_text(f"header\n=== node fakenode01, job {job}, stage G, {start} ===\n{r.stdout[-2000:]}\n")
    res = ROOT / "teacher_outputs" / "stage_results" / f"stageG_{tag}_job{job}.txt"
    res.parent.mkdir(parents=True, exist_ok=True)
    res.write_text(f"RESULT={'PASS' if infra == 'PASS' else 'FAIL'}\nINFRA={infra}\nJOB={job}\nNODE=fakenode01\nUTC={utc()}\n"
                   f"RUN_DIR={PREFIX}/teacher_outputs/{run_dir}\nGEN_TAG={tag}\nGEN_COMPLETE={complete}\n"
                   f"GEN_RESULT=fake rc={r.returncode}\n")
    lose = os.environ.get("FAKE_TALON_LOSE_ANSWER") == tag and once(st, "lose:" + tag)
    save(st)
    if lose:
        sys.exit(255)
    print(f"  Submitted batch job {job}")


def ssh(cmd):
    log("SSH " + cmd)
    st = state()
    if "submit_pipeline.sh generate" in cmd:
        return submit(cmd)
    if cmd.startswith("squeue"):
        name = re.search(r"-n (\S+)", cmd).group(1)
        for job, j in st["jobs"].items():
            if j["name"] == name and j["polls_left"] > 0:
                print(f"{job},RUNNING")
                j["polls_left"] -= 1
        save(st)
        return
    if cmd.startswith("sha256sum"):
        import hashlib
        for part in cmd.split(";"):
            for p in part.split()[1:]:
                f = m(p)
                if f.exists():
                    print(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {p}")
        return
    if cmd.startswith("cat ") and cmd.endswith("submit_log.txt"):
        if os.environ.get("FAKE_TALON_UNREADABLE_LOG") == "1":
            print("cat: Permission denied", file=sys.stderr)
            sys.exit(1)
        f = m(cmd[4:])
        print(f.read_text() if f.exists() else "", end="")
        return
    if cmd.startswith("cat "):
        f = m(cmd[4:])
        if not f.exists():
            sys.exit(1)
        print(f.read_text(), end="")
        return
    if cmd.startswith("head -n 40 "):
        f = m(cmd[len("head -n 40 "):])
        if not f.exists():
            sys.exit(1)
        print("\n".join(f.read_text().splitlines()[:40]))
        return
    if cmd.startswith("ls -1 "):
        for p in cmd[6:].split():
            d = m(p)
            if d.exists():
                for x in sorted(os.listdir(d)):
                    print(x)
        return
    print(f"fake talon: unknown command {cmd}", file=sys.stderr)
    sys.exit(127)


def scp(args):
    args = [a for a in args if a not in ("-o", "BatchMode=yes")]
    rec = "-r" in args
    src, dst = [a for a in args if a != "-r"]
    log(f"SCP {'-r ' if rec else ''}{src} {dst}")
    if ":" in src and not re.match(r"^[A-Za-z]:\\", src):
        s = m(src.split(":", 1)[1])
        if not s.exists():
            print(f"scp: {src}: No such file", file=sys.stderr)
            sys.exit(1)
        d = Path(dst)
        if s.is_dir():
            shutil.copytree(s, d / s.name if d.is_dir() else d)
        else:
            shutil.copy2(s, d / s.name if d.is_dir() else d)
    else:
        d = m(dst.split(":", 1)[1])
        shutil.copy2(src, d)


if __name__ == "__main__":
    if sys.argv[1] == "ssh":
        ssh(sys.argv[3])
    else:
        scp(sys.argv[2:])
