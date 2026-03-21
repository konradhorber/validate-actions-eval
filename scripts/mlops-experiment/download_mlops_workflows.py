#!/usr/bin/env python3
"""
Download GitHub Actions workflows from MLOps repositories.

This script downloads workflow files from repositories listed in mlops-sources.json
for the MLOps evaluation study. It creates a manifest file for academic traceability.

Usage:
    python scripts/mlops-experiment/download_mlops_workflows.py
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GITHUB_API_BASE = "https://api.github.com"
SCRIPT_DIR = Path(__file__).parent
SOURCES_JSON = SCRIPT_DIR / "mlops-sources.json"
OUTPUT_DIR = SCRIPT_DIR / "mlops-workflows"
MANIFEST_FILE = SCRIPT_DIR / "collection-manifest.json"
GITHUB_TOKEN = os.getenv("GH_TOKEN")

if not GITHUB_TOKEN:
    print("Error: GH_TOKEN environment variable is required")
    print("Set it in .env file or export GH_TOKEN=your_token")
    sys.exit(1)

# Headers for GitHub API requests
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "validate-actions-mlops-study",
}


def load_sources() -> Dict:
    """Load the MLOps sources configuration."""
    if not SOURCES_JSON.exists():
        print(f"Error: Sources file {SOURCES_JSON} not found")
        sys.exit(1)

    with open(SOURCES_JSON, "r") as f:
        return json.load(f)


def create_output_directory() -> Path:
    """Create the output directory if it doesn't exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def sanitize_filename(name: str) -> str:
    """Sanitize filename to be filesystem-safe."""
    return (
        name.replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
        .replace("?", "_")
        .replace("*", "_")
        .replace('"', "_")
    )


def get_repo_info(owner: str, repo: str) -> Optional[Dict]:
    """Get repository metadata including commit SHA for reproducibility."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return {
                "full_name": data.get("full_name"),
                "description": data.get("description"),
                "stars": data.get("stargazers_count"),
                "default_branch": data.get("default_branch"),
                "url": data.get("html_url"),
            }
    except requests.RequestException as e:
        print(f"  Warning: Could not fetch repo info for {owner}/{repo}: {e}")
    return None


def get_latest_commit_sha(owner: str, repo: str, branch: str = "main") -> Optional[str]:
    """Get the latest commit SHA for reproducibility."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{branch}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            return response.json().get("sha")
        # Try master if main doesn't exist
        if branch == "main":
            return get_latest_commit_sha(owner, repo, "master")
    except requests.RequestException:
        pass
    return None


