"""Run the audit's probe candidates through the repaired R checks (R sandbox) to test its predictions."""
import csv, json, sys
sys.path.insert(0, "code/generation")
import generate_benchmark as gb

rows = {r["item_id"]: r for r in csv.DictReader(open("data/verification_logs/2026-11-21_benchmark_check_repairs/review_sheet.csv", encoding="utf-8-sig"))}
# (item, candidate, audit prediction)
P = [
 ("BM0254", 'merge(p, q, by = "id", all.x = TRUE)', True), ("BM0254", "merge(p, q)", False), ("BM0254", "merge(q, p, all.y = TRUE)", False),
 ("BM0474", "replicate(500, sum(runif(15))/15)", True), ("BM0474", "replicate(500, mean(runif(14)))", False),
 ("BM0594", "set.seed(42); rpois(5, lambda = 6)", True), ("BM0594", "set.seed(42); rpois(5, 5)", False),
 ("BM0714", "sum(M[cbind(1:3, 1:3)])", True), ("BM0714", "sum(M)", False), ("BM0714", "15", True),
 ("BM0738", 'paste0("tau2_", sort(unique(as.character(subject))))', True), ("BM0738", 'paste0("tau2_", as.integer(subject))', False),
 ("BM0794", "parts[sample(nrow(parts)), , drop = FALSE]", True), ("BM0794", "parts[1:3, ]", False),
 ("BM0794", "parts[sample(nrow(parts), prob = rep(1, nrow(parts))), ]", False),
 ("BM0958", "sum(occ > mean(occ, trim = 0.1, na.rm = TRUE), na.rm = TRUE)/sum(!is.na(occ))", True),
 ("BM0958", "mean(occ > median(occ, na.rm = TRUE), na.rm = TRUE)", True),
 ("BM0958", "mean(occ >= mean(occ, trim = 0.1, na.rm = TRUE), na.rm = TRUE)", True),
 ("BM1014", "unname(coef(lm(capacity ~ cycles))[2])", True), ("BM1014", "coef(lm(capacity ~ cycles))[1]", False),
 ("BM1078", "coef(glm(cbind(F, 10 - F) ~ log10(S), family = binomial))[2]", True),
 ("BM1078", "coef(glm(cbind(F, 10 - F) ~ log10(S), family = binomial))[1]", False),
 ("BM1138", "sum(nchar(toupper(levels(f)[as.integer(f)])))", True), ("BM1138", "sum(nchar(as.character(f)))", True),
 ("BM0003", 'format(x, "%A")', True), ("BM0003", 'format(x, "%a")', False),
 ("BM0023", "anova(model_reduced, model_full)", False),
 ("BM0103", "max(nchar(codes))", True),
 ("BM0183", "sum(time < 9)/length(time)", True), ("BM0183", "mean(time <= 9)", False),
 ("BM0583", "table(factor(x))", False), ("BM0583", "table(x[x != 4])", False), ("BM0583", "c(`1`=2, `2`=3, `3`=1, `4`=1)", None),
 ("BM0683", "cumsum(x/sum(x))", True), ("BM0683", "cumsum(x)", False),
 ("BM0049", "quantile(replicate(10000, mean(rnorm(25))), c(0.025, 0.975))", True),
 ("BM0049", "quantile(colMeans(matrix(rnorm(25*10000), 25)), c(0.05, 0.95))", False),
 ("BM0429", 'x[order(as.integer(sub(".*_", "", x)))]', True), ("BM0429", "sort(x)", False),
 ("BM0509", "apply(M, 1, function(v) diff(range(v)))", True), ("BM0509", "apply(M, 2, function(v) max(v)-min(v))", False),
 ("BM0649", "sum(rpois(1000, lambda = 3) == 5)", True), ("BM0649", "sum(rpois(1000, lambda = 4) == 5)", False),
 ("BM0689", "c(R = 19, D = 5)", True),
 ("BM0813", "predict(fit, newdata = data.frame(rh = 55, temp = 22))", True), ("BM0813", "predict(fit, newdata = data.frame(temp = 22, rh = 50))", False),
 ("BM0849", "set.seed(42); sum(rnorm(10000) > 1)/10000", True), ("BM0849", "set.seed(42); mean(rnorm(10000) > 0)", False),
 ("BM1049", "mean(rnorm(1000))", False), ("BM1049", "set.seed(99); mean(replicate(1000, mean(rnorm(50, 0, 1))))", False),
 ("DV0003", "c(L1 = 7, L2 = 4)", True),
 ("DV0038", "quantile(replicate(10000, var(rnorm(20, sd = 3))/var(rnorm(25, sd = 2))), 0.8)", False),
 ("DV0054", "sum(x == 2)", True),
 ("DV0118", "which(abs(L - 50) > 1.96*u)", True),
 ("DV0134", '"123"', True),
 ("DV0218", 'fit$parameters[["log-odds"]]', True),
]
rs = gb.rscript_path()
out = []
for iid, cand, pred in P:
    item = {"r_check": rows[iid]["new_check"]}
    got = gb.r_check_result(item, cand, rs)
    out.append((iid, cand, pred, got))
    flag = "" if pred is None or got == pred else "   <-- AUDIT PREDICTION WRONG"
    print(f"{iid}  pred={pred}  R={got}  {cand}{flag}")
# premise and fact checks
for code in ['paste0("tau2_", factor(c("S1","S2","S1")))', "6[-3]", "length(c(3, sample(1:6[-3])))",
             "tryCatch(matrix(1:3, nrow = 2, ncol = 2), error = function(e) -1)", "tryCatch(log(1, base = 0), error = function(e) 42)",
             "str(tapply(c(2,5,1,3), c('L1','L1','L2','L2'), sum))",
             "occ <- c(0.82,0.91,NA,0.76,0.88,0.94,0.79,0.85,NA,0.90,0.83,0.85); c(median(occ,na.rm=TRUE), mean(occ,trim=0.1,na.rm=TRUE))",
             "u <- c(0.35,0.50,0.40,0.45,0.20,0.60); L <- c(50.8,49.6,51.5,50.1,51.0,49.2); which(abs(L-50) > 1.96*u); u^2 < median(u^2)",
             "df <- data.frame(x=rnorm(5), z=rnorm(5), g=factor(c('a','b','c','a','b'))); ncol(model.matrix(~ x*z + g, df)); tryCatch(ncol(model.matrix(y ~ x*z + g, data = df)), error=function(e) conditionMessage(e))"]:
    print("FACT:", code, "->", gb.run_r(f"print({code})" if ";" not in code else code.replace("; ", "; print(", 0) if False else f"{{ {code} }}" if False else "print(eval(parse(text = " + json.dumps(code) + ")))", rs))
