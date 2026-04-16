"""Auto-label findings_to_label.csv with TP / FP / INFRA / AMBIGUOUS via a documented rubric.

Each label carries a short `notes` field explaining the judgement. Ambiguous cases are
flagged for human review; after the human pass, rerun the rest of the pipeline unchanged.

Rubric (conservative — when in doubt, AMBIGUOUS):

validate-actions:
  marketplace  "Couldn't fetch..."               → INFRA  (network, not a validation finding)
  action-input "uses unknown input: X"           → TP     (documented input contract)
               "requires inputs: X"              → TP
  action-version "Using specific version of ./"  → FP     (local action path, no version concept)
                 "without version specification" → TP     (valid security recommendation)
                 "outdated"                      → TP
                 "pin to SHA"                    → TP
  events-syntax-error                            → TP     (schema rule)
  jobs-syntax-error "Unknown job key: continue-on-error" → FP  (valid GH Actions key)
                    "Strategy fail-fast must be a boolean" → TP
                    "Matrix definition resulted in no job combinations" → AMBIG (could be intentional)
                    other "Unknown job key" → AMBIG (need to verify key is truly invalid)
                    other                        → TP
  expressions-contexts "does not match any context" → AMBIG  (tool's context model may lag; verify)
  yaml-syntax                                    → TP     (PyYAML said so)

actionlint:
  action "the runner of ...@vX is too old"       → TP     (deprecated Node runner)
         "action ... does not exist" / "not found" → TP
         "input ... is not defined"              → TP
         "unexpected input"                      → TP
         "missing input"                         → TP
  expression "property X is not defined"         → TP     (expression can't resolve)
             other                               → TP
  runner-label "label X is unknown"              → AMBIG  (often self-hosted / org runner)
  syntax-check                                   → TP
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IN_CSV = REPO_ROOT / "corpora" / "labeled_realworld" / "findings_to_label.csv"
OUT_CSV = REPO_ROOT / "corpora" / "labeled_realworld" / "findings_labeled.csv"


def label_one(tool: str, rule: str, severity: str, message: str, context: str) -> tuple[str, str]:
    t = tool
    r = (rule or "").lower()
    m = (message or "")
    ml = m.lower()

    # --- validate-actions ---
    if t == "validate-actions":
        if r == "marketplace" and "couldn't fetch" in ml:
            return "INFRA", "network: no GH_TOKEN; not a validation finding"
        if r == "action-input":
            if "unknown input" in ml or "requires inputs" in ml:
                return "TP", "documented input contract violation"
            return "AMBIG", "unfamiliar action-input message"
        if r == "action-version":
            if re.search(r"\bof \./|of \.\b", m) and "./" in m:
                return "FP", "local action path ./ has no version concept"
            if "without version" in ml or "without version spec" in ml:
                return "TP", "valid security recommendation"
            if "outdated" in ml or "pin" in ml or "sha" in ml:
                return "TP", "outdated / unpinned action"
            return "AMBIG", "unfamiliar action-version message"
        if r == "events-syntax-error":
            return "TP", "schema violation on on.* event"
        if r == "jobs-syntax-error":
            if re.search(r"unknown job key:\s*continue-on-error", ml):
                return "FP", "continue-on-error IS a valid job-level key"
            if "must be a boolean" in ml or "must be a string" in ml or "must be a number" in ml:
                return "TP", "schema type violation"
            if "no job combinations" in ml:
                return "AMBIG", "matrix include/exclude pruned all combos — could be intentional"
            if "unknown job key" in ml:
                return "AMBIG", "verify key is not a valid GH-Actions extension"
            return "AMBIG", "unfamiliar jobs-syntax-error message"
        if r == "expressions-contexts":
            # real typo vs tool's context model being incomplete — conservative default
            if "does not match any context" in ml or "unknown property" in ml:
                return "AMBIG", "context may be a needs-output the tool can't resolve statically"
            return "AMBIG", "unfamiliar expressions-contexts message"
        if r == "yaml-syntax":
            return "TP", "PyYAML-level parse error"

    # --- actionlint ---
    if t == "actionlint":
        if r == "action":
            if "too old to run" in ml:
                return "TP", "deprecated Node runner version"
            if "does not exist" in ml or "could not be found" in ml or "not found" in ml:
                return "TP", "action repo/ref resolves to nothing"
            if "unexpected input" in ml or "is not defined" in ml or "not defined as input" in ml:
                return "TP", "action-metadata says input unknown"
            if "missing input" in ml or "required input" in ml:
                return "TP", "required input missing"
            return "AMBIG", "unfamiliar actionlint action-message"
        if r == "expression":
            if "is not defined" in ml or "not defined in object type" in ml:
                return "TP", "unresolved property reference"
            return "TP", "expression-layer issue"
        if r == "runner-label":
            if "is unknown" in ml:
                return "AMBIG", "often self-hosted / org runner — can't verify without repo config"
            return "AMBIG", "unfamiliar runner-label message"
        if r == "syntax-check":
            return "TP", "explicit schema mismatch"

    return "AMBIG", "no rule matched"


def main() -> None:
    rows = list(csv.DictReader(IN_CSV.open()))
    out_rows: list[dict] = []
    from collections import Counter
    c: Counter = Counter()
    for row in rows:
        label, notes = label_one(
            row["tool"], row["rule"], row["severity"], row["message"], row.get("context", ""),
        )
        row["label"] = label
        row["notes"] = notes
        c[(row["tool"], label)] += 1
        out_rows.append(row)

    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=out_rows[0].keys())
        w.writeheader()
        w.writerows(out_rows)

    print(f"Wrote {len(out_rows)} labeled findings → {OUT_CSV}")
    for (tool, lbl), n in sorted(c.items()):
        print(f"  {tool:17s}  {lbl:6s}  {n}")


if __name__ == "__main__":
    main()
