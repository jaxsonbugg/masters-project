"""
rounding_fixes.py - the owner's hand corrections of small printed-number errors in benchmark questions.

WHAT THIS IS AND WHY (owner's decisions, 2026-11-21; plan "resolve the Codex flags")
The Codex screen flagged 65 benchmark questions whose printed statistical output has numbers that do not quite fit
together (usually a p-value that does not match its own test statistic and degrees of freedom). Jaxson fixes these by hand,
all at once at the end; Claude writes no benchmark text. This tool does the arithmetic and the bookkeeping:

  fix-sheet        For each such question, find the printed number that does not fit and recompute it in the R sandbox, by
                   the owner's rule: the inputs, estimates, test statistic and degrees of freedom stay as printed; only the
                   final value(s) are recomputed (the p-value or the interval); if the statistic itself does not match its
                   inputs (for example t is not estimate / standard error), it is recomputed from them first.
                   Each question is classified:
                     display_only    a printed number is corrected; the key and the conclusion do not change;
                     reference_key   the key itself must be retyped (for a number question whose key is the corrected
                                     value); listed separately and explicitly, never applied silently;
                     substantive     the corrected value would cross a significance threshold (0.1, 0.05, 0.01, 0.001),
                                     so the conclusion or the key could change: REPLACED, never fixed (owner's rule);
                     not_computable  no standard printout could be read, or the inconsistency cannot be recomputed from
                                     what is printed (for example a Tukey table without group sizes): REPLACED.
                   Output: rounding_fixes.csv (one row per correction: the exact current text, the suggested corrected
                   text, the R computation, and an empty new_text column the owner fills) and fix_classification.json.
  apply-owner-fixes  Apply every new_text the owner typed in ONE step (all or nothing: each current text must appear exactly
                   once, every row must be filled), record the old and new text, and re-run the format checks, the printout
                   check and R (keys and verify) on the edited questions. The edited questions are then screened by Codex.

EXAMPLE (BM0004): "LRT = 7.823, df = 1, p-value = 0.005214". R: pchisq(7.823, 1, lower.tail = FALSE) = 0.005159. The p-value
is the final value, so it is corrected: suggested "LRT = 7.823, df = 1, p-value = 0.005159". 0.005214 and 0.005159 are on the
same side of every threshold, so the conclusion ("significant at 0.01") is unchanged: display_only.
"""

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
import output_check as oc  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

THRESHOLDS = (0.1, 0.05, 0.01, 0.001)
NUM, PVAL = oc.NUM, oc.PVAL


def fmt_like(old_text, value):
    """Format `value` the way `old_text` was printed: the same number of decimals, or the same mantissa digits in
    scientific notation. '0.02838' -> '0.02826'; '1.2e-07' -> '3.9e-07'."""
    t = old_text.strip()
    m = re.fullmatch(r"-?\d+(?:\.(\d+))?[eE]([-+]?\d+)", t)
    if m:
        dec = len(m.group(1) or "")
        out = f"{value:.{dec}e}"
        mant, exp = out.split("e")
        return f"{mant}e{int(exp):03d}" if t.lower().split("e")[1].startswith(("-0", "+0")) and len(t.split("e")[1].lstrip("+-")) == 3 \
            else f"{mant}e{'-' if int(exp) < 0 else ''}{abs(int(exp)):02d}"
    dec = len(t.split(".")[1]) if "." in t else 0
    return f"{value:.{dec}f}"


def is_rounding_of(printed, half, value):
    """Is `printed` (with half of its last unit, `half`) a correct rounding of `value`? A purely relative tolerance, so it
    also works for very small p-values such as 1.2e-16 (an absolute tolerance would call 1.9e-17 a match)."""
    return abs(printed - value) <= half * (1 + 1e-9) + abs(value) * 1e-12


def stated_levels(question):
    """Significance levels the question names ('at the 10% level', 'alpha = 0.02'), added to the standard thresholds."""
    out = set()
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(?:significance|level)", question, flags=re.I):
        out.add(float(m.group(1)) / 100)
    for m in re.finditer(r"(?:alpha|α|significance level(?: of)?)\s*=?\s*(0?\.\d+)", question, flags=re.I):
        out.add(float(m.group(1)))
    return out


def crosses(p_old, p_new, extra=()):
    lo, hi = sorted((p_old, p_new))
    return [t for t in sorted(set(THRESHOLDS) | set(extra)) if lo < t <= hi or lo <= t < hi]


