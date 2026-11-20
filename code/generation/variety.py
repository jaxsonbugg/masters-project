"""
variety.py - read the taxonomy and the context deck, check them, and deal question slots into frozen slot files.

WHAT THIS IS AND WHY
Every question the teacher writes starts from a *slot*: a short description of what the question must be about
(category, subtopic, difficulty, answer type, and a real-world setting). The old built-in list in
generate_benchmark.py had only 138 slot combinations, so the teacher wrote near-copies. This script uses the
project's taxonomy (data/taxonomy/subtopics.yaml, about 720 subtopics) and context deck
(data/taxonomy/contexts.yaml, about 30 settings plus a "no applied context" card) to deal slots like cards from
shuffled decks, and writes them to a FROZEN SLOT FILE that every later step reads (docs/methodology/workflow.md
Section 4, safeguards 2 and 4).

HOW DEALING WORKS (plain steps)
1. Category and difficulty follow the fixed 20-slot PATTERN of generate_benchmark.py (30/20/20/15/15 % by
   category, 40/35/25 % by difficulty), so any 20 consecutive slots have the target mix.
2. R interpretation alternates number, number, short text (2:1), from the taxonomy's two R-interpretation blocks.
3. Subtopic: each (category block, difficulty) has its own deck. A deck is a shuffled list of all subtopics of
   that block, laid out ROUND-ROBIN OVER AREAS (one subtopic from each area in turn), so no area dominates. A
   subtopic is not dealt again at that difficulty until the whole deck has been used; then a fresh shuffle starts.
4. Context: each category has a deck of the ~30 contexts plus enough "none" cards to give the category's
   no-context share exactly over each full deck (for example 30 contexts + 45 "none" = 60 % none).
5. Multiple-choice slots rotate the preferred correct letter A, B, C, D.
6. Every deck is deterministic: card number i of a deck depends only on the set's seed, the deck's name and i.
   So the deck "state" is just how many cards were dealt, and REPLACEMENT slots continue the same decks
   without repeating a card already dealt (docs/methodology/workflow.md, the like-for-like replenishment rule).

FINGERPRINTS (so old and new benchmark ids can never be confused)
Every slot carries "slot_scheme": "taxonomy-v2". The manifest beside each slot file records the SHA-256 of the
slot file, of the taxonomy and of the context deck, the seed and the deck state. New tools refuse benchmark
items that do not carry the slot file's fingerprint; the old ids BM0001-BM0120 (Claude-era trials) and the old
deployment-test slots stay on the old built-in list ("blueprint v1") in generate_benchmark.py.

COMMANDS
  python variety.py check                                   check the taxonomy and contexts; print counts
  python variety.py deal --set benchmark --n 1150 --seed S --out data/slots     write a slot file + manifest
  python variety.py replace --manifest M --like <slot id> [--count 1]          deal like-for-like replacements
  python variety.py report --slots F [--prefixes 1000,10000]                   the target mix of a slot file

Example: `deal --set benchmark --n 1150` gives BM0001-BM1150; slot BM0001 might be
  numerical / "binomial probability" (area "distributions") / intro / number / context "sports".
"""

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_benchmark as gb  # noqa: E402  (the 20-slot PATTERN and the answer types)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = gb.REPO
TAXONOMY_FILE = REPO / "data" / "taxonomy" / "subtopics.yaml"
CONTEXTS_FILE = REPO / "data" / "taxonomy" / "contexts.yaml"
SLOT_SCHEME = "taxonomy-v2"
DEALER_VERSION = "variety-1"
# 2:1 number to short text, as in the old blueprint (100 + 50 per 1,000). It is 9 long, not 3: the pattern has 3
# r_interpretation slots per 20 (intro, intermediate, intro), so a 3-long rotation would always give short text
# to the same difficulty; over 9 slots each answer type meets both difficulties.
R_INTERP_ROTATION = ["number", "number", "short_text", "number", "short_text", "number", "short_text", "number", "number"]
NONE = "none"
# The id of each set: (prefix, digits). The benchmark keeps BM (its slot fingerprint tells it apart from the
# archived Claude-era BM ids); SM is a separate smoke set used only to test the generator on the cluster.
SETS = {"benchmark": ("BM", 4), "dev": ("DV", 4), "tv": ("TV", 4), "train": ("TR", 6), "smoke": ("SM", 4)}
REPLACEMENT_PREFIX = {"benchmark": ("BM", 4), "dev": ("DV", 4), "tv": ("TV", 4), "train": ("TRR", 6),
                      "smoke": ("SM", 4)}
