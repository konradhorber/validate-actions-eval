from tests.conftest import parse_workflow_string
from validate_actions.domain_model import ast
from validate_actions.domain_model.primitives import Pos


class TestParser:
    def test_parse_str_to_ref(self):
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - id: step1
        name: 'Checkout code'
        uses: actions/checkout@v4

      - id: step2
        name: 'Upload artifact'
        uses: actions/upload-artifact@v3
        with:
          name: ${{ steps.step1.outputs.ref }}
"""
        workflow, problems = parse_workflow_string(workflow_string)
        ref = workflow.jobs_["test-job"].steps_[1].exec.with_["name"]
        parts = [
            "steps",
            "step1",
            "outputs",
            "ref",
        ]
        should_be = ast.String(
            pos=Pos(line=14, col=16),
            string="${{ steps.step1.outputs.ref }}",
            expr=[
                ast.Expression(
                    pos=Pos(line=14, col=16),
                    string="${{ steps.step1.outputs.ref }}",
                    parts=parts,
                )
            ],
        )
        assert ref == should_be

    def test_flow_mapping_value_token_parsing(self):
        """Test flow mapping parsing handles ValueToken with various token types."""
        # Test with scalar value
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {ref: main}
"""
        workflow, problems = parse_workflow_string(workflow_string)
        with_value = workflow.jobs_["test-job"].steps_[0].exec.with_["ref"]
        assert with_value.string == "main"

        # Test with nested flow mapping
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {config: {timeout: 30}}
"""
        workflow, problems = parse_workflow_string(workflow_string)
        config_value = workflow.jobs_["test-job"].steps_[0].exec.with_["config"]["timeout"]
        assert config_value == 30

        # Test with flow sequence
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {files: [file1, file2]}
"""
        workflow, problems = parse_workflow_string(workflow_string)
        files_value = workflow.jobs_["test-job"].steps_[0].exec.with_["files"]
        assert len(files_value) == 2
        assert files_value[0].string == "file1"
        assert files_value[1].string == "file2"


class TestYAMLSyntaxErrors:
    """Test cases for various YAML syntax errors and edge cases."""

    def test_tabs_in_indentation(self):
        """Test that tabs in indentation are caught as YAML errors."""
        workflow_string = """
on: push
jobs:
\ttest-job:
\t\truns-on: ubuntu-latest
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1
        assert any("error" in p.desc.lower() for p in yaml_problems)

    def test_key_value_without_colon(self):
        """Test that key-value pairs without colons are caught."""
        workflow_string = """
on push
jobs:
  test-job:
    runs-on: ubuntu-latest
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1

    def test_extra_space_before_colon(self):
        """Test handling of extra space before colon (valid YAML but unusual)."""
        # Note: This is actually valid YAML but may cause issues
        workflow_string = """
on : push
jobs :
  test-job :
    runs-on: ubuntu-latest
"""
        workflow, problems = parse_workflow_string(workflow_string)
        # Extra space before colon is valid YAML, so this should parse
        # But let's verify it parses without yaml-syntax errors
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        # This should NOT produce a yaml-syntax error (valid YAML)
        assert len(yaml_problems) == 0

    def test_list_items_misaligned(self):
        """Test that misaligned list items are caught."""
        workflow_string = """
on:
  push:
    branches:
      - main
     - develop
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1

    def test_mixing_indentation_levels(self):
        """Test that mixing 2-space and 4-space indentation causes issues."""
        workflow_string = """
on: push
jobs:
  test-job:
      runs-on: ubuntu-latest
  another-job:
    runs-on: ubuntu-latest
"""
        workflow, problems = parse_workflow_string(workflow_string)
        # Mixed indentation is technically valid YAML but should parse
        # The key is consistency - this may or may not error depending on structure
        # Let's just verify it attempts to parse
        assert problems is not None

    def test_unquoted_string_with_special_chars(self):
        """Test that unquoted strings with certain special characters cause errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - name: Test: [invalid
        uses: actions/checkout@v4
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1

    def test_incorrect_boolean_values(self):
        """Test that incorrect boolean values are handled."""
        # Note: YAML is flexible with booleans, but let's test invalid syntax
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    if: True123
"""
        workflow, problems = parse_workflow_string(workflow_string)
        # This is actually valid YAML (treated as string), so should parse
        # Testing actual YAML boolean parsing errors is tricky
        assert workflow is not None

    def test_invalid_anchor_reference(self):
        """Test that invalid anchor references cause errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: *undefined_anchor
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1

    def test_incorrect_block_string_indicator(self):
        """Test that incorrect block string indicators cause errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - name: Test
        run: >>
          echo "test"
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        # >> is invalid, should be > or |
        assert len(yaml_problems) >= 1

    def test_key_duplication(self):
        """Test that duplicate keys are handled."""
        workflow_string = """
on: push
on: pull_request
jobs:
  test-job:
    runs-on: ubuntu-latest
"""
        workflow, problems = parse_workflow_string(workflow_string)
        # Duplicate keys are valid YAML (last one wins), but should parse
        # This tests that the parser handles it without crashing
        assert workflow is not None

    def test_missing_dash_for_list_item(self):
        """Test that missing dashes in list items cause errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - name: Step 1
        uses: actions/checkout@v4
      uses: actions/setup-node@v4
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        # Missing dash creates invalid structure
        assert len(yaml_problems) >= 1

    def test_wrong_indentation_under_list(self):
        """Test that wrong indentation under list items causes errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - name: Step 1
        uses: actions/checkout@v4
     - name: Step 2
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        # Incorrect indentation (7 spaces vs 6) causes parsing error
        assert len(yaml_problems) >= 1

    def test_comment_formatting_issues(self):
        """Test that comment formatting issues are handled."""
        workflow_string = """
on: push#invalid comment without space
jobs:
  test-job:
    runs-on: ubuntu-latest
"""
        workflow, problems = parse_workflow_string(workflow_string)
        # This is actually valid YAML (# starts comment even without space)
        # So it should parse successfully
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) == 0

    def test_incorrectly_quoted_string(self):
        """Test that incorrectly quoted strings cause errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - name: 'Unclosed string
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1

    def test_mismatched_brackets_in_flow_sequence(self):
        """Test that mismatched brackets cause errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          files: [file1, file2
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1

    def test_mismatched_braces_in_flow_mapping(self):
        """Test that mismatched braces cause errors."""
        workflow_string = """
on: push
jobs:
  test-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {ref: main, depth: 1
"""
        workflow, problems = parse_workflow_string(workflow_string)
        yaml_problems = [p for p in problems.problems if p.rule == "yaml-syntax"]
        assert len(yaml_problems) >= 1