class Finding:
    def __init__(self, kind, old, new, value_expr, explanation, p_old=None, p_new=None):
        self.kind, self.old, self.new, self.expr, self.explanation = kind, old, new, value_expr, explanation
        self.p_old, self.p_new = p_old, p_new


def _p_line_findings(text):
    """'STAT = x, df = d, p-value = p' lines (t, X-squared, LRT, chi-squared) and 'F = x, num df = a, denom df = b, p-value = p'."""
    out = []
    for m in re.finditer(rf"\b(t|X-squared|LRT|LR|Chisq|chi-squared|Chi-squared|G)\s*=\s*({NUM}),\s*df\s*=\s*({NUM}),\s*p-value\s*=\s*({NUM})", text):
        stat, x, df, p = m.group(1), m.group(2), m.group(3), m.group(4)
        xv, dfv, pv = float(x), float(df), float(p)
        if stat == "t":
            alt = re.search(r"alternative hypothesis:\s*true .*? is (not equal to|greater than|less than)", text[m.end():m.end() + 400])
            side = alt.group(1) if alt else "not equal to"
            if side == "not equal to":
                expr = f"2 * pt(-abs({x}), {df})"
            elif (xv > 0) == (side == "greater than"):
                expr = f"pt(-abs({x}), {df})"
            else:
                expr = f"1 - pt(-abs({x}), {df})"
        else:
            expr = f"pchisq({x}, {df}, lower.tail = FALSE)"
        out.append((m.group(0), p, expr, f"{stat} = {x} on {df} df"))
    for m in re.finditer(rf"\bF\s*=\s*({NUM}),\s*(?:num df|df1)\s*=\s*({NUM}),\s*(?:denom df|den df|df2)\s*=\s*({NUM}),"
                         rf"\s*p-value\s*=\s*({NUM})", text, flags=re.I):
        f, a, b = m.group(1), m.group(2), m.group(3)
        after = text[m.end():m.end() + 300]
        if "ratio of variances" in after:            # var.test: the tail depends on the alternative hypothesis
            alt = re.search(r"is (not equal to|greater than|less than)", after)
            side = alt.group(1) if alt else "not equal to"
            expr = {"not equal to": f"2 * min(pf({f}, {a}, {b}), pf({f}, {a}, {b}, lower.tail = FALSE))",
                    "greater than": f"pf({f}, {a}, {b}, lower.tail = FALSE)", "less than": f"pf({f}, {a}, {b})"}[side]
        else:
            expr = f"pf({f}, {a}, {b}, lower.tail = FALSE)"
        out.append((m.group(0), m.group(4), expr, f"F = {f} on {a} and {b} df"))
    for m in re.finditer(rf"\bchi2\(({NUM})\)\s*=\s*({NUM}),\s*p-value\s*=\s*({NUM})", text, flags=re.I):
        out.append((m.group(0), m.group(3), f"pchisq({m.group(2)}, {m.group(1)}, lower.tail = FALSE)",
                    f"chi-squared = {m.group(2)} on {m.group(1)} df"))
    m = re.search(rf"statistic:\s*({NUM})\s*\n\s*Degrees of freedom:\s*({NUM})\s*\n[^\n]*p-value:\s*({NUM})", text, flags=re.I)
    if m:
        out.append((m.group(0).split("\n")[-1].strip(), m.group(3), f"pchisq({m.group(1)}, {m.group(2)}, lower.tail = FALSE)",
                    f"chi-squared statistic {m.group(1)} on {m.group(2)} df"))
    for m in re.finditer(rf"F-statistic:\s*({NUM})\s+on\s+({NUM})\s+and\s+({NUM})\s+DF,\s*p-value:\s*({NUM})", text):
        out.append((m.group(0), m.group(4), f"pf({m.group(1)}, {m.group(2)}, {m.group(3)}, lower.tail = FALSE)",
                    f"F = {m.group(1)} on {m.group(2)} and {m.group(3)} df"))
    return out


