"""Shared dataclasses and matching logic for the head-to-head tool comparison.

Both the synthetic-corpus driver and the labeled-real-world driver use this module so
finding-matching, per-layer recall, and FPR are computed consistently across corpora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Finding:
    """A single diagnostic emitted by a tool about a workflow file."""

    tool: str
    file: str
    line: Optional[int]
    col: Optional[int]
    rule: str  # tool-specific rule id (e.g. "action-input", "syntax-check")
    message: str
    severity: str = "error"  # "error" | "warning" | "info"


@dataclass
class RunResult:
    """Result of running one tool on one workflow file."""

    tool: str
    file: str
    findings: list[Finding] = field(default_factory=list)
    runtime_s: float = 0.0
    exit_code: int = 0
    crashed: bool = False
    crash_reason: str = ""


def _norm(s: str) -> str:
    return (s or "").lower()


def matches_expected(finding: Finding, expected: str) -> bool:
    """Does this finding correspond to the `expected_finding` label from labels.csv?

    The label is either:
    - a rule id that should match finding.rule directly, or
    - a short substring/keyword that should appear in the finding message.

    We accept a hit on rule OR message. Case-insensitive substring on both.
    Empty/None expected → always false (no ground truth).
    """
    if not expected:
        return False
    exp = _norm(expected)
    if exp in _norm(finding.rule):
        return True
    if exp in _norm(finding.message):
        return True
    return False


_KEYWORD_FALLBACKS = {
    # keywords drawn from the source test names in labels.csv → message patterns
    # both validate-actions and actionlint tend to surface.
    "required_input": ["required", "missing input", "not provided"],
    "unknown_input": ["unknown input", "unexpected input", "no such input", "bogus_unknown_input"],
    "non_existent_input": ["unknown input", "unexpected input"],
    "invalid_shell": ["shell", "invalid", "fishfish"],
    "shell": ["shell", "invalid", "fishfish"],
    "invalid_permission": ["permission", "invalid"],
    "cycle": ["cycle", "cyclic", "depend", "circular"],
    "duplicate": ["duplicate"],
    "undefined_context": ["context", "undefined", "not defined", "unknown"],
    "outdated_action": ["outdated", "deprecated"],
    "unknown_action": ["not found", "does not exist", "unknown"],
    "missing_required": ["required", "missing"],
    "invalid_event": ["event", "invalid"],
    "invalid_workflow": ["invalid", "workflow"],
    "invalid_job": ["job", "invalid"],
    "invalid_runs_on": ["runs-on", "invalid"],
    "invalid_needs": ["needs", "invalid", "undefined", "does not exist", "non-existent", "nonexistent"],
    "undefined_job": ["does not exist", "non-existent", "nonexistent", "not defined", "undefined", "unknown job"],
    "parser": ["parse", "yaml", "syntax", "error parsing", "scan"],
    "syntax": ["parse", "yaml", "syntax", "error parsing", "scan", "mapping", "flow"],
}


def matches_by_keyword_fallback(finding: Finding, source_test: str) -> bool:
    """When the expected_finding label is just the source test name (e.g. `test_invalid_shell`),
    try mapping by keyword — catches actionlint findings whose rule ids differ from
    validate-actions' but whose messages discuss the same concept.
    """
    lower = source_test.lower()
    for key, phrases in _KEYWORD_FALLBACKS.items():
        if key in lower:
            for phrase in phrases:
                if phrase in _norm(finding.message):
                    return True
                if phrase in _norm(finding.rule):
                    return True
    # weak fallback: any word from the test name (len>=5) appearing in the message
    for word in re.findall(r"[a-z]{5,}", lower):
        if word in {"input", "output"}:
            continue  # too generic
        if word in _norm(finding.message):
            return True
    return False


def case_detected(
    findings: list[Finding],
    expected_finding: str,
    source_test: str,
) -> bool:
    """Did the tool detect the expected error pattern for this synthetic case?

    Strategy:
    1. If any finding matches `expected_finding` directly (rule/message substring) → hit.
    2. Else, if any finding matches via keyword fallback derived from source_test → hit.
    3. Else if the tool emitted ANY finding, we still count it as a detection only when
       the expected_finding field was empty/unusable. Otherwise miss.
    """
    if not findings:
        return False
    for f in findings:
        if matches_expected(f, expected_finding):
            return True
    for f in findings:
        if matches_by_keyword_fallback(f, source_test):
            return True
    # No structured match. Be strict: emitting an unrelated finding is not a true positive.
    return False