# Package names that break the "base R and stats only" rule (a word like "forecast" is fine on its own).
NON_BASE_R = re.compile(r"auto\.arima|ggplot|dplyr|tidyr|tidyverse|data\.table|caret|lme4|library\s*\(|::", re.I)


class TaxonomyError(Exception):
    """The taxonomy or the context deck is malformed; nothing may be dealt from it."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """A YAML loader that REFUSES a key repeated in the same mapping. Plain YAML keeps only the last one, which is
    how two areas both named "data frames" once silently dropped 16 subtopics."""


def _construct_unique_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise TaxonomyError(f"the key {key!r} appears twice in the same block (line {key_node.start_mark.line + 1}); "
                                f"YAML would silently keep only the last one")
        seen.add(key)
    return loader.construct_mapping(node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_taxonomy(path=TAXONOMY_FILE):
    """{block: {"category", "answer_type", "areas": {area: [subtopics]}}} plus the file's SHA-256. Raises TaxonomyError."""
    path = Path(path)
    try:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as e:
        raise TaxonomyError(f"{path} is not valid YAML: {e}")
    blocks = {}
    for name, b in (doc or {}).get("categories", {}).items():
        cat = b.get("category", name)
        atype = b.get("answer_type")
        areas = b.get("areas") or {}
        if not atype or not areas:
            raise TaxonomyError(f"block {name!r} needs an answer_type and at least one area")
        clean = {}
        for area, subs in areas.items():
            if not isinstance(subs, list) or not subs or not all(isinstance(s, str) and s.strip() for s in subs):
                raise TaxonomyError(f"block {name!r}, area {area!r}: must be a non-empty list of subtopic lines")
            clean[area] = [s.strip() for s in subs]
        blocks[name] = {"category": cat, "answer_type": atype, "areas": clean}
    # a subtopic may appear in two DIFFERENT categories (numerical "weighted mean" vs R generation "weighted
    # mean"), but never twice inside one category
    by_cat = defaultdict(list)
    for b in blocks.values():
        for subs in b["areas"].values():
            by_cat[b["category"]].extend(subs)
    for cat, subs in by_cat.items():
        reps = sorted(s for s, k in Counter(subs).items() if k > 1)
        if reps:
            raise TaxonomyError(f"category {cat!r} lists these subtopics more than once: {reps}")
    expected = {"numerical", "conceptual", "r_generation", "r_interpretation", "output_interpretation"}
    if set(by_cat) != expected:
        raise TaxonomyError(f"the taxonomy's categories {sorted(by_cat)} differ from the pattern's {sorted(expected)}")
    rint = {b["answer_type"] for b in blocks.values() if b["category"] == "r_interpretation"}
    if rint != {"number", "short_text"}:
        raise TaxonomyError("r_interpretation needs one block with answer_type number and one with short_text")
    return blocks, sha256_file(path)