def _table_findings(text):
    """Rows of ANOVA tables (Df ... F value Pr(>F)), analysis-of-deviance tables (... Df Deviance Pr(>Chi)) and coefficient
    tables (t or z value, Pr(>|t|) / Pr(>|z|)) whose p-value can be recomputed from the row and the printed df."""
    out = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"Df\s+Sum Sq\s+Mean Sq\s+F value\s+Pr\(>F\)", line):
            rows, resid = [], None
            for l in lines[i + 1:]:
                r = re.match(rf"\s*(\S+)\s+({NUM})\s+({NUM})\s+({NUM})(?:\s+({NUM})\s+({NUM}))?", l)
                if not r:
                    break
                if r.group(1).lower().startswith("residual"):
                    resid = r
                elif r.group(5):
                    rows.append((l, r))
            if resid:
                for l, r in rows:
                    out.append((l.strip(), r.group(6), f"pf({r.group(5)}, {r.group(2)}, {resid.group(2)}, lower.tail = FALSE)",
                                f"F = {r.group(5)} on {r.group(2)} and {resid.group(2)} df"))
        if re.search(r"Res\.Df\s+RSS\s+Df\s+Sum of Sq\s+F\s+Pr\(>F\)", line):
            for l in lines[i + 1:]:
                if not l.strip() or l.strip().startswith(("---", "Signif")):
                    break
                r = re.match(rf"\s*\d+\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})", l)
                if r and "<" not in l:
                    out.append((l.strip(), r.group(6), f"pf({r.group(5)}, {r.group(3)}, {r.group(1)}, lower.tail = FALSE)",
                                f"F = {r.group(5)} on {r.group(3)} and {r.group(1)} df"))
        if re.search(r"Deviance\s+Pr\(>Chi\)|Pr\(>Chi\)", line) and "Df" in line:
            for l in lines[i + 1:]:
                nums = re.findall(rf"(?<![\w.]){NUM}(?![\w.])", l)
                if not l.strip() or l.strip().startswith(("---", "Signif")):
                    break
                if "<" in l:
                    continue         # a bound such as "< 2.2e-16" is not a value to recompute
                if len(nums) >= 5:   # Resid.Df Resid.Dev Df Deviance Pr(>Chi)  (the row number may come first)
                    df, dev, p = nums[-3], nums[-2], nums[-1]
                    out.append((l.strip(), p, f"pchisq({dev}, {df}, lower.tail = FALSE)", f"deviance {dev} on {df} df"))
        hm = re.search(r"Estimate\s+Std\. Error\s+([tz]) value\s+Pr\(>\|[tz]\|\)", line)
        if hm:
            kind = hm.group(1)
            dfm = re.search(rf"on\s+({NUM})\s+degrees of freedom", text)
            for l in lines[i + 1:]:
                r = re.match(rf"\s*(\S+)\s+({NUM})\s+({NUM})\s+({NUM})\s+({PVAL})", l)
                if not r:
                    break
                if r.group(5).lstrip().startswith("<"):
                    continue
                if kind == "z":
                    out.append((l.strip(), r.group(5), f"2 * pnorm(-abs({r.group(4)}))", f"z = {r.group(4)}"))
                elif dfm:
                    out.append((l.strip(), r.group(5), f"2 * pt(-abs({r.group(4)}), {dfm.group(1)})",
                                f"t = {r.group(4)} on {dfm.group(1)} df"))
    return out


def r_value(expr, rscript):
    import generate_benchmark as gb
    ok, out = gb.run_r(f"options(digits = 15); cat({expr})", rscript)
    return [float(x) for x in out.split()] if ok else None


def statistic_fixes(question):
    """Coefficient rows whose printed t or z value is not estimate / standard error (both as printed, with their rounding):
    {old row: (old stat text, new stat text)}. Owner's rule: the statistic is recomputed first, then its p-value."""
    out = {}
    for m in re.finditer(rf"(?m)^\s*\S+\s+({NUM})\s+({NUM})\s+({NUM})\s+({PVAL})", question):
        est, se, st = m.group(1), m.group(2), m.group(3)
        try:
            (e, he), (s_, hs), (t, ht) = oc.num(est), oc.num(se), oc.num(st)
        except ValueError:
            continue
        if s_ - hs <= 0 or not re.search(r"Estimate\s+Std\. Error\s+[tz] value", question):
            continue
        lo, hi = oc.corners(lambda a, b: a / b, (e - he, e + he), (s_ - hs, s_ + hs))
        if t + ht < lo * (1 - 1e-9) - 1e-12 or t - ht > hi * (1 + 1e-9) + 1e-12:
            out[m.group(0).strip()] = (st, fmt_like(st, e / s_))
    return out


