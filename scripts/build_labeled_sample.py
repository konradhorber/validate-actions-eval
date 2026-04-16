"""Stratified random sample of real-world workflows for labeled P/R measurement.

Sample: ~80 from top-100 workflows (stratified by repo, capped to 2 per repo so large
monorepos don't dominate) + 20 from MLOps (stratified by category A-E).

Output:
  corpora/labeled_realworld/manifest.csv  (file, source, stratum, sha256)
  corpora/labeled_realworld/sample/<orig_name>.yml  (copies, for compare_tools)
"""

from __future__ import annotations

import csv
import hashlib
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path

SEED = 20260416
N_TOP100 = 80
N_MLOPS = 20
PER_REPO_CAP = 2  # avoid dominance by monorepos

REPO_ROOT = Path(__file__).resolve().parent.parent
TOP100_DIR = REPO_ROOT / "scripts" / "top-100-workflows"
MLOPS_DIR = REPO_ROOT / "scripts" / "mlops-experiment" / "mlops-workflows"
OUT_ROOT = REPO_ROOT / "corpora" / "labeled_realworld"
SAMPLE_DIR = OUT_ROOT / "sample"
MANIFEST = OUT_ROOT / "manifest.csv"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _top100_repo(filename: str) -> str:
    """Files are named `owner_repo_<rest>.yml`. Use `owner_repo` as stratum."""
    parts = filename.split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else parts[0]


def _mlops_category(filename: str) -> str:
    """Files are named `<CategoryLetter>_...` — pull the leading letter."""
    m = re.match(r"([A-Z])_", filename)
    return m.group(1) if m else "?"


def sample_top100(rng: random.Random) -> list[tuple[Path, str]]:
    all_files = sorted(TOP100_DIR.glob("*.yml"))
    rng.shuffle(all_files)
    per_repo: dict[str, int] = defaultdict(int)
    picked: list[tuple[Path, str]] = []
    for f in all_files:
        repo = _top100_repo(f.name)
        if per_repo[repo] >= PER_REPO_CAP:
            continue
        per_repo[repo] += 1
        picked.append((f, repo))
        if len(picked) >= N_TOP100:
            break
    return picked


def sample_mlops(rng: random.Random) -> list[tuple[Path, str]]:
    by_cat: dict[str, list[Path]] = defaultdict(list)
    for f in sorted(MLOPS_DIR.glob("*.yml")):
        by_cat[_mlops_category(f.name)].append(f)
    # proportional-ish per category
    total = sum(len(v) for v in by_cat.values())
    picked: list[tuple[Path, str]] = []
    for cat, files in sorted(by_cat.items()):
        rng.shuffle(files)
        quota = max(1, round(N_MLOPS * len(files) / total))
        for f in files[:quota]:
            picked.append((f, cat))
    # trim/extend to exactly N_MLOPS
    all_rest = [(f, _mlops_category(f.name)) for f in sorted(MLOPS_DIR.glob("*.yml"))
                if (f, _mlops_category(f.name)) not in picked]
    rng.shuffle(all_rest)
    while len(picked) < N_MLOPS and all_rest:
        picked.append(all_rest.pop())
    return picked[:N_MLOPS]


def main() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for f in SAMPLE_DIR.glob("*.yml"):
        f.unlink()

    rng = random.Random(SEED)
    top = sample_top100(rng)
    mlops = sample_mlops(rng)

    rows: list[dict] = []
    for src, stratum in top:
        dest = SAMPLE_DIR / src.name
        shutil.copy(src, dest)
        rows.append({
            "file": dest.name,
            "source": "top-100",
            "stratum": stratum,
            "sha256": _sha256(src),
            "original_path": str(src.relative_to(REPO_ROOT)),
        })
    for src, stratum in mlops:
        dest = SAMPLE_DIR / src.name
        shutil.copy(src, dest)
        rows.append({
            "file": dest.name,
            "source": "mlops",
            "stratum": stratum,
            "sha256": _sha256(src),
            "original_path": str(src.relative_to(REPO_ROOT)),
        })

    with MANIFEST.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "source", "stratum", "sha256", "original_path"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Summary
    by_source: dict[str, int] = defaultdict(int)
    by_stratum: dict[str, int] = defaultdict(int)
    for r in rows:
        by_source[r["source"]] += 1
        by_stratum[f'{r["source"]}/{r["stratum"]}'] += 1
    print(f"Wrote {len(rows)} workflows → {SAMPLE_DIR}")
    print(f"Manifest: {MANIFEST}")
    print(f"By source: {dict(by_source)}")
    top_strata = sorted(by_stratum.items(), key=lambda x: -x[1])[:8]
    print(f"Top strata: {top_strata}")


if __name__ == "__main__":
    main()
