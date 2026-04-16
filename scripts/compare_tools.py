"""Head-to-head comparison driver for validate-actions and actionlint.

Runs both tools against a corpus of workflow files and emits:
- a per-file CSV (one row per tool × file) with runtime and finding counts
- a summary JSON with per-layer recall (if labels given), FPR (for a "all valid" corpus),
  and runtime distribution.

Usage:

  # synthetic corpus (recall)
  python scripts/compare_tools.py \\
      --corpus corpora/synthetic \\
      --labels corpora/synthetic/labels.csv \\
      --out out/synthetic

  # curated templates (FPR — all assumed valid)
  python scripts/compare_tools.py \\
      --corpus ../validate-actions/tests/fixtures/workflows/official_workflows \\
      --assume-valid \\
      --out out/curated

  # real-world (runtime + volume only, no ground truth)
  python scripts/compare_tools.py --corpus scripts/top-100-workflows --out out/realworld
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.eval_core import RunResult, case_detected  # noqa: E402
from scripts.runners import actionlint_runner, validate_actions_runner  # noqa: E402

TOOLS = {
    "validate-actions": validate_actions_runner.run,
    "actionlint": actionlint_runner.run,
}


def gather_files(corpus_root: Path) -> list[Path]:
    files: list[Path] = []
    for pat in ("*.yml", "*.yaml"):
        files.extend(corpus_root.rglob(pat))
    return sorted(files)


def load_labels(labels_csv: Optional[Path]) -> dict[str, dict]:
    """Map corpus-relative posix path → row dict from labels.csv."""
    if not labels_csv or not labels_csv.exists():
        return {}
    with labels_csv.open() as fh:
        reader = csv.DictReader(fh)
        return {row["file"]: row for row in reader}


def relative_to_corpus(file: Path, corpus_root: Path) -> str:
    return file.relative_to(corpus_root).as_posix()


def run_all(corpus_root: Path, files: list[Path], errors_only: bool = False) -> dict[str, list[RunResult]]:
    results: dict[str, list[RunResult]] = {t: [] for t in TOOLS}
    total = len(files)
    for i, f in enumerate(files, 1):
        for tool, runner in TOOLS.items():
            rr = runner(f)
            if errors_only:
                rr.findings = [x for x in rr.findings if x.severity == "error"]
            results[tool].append(rr)
        if i % 25 == 0 or i == total:
            print(f"  [{i}/{total}] last={f.name}", file=sys.stderr)
    return results


def summarize(
    results: dict[str, list[RunResult]],
    files: list[Path],
    corpus_root: Path,
    labels: dict[str, dict],
    assume_valid: bool,
) -> dict:
    summary: dict = {"per_tool": {}}

    layers = set()
    for lbl in labels.values():
        if lbl.get("layer"):
            layers.add(lbl["layer"])

    for tool, runs in results.items():
        runtimes = [r.runtime_s for r in runs]
        n = len(runs)
        finding_counts = [len(r.findings) for r in runs]
        error_counts = [sum(1 for x in r.findings if x.severity == "error") for r in runs]
        warning_counts = [sum(1 for x in r.findings if x.severity == "warning") for r in runs]
        crashes = sum(1 for r in runs if r.crashed)

        per_layer_hits: dict[str, int] = {L: 0 for L in layers}
        per_layer_total: dict[str, int] = {L: 0 for L in layers}

        files_flagged_any = 0
        files_flagged_err = 0
        for run, path in zip(runs, files):
            rel = relative_to_corpus(path, corpus_root)
            if run.findings:
                files_flagged_any += 1
            if any(f.severity == "error" for f in run.findings):
                files_flagged_err += 1
            if labels:
                lbl = labels.get(rel)
                if lbl:
                    layer = lbl["layer"]
                    per_layer_total[layer] = per_layer_total.get(layer, 0) + 1
                    hit = case_detected(
                        run.findings,
                        lbl.get("expected_finding", "") or "",
                        lbl.get("source_test", "") or "",
                    )
                    if hit:
                        per_layer_hits[layer] = per_layer_hits.get(layer, 0) + 1

        tool_summary: dict = {
            "n_files": n,
            "n_crashes": crashes,
            "n_files_flagged_any": files_flagged_any,
            "n_files_flagged_error": files_flagged_err,
            "total_findings": sum(finding_counts),
            "total_errors": sum(error_counts),
            "total_warnings": sum(warning_counts),
            "runtime_s": {
                "mean": statistics.mean(runtimes) if runtimes else 0,
                "median": statistics.median(runtimes) if runtimes else 0,
                "p95": _percentile(runtimes, 95),
                "max": max(runtimes) if runtimes else 0,
                "total": sum(runtimes),
            },
        }

        if labels:
            overall_hits = sum(per_layer_hits.values())
            overall_total = sum(per_layer_total.values())
            tool_summary["recall"] = {
                "overall": _safe_div(overall_hits, overall_total),
                "by_layer": {
                    L: {
                        "hits": per_layer_hits.get(L, 0),
                        "total": per_layer_total.get(L, 0),
                        "recall": _safe_div(per_layer_hits.get(L, 0), per_layer_total.get(L, 0)),
                    }
                    for L in sorted(layers)
                },
            }

        if assume_valid:
            tool_summary["fpr"] = {
                "total_files": n,
                "errors_only": {
                    "files_flagged": files_flagged_err,
                    "rate": _safe_div(files_flagged_err, n),
                },
                "any_severity": {
                    "files_flagged": files_flagged_any,
                    "rate": _safe_div(files_flagged_any, n),
                },
            }

        summary["per_tool"][tool] = tool_summary

    return summary


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * (p / 100)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def write_csv(
    out_csv: Path,
    results: dict[str, list[RunResult]],
    files: list[Path],
    corpus_root: Path,
    labels: dict[str, dict],
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "tool",
                "file",
                "layer",
                "expected_finding",
                "detected",
                "n_findings",
                "runtime_s",
                "exit_code",
                "crashed",
            ]
        )
        for tool, runs in results.items():
            for run, path in zip(runs, files):
                rel = relative_to_corpus(path, corpus_root)
                lbl = labels.get(rel, {}) if labels else {}
                detected = ""
                if lbl:
                    detected = "1" if case_detected(
                        run.findings,
                        lbl.get("expected_finding", "") or "",
                        lbl.get("source_test", "") or "",
                    ) else "0"
                w.writerow(
                    [
                        tool,
                        rel,
                        lbl.get("layer", ""),
                        lbl.get("expected_finding", ""),
                        detected,
                        len(run.findings),
                        f"{run.runtime_s:.4f}",
                        run.exit_code,
                        int(run.crashed),
                    ]
                )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="Directory of workflow files")
    ap.add_argument("--labels", help="labels.csv with per-file ground truth (for recall)")
    ap.add_argument(
        "--assume-valid",
        action="store_true",
        help="Treat all files as valid (any finding counts toward FPR)",
    )
    ap.add_argument("--out", required=True, help="Output path prefix (writes .csv and .json)")
    ap.add_argument("--limit", type=int, default=0, help="Cap files processed (0 = all)")
    ap.add_argument(
        "--errors-only",
        action="store_true",
        help="Filter each tool's findings to severity='error' before matching/counting.",
    )
    args = ap.parse_args()

    corpus_root = Path(args.corpus).resolve()
    files = gather_files(corpus_root)
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"No .yml/.yaml files under {corpus_root}", file=sys.stderr)
        sys.exit(2)

    labels = load_labels(Path(args.labels)) if args.labels else {}

    out_prefix = Path(args.out)
    out_csv = out_prefix.with_suffix(".csv")
    out_json = out_prefix.with_suffix(".json")

    mode = " (errors-only)" if args.errors_only else ""
    print(f"Running {len(TOOLS)} tools over {len(files)} files from {corpus_root}{mode}", file=sys.stderr)
    results = run_all(corpus_root, files, errors_only=args.errors_only)

    write_csv(out_csv, results, files, corpus_root, labels)
    summary = summarize(results, files, corpus_root, labels, args.assume_valid)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2))

    print(f"Wrote {out_csv} ({sum(len(v) for v in results.values())} rows)")
    print(f"Wrote {out_json}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