def var_test_interval(question, rscript):
    """var.test: the printed confidence interval recomputed from the printed F and df (it is F / qf(upper), F / qf(lower))."""
    m = re.search(rf"\bF\s*=\s*({NUM}),\s*(?:num df|df1)\s*=\s*({NUM}),\s*(?:denom df|den df|df2)\s*=\s*({NUM}),[^\n]*\n"
                  rf"alternative hypothesis: true ratio of variances is not equal to 1\s*\n\s*(\d+) percent confidence interval:\s*\n"
                  rf"(\s*({NUM})\s+({NUM}))", question)
    if not m:
        return []
    f, a, b, lev, line, lo_t, hi_t = m.groups()
    q = (1 - float(lev) / 100) / 2
    vals = r_value(f"c({f} / qf({1 - q}, {a}, {b}), {f} / qf({q}, {a}, {b}))", rscript)
    if not vals:
        return []
    (lo, hlo), (hi, hhi) = oc.num(lo_t), oc.num(hi_t)
    if is_rounding_of(lo, hlo, vals[0]) and is_rounding_of(hi, hhi, vals[1]):
        return []
    new_line = line.replace(lo_t, fmt_like(lo_t, vals[0]), 1).replace(hi_t, fmt_like(hi_t, vals[1]), 1)
    return [Finding("interval", line.strip(), new_line.strip(), f"F / qf(...) with F = {f}, df = {a}, {b}",
                    f"the {lev}% interval for the variance ratio from F = {f} on {a} and {b} df is "
                    f"({vals[0]:.6g}, {vals[1]:.6g}); printed ({lo_t}, {hi_t})")]


def find_corrections(question, rscript):
    """[Finding] for the question; [] if nothing recomputable is inconsistent."""
    import generate_benchmark as gb
    found = []
    stat_fix = statistic_fixes(question)
    for old_line, p_text, expr, desc in _p_line_findings(question) + _table_findings(question):
        if old_line in stat_fix:                          # recompute the statistic first, then the p-value from it
            old_st, new_st = stat_fix[old_line]
            expr = expr.replace(old_st, new_st)
            desc = f"{desc} (statistic recomputed as estimate / standard error: {old_st} -> {new_st})"
            old_line_new = re.sub(rf"(?<![\w.]){re.escape(old_st)}(?![\w.])", new_st, old_line, count=1)
        else:
            old_line_new = old_line
        ok, out = gb.run_r(f"options(digits = 15); cat({expr})", rscript)
        if not ok:
            continue
        p_new = float(out.strip().split()[-1])
        p_old, half = oc.num(p_text)
        if is_rounding_of(p_old, half, p_new) and old_line not in stat_fix:
            continue                                       # the printed value is a correct rounding of R's value
        if old_line in stat_fix and is_rounding_of(p_old, half, p_new):
            found.append(Finding("statistic", old_line, old_line_new, expr, desc, p_old, p_new))
            continue
        new_p_text = fmt_like(p_text, p_new)
        head, _, tail = old_line_new.rpartition(p_text)
        new_line = head + new_p_text + tail
        found.append(Finding("p_value", old_line, new_line, expr, f"{desc} gives p = {p_new:.6g} (R: {expr}); printed {p_text}",
                             p_old, p_new))
    found += var_test_interval(question, rscript)
    return found


def classify(item, findings):
    if not findings:
        return "not_computable"
    extra = stated_levels(item.get("question", ""))
    for f in findings:
        if f.p_old is not None and crosses(f.p_old, f.p_new, extra):
            return "substantive"
    key = (item.get("canonical_answer") or "").strip()
    if item.get("answer_type") == "number" and any(key and key in f.old.split() for f in findings):
        return "reference_key"
    return "display_only"


