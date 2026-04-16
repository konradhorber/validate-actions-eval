"""Summarize precision per tool and per layer from findings_labeled.csv."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IN_CSV = REPO_ROOT / "corpora" / "labeled_realworld" / "findings_labeled.csv"
OUT_JSON = REPO_ROOT / "out" / "realworld_precision.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--errors-only", action="store_true",
                    help="Exclude warning-level findings from both the numerator and denominator.")
    ap.add_argument("--out", default=str(OUT_JSON))
    args = ap.parse_args()
    rows = list(csv.DictReader(IN_CSV.open()))
    if args.errors_only:
        rows = [r for r in rows if r.get("severity", "") == "error"]

    # overall + per-layer, excluding INFRA
    def _bucket():
        return {"TP": 0, "FP": 0, "AMBIG": 0, "INFRA": 0}

    per_tool: dict[str, dict[str, int]] = defaultdict(_bucket)
    per_tool_layer: dict[tuple[str, str], dict[str, int]] = defaultdict(_bucket)

    for r in rows:
        per_tool[r["tool"]][r["label"]] += 1
        per_tool_layer[(r["tool"], r["layer"])][r["label"]] += 1

    summary: dict = {"per_tool": {}, "per_tool_layer": {}, "notes": {
        "INFRA_excluded": "marketplace fetch warnings excluded from P/R — they reflect missing "
                          "GH_TOKEN rather than validation quality",
        "AMBIG_excluded": "AMBIG findings excluded from precision (should be 0 after promotion).",
        "layer_assignment": "layer is rule-based heuristic; see collect_findings.layer_of_rule",
    }}

    def _prec(b: dict[str, int]) -> float:
        denom = b["TP"] + b["FP"]
        return b["TP"] / denom if denom else 0.0

    for tool, b in per_tool.items():
        summary["per_tool"][tool] = {
            **b,
            "precision_excl_ambig_infra": _prec(b),
            "total_findings": sum(b.values()),
        }

    for (tool, layer), b in per_tool_layer.items():
        summary["per_tool_layer"].setdefault(tool, {})[layer] = {
            **b,
            "precision_excl_ambig_infra": _prec(b),
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {out_path} (errors_only={args.errors_only})")

    print()
    print("=== Overall precision (excluding INFRA + AMBIG) ===")
    for tool, v in summary["per_tool"].items():
        print(f"  {tool:17s}  TP={v['TP']:4d}  FP={v['FP']:4d}  INFRA={v['INFRA']:4d}  "
              f"AMBIG={v['AMBIG']:3d}  precision={v['precision_excl_ambig_infra']*100:.1f}%")

    print()
    print("=== Per-layer precision ===")
    for tool in sorted(summary["per_tool_layer"].keys()):
        print(f"  {tool}:")
        for layer, v in sorted(summary["per_tool_layer"][tool].items()):
            denom = v["TP"] + v["FP"]
            if denom == 0 and v["INFRA"] == 0:
                continue
            print(f"    {layer:10s}  TP={v['TP']:3d}  FP={v['FP']:3d}  INFRA={v['INFRA']:3d}  "
                  f"precision={v['precision_excl_ambig_infra']*100:.1f}%")


if __name__ == "__main__":
    main()
