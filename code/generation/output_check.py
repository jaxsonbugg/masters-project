"""
output_check.py - is the statistical software output printed in a benchmark question consistent with itself?

WHAT THIS IS AND WHY (Jaxson's decision of 2026-11-20; docs/methodology/workflow.md Section 4, safeguard 6)
Output-interpretation questions show a printout (a t-test, a regression table, an ANOVA table, a chi-square test) and ask
what it means. The teacher writes those numbers itself, and they do not always agree with each other: in the Claude-era
trials 6 of 18 such items had small inconsistencies, and in the stage G smoke test (Talon job 291) SM0010 printed a 95%
confidence interval of 0.992 to 1.408 for a coefficient whose own estimate 1.2 and standard error 0.24 give about 0.71 to
1.69. No answer key was affected so far, but an impossible table makes a question confusing or debatable, and the
benchmark is the measuring instrument. This module recomputes what can be recomputed from the printout itself. A benchmark
or development question (prompt v8) whose printout fails is unusable and is asked again (up to 3 attempts), then replaced
by a spare. Training data is NOT checked this way (no correctness filtering, safeguard 9).

WHAT IS CHECKED (only what is printed; nothing is assumed)
  1. R's t-test lines "t = 2.145, df = 18, p-value = 0.04546": the p-value from t and df (two-sided, or one-sided when the
     "alternative hypothesis" line says greater or less); and, when the means and the confidence interval are printed, the
     interval's centre (the mean difference) and its half-width (critical t value x standard error, where the standard
     error is the mean difference divided by t).
  2. Coefficient tables ("Estimate Std. Error t value Pr(>|t|)", or z for glm): t = estimate / standard error; the p-value
     when the degrees of freedom are printed ("on 25 degrees of freedom") or the table uses z (the normal distribution).
  3. Confidence intervals for coefficients (a separate "2.5 % 97.5 %" or "lower upper" table under a 95% heading, or
     two "2.5 % 97.5 %" columns inside the coefficient table): centre = estimate
     and half-width = critical value x standard error (critical value t(0.975, df) if df is printed, else between 1.95
     and 3.2, which covers every t distribution with at least 3 degrees of freedom).
  4. "F-statistic: 25.3 on 2 and 27 DF, p-value: 6.1e-07", ANOVA tables (mean square = sum of squares / df; F = mean square /
     residual mean square; p from F), and chi-square lines "X-squared = 6.10, df = 1, p-value = 0.0135".

HOW ROUNDING IS ALLOWED FOR (so a correctly rounded printout never fails)
Every printed number stands for an interval: "0.24" means anything from 0.235 to 0.245. A check recomputes the range of
values the printed inputs allow and passes if the printed result's own interval overlaps it, with 1% relative slack on
top. Example (SM0004, smoke test): t = 2.145 on 18 df gives a two-sided p-value of 0.04585; the printout says 0.04546, a
0.85% difference: it passes. Example (Claude-era BM0070): F = 4 on 3 and 20 df gives 0.0221; the printout said 0.0215, a
2.7% difference: it fails.

WHAT IT CANNOT DO
It reads only these standard R formats; any other printout (a confusion matrix, a correlation matrix, custom tables) is
left to the Codex screen and the manual audit. It checks consistency, not whether the question is good.

The distribution functions are written out here (regularized incomplete beta and gamma functions, Numerical Recipes
style) so the check runs on Talon without SciPy or R; code/tests/generation_test checks them against R.
"""

import math
import re

# ---------------------------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------------------------
def _betacf(a, b, x):
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betai(a, b, x):
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def gammaq(a, x):
    """Regularized upper incomplete gamma function Q(a, x)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1.0:                     # series for P, then Q = 1 - P
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(1000):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 3e-16:
                break
        return max(0.0, 1.0 - s * math.exp(-x + a * math.log(x) - gln))
    tiny = 1e-300                       # continued fraction for Q
    b = x + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def p_t_two(t, df):
    """Two-sided p-value P(|T| >= |t|) for a t distribution; df = inf gives the normal distribution."""
    t = abs(t)
    if math.isinf(df):
        return math.erfc(t / math.sqrt(2.0))
    return betai(df / 2.0, 0.5, df / (df + t * t))


def p_f_upper(f, d1, d2):
    if f <= 0:
        return 1.0
    return betai(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


def p_chisq_upper(x, k):
    return gammaq(k / 2.0, x / 2.0)


def t_crit(level, df):
    """The critical value c with P(|T| <= c) = level, by bisection on p_t_two."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1 - p_t_two(mid, df) < level:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------------------------
