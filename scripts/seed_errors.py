"""Seed known error patterns into real-world workflows for a recall benchmark.

Picks workflows from the labeled sample that BOTH tools currently call clean
(ignoring INFRA-only findings). For each, apply one mutation per layer (rotating
through syntax / schema / registry / execution). The canonical patterns come from
the synthetic corpus (corpora/synthetic/labels.csv), so seeded bugs mirror real
failure modes — not invented ones.

Output: corpora/labeled_realworld/seeded/<orig_stem>__<layer>.yml and seeded_labels.csv
"""

from __future__ import annotations

import csv
import random
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "corpora" / "labeled_realworld" / "sample"
FINDINGS_CSV = REPO_ROOT / "corpora" / "labeled_realworld" / "findings_labeled.csv"
OUT_DIR = REPO_ROOT / "corpora" / "labeled_realworld" / "seeded"
LABELS_CSV = REPO_ROOT / "corpora" / "labeled_realworld" / "seeded_labels.csv"

SEED = 20260416


def pick_clean_workflows(n: int) -> list[Path]:
    """Workflows with NO non-INFRA findings from either tool."""
    findings = list(csv.DictReader(FINDINGS_CSV.open()))
    file_flagged: dict[str, bool] = {}
    for r in findings:
        if r["label"] in {"TP", "FP", "AMBIG"}:  # any real finding, regardless of tool
            file_flagged[r["file"]] = True
    all_files = [p.name for p in SAMPLE_DIR.glob("*.yml")]
    clean = [name for name in all_files if not file_flagged.get(name, False)]
    rng = random.Random(SEED)
    rng.shuffle(clean)
    return [SAMPLE_DIR / name for name in clean[:n]]


# --- Mutations ---
# Each returns (mutated_text, expected_finding_keyword) or None if mutation can't apply.

def mutate_syntax(text: str) -> tuple[str, str] | None:
    """Introduce a YAML syntax error: unclosed flow sequence or unterminated string."""
    # Primary: break a flow sequence like `branches: [main]` by removing the closing ]
    m = re.search(r"^(\s*)(branches|paths|tags)\s*:\s*\[([^\]]*)\]", text, flags=re.MULTILINE)
    if m:
        new_line = f"{m.group(1)}{m.group(2)}: [{m.group(3)}"
        return text[:m.start()] + new_line + text[m.end():], "syntax"
    # Fallback 1: break a `name: 'Something'` quote by dropping the closing quote
    m = re.search(r"^(\s*name\s*:\s*')([^']*)'(.*)$", text, flags=re.MULTILINE)
    if m:
        new_line = f"{m.group(1)}{m.group(2)}{m.group(3)}"  # quote kept open
        return text[:m.start()] + new_line + text[m.end():], "syntax"
    # Fallback 2: introduce a tab at the start of a line under a mapping
    m = re.search(r"^(  )(\w+)\s*:\s*\n", text, flags=re.MULTILINE)
    if m:
        # prepend a tab-indented line that PyYAML rejects
        bad = "\n\t\tbadly_indented_with_tabs: 1\n"
        return text[:m.end()] + bad + text[m.end():], "syntax"
    return None


def mutate_schema(text: str) -> tuple[str, str] | None:
    """Invalid schema: set an invalid shell. Find any `shell: bash` and replace with `shell: fishfish`."""
    if re.search(r"\bshell\s*:\s*\w+", text):
        new = re.sub(r"\bshell\s*:\s*\w+", "shell: fishfish", text, count=1)
        return new, "shell"
    # fallback: inject defaults.run.shell:fishfish under first job
    m = re.search(r"^(\s*)([A-Za-z0-9_\-]+)\s*:\s*\n\s*runs-on\s*:", text, flags=re.MULTILINE)
    if m:
        indent = m.group(1) + "  "
        inject = f"\n{indent}defaults:\n{indent}  run:\n{indent}    shell: fishfish"
        insertion_point = m.end()  # right after "runs-on:"
        # find end of that line
        nl = text.find("\n", insertion_point)
        if nl > 0:
            return text[:nl] + inject + text[nl:], "shell"
    return None


def mutate_registry(text: str) -> tuple[str, str] | None:
    """Add an unknown input to an existing `uses:` step that also has `with:`.
    We add `bogus_unknown_input: "seed"` to the first with-block we find."""
    # Find a `with:\n` followed by indented entries
    m = re.search(r"^(\s*)with\s*:\s*\n((?:\1 +\S.*\n)+)", text, flags=re.MULTILINE)
    if m:
        indent = m.group(1) + "  "
        injected_line = f"{indent}bogus_unknown_input: 'seed'\n"
        return text[:m.end()] + injected_line + text[m.end():], "unknown_input"
    return None


def mutate_execution(text: str) -> tuple[str, str] | None:
    """Reference an undefined job in `needs:` of an existing job."""
    m = re.search(
        r"^(?P<indent>  )(?P<job>[A-Za-z0-9_\-]+)\s*:\s*\n(?P=indent)  runs-on\s*:",
        text,
        flags=re.MULTILINE,
    )
    if m:
        needs_line = f"{m.group('indent')}  needs: nonexistent-seed-job\n"
        nl = text.find("\n", m.start())
        if nl > 0:
            # Keyword chosen so case_detected's substring-match lands on messages like
            # "non-existent job" (validate-actions) or "does not exist" (actionlint).
            return text[: nl + 1] + needs_line + text[nl + 1:], "nonexistent-seed-job"
    return None


MUTATIONS = [
    ("syntax", mutate_syntax),
    ("schema", mutate_schema),
    ("registry", mutate_registry),
    ("execution", mutate_execution),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in OUT_DIR.glob("*.yml"):
        f.unlink()

    clean_files = pick_clean_workflows(40)  # up to 40 candidates; actual seeds = those where mutations apply
    print(f"Picked {len(clean_files)} clean workflows")

    labels: list[dict] = []
    successes = {L: 0 for L, _ in MUTATIONS}

    for fp in clean_files:
        orig = fp.read_text(errors="replace")
        for layer, mutator in MUTATIONS:
            result = mutator(orig)
            if result is None:
                continue
            mutated_text, expected_keyword = result
            out_name = f"{fp.stem}__{layer}.yml"
            (OUT_DIR / out_name).write_text(mutated_text)
            labels.append({
                "file": out_name,
                "layer": layer,
                "source_file": fp.name,
                "expected_finding": expected_keyword,
                "source_test": f"seed_{layer}",
            })
            successes[layer] += 1

    with LABELS_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "layer", "source_file", "expected_finding", "source_test"])
        w.writeheader()
        w.writerows(labels)

    print(f"Wrote {len(labels)} seeded cases → {OUT_DIR}")
    for L, n in successes.items():
        print(f"  {L}: {n}")
    print(f"Labels: {LABELS_CSV}")


if __name__ == "__main__":
    main()
