"""
separation.py - keep everything Codex produces away from the models' development (owner's decision, 2026-11-21).

WHAT THIS IS AND WHY (docs/methodology/workflow.md Section 2.3)
Codex is used only like a teacher grading tests: it screens benchmark questions and grades benchmark answers of finished
models. OpenAI's Usage Policies forbid using its outputs as training material or training signals (labels, scores,
selecting, filtering or validating training data), including evaluation outputs that are later used that way. So no Codex
output may ever reach the training data, the training code, the development-set measures or the teacher setup.

Upstream, Codex runs in a separate workspace folder and its results are stored only under folders with "codex" in their
name. Downstream (this module), every tool that builds or reads TRAINING-side material refuses:
  - any input path inside the Codex workspace, the Codex key folder, or any folder or file whose name contains "codex";
  - any row that carries a Codex field (a key starting with "codex", or a "verdicts" list).
A refusal stops the tool with a plain message; nothing is read.

Used by: generate_set.py collect-train, decontaminate.py (and later the training script and the development scorecard).
"""

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def codex_roots():
    p = yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())
    roots = [REPO / "results" / "codex"]
    for key in ("codex_workspace", "codex_keys"):
        if p.get(key):
            roots.append(Path(p[key]))
    return [r.resolve() for r in roots]


def is_codex_path(path):
    rp = Path(path).resolve()
    if any("codex" in part.lower() for part in rp.parts):
        return True
    for root in codex_roots():
        try:
            rp.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def refuse_codex_path(path, tool):
    """Stop `tool` if `path` is Codex material."""
    if path and is_codex_path(path):
        sys.exit(f"{tool}: refused {path}: it is Codex material, and Codex output must never reach training-side code "
                 f"(docs/methodology/workflow.md Section 2.3). Nothing was read.")


def refuse_codex_rows(rows, tool, source=""):
    """Stop `tool` if any row carries a Codex field."""
    for r in rows:
        if not isinstance(r, dict):
            continue
        bad = [k for k in r if k.lower().startswith("codex") or k == "verdicts"]
        if bad:
            sys.exit(f"{tool}: refused {source or 'input'}: row {r.get('item_id', '?')} carries Codex field(s) {bad}; Codex "
                     f"output must never reach training-side code (workflow.md Section 2.3). Nothing was used.")