# Printed numbers as intervals
# ---------------------------------------------------------------------------------------------
NUM = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
PVAL = r"(?:<\s*)?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def num(s):
    """(value, half of the last printed unit) of a printed number: '0.24' -> (0.24, 0.005); '1.2e-07' -> (1.2e-07, 5e-09)."""
    s = s.strip()
    m = re.fullmatch(r"(-?)(\d+)(?:\.(\d+))?(?:[eE]([-+]?\d+))?", s)
    if not m:
        raise ValueError(s)
    dec = len(m.group(3) or "")
    exp = int(m.group(4) or 0)
    return float(s), 0.5 * 10.0 ** (exp - dec)


def overlaps(printed, half, lo, hi, rel=0.01):
    """Does the printed value's rounding interval overlap [lo, hi] widened by `rel` (relative)?"""
    lo2, hi2 = lo - rel * abs(lo) - 1e-12, hi + rel * abs(hi) + 1e-12
    return printed + half >= lo2 and printed - half <= hi2


def pval(text):
    """(value, half unit, is_upper_bound) of a printed p-value such as '0.0131', '<2e-16', '< 2.2e-16', '0.0000'."""
    t = text.replace(" ", "")
    if t.startswith("<"):
        v, _ = num(t[1:])
        return v, 0.0, True
    v, h = num(t)
    return v, h, False


def p_ok(printed_text, p_lo, p_hi):
    v, h, bound = pval(printed_text)
    if bound:
        return p_lo < v * 1.01
    return overlaps(v, h, p_lo, p_hi)


def corners(f, *ranges):
    """min and max of f over all corners of the given (lo, hi) ranges (f is monotone in each argument here)."""
    import itertools
    vals = [f(*c) for c in itertools.product(*ranges)]
    return min(vals), max(vals)


def rng(v, h):
    return (v - h, v + h)


# ---------------------------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------------------------
def _p_two_range(t, ht, df, hdf):
    lo_t, hi_t = abs(t) - ht, abs(t) + ht
    if lo_t <= 0:
        return 0.0, 1.0
    dfs = (max(df - hdf, 0.5), df + hdf) if not math.isinf(df) else (df, df)
    return corners(lambda a, d: p_t_two(a, d), (lo_t, hi_t), dfs)


def check_htest(text, problems):
    for m in re.finditer(rf"\bt\s*=\s*({NUM}),\s*df\s*=\s*({NUM}),\s*p-value\s*([<=])\s*({PVAL})", text):
        t, ht = num(m.group(1))
        df, hdf = num(m.group(2))
        ptxt = ("<" if m.group(3) == "<" else "") + m.group(4)
        alt = re.search(r"alternative hypothesis:\s*true .*? is (not equal to|greater than|less than)", text[m.end():m.end() + 400])
        side = alt.group(1) if alt else "not equal to"
        lo, hi = _p_two_range(t, ht, df, hdf)
        if side != "not equal to":
            same_direction = (t > 0) == (side == "greater than")
            lo, hi = (lo / 2, hi / 2) if same_direction else (1 - hi / 2, 1 - lo / 2)
        if not p_ok(ptxt, lo, hi):
            problems.append(f"t = {m.group(1)} on df = {m.group(2)} gives a {'two' if side == 'not equal to' else 'one'}-sided "
                            f"p-value of about {(lo + hi) / 2:.4g}, but the printout says {ptxt}")
        # the confidence interval of a two-sided test, if printed with the estimates
        tail = text[m.end():m.end() + 600]
        ci = re.search(rf"(\d+(?:\.\d+)?) percent confidence interval:\s*\n\s*({NUM})\s+({NUM})", tail)
        if not ci or side != "not equal to" or abs(t) < 1e-9:
            continue
        level = float(ci.group(1)) / 100
        (l, hl), (u, hu) = num(ci.group(2)), num(ci.group(3))
        est = None
        two = re.search(rf"mean of x\s+mean of y\s*\n\s*({NUM})\s+({NUM})", tail)
        one = re.search(rf"(?:mean difference|mean of the differences|mean of x)\s*\n\s*({NUM})\s*(?:\n|$)", tail)
        if two:
            (a, ha), (b, hb) = num(two.group(1)), num(two.group(2))
            est, hest = a - b, ha + hb
        elif one:
            a, ha = num(one.group(1))
            mu = re.search(rf"true (?:mean|mean difference|difference in means) is not equal to ({NUM})", text[m.end():m.end() + 400])
            mu_v, hmu = num(mu.group(1)) if mu else (0.0, 0.0)
            est, hest = a - mu_v, ha + hmu
        if est is None or abs(est) < 1e-12:
            continue
        centre, hc = (l + u) / 2, (hl + hu) / 2
        if not overlaps(centre, hc, est - hest, est + hest):
            problems.append(f"the {ci.group(1)}% interval {ci.group(2)} to {ci.group(3)} is centred at {centre:.4g}, but the "
                            f"printed means give a difference of {est:.4g}")
            continue
        se_lo, se_hi = corners(lambda e, tt: abs(e / tt), rng(est, hest), (abs(t) - ht, abs(t) + ht))
        crit = t_crit(level, df)
        w, hw = (u - l) / 2, (hu + hl) / 2
        if not overlaps(w, hw, crit * se_lo, crit * se_hi, rel=0.02):
            problems.append(f"the {ci.group(1)}% interval has half-width {w:.4g}, but t = {m.group(1)} with df = {m.group(2)} "
                            f"implies about {crit * (se_lo + se_hi) / 2:.4g}")