def cmd_fix_sheet(args):
    import generate_benchmark as gb
    rscript = gb.rscript_path()
    flags = [r for r in csv.DictReader(open(args.flags, encoding="utf-8-sig")) if r["group"].startswith("1")]
    items = {json.loads(l)["item_id"]: json.loads(l) for l in Path(args.items).read_text(encoding="utf-8").splitlines() if l.strip()}
    rows, classes = [], {}
    for fl in flags:
        pos = items[fl["item_id"]]
        it = pos["item"]
        findings = find_corrections(it["question"], rscript)
        cls = classify(it, findings)
        classes[fl["item_id"]] = {"position": pos.get("position"), "class": cls, "codex_reason": fl["codex_reason"],
                                  "findings": [f.explanation for f in findings]}
        if cls in ("display_only", "reference_key"):
            for f in findings:
                if it["question"].count(f.old) != 1:
                    classes[fl["item_id"]]["class"] = "not_computable"
                    classes[fl["item_id"]]["note"] = "the line to correct is not unique in the question"
                    break
            else:
                for f in findings:
                    rows.append({"position": pos.get("position"), "item_id": fl["item_id"], "kind": cls, "field": "question",
                                 "current_text": f.old, "suggested_text": f.new, "computation": f.explanation,
                                 "conclusion_unchanged": "yes", "new_text": "", "owner_note": ""})
                if cls == "reference_key":
                    p_new = findings[0].p_new
                    rows.append({"position": pos.get("position"), "item_id": fl["item_id"], "kind": "reference_key", "field": "key",
                                 "current_text": it["canonical_answer"], "suggested_text": fmt_like(it["canonical_answer"], p_new),
                                 "computation": findings[0].explanation, "conclusion_unchanged": "yes", "new_text": "", "owner_note": ""})
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "rounding_fixes.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["position", "item_id", "kind", "field", "current_text", "suggested_text", "computation",
                                           "conclusion_unchanged", "new_text", "owner_note"])
        w.writeheader()
        w.writerows(rows)
    (out / "fix_classification.json").write_text(json.dumps(classes, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    counts = {}
    for c in classes.values():
        counts[c["class"]] = counts.get(c["class"], 0) + 1
    print(json.dumps({"flags": len(flags), "classes": counts, "sheet_rows": len(rows)}, indent=1))
    print(f"-> {out / 'rounding_fixes.csv'} and {out / 'fix_classification.json'}; substantive and not_computable go to replacement")


def apply_fixes(items_by_id, sheet_rows):
    """All or nothing: returns (changed item ids, problems). Items are changed in place only if there are no problems."""
    problems, plan = [], {}
    for r in sheet_rows:
        if not (r.get("new_text") or "").strip():
            problems.append(f"{r['item_id']}: new_text is empty (every row must be filled before anything is applied)")
            continue
        it = items_by_id.get(r["item_id"])
        if it is None:
            problems.append(f"{r['item_id']}: not in the items file")
            continue
        field = "canonical_answer" if r["field"] == "key" else "question"
        cur = it["item"][field]
        if field == "question" and cur.count(r["current_text"]) != 1:
            problems.append(f"{r['item_id']}: the current text does not appear exactly once in the question")
        if field == "canonical_answer" and cur.strip() != r["current_text"].strip():
            problems.append(f"{r['item_id']}: the current key is not {r['current_text']!r}")
        plan.setdefault(r["item_id"], []).append((field, r["current_text"], r["new_text"], r["kind"]))
    if problems:
        return [], problems
    for iid, edits in plan.items():
        it = items_by_id[iid]
        hist = it.setdefault("owner_fixes", [])
        for field, old, new, kind in edits:
            if field == "question":
                it["item"]["question"] = it["item"]["question"].replace(old, new, 1)
            else:
                it["item"]["canonical_answer"] = new.strip()
            hist.append({"field": field, "kind": kind, "old": old, "new": new})
        it["owner_fixed"] = True
    return sorted(plan), []


def cmd_apply(args):
    import generate_benchmark as gb
    import output_check
    import set_prompts as sp
    rows = list(csv.DictReader(open(args.sheet, encoding="utf-8-sig")))
    items = [json.loads(l) for l in Path(args.items).read_text(encoding="utf-8").splitlines() if l.strip()]
    by = {r["item_id"]: r for r in items}
    changed, problems = apply_fixes(by, rows)
    if problems:
        print("NOTHING APPLIED:")
        for p in problems:
            print("  ", p)
        sys.exit(2)
    rscript = gb.rscript_path()
    report = {}
    for iid in changed:
        r = by[iid]
        fmt = sp.check_benchmark_item(r["item"], r["slot"], version="benchmark-v8")
        pc = output_check.check(r["item"]["question"])
        status, issues, _ = gb.verify_item(r["item"], rscript)
        report[iid] = {"format": fmt, "printout": pc, "verify": [status] + issues}
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in items), encoding="utf-8", newline="\n")
    Path(args.out + ".changed.txt").write_text("".join(i + "\n" for i in changed), encoding="utf-8", newline="\n")
    Path(args.out + ".checks.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    bad = {i: v for i, v in report.items() if v["format"] or v["printout"] or v["verify"][0] == "FLAGGED"}
    print(f"applied {len(changed)} edited question(s) -> {args.out}; {len(bad)} still have a check finding")
    for i, v in bad.items():
        print("  ", i, v)
    print(f"next: Codex screen and alignment of the edited questions ({args.out}.changed.txt)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fix-sheet")
    p.add_argument("--flags", required=True, help="screen_flags.csv from codex_batch.py report")
    p.add_argument("--items", required=True, help="benchmark positions (fill-bench output)")
    p.add_argument("--out-dir", required=True)
    p = sub.add_parser("apply-owner-fixes")
    p.add_argument("--sheet", required=True)
    p.add_argument("--items", required=True)
    p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    {"fix-sheet": cmd_fix_sheet, "apply-owner-fixes": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    main()
