"""Revised R checks (round 2) after the ChatGPT audit, owner's decision 2026-11-21: Claude rewrites, R verifies, owner approves each.
Each entry: item id -> (new check, [(candidate, expected)]). The key is always tested too (expected TRUE)."""
import csv, json, sys
sys.path.insert(0, "code/generation")
import generate_benchmark as gb

# helper used inside checks: evaluate the candidate in a fresh environment holding the given objects
EV = "ev <- function(...) { e <- new.env(); vals <- list(...); for (n in names(vals)) assign(n, vals[[n]], envir = e); eval(parse(text = candidate), envir = e) }; "

# the uppercase step: toupper(...) or casefold(..., upper = TRUE) (owner's decision, 2026-11-21)
UP = ('(grepl("toupper\\\\s*\\\\(", candidate) || (grepl("casefold\\\\s*\\\\(", candidate) && '
      'grepl("upper\\\\s*=\\\\s*(TRUE|T)\\\\b", candidate)))')

C = {
 "BM0958": (EV + "q <- c(0.82, 0.91, NA, 0.76, 0.88, 0.94, 0.79, 0.85, NA, 0.90, 0.83, 0.85); "
            "o2 <- c(0.10, 0.20, NA, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.99); "
            "ref <- function(occ) mean(occ > mean(occ, trim = 0.1, na.rm = TRUE), na.rm = TRUE); "
            "isTRUE(all.equal(ev(occ = q), 0.4)) && isTRUE(all.equal(ev(occ = o2), ref(o2)))",
            [("mean(occ > median(occ, na.rm = TRUE), na.rm = TRUE)", False), ("0.4", False),
             ("sum(occ > mean(occ, trim = 0.1, na.rm = TRUE), na.rm = TRUE) / sum(!is.na(occ))", True)]),
 "BM1138": ('f <- factor(c("alpha", "Beta", "gamma")); ' + UP + ' && '
            "isTRUE(all.equal(eval(parse(text = candidate)), 14))",
            [("sum(nchar(as.character(f)))", False), ("sum(nchar(casefold(as.character(f), upper = TRUE)))", True),
             ("sum(nchar(casefold(as.character(f))))", False),("sum(nchar(toupper(levels(f)[as.integer(f)])))", True), ("14", False)]),
 "BM0103": ('codes <- c("measles", "polio", "hepatitis_b", "rotavirus"); ' + UP + ' && '
            "isTRUE(all.equal(eval(parse(text = candidate)), 11))",
            [("max(nchar(codes))", False), ("max(nchar(casefold(codes, upper = TRUE)))", True), ("max(nchar(casefold(codes)))", False),("max(nchar(toupper(codes)))", True), ("11", False)]),
 "BM0689": ('loan_outcomes <- c("R", "R", "R", "R", "R", "R", "R", "R", "R", "R", "D", "D", "D", "D", "D", "R", "R", "R", "R", "R", "R", "R", "R", "R"); '
            'r <- eval(parse(text = candidate)); inherits(r, "table") && isTRUE(all.equal(as.vector(r), c(19, 5))) && identical(names(r), c("R", "D"))',
            [("c(R = 19, D = 5)", False), ('table(loan_outcomes)[c("R", "D")]', True), ("table(loan_outcomes)", False)]),
 "BM0583": ("x <- c(1, 2, 2, 3, 2, 4, 1); r <- eval(parse(text = candidate)); "
            'inherits(r, "table") && length(dim(r)) == 1 && identical(as.vector(r), c(2L, 3L, 1L, 1L)) && identical(dimnames(r)[[1]], c("1", "2", "3", "4"))',
            [("table(factor(x))", True), ("table(x[x != 4])", False), ("c(`1`=2, `2`=3, `3`=1, `4`=1)", False), ("table(as.character(x))", True)]),
 "BM1049": ("r <- vapply(1:40, function(s) { set.seed(s); as.numeric(eval(parse(text = candidate))) }, numeric(1)); "
            "all(is.finite(r)) && ((sd(r) > 0.0030 && sd(r) < 0.0062 && all(abs(r) < 0.025)) || "
            '(sd(r) == 0 && abs(r[1]) < 0.02 && grepl("rnorm", candidate)))',
            [("mean(rnorm(1000))", False), ("set.seed(99); mean(replicate(1000, mean(rnorm(50, 0, 1))))", True), ("0", False),
             ("mean(colMeans(matrix(rnorm(50 * 1000), 50)))", True), ("mean(replicate(1000, mean(rnorm(50, 0, 2))))", False)]),
 "BM0794": ("parts <- data.frame(id = 1:5, length_mm = c(10.1, 10.3, 9.9, 10.0, 10.2), defects = c(0, 1, 0, 2, 0)); "
            "ok_perm <- function(r) { if (!is.data.frame(r) || nrow(r) != 5 || !identical(names(r), names(parts))) return(FALSE); "
            "rr <- r[order(r$id), ]; rownames(rr) <- NULL; isTRUE(all.equal(rr, parts)) }; "
            "res <- lapply(1:10, function(s) { set.seed(s); eval(parse(text = candidate)) }); "
            "orders <- vapply(res, function(r) if (is.data.frame(r) && !is.null(r$id)) paste(r$id, collapse = ',') else '', ''); "
            'grepl("sample", candidate) && all(vapply(res, ok_perm, logical(1))) && (length(unique(orders)) > 1 || grepl("set.seed", candidate))',
            [("parts[1:3, ]", False), ("parts", False), ("parts[sample(nrow(parts)), , drop = FALSE]", True),
             ("parts[sample(1:5), ]", True), ("set.seed(7); parts[sample(nrow(parts)), ]", True)]),
 "DV0003": (EV + 'ref <- function(line, defects) c(tapply(defects, line, sum)); '
            'isTRUE(all.equal(c(ev(line = c("L1", "L1", "L2", "L2"), defects = c(2, 5, 1, 3))), c(L1 = 7, L2 = 4))) && '
            'isTRUE(all.equal(c(ev(line = c("A", "B", "B", "C", "A"), defects = c(1, 2, 3, 4, 5))), ref(c("A", "B", "B", "C", "A"), c(1, 2, 3, 4, 5))))',
            [("c(L1 = 7, L2 = 4)", False), ("c(tapply(defects, line, sum))", True), ("sapply(split(defects, line), sum)", True)]),
 "DV0054": (EV + 'grepl("table\\\\s*\\\\(", candidate) && isTRUE(all.equal(as.numeric(ev(x = c(1, 2, 2, 3, 3, 3, 3))), 2)) && '
            "isTRUE(all.equal(as.numeric(ev(x = c(2, 2, 2, 5))), 3)) && length(ev(x = c(2, 2, 2, 5))) == 1",
            [("sum(x == 2)", False), ("2", False), ('as.numeric(table(x)["2"])', True)]),
 "DV0118": (EV + "ref <- function(L, u) which(abs(L - 50.0) > 1.96 * u & u^2 < median(u^2)); "
            "isTRUE(all.equal(ev(L = c(50.8, 49.6, 51.5, 50.1, 51.0, 49.2), u = c(0.35, 0.50, 0.40, 0.45, 0.20, 0.60)), c(1L, 3L, 5L))) && "
            "isTRUE(all.equal(ev(L = c(52.0, 50.9, 49.0, 50.1, 53.0, 50.2), u = c(0.30, 0.40, 0.20, 0.50, 0.80, 0.60)), "
            "ref(c(52.0, 50.9, 49.0, 50.1, 53.0, 50.2), c(0.30, 0.40, 0.20, 0.50, 0.80, 0.60))))",
            [("which(abs(L - 50) > 1.96*u)", False), ("c(1, 3, 5)", False),
             ("which((L - 1.96*u > 50 | L + 1.96*u < 50) & u^2 < median(u^2))", True)]),
 "DV0134": (EV + 'grepl("regmatches", candidate) && grepl("regexec", candidate) && '
            'isTRUE(all.equal(unlist(ev(x = "abc123def")), "123")) && isTRUE(all.equal(unlist(ev(x = "zz42yy")), "42"))',
            [('"123"', False), ('unlist(regmatches(x, regexec("[0-9]+", x)))', True), ('regmatches(x, regexpr("[0-9]+", x))', False)]),
 "DV0218": (EV + '!grepl("[$`]", candidate) && '
            'isTRUE(all.equal(ev(fit = list(iteration = 150, parameters = list("log-odds" = 0.42, "intercept" = -1.5), converged = TRUE)), 0.42)) && '
            'isTRUE(all.equal(ev(fit = list(iteration = 9, parameters = list("log-odds" = 0.77, "intercept" = 2), converged = FALSE)), 0.77))',
            [('fit$parameters[["log-odds"]]', False), ("0.42", False), ('fit[["parameters"]]["log-odds"]', False),
             ('fit[[2]][[1]]', True)]),
}

if __name__ == "__main__":
    sheet = {r["item_id"]: r for r in csv.DictReader(open("data/verification_logs/2026-11-21_benchmark_check_repairs/review_sheet.csv", encoding="utf-8-sig"))}
    rs = gb.rscript_path()
    bad = 0
    for iid, (chk, probes) in C.items():
        key = sheet[iid]["key"]
        for cand, exp in [(key, True)] + probes + [("NULL", False), ("-999999", False), ('"zzz"', False)]:
            got = gb.r_check_result({"r_check": chk}, cand, rs)
            ok = got == exp
            bad += not ok
            print(f"{'ok ' if ok else 'BAD'} {iid} expect={exp} got={got}  {cand}")
    print("problems:", bad)
    json.dump({k: v[0] for k, v in C.items()}, open(sys.argv[1], "w"), indent=1)