def _residual_df(text):
    m = re.search(rf"on\s+({NUM})\s+degrees of freedom", text)
    return float(m.group(1)) if m else None


def coefficient_rows(text):
    """{name: (estimate, std. error, t or z, p, interval or None)} and the statistic kind ('t' or 'z') of R coefficient
    tables. The interval is read when the table carries two extra columns "2.5 %  97.5 %" after the p-value (a layout the
    teacher used in the second smoke test, SM0010 of job 295)."""
    rows, kind = {}, None
    for hm in re.finditer(r"Estimate\s+Std\. Error\s+([tz]) value\s+Pr\(>\|[tz]\|\)(\s+2\.5\s*%\s+97\.5\s*%)?", text):
        kind, inline = hm.group(1), bool(hm.group(2))
        for line in text[hm.end():].split("\n")[1:]:
            if not line.strip() or line.strip().startswith(("---", "Signif")):
                break
            r = re.match(rf"\s*(\S+)\s+({NUM})\s+({NUM})\s+({NUM})\s+({PVAL})(?:\s+(?:\*{{1,3}}|\.)(?=\s|$))?(?:\s+({NUM})\s+({NUM}))?", line)
            if not r:
                break
            ci = (r.group(6), r.group(7)) if inline and r.group(6) else None
            rows[r.group(1)] = (r.group(2), r.group(3), r.group(4), r.group(5), ci)
    return rows, kind


def _check_interval(name, lo_t, hi_t, est_t, se_t, df, level, problems):
    """An interval for one coefficient: centred at its estimate, half-width = critical value x standard error."""
    (l, hl), (u, hu) = num(lo_t), num(hi_t)
    (e, he), (s, hs) = num(est_t), num(se_t)
    centre, hc = (l + u) / 2, (hl + hu) / 2
    w, hw = (u - l) / 2, (hl + hu) / 2
    if not overlaps(centre, hc, e - he, e + he):
        problems.append(f"interval for {name} ({lo_t} to {hi_t}) is not centred at its estimate {est_t}")
        return
    if df is not None:
        c_lo = c_hi = t_crit(level, df)
    else:
        c_lo, c_hi = (1.95, 3.2) if abs(level - 0.95) < 1e-9 else (None, None)
    if c_lo is None or s - hs <= 0:
        return
    if not overlaps(w, hw, c_lo * (s - hs), c_hi * (s + hs), rel=0.02):
        expect = f"{c_lo * s:.4g}" if c_lo == c_hi else f"between {c_lo * s:.3g} and {c_hi * s:.3g}"
        problems.append(f"interval for {name} ({lo_t} to {hi_t}) has half-width {w:.4g}, but estimate {est_t} with standard "
                        f"error {se_t} gives a half-width of {expect} for a {level:.0%} interval")


def check_coefficients(text, problems):
    rows, kind = coefficient_rows(text)
    if not rows:
        return
    df = math.inf if kind == "z" else _residual_df(text)
    for name, (e_t, s_t, t_t, p_t, ci) in rows.items():
        if ci:
            _check_interval(name, ci[0], ci[1], e_t, s_t, df, 0.95, problems)
        (e, he), (s, hs), (t, ht) = num(e_t), num(s_t), num(t_t)
        if s - hs <= 0:
            continue
        lo, hi = corners(lambda a, b: a / b, rng(e, he), (s - hs, s + hs))
        if not overlaps(t, ht, lo, hi):
            problems.append(f"coefficient {name}: estimate {e_t} / standard error {s_t} = {e / s:.4g}, but the printed "
                            f"{kind} value is {t_t}")
            continue
        if df is not None:
            plo, phi = _p_two_range(t, ht, df, 0.0)
            if not p_ok(p_t, plo, phi):
                problems.append(f"coefficient {name}: {kind} = {t_t}" + (f" on {df:g} df" if not math.isinf(df) else "")
                                + f" gives p of about {(plo + phi) / 2:.3g}, but the printout says {p_t}")
    # confidence intervals for the same coefficients
    head = re.search(r"(?:(\d+(?:\.\d+)?)\s*%[^\n]*\n)?[^\n]*?(2\.5\s*%\s+97\.5\s*%|lower\s+upper)\s*\n", text)
    if not head:
        return
    level = 0.95
    if head.group(2).startswith("lower"):
        lv = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent) confidence interval", text[max(0, head.start() - 200):head.end()], re.I)
        if not lv:
            return
        level = float(lv.group(1)) / 100
    for line in text[head.end():].split("\n"):
        r = re.match(rf"\s*(\S+)\s+({NUM})\s+({NUM})\s*$", line)
        if not r:
            break
        name = r.group(1)
        if name in rows and not rows[name][4]:
            _check_interval(name, r.group(2), r.group(3), rows[name][0], rows[name][1], df, level, problems)


