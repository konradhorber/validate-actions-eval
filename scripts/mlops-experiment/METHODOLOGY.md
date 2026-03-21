# MLOps Workflow Evaluation Methodology

## Purpose

This document describes the systematic methodology for selecting MLOps example workflows for evaluation with the `validate-actions` tool. The selection criteria are designed to be reproducible and defensible for academic publication.

## Selection Criteria

A repository is included in this evaluation if it meets ALL of the following criteria:

1. **Contains GitHub Actions workflows** - The repository must have `.github/workflows/*.yml` or `.yaml` files
2. **MLOps-focused purpose** - The repository's primary purpose is to demonstrate, template, or facilitate MLOps practices
3. **Example/Template nature** - The workflows are intended for practitioners to use or adapt (not just the tool's internal CI/CD)
4. **Publicly accessible** - The repository is publicly available on GitHub
5. **Documentation or official backing** - The repository is either:
   - Maintained by a recognized MLOps tool vendor/cloud provider, OR
   - Referenced in official documentation, OR
   - Has significant community adoption (>50 stars for template repos)

## Source Categories

Repositories are categorized into the following types to ensure comprehensive coverage of the MLOps ecosystem:

### Category A: Cloud Provider MLOps Templates
**Rationale**: Cloud providers offer official MLOps templates that represent vendor-recommended best practices for production ML deployments.

| Source | Repository | Expected Content |
|--------|------------|------------------|
| AWS SageMaker | `aws-samples/mlops-sagemaker-github-actions` | Train, register, deploy workflows |
| Azure ML | `Azure/mlops-v2` | MLOps v2 reference architecture |
| Azure ML Samples | `Azure-Samples/mlops-enterprise-template` | Enterprise MLOps patterns |
| Google Cloud | `GoogleCloudPlatform/mlops-with-vertex-ai` | Vertex AI pipelines |

### Category B: ML Framework Official Examples
**Rationale**: ML frameworks provide reference implementations that practitioners commonly adopt.

| Source | Repository | Expected Content |
|--------|------------|------------------|
| DVC + CML | `iterative/cml` (examples) | Continuous ML reporting |
| DVC Guide | `mlops-guide/dvc-gitactions` | DVC pipeline workflows |
| MLflow | MLflow example repos | Experiment tracking integration |
| ZenML | `zenml-io/zenml-gitflow` | ZenML orchestration patterns |

### Category C: Data/Model Quality Tools
**Rationale**: These tools address ML-specific quality concerns (data validation, model monitoring).

| Source | Repository | Expected Content |
|--------|------------|------------------|
| Great Expectations | `great-expectations/great_expectations_action` | Data validation workflows |
| Evidently AI | `evidentlyai/evidently-action` | Model/data drift monitoring |

### Category D: Community MLOps Templates
**Rationale**: Well-adopted community templates reflect practitioner patterns and real-world usage.

| Source | Repository | Expected Content |
|--------|------------|------------------|
| MLOps Guide | `mlops-guide/mlops-template` | End-to-end MLOps template |
| fmind | `fmind/mlops-python-package` | MLOps Python packaging |
| Made With ML | `GokuMohandas/mlops-course` | MLOps course materials |

### Category E: LLMOps Tools and Examples
**Rationale**: Large Language Model operations (LLMOps) represents an emerging specialization within MLOps, addressing unique challenges in LLM deployment, evaluation, and continuous improvement. Including this category addresses the growing importance of CI/CD practices for LLM-based applications.

| Source | Repository | Expected Content |
|--------|------------|------------------|
| LangChain | `langchain-samples/cicd-pipeline-example` | LLM agent CI/CD with LangSmith |
| Promptfoo | `promptfoo/promptfoo-action` | LLM output testing and evaluation |

## Workflow Extraction Process

For each repository:

1. **Clone or API fetch** the `.github/workflows/` directory
2. **Extract all `.yml` and `.yaml` files** that represent workflow definitions
3. **For README-embedded examples**: When documentation shows example workflows but no actual workflow files exist, extract the YAML from documentation
4. **Record metadata**: Source repo, category, workflow purpose, date collected

## Comparison with Prior Work

This methodology mirrors the paper's existing evaluation approach:
- **161 GitHub Starter Templates**: Official templates from github.com/actions/starter-workflows
- **598 Production Workflows**: Top-100 repositories by GitHub stars

The MLOps evaluation extends this to specialized ML pipeline configurations, testing whether general-purpose validation frameworks apply to domain-specific workflows.

## Expected Dataset Size

Target: **80-100 workflows** across categories

Actual collection: **84 workflows** from 18 repositories

| Category | Description | Workflows |
|----------|-------------|-----------|
| A | Cloud Provider Templates | 9 |
| B | ML Framework Examples | 46 |
| C | Data/Model Quality Tools | 5 |
| D | Community Templates | 16 |
| E | LLMOps Tools | 8 |

This sample size is:
- Sufficient to identify MLOps-specific patterns and enable statistical comparison
- Comparable to the starter templates evaluation (N=161)
- Covers both traditional MLOps and emerging LLMOps practices

## Reproducibility

All source repositories are versioned. The exact commit SHAs are recorded at collection time to ensure reproducibility. The collection script outputs a manifest file documenting each workflow's provenance.