def load_contexts(path=CONTEXTS_FILE):
    path = Path(path)
    try:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as e:
        raise TaxonomyError(f"{path} is not valid YAML: {e}")
    shares = doc.get("no_context_share") or {}
    ctx = doc.get("contexts") or []
    names = [c.get("name", "").strip() for c in ctx]
    if not ctx or any(not n for n in names) or any(not (c.get("description") or "").strip() for c in ctx):
        raise TaxonomyError("every context needs a name and a one-line description")
    reps = sorted(n for n, k in Counter(names).items() if k > 1)
    if reps:
        raise TaxonomyError(f"contexts listed more than once: {reps}")
    for cat in ("numerical", "conceptual", "r_generation", "r_interpretation", "output_interpretation"):
        s = shares.get(cat)
        if not isinstance(s, (int, float)) or not 0 <= s < 1:
            raise TaxonomyError(f"no_context_share for {cat!r} must be a number from 0 to below 1")
    return {"shares": shares, "contexts": [{"name": c["name"].strip(), "description": c["description"].strip()} for c in ctx]}, \
        sha256_file(path)


# ---------------------------------------------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------------------------------------------
class Deck:
    """A deterministic, endless deck. Card i is in cycle i // len(cards); each cycle is a fresh seeded layout
    of all cards, so nothing repeats inside a cycle and the deck's state is just the number of cards dealt."""

    def __init__(self, name, seed, layout):
        self.name, self.seed, self.layout = name, seed, layout      # layout(rng) -> one cycle's card order
        self.dealt = 0
        self._cache = {}

    def _cycle(self, c):
        if c not in self._cache:
            self._cache = {c: self.layout(random.Random(f"{self.seed}|{self.name}|cycle{c}"))}
        return self._cache[c]

    def card(self, i):
        first = self._cycle(0)
        n = len(first)
        return self._cycle(i // n)[i % n]

    def deal(self):
        c = self.card(self.dealt)
        self.dealt += 1
        return c


def _area_round_robin(areas):
    """Layout of one subtopic cycle: shuffle within each area and the order of the areas, then take one subtopic
    from each area in turn, so consecutive slots come from different areas."""
    def layout(rng):
        lists = []
        for area, subs in areas.items():
            l = [(area, s) for s in subs]
            rng.shuffle(l)
            lists.append(l)
        rng.shuffle(lists)
        out, k = [], 0
        while any(lists):
            for l in lists:
                if k < len(l):
                    out.append(l[k])
            k += 1
            if all(k >= len(l) for l in lists):
                break
        return out
    return layout


def none_cards(share, n_contexts):
    """How many "none" cards give exactly `share` of a deck with n_contexts real contexts (rounded)."""
    return round(share * n_contexts / (1 - share)) if share > 0 else 0


def _context_layout(contexts, k_none):
    def layout(rng):
        cards = [c["name"] for c in contexts] + [NONE] * k_none
        rng.shuffle(cards)
        return cards
    return layout


class Dealer:
    def __init__(self, blocks, ctx, seed, state=None):
        self.blocks, self.ctx, self.seed = blocks, ctx, seed
        self.block_of = {}
        for name, b in blocks.items():
            self.block_of[(b["category"], b["answer_type"])] = name
        self.sub_decks, self.ctx_decks = {}, {}
        for name, b in blocks.items():
            for diff in ("intro", "intermediate", "graduate"):
                self.sub_decks[(name, diff)] = Deck(f"sub:{name}:{diff}", seed, _area_round_robin(b["areas"]))
        n = len(ctx["contexts"])
        for cat, share in ctx["shares"].items():
            self.ctx_decks[cat] = Deck(f"ctx:{cat}", seed, _context_layout(ctx["contexts"], none_cards(share, n)))
        self.descriptions = {c["name"]: c["description"] for c in ctx["contexts"]}
        self.counters = {"r_interp": 0, "mc": 0}
        if state:
            self.load_state(state)

    def state(self):
        return {"sub": {f"{k[0]}|{k[1]}": d.dealt for k, d in self.sub_decks.items()},
                "ctx": {k: d.dealt for k, d in self.ctx_decks.items()}, "counters": dict(self.counters)}

    def load_state(self, st):
        for k, v in st["sub"].items():
            name, diff = k.split("|")
            self.sub_decks[(name, diff)].dealt = v
        for k, v in st["ctx"].items():
            self.ctx_decks[k].dealt = v
        self.counters = dict(st["counters"])

    def _slot(self, item_id, cat, diff, atype, context, letter):
        block = self.block_of[(cat, atype)]
        area, sub = self.sub_decks[(block, diff)].deal()
        return {"item_id": item_id, "category": cat, "subtopic": sub, "area": area, "difficulty": diff,
                "answer_type": atype, "preferred_letter": letter, "context": context,
                "context_text": "" if context == NONE else self.descriptions[context], "slot_scheme": SLOT_SCHEME}

    def deal_one(self, item_id, pattern_index):
        cat, diff = gb.PATTERN[pattern_index % len(gb.PATTERN)]
        if cat == "r_interpretation":
            atype = R_INTERP_ROTATION[self.counters["r_interp"] % len(R_INTERP_ROTATION)]
            self.counters["r_interp"] += 1
        else:
            atype = gb.ANSWER_TYPE[cat]
        letter = ""
        if atype == "multiple_choice":
            letter = "ABCD"[self.counters["mc"] % 4]
            self.counters["mc"] += 1
        context = self.ctx_decks[cat].deal()
        return self._slot(item_id, cat, diff, atype, context, letter)

    def deal_like(self, item_id, like):
        """A like-for-like replacement: same category, difficulty, answer type, context card and preferred
        letter as `like`; only the subtopic is the next card of the continued deck."""
        return {**self._slot(item_id, like["category"], like["difficulty"], like["answer_type"], like["context"],
                             like.get("preferred_letter", "")), "replaces": like["item_id"]}


def make_id(set_name, k, replacement=False):
    prefix, width = (REPLACEMENT_PREFIX if replacement else SETS)[set_name]
    return f"{prefix}{k:0{width}d}"


# ---------------------------------------------------------------------------------------------------------------
# Slot files
# ---------------------------------------------------------------------------------------------------------------
def write_jsonl(path, rows):
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_slots(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def slot_fingerprint(path):
    """SHA-256 of a slot file's bytes: the fingerprint every run, reply and item must carry."""
    return sha256_file(path)


def cmd_deal(args):
    blocks, tax_sha = load_taxonomy(args.taxonomy)
    ctx, ctx_sha = load_contexts(args.contexts)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slot_path = out / f"{args.set}_slots.jsonl"
    man_path = out / f"{args.set}_slots.manifest.json"
    if slot_path.exists() and not args.overwrite:
        sys.exit(f"{slot_path} exists. Slot files are frozen; pass --overwrite only for a file nothing has used yet.")
    d = Dealer(blocks, ctx, args.seed)
    slots = [d.deal_one(make_id(args.set, k), k - 1) for k in range(1, args.n + 1)]
    sha = write_jsonl(slot_path, slots)
    manifest = {"set": args.set, "n": args.n, "seed": args.seed, "slot_scheme": SLOT_SCHEME,
                "dealer_version": DEALER_VERSION, "slots_file": slot_path.name, "slots_sha256": sha,
                "taxonomy_file": str(Path(args.taxonomy).as_posix()), "taxonomy_sha256": tax_sha,
                "contexts_file": str(Path(args.contexts).as_posix()), "contexts_sha256": ctx_sha,
                "deck_state": d.state(), "replacements": [], "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    print(f"dealt {args.n} {args.set} slots ({slots[0]['item_id']}-{slots[-1]['item_id']}) -> {slot_path}")
    print(f"slots_sha256 {sha}\ntaxonomy_sha256 {tax_sha}\ncontexts_sha256 {ctx_sha}")
    return slot_path, man_path


def deal_replacements(man_path, likes, taxonomy=TAXONOMY_FILE, contexts=CONTEXTS_FILE):
    """Deal like-for-like replacement slots from the continued decks of a slot file; append them to
    <set>_replacements.jsonl and record the new deck state in the manifest. Returns the new slots."""
    man_path = Path(man_path)
    m = json.loads(man_path.read_text(encoding="utf-8"))
    blocks, tax_sha = load_taxonomy(taxonomy)
    ctx, ctx_sha = load_contexts(contexts)
    if (tax_sha, ctx_sha) != (m["taxonomy_sha256"], m["contexts_sha256"]):
        sys.exit("the taxonomy or the context deck changed since this slot file was dealt; replacements would not "
                 "continue the same decks. Nothing was dealt.")
    d = Dealer(blocks, ctx, m["seed"], state=m["deck_state"])
    rep_path = man_path.parent / f"{m['set']}_replacements.jsonl"
    existing = read_slots(rep_path) if rep_path.exists() else []
    if m["set"] in ("benchmark", "dev", "tv", "smoke"):
        start = m["n"] + len(existing) + 1           # new spares continue the set's own numbering
    else:
        start = len(existing) + 1                     # TRR000001, TRR000002, ...
    new = [d.deal_like(make_id(m["set"], start + i, replacement=True), like) for i, like in enumerate(likes)]
    rows = existing + new
    m["replacements_file"] = rep_path.name
    m["replacements_sha256"] = write_jsonl(rep_path, rows)
    m["deck_state"] = d.state()
    m["replacements"].append({"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "ids": [s["item_id"] for s in new], "replaces": [s["replaces"] for s in new]})
    man_path.write_text(json.dumps(m, indent=2), encoding="utf-8", newline="\n")
    return new


def cmd_replace(args):
    m = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    slots = {s["item_id"]: s for s in read_slots(Path(args.manifest).parent / m["slots_file"])}
    rep = Path(args.manifest).parent / f"{m['set']}_replacements.jsonl"
    if rep.exists():
        slots.update({s["item_id"]: s for s in read_slots(rep)})
    if args.like not in slots:
        sys.exit(f"{args.like} is not a slot of this set")
    new = deal_replacements(args.manifest, [slots[args.like]] * args.count, args.taxonomy, args.contexts)
    for s in new:
        print(json.dumps(s, ensure_ascii=False))


# ---------------------------------------------------------------------------------------------------------------
# check and report
# ---------------------------------------------------------------------------------------------------------------
def requirement(n_slots):
    """How many slots of each (category block, difficulty) the first n_slots of the pattern ask for."""
    need = Counter()
    rint = 0
    for i in range(n_slots):
        cat, diff = gb.PATTERN[i % len(gb.PATTERN)]
        if cat == "r_interpretation":
            atype = R_INTERP_ROTATION[rint % len(R_INTERP_ROTATION)]
            rint += 1
        else:
            atype = gb.ANSWER_TYPE[cat]
        need[(cat, atype, diff)] += 1
    return need


def cmd_check(args):
    try:
        blocks, tax_sha = load_taxonomy(args.taxonomy)
        ctx, ctx_sha = load_contexts(args.contexts)
    except TaxonomyError as e:
        print(f"TAXONOMY CHECK FAILED: {e}")
        sys.exit(1)
    problems = []
    print(f"taxonomy {args.taxonomy}  sha256 {tax_sha}")
    total = 0
    for name, b in blocks.items():
        n = sum(len(s) for s in b["areas"].values())
        total += n
        print(f"  {name:<26} {b['category']:<22} {b['answer_type']:<16} {n:>4} subtopics in {len(b['areas'])} areas")
        for area, subs in b["areas"].items():
            print(f"      {len(subs):>3}  {area}")
            for s in subs:
                if NON_BASE_R.search(s):
                    problems.append(f"{name} / {area}: {s!r} names a non-base-R package")
    print(f"  total {total} subtopics")
    need = requirement(args.benchmark_slots)
    print(f"size rule for a {args.benchmark_slots}-slot benchmark (no repeated subtopic at one difficulty):")
    for (cat, atype, diff), k in sorted(need.items()):
        name = next(n for n, b in blocks.items() if b["category"] == cat and b["answer_type"] == atype)
        have = sum(len(s) for s in blocks[name]["areas"].values())
        flag = "ok" if have >= k else "TOO FEW"
        print(f"  {cat:<22} {atype:<16} {diff:<13} needs {k:>4}, has {have:>4}  {flag}")
        if have < k:
            problems.append(f"{cat}/{atype}/{diff}: needs {k} subtopics, has {have}")
    n = len(ctx["contexts"])
    print(f"contexts {args.contexts}  sha256 {ctx_sha}: {n} contexts")
    for cat, share in ctx["shares"].items():
        k = none_cards(share, n)
        print(f"  {cat:<22} no-context share {share:.2f} -> {k} 'none' cards per {n + k}-card deck "
              f"(exact share {k / (n + k):.3f})")
    for p in problems:
        print("  PROBLEM:", p)
    print("TAXONOMY CHECK " + ("PASSED" if not problems else f"FAILED ({len(problems)} problem(s))"))
    sys.exit(1 if problems else 0)


def mix(slots):
    keys = ("category", "difficulty", "answer_type", "area", "context")
    out = {k: Counter(s[k] if k != "context" else ("none" if s["context"] == NONE else "applied") for s in slots)
           for k in keys}
    out["context_name"] = Counter(s["context"] for s in slots)
    out["no_context_by_category"] = {c: round(sum(1 for s in slots if s["category"] == c and s["context"] == NONE)
                                              / max(1, sum(1 for s in slots if s["category"] == c)), 3)
                                     for c in sorted({s["category"] for s in slots})}
    subs = Counter((s["category"], s["subtopic"]) for s in slots)
    out["subtopics_used"] = len(subs)
    out["subtopic_max_use"] = max(subs.values()) if subs else 0
    out["subtopic_min_use"] = min(subs.values()) if subs else 0
    return out


def cmd_report(args):
    slots = read_slots(args.slots)
    prefixes = [int(x) for x in args.prefixes.split(",")] if args.prefixes else [len(slots)]
    for p in prefixes:
        part = slots[:p]
        mx = mix(part)
        print(f"=== first {len(part)} slots ===")
        for k in ("category", "difficulty", "answer_type"):
            print(f"  {k}: " + ", ".join(f"{a} {b / len(part):.1%}" for a, b in sorted(mx[k].items())))
        print(f"  context: applied {mx['context']['applied'] / len(part):.1%}, none {mx['context'].get('none', 0) / len(part):.1%}; "
              f"no-context share by category {mx['no_context_by_category']}")
        print(f"  contexts used {len(mx['context_name'])}; subtopics used {mx['subtopics_used']} "
              f"(min {mx['subtopic_min_use']}, max {mx['subtopic_max_use']} uses)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--taxonomy", default=str(TAXONOMY_FILE))
    ap.add_argument("--contexts", default=str(CONTEXTS_FILE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="check the taxonomy and the context deck")
    p.add_argument("--benchmark-slots", type=int, default=1150)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("deal", help="deal a set's slots into a frozen slot file and manifest")
    p.add_argument("--set", required=True, choices=list(SETS))
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--seed", required=True, help="the set's seed, recorded in the manifest (each set uses its own)")
    p.add_argument("--out", required=True)
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(fn=cmd_deal)
    p = sub.add_parser("replace", help="deal like-for-like replacement slots from the continued decks")
    p.add_argument("--manifest", required=True)
    p.add_argument("--like", required=True)
    p.add_argument("--count", type=int, default=1)
    p.set_defaults(fn=cmd_replace)
    p = sub.add_parser("report", help="the target mix of a slot file, optionally for several prefixes")
    p.add_argument("--slots", required=True)
    p.add_argument("--prefixes", default=None)
    p.set_defaults(fn=cmd_report)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