def check_f_and_anova(text, problems):
    for m in re.finditer(rf"F-statistic:\s*({NUM})\s+on\s+({NUM})\s+and\s+({NUM})\s+DF,\s*p-value:\s*({PVAL})", text):
        f, hf = num(m.group(1))
        d1, d2 = float(m.group(2)), float(m.group(3))
        lo, hi = corners(lambda x: p_f_upper(x, d1, d2), (max(f - hf, 0.0), f + hf))
        if not p_ok(m.group(4), lo, hi):
            problems.append(f"F = {m.group(1)} on {m.group(2)} and {m.group(3)} DF gives p of about {(lo + hi) / 2:.3g}, but "
                            f"the printout says {m.group(4)}")
    for hm in re.finditer(r"Df\s+Sum Sq\s+Mean Sq\s+F value\s+Pr\(>F\)", text):
        rows, resid = [], None
        for line in text[hm.end():].split("\n")[1:]:
            r = re.match(rf"\s*(\S+)\s+({NUM})\s+({NUM})\s+({NUM})(?:\s+({NUM})\s+({PVAL}))?", line)
            if not r:
                break
            if r.group(1).lower().startswith("residual"):
                resid = r
            elif r.group(5):
                rows.append(r)
        for r in rows + ([resid] if resid else []):
            (d, _), (ss, hss), (ms, hms) = num(r.group(2)), num(r.group(3)), num(r.group(4))
            if d > 0 and not overlaps(ms, hms, (ss - hss) / d, (ss + hss) / d):
                problems.append(f"ANOVA row {r.group(1)}: Sum Sq {r.group(3)} / Df {r.group(2)} = {ss / d:.4g}, but Mean Sq is {r.group(4)}")
        if not resid:
            continue
        (dr, _), (msr, hmsr) = num(resid.group(2)), num(resid.group(4))
        for r in rows:
            (d, _), (ms, hms), (f, hf) = num(r.group(2)), num(r.group(4)), num(r.group(5))
            if msr - hmsr > 0:
                lo, hi = corners(lambda a, b: a / b, rng(ms, hms), (msr - hmsr, msr + hmsr))
                if not overlaps(f, hf, lo, hi):
                    problems.append(f"ANOVA row {r.group(1)}: Mean Sq {r.group(4)} / residual Mean Sq {resid.group(4)} = "
                                    f"{ms / msr:.4g}, but F is {r.group(5)}")
                    continue
            plo, phi = corners(lambda x: p_f_upper(x, d, dr), (max(f - hf, 0.0), f + hf))
            if not p_ok(r.group(6), plo, phi):
                problems.append(f"ANOVA row {r.group(1)}: F = {r.group(5)} on {r.group(2)} and {resid.group(2)} df gives p of "
                                f"about {(plo + phi) / 2:.3g}, but Pr(>F) is {r.group(6)}")


def check_chisq(text, problems):
    for m in re.finditer(rf"X-squared\s*=\s*({NUM}),\s*df\s*=\s*({NUM}),\s*p-value\s*([<=])\s*({PVAL})", text):
        x, hx = num(m.group(1))
        k = float(m.group(2))
        ptxt = ("<" if m.group(3) == "<" else "") + m.group(4)
        lo, hi = corners(lambda v: p_chisq_upper(v, k), (max(x - hx, 0.0), x + hx))
        if not p_ok(ptxt, lo, hi):
            problems.append(f"X-squared = {m.group(1)} on df = {m.group(2)} gives p of about {(lo + hi) / 2:.3g}, but the "
                            f"printout says {ptxt}")


def check(text):
    """Problems found in the printed output of a question (empty list = consistent, or nothing checkable)."""
    problems = []
    text = text.replace("\r\n", "\n")
    for fn in (check_htest, check_coefficients, check_f_and_anova, check_chisq):
        try:
            fn(text, problems)
        except (ValueError, ZeroDivisionError, OverflowError):
            continue     # a number the parser could not read: left to the screen, never a crash
    return ["printed output is inconsistent: " + p for p in problems]