def get_workflow_files(owner: str, repo: str, workflow_path: str) -> List[Dict]:
    """Get list of workflow files from a repository."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{workflow_path}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)

        if response.status_code == 404:
            print(f"  No workflows directory found at {workflow_path}")
            return []

        if response.status_code != 200:
            print(f"  Error fetching workflow list: {response.status_code}")
            return []

        files = response.json()
        if not isinstance(files, list):
            print(f"  Unexpected response format for {owner}/{repo}")
            return []

        workflow_files = [
            f for f in files if f["type"] == "file" and f["name"].endswith((".yml", ".yaml"))
        ]

        return workflow_files

    except requests.RequestException as e:
        print(f"  Request error for {owner}/{repo}: {e}")
        return []


def download_workflow_file(
    owner: str,
    repo: str,
    category: str,
    file_info: Dict,
    output_dir: Path,
) -> Optional[Dict]:
    """Download a single workflow file and return metadata."""
    filename = file_info["name"]
    download_url = file_info["download_url"]

    # Create output filename: category_owner_repo_filename
    # This naming preserves provenance and enables categorical analysis
    sanitized_owner = sanitize_filename(owner)
    sanitized_repo = sanitize_filename(repo)
    sanitized_filename = sanitize_filename(filename)
    output_filename = f"{category}_{sanitized_owner}_{sanitized_repo}_{sanitized_filename}"
    output_path = output_dir / output_filename

    try:
        response = requests.get(download_url, headers=HEADERS, timeout=30)

        if response.status_code != 200:
            print(f"    Error downloading {filename}: {response.status_code}")
            return None

        # Write the file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)

        print(f"    Downloaded: {output_filename}")
        return {
            "original_name": filename,
            "saved_as": output_filename,
            "source_url": file_info.get("html_url"),
            "download_url": download_url,
            "sha": file_info.get("sha"),
            "size_bytes": len(response.text),
        }

    except requests.RequestException as e:
        print(f"    Request error downloading {filename}: {e}")
        return None
    except Exception as e:
        print(f"    Error writing {filename}: {e}")
        return None


def check_rate_limit():
    """Check current rate limit status."""
    url = f"{GITHUB_API_BASE}/rate_limit"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            rate_limit = response.json()
            core = rate_limit["resources"]["core"]
            remaining = core["remaining"]
            reset_time = core["reset"]

            print(f"Rate limit: {remaining} requests remaining")

            if remaining < 10:
                wait_time = reset_time - int(time.time()) + 1
                print(f"Rate limit low, waiting {wait_time} seconds...")
                time.sleep(wait_time)

    except Exception as e:
        print(f"Could not check rate limit: {e}")


def main():
    """Main function to download all MLOps workflow files."""
    print("=" * 70)
    print("MLOps Workflow Collection for Academic Evaluation")
    print("=" * 70)

    print("\nLoading source repositories...")
    sources = load_sources()
    repositories = sources["repositories"]
    print(f"Found {len(repositories)} repositories to process")

    print("\nCreating output directory...")
    output_dir = create_output_directory()
    print(f"Output directory: {output_dir.absolute()}")

    # Initialize manifest for academic traceability
    manifest = {
        "collection_metadata": {
            "collected_at": datetime.utcnow().isoformat() + "Z",
            "methodology": sources["metadata"]["methodology"],
            "categories": sources["metadata"]["categories"],
            "tool_version": "validate-actions MLOps study",
        },
        "summary": {
            "total_repos": 0,
            "total_workflows": 0,
            "by_category": {},
        },
        "repositories": [],
    }

    total_workflows = 0
    successful_downloads = 0

    for i, repo_info in enumerate(repositories, 1):
        owner = repo_info["owner"]
        repo = repo_info["repo"]
        category = repo_info["category"]
        workflow_path = repo_info.get("workflow_path", ".github/workflows")

        print(f"\n[{i}/{len(repositories)}] Processing {owner}/{repo} (Category {category})")

        # Check rate limit every 5 repositories
        if i % 5 == 0:
            check_rate_limit()

        # Get repository metadata for manifest
        github_info = get_repo_info(owner, repo)
        commit_sha = get_latest_commit_sha(
            owner, repo, github_info.get("default_branch", "main") if github_info else "main"
        )

        # Get workflow files
        workflow_files = get_workflow_files(owner, repo, workflow_path)

        if not workflow_files:
            print(f"  Skipping: no workflow files found")
            continue

        print(f"  Found {len(workflow_files)} workflow files")
        total_workflows += len(workflow_files)

        # Track downloads for this repo
        repo_manifest = {
            "owner": owner,
            "repo": repo,
            "category": category,
            "category_name": repo_info.get("category_name"),
            "description": repo_info.get("description"),
            "workflow_path": workflow_path,
            "github_url": repo_info.get("url"),
            "commit_sha": commit_sha,
            "stars": github_info.get("stars") if github_info else repo_info.get("stars"),
            "workflows_collected": [],
        }

        # Download each workflow file
        for file_info in workflow_files:
            result = download_workflow_file(
                owner,
                repo,
                category,
                file_info,
                output_dir,
            )
            if result:
                successful_downloads += 1
                repo_manifest["workflows_collected"].append(result)

            # Small delay to be respectful to the API
            time.sleep(0.1)

        manifest["repositories"].append(repo_manifest)

        # Update category counts
        if category not in manifest["summary"]["by_category"]:
            manifest["summary"]["by_category"][category] = {
                "name": repo_info.get("category_name"),
                "repos": 0,
                "workflows": 0,
            }
        manifest["summary"]["by_category"][category]["repos"] += 1
        manifest["summary"]["by_category"][category]["workflows"] += len(
            repo_manifest["workflows_collected"]
        )

    # Finalize manifest
    manifest["summary"]["total_repos"] = len(
        [r for r in manifest["repositories"] if r["workflows_collected"]]
    )
    manifest["summary"]["total_workflows"] = successful_downloads

    # Save manifest
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

    # Print summary
    print("\n" + "=" * 70)
    print("COLLECTION SUMMARY")
    print("=" * 70)
    print(f"Total workflow files found: {total_workflows}")
    print(f"Successfully downloaded: {successful_downloads}")
    print(f"Failed downloads: {total_workflows - successful_downloads}")
    print(f"\nOutput directory: {output_dir.absolute()}")
    print(f"Manifest file: {MANIFEST_FILE.absolute()}")

    print("\nWorkflows by category:")
    for cat_id, cat_data in manifest["summary"]["by_category"].items():
        print(f"  {cat_id} ({cat_data['name']}): {cat_data['workflows']} workflows")

    print("\nFiles saved with naming convention: category_owner_repo_filename")
    print("Example: A_aws-samples_mlops-sagemaker_build.yml")

    if successful_downloads > 0:
        print(f"\nReady for validation with: python scripts/mlops-experiment/test_mlops_workflows.py")


if __name__ == "__main__":
    main()
