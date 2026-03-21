#!/usr/bin/env python3
"""
Test script for MLOps GitHub workflows validation study.

This script validates all workflows in scripts/mlops-experiment/mlops-workflows/
and produces category-based analysis suitable for academic publication.

Usage:
    # Test all workflows
    python scripts/mlops-experiment/test_mlops_workflows.py

    # Test specific category
    python scripts/mlops-experiment/test_mlops_workflows.py --category A

    # Export results to JSON
    python scripts/mlops-experiment/test_mlops_workflows.py --output results.json

    # Verbose output
    python scripts/mlops-experiment/test_mlops_workflows.py --verbose
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

# Add the project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from validate_actions.cli import StandardCLI  # noqa: E402
from validate_actions.globals.cli_config import CLIConfig  # noqa: E402


class WorkflowTestResult:
    """Represents the result of testing a single workflow."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.filename = file_path.name

        # Parse naming convention: category_owner_repo_workflowname.yml
        parts = self.filename.split("_", 3)
        self.category = parts[0] if len(parts) > 0 else "unknown"
        self.owner = parts[1] if len(parts) > 1 else "unknown"
        self.repo = parts[2] if len(parts) > 2 else "unknown"
        self.workflow_name = parts[3] if len(parts) > 3 else self.filename

        self.success = False
        self.processing_time = 0.0
        self.error_count = 0
        self.warning_count = 0
        self.exception: Optional[Exception] = None
        self.exit_code = 0

    @property
    def status(self) -> str:
        if self.exception:
            return "EXCEPTION"
        elif self.error_count > 0:
            return "FAIL"
        elif self.warning_count > 0:
            return "WARN"
        else:
            return "PASS"

    @property
    def source_repo(self) -> str:
        return f"{self.owner}/{self.repo}"


