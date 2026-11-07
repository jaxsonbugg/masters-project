"""
test_regression.py - check that the shared benchmark functions still behave exactly as recorded.

WHAT IT DOES
Takes a fresh snapshot with capture.py and compares it, part by part, with a saved snapshot (by default
snapshot_synthetic.json in this folder). Prints PASS or FAIL for every part and, for a failure, the first
difference. Exit code 0 means everything matched. See capture.py for what a snapshot contains and why.

HOW TO RUN (with the project's Python; R must be installed)
  python test_regression.py                                          against snapshot_synthetic.json
  python test_regression.py --snapshot <saved.json> --items <items.jsonl>   against a snapshot that included an items file
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import capture  # noqa: E402

FAILS = []


def first_diff(a, b, path="$"):
    if type(a) is not type(b):
        return f"{path}: {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}: present only in the {'saved' if k in a else 'new'} snapshot"
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: saved {a!r:.200} vs new {b!r:.200}"


def chk(name, saved, new):
    d = first_diff(saved, new)
    print(("PASS " if d is None else "FAIL ") + name + ("" if d is None else f"\n     first difference: {d}"))
    if d is not None:
        FAILS.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=str(HERE / "snapshot_synthetic.json"))
    ap.add_argument("--items", default=None)
    args = ap.parse_args()
    saved = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    # Round-trip the new snapshot through JSON so tuples and lists compare the same way as in the saved file.
    new = json.loads(json.dumps(capture.snapshot(args.items), ensure_ascii=False, sort_keys=True))
    for key in sorted(saved):
        if key in ("replies", "items"):
            continue
        chk(key, saved[key], new.get(key))
    for s, n in zip(saved["replies"], new["replies"]):
        chk(f"reply case: {s['case']}", s, n)
    chk("number of reply cases", len(saved["replies"]), len(new["replies"]))
    if "items" in saved:
        for s, n in zip(saved["items"], new.get("items", [])):
            chk(f"item {s['item_id']}", s, n)
        chk("number of items", len(saved["items"]), len(new.get("items", [])))
    extra = sorted(set(new) - set(saved))
    chk("no unexpected new parts", [], extra)
    total = sum(1 for _ in saved) + len(saved["replies"]) + len(saved.get("items", []))
    print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED'} ({total} parts compared)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
