"""Run both tools on the labeled sample and emit `findings_to_label.csv`.

One row per finding with: tool, file, line, col, rule, severity, message, context (3-line YAML snippet).
The `label` column is left blank — filled in later by label_findings.py.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.runners import actionlint_runner, validate_actions_runner  # noqa: E402

REPO_ROOT = _HERE.parent
SAMPLE_DIR = REPO_ROOT / "corpora" / "labeled_realworld" / "sample"
OUT_CSV = REPO_ROOT / "corpora" / "labeled_realworld" / "findings_to_label.csv"


def context_snippet(file_path: Path, line: int | None, width: int = 2) -> str:
    """Return a short 1-5 line snippet around the finding's line. Newlines → \\n."""
    if not line or line < 1:
        return ""
    try:
        lines = file_path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    lo = max(0, line - 1 - width)
    hi = min(len(lines), line + width)
    out = []
    for i in range(lo, hi):
        marker = ">" if (i + 1) == line else " "
        out.append(f"{marker} {i + 1:3d}: {lines[i]}")
    return "\n".join(out).replace("\n", "\\n")


def layer_of_rule(tool: str, rule: str, message: str) -> str:
    """Heuristic layer classification for precision breakdown."""
    r = (rule or "").lower()
    m = (message or "").lower()
    # registry (action marketplace / metadata)
    if r in {"action-input", "action-output", "action-version", "marketplace"}: return "registry"
    if tool == "actionlint" and r == "action":  # actionlint bundles all marketplace-layer checks here
        return "registry"
    if "action" in r and "uses" in r: return "registry"
    if "input" in m and ("required" in m or "unknown" in m): return "registry"
    # execution / expressions
    if r in {"expressions-contexts", "expressions", "expression", "if-cond", "cond"}: return "execution"
    if "expression" in r or "context" in r: return "execution"
    # syntax
    if r == "yaml-syntax" or "syntax" in r: return "syntax"
    # default: schema (everything else from structural/schema checks)
    return "schema"


def main() -> None:
    files = sorted(SAMPLE_DIR.glob("*.yml"))
    print(f"Running 2 tools × {len(files)} files = {2 * len(files)} invocations", file=sys.stderr)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "sample_id", "tool", "file", "line", "col", "rule", "severity",
            "message", "layer", "context", "label", "notes",
        ])
        sid = 0
        for i, fp in enumerate(files, 1):
            runs = [
                validate_actions_runner.run(fp),
                actionlint_runner.run(fp),
            ]
            for rr in runs:
                for f in rr.findings:
                    sid += 1
                    layer = layer_of_rule(rr.tool, f.rule, f.message)
                    w.writerow([
                        sid, rr.tool, fp.name, f.line, f.col, f.rule,
                        f.severity, f.message, layer,
                        context_snippet(fp, f.line),
                        "", "",
                    ])
            if i % 20 == 0:
                print(f"  [{i}/{len(files)}] findings so far: {sid}", file=sys.stderr)

    print(f"Wrote {sid} findings to {OUT_CSV}")


if __name__ == "__main__":
    main()