class MLOpsWorkflowTester:
    """Testing class for MLOps workflows with category-based analysis."""

    # Category names for reporting
    CATEGORY_NAMES = {
        "A": "Cloud Provider Templates",
        "B": "ML Framework Examples",
        "C": "Data/Model Quality Tools",
        "D": "Community Templates",
        "E": "LLMOps Tools",
    }

    def __init__(self, debug: bool = False, verbose: bool = False):
        self.debug = debug
        self.verbose = verbose
        self.setup_logging()
        self.results: List[WorkflowTestResult] = []

    def setup_logging(self):
        """Configure logging based on debug/verbose settings."""
        level = logging.DEBUG if self.debug else logging.INFO
        format_str = (
            "%(asctime)s - %(levelname)s - %(message)s" if self.debug else "%(message)s"
        )
        logging.basicConfig(
            level=level, format=format_str, handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    def get_workflow_files(
        self, base_path: Path, category: Optional[str] = None
    ) -> List[Path]:
        """Get list of workflow files to test, optionally filtered by category."""
        all_workflows = list(base_path.glob("*.yml")) + list(base_path.glob("*.yaml"))

        if category:
            # Filter by category prefix
            all_workflows = [
                f for f in all_workflows if f.name.startswith(f"{category}_")
            ]

        return sorted(all_workflows)

    def test_single_workflow(self, file_path: Path) -> WorkflowTestResult:
        """Test a single workflow file and return detailed results."""
        result = WorkflowTestResult(file_path)
        start_time = time.time()

        try:
            self.logger.debug(f"Processing {result.source_repo}/{result.workflow_name}")

            # Create CLI config for single file validation
            config = CLIConfig(
                workflow_file=str(file_path),
                fix=False,
                github_token=os.getenv("GH_TOKEN"),
                max_warnings=sys.maxsize,
            )

            # Use StandardCLI to validate the single file
            cli = StandardCLI(config)
            result.exit_code = cli._run_single_file(file_path)

            # Extract error and warning counts from aggregator
            result.error_count = cli.aggregator.get_total_errors()
            result.warning_count = cli.aggregator.get_total_warnings()
            result.success = result.error_count == 0

            if self.verbose or self.debug:
                self.log_workflow_details(result)

        except Exception as e:
            result.exception = e
            self.logger.error(
                f"Exception processing {result.source_repo}/{result.workflow_name}: {e}"
            )
            if self.debug:
                import traceback

                self.logger.debug(traceback.format_exc())

        result.processing_time = time.time() - start_time
        return result

    def log_workflow_details(self, result: WorkflowTestResult):
        """Log detailed information for a workflow result."""
        status_symbol = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "EXCEPTION": "💥"}
        symbol = status_symbol.get(result.status, "?")

        self.logger.info(
            f"{symbol} [{result.category}] {result.source_repo}/{result.workflow_name} "
            f"({result.processing_time:.3f}s) - "
            f"Errors: {result.error_count}, Warnings: {result.warning_count}"
        )

    def run_tests(
        self, workflows_dir: Path, category: Optional[str] = None
    ) -> List[WorkflowTestResult]:
        """Run tests on selected workflows."""
        workflow_files = self.get_workflow_files(workflows_dir, category)

        if not workflow_files:
            self.logger.error("No workflow files found to test")
            return []

        self.logger.info(f"Testing {len(workflow_files)} MLOps workflows...")

        self.results = []
        for file_path in workflow_files:
            result = self.test_single_workflow(file_path)
            self.results.append(result)

        return self.results

    def generate_summary(self) -> Dict:
        """Generate summary statistics with category breakdown for paper."""
        if not self.results:
            return {}

        summary: Dict = {
            "total_workflows": len(self.results),
            "by_status": defaultdict(int),
            "by_category": {},
            "by_repo": defaultdict(
                lambda: {"total": 0, "pass": 0, "warn": 0, "fail": 0, "exception": 0}
            ),
            "total_errors": sum(r.error_count for r in self.results),
            "total_warnings": sum(r.warning_count for r in self.results),
            "processing_time": sum(r.processing_time for r in self.results),
            "validation_rate": 0.0,
            "problematic_workflows": [],
        }

        # Initialize category stats
        for cat_id in set(r.category for r in self.results):
            cat_name = self.CATEGORY_NAMES.get(cat_id, f"Category {cat_id}")
            summary["by_category"][cat_id] = {
                "name": cat_name,
                "total": 0,
                "pass": 0,
                "warn": 0,
                "fail": 0,
                "exception": 0,
                "errors": 0,
                "warnings": 0,
            }

        for result in self.results:
            status = result.status
            summary["by_status"][status] += 1

            # Category stats
            cat_stats = summary["by_category"][result.category]
            cat_stats["total"] += 1
            cat_stats[status.lower()] += 1
            cat_stats["errors"] += result.error_count
            cat_stats["warnings"] += result.warning_count

            # Repo stats
            repo_stats = summary["by_repo"][result.source_repo]
            repo_stats["total"] += 1
            repo_stats[status.lower()] += 1

        # Calculate validation success rate
        passing = summary["by_status"]["PASS"] + summary["by_status"]["WARN"]
        summary["validation_rate"] = (passing / len(self.results)) * 100

        # Get problematic workflows (for paper discussion)
        summary["problematic_workflows"] = [
            {
                "file": f"[{r.category}] {r.source_repo}/{r.workflow_name}",
                "category": r.category,
                "errors": r.error_count,
                "warnings": r.warning_count,
                "status": r.status,
            }
            for r in sorted(
                self.results, key=lambda x: (x.error_count, x.warning_count), reverse=True
            )[:15]
            if r.error_count > 0 or r.warning_count > 0
        ]

        return summary

    def print_summary(self):
        """Print a human-readable summary of test results."""
        summary = self.generate_summary()

        if not summary:
            print("No test results to summarize")
            return

        print(f"\n{'='*70}")
        print("MLOPS WORKFLOW VALIDATION STUDY - RESULTS")
        print(f"{'='*70}")

        print(f"\nTotal workflows tested: {summary['total_workflows']}")
        print(f"Total processing time: {summary['processing_time']:.2f}s")
        print(f"Validation success rate: {summary['validation_rate']:.1f}%")
        print()

        print("Overall Results by Status:")
        for status, count in summary["by_status"].items():
            percentage = (count / summary["total_workflows"]) * 100
            print(f"  {status}: {count} ({percentage:.1f}%)")
        print()

        print("Results by Category (for paper Table):")
        print("-" * 70)
        print(
            f"{'Category':<35} {'Total':>6} {'Pass':>6} {'Warn':>6} {'Fail':>6} {'Rate':>8}"
        )
        print("-" * 70)

        for cat_id in sorted(summary["by_category"].keys()):
            cat = summary["by_category"][cat_id]
            pass_rate = (
                ((cat["pass"] + cat["warn"]) / cat["total"]) * 100 if cat["total"] > 0 else 0
            )
            print(
                f"{cat_id}: {cat['name']:<30} {cat['total']:>6} {cat['pass']:>6} "
                f"{cat['warn']:>6} {cat['fail']:>6} {pass_rate:>7.1f}%"
            )

        print("-" * 70)
        print()

        print("Total problems found:")
        print(f"  Errors: {summary['total_errors']}")
        print(f"  Warnings: {summary['total_warnings']}")

        if summary["problematic_workflows"]:
            print("\nMost problematic workflows (for paper discussion):")
            for item in summary["problematic_workflows"]:
                print(
                    f"  {item['file']}: {item['errors']} errors, {item['warnings']} warnings"
                )

        print("\n" + "=" * 70)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Validate MLOps workflows for academic study",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test all MLOps workflows
  python scripts/mlops-experiment/test_mlops_workflows.py

  # Test only Cloud Provider templates (Category A)
  python scripts/mlops-experiment/test_mlops_workflows.py --category A

  # Export results for paper
  python scripts/mlops-experiment/test_mlops_workflows.py --output mlops-results.json

  # Verbose output with per-workflow details
  python scripts/mlops-experiment/test_mlops_workflows.py --verbose
        """,
    )

    parser.add_argument(
        "--category",
        choices=["A", "B", "C", "D", "E"],
        help="Test only workflows from specific category",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output with per-workflow details"
    )
    parser.add_argument("--output", "-o", help="Output results to JSON file")

    args = parser.parse_args()

    # Find the workflows directory
    script_dir = Path(__file__).parent
    workflows_dir = script_dir / "mlops-workflows"

    if not workflows_dir.exists():
        print(f"Error: MLOps workflows directory not found at {workflows_dir}")
        print("Run download_mlops_workflows.py first to collect the workflows.")
        sys.exit(1)

    # Create tester and run tests
    tester = MLOpsWorkflowTester(debug=args.debug, verbose=args.verbose)
    results = tester.run_tests(workflows_dir, category=args.category)

    if not results:
        sys.exit(1)

    # Print summary
    tester.print_summary()

    # Export to JSON if requested
    if args.output:
        summary = tester.generate_summary()
        summary["detailed_results"] = [
            {
                "file": r.filename,
                "category": r.category,
                "source_repo": r.source_repo,
                "workflow_name": r.workflow_name,
                "status": r.status,
                "processing_time": r.processing_time,
                "error_count": r.error_count,
                "warning_count": r.warning_count,
                "exit_code": r.exit_code,
            }
            for r in results
        ]

        # Convert defaultdicts to regular dicts for JSON serialization
        summary["by_status"] = dict(summary["by_status"])
        summary["by_repo"] = dict(summary["by_repo"])

        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nDetailed results exported to {output_path}")

    # Exit with appropriate code
    summary = tester.generate_summary()
    if summary["by_status"].get("EXCEPTION", 0) > 0 or summary["by_status"].get("FAIL", 0) > 0:
        sys.exit(1)
    elif summary["by_status"].get("WARN", 0) > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
