"""Tests for survey MCP profile and path resolution."""
from academic_mcp_server.survey.mcp import SURVEY_TOOL_NAMES, mcp
from academic_mcp_server.survey.paths import REPO_DIRNAME, resolve_mcp_survey_src


def test_survey_mcp_name() -> None:
    assert mcp.name == "paperSearch"


def test_survey_mcp_registers_expected_tools() -> None:
    names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert set(SURVEY_TOOL_NAMES) <= names
    assert "crossref_journal_works" not in names
    assert "semantic_scholar_author_search" not in names


def test_mcp_survey_src_points_at_repo() -> None:
    src = resolve_mcp_survey_src()
    assert src.name == "src"
    assert src.parent.name in {REPO_DIRNAME, "academic-mcp-server-copilot"}
