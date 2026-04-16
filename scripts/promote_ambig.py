"""Second-pass labeler: resolve AMBIG findings by inspecting workflow content.

Rules:
- actionlint `runner-label` "is unknown" → FP
  Rationale: the message lists GitHub-hosted labels as "available". Actionlint isn't
  configured to know about self-hosted / custom labels. The flagged labels are all
  consistent with custom runners (e.g. `gcp-p100-test`, `electron-arc-...`, `ubicloud-...`).

- validate-actions `jobs-syntax-error` matrix-related → FP
  Rationale: the tool's matrix model doesn't accept complex-object axis values;
  GitHub Actions does. Verified against tailwindcss/ci.yml.

- validate-actions `expressions-contexts` `needs.<job>.outputs.<prop>`:
  - If `<job>` is defined IN the workflow → FP (reusable-workflow outputs tool can't resolve).
  - If `<job>` is NOT defined → TP (real typo).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IN_CSV = REPO_ROOT / "corpora" / "labeled_realworld" / "findings_labeled.csv"
SAMPLE_DIR = REPO_ROOT / "corpora" / "labeled_realworld" / "sample"


_NEEDS_JOB_RE = re.compile(r"needs\.([A-Za-z0-9_\-]+)\.outputs\.([A-Za-z0-9_\-]+)")


def job_defined(workflow_text: str, job_name: str) -> bool:
    """Conservative check: is there a top-level `  <job_name>:` entry under `jobs:`?"""
    # Find jobs: section boundaries
    lines = workflow_text.splitlines()
    in_jobs = False
    jobs_indent = None
    for ln in lines:
        stripped = ln.rstrip()
        if re.match(r"^jobs\s*:\s*$", stripped):
            in_jobs = True
            continue
        if in_jobs:
            if re.match(r"^\S", ln):  # back at column 0 → jobs section ended
                in_jobs = False
                continue
            if jobs_indent is None and ln.strip():
                jobs_indent = len(ln) - len(ln.lstrip())
            if jobs_indent is not None and ln.startswith(" " * jobs_indent):
                # a job key at the right indent
                m = re.match(r"^" + " " * jobs_indent + r"([A-Za-z0-9_\-]+)\s*:", ln)
                if m and m.group(1) == job_name:
                    return True
    return False


def promote(tool: str, rule: str, message: str, file: str) -> tuple[str, str] | None:
    r = (rule or "").lower()
    ml = (message or "").lower()

    if tool == "actionlint" and r == "runner-label" and "is unknown" in ml:
        return "FP", "actionlint lacks self-hosted label config; custom labels are valid"

    if tool == "validate-actions" and r == "jobs-syntax-error":
        if ("matrix" in ml or "job combinations" in ml or
            "matrix axis" in ml or "matrix exclude" in ml):
            return "FP", "complex-object matrix axis values are valid in GH Actions; tool limitation"

    if tool == "validate-actions" and r == "expressions-contexts":
        m = _NEEDS_JOB_RE.search(message)
        if m:
            job_name = m.group(1)
            wf_path = SAMPLE_DIR / file
            if wf_path.exists():
                text = wf_path.read_text(errors="replace")
                if job_defined(text, job_name):
                    return "FP", f"reusable-workflow outputs of job '{job_name}' unresolvable by static tool"
                else:
                    return "TP", f"referenced job '{job_name}' not defined in workflow"
        # `GITHUB.foo` (uppercase) — context is case-insensitive in GH Actions.
        if "unknown property 'GITHUB'" in message.lower() or "'GITHUB'" in message:
            return "FP", "GitHub Actions context references are case-insensitive"
        # `matrix.<complex-axis>.prop` — downstream of complex-matrix limitation
        if re.search(r"matrix\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", message):
            return "FP", "downstream of complex-matrix-axis limitation"
        # `matrix.<axis>` when the workflow has complex matrix axes
        if "unknown property 'runner'" in message.lower() or "unknown property 'node-version'" in message.lower():
            return "FP", "matrix axis present but tool couldn't build context (complex-matrix limitation)"

    return None


def main() -> None:
    rows = list(csv.DictReader(IN_CSV.open()))
    promoted = 0
    from collections import Counter
    before: Counter = Counter()
    after: Counter = Counter()
    for row in rows:
        before[(row["tool"], row["label"])] += 1
        if row["label"] == "AMBIG":
            result = promote(row["tool"], row["rule"], row["message"], row["file"])
            if result:
                row["label"], row["notes"] = result
                promoted += 1
        after[(row["tool"], row["label"])] += 1

    with IN_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    print(f"Promoted {promoted} AMBIG findings.")
    print("After:")
    for (tool, lbl), n in sorted(after.items()):
        print(f"  {tool:17s}  {lbl:6s}  {n}")


if __name__ == "__main__":
    main()
