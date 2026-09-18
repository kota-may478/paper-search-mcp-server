"""Cursor/Ubuntu survey MCP profile. Display name: paperSearch."""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools import Tool

from academic_mcp_server.server import mcp as _full_mcp
from academic_mcp_server.server import server_lifespan

SURVEY_TOOL_NAMES: tuple[str, ...] = (
    "search_papers",
    "semantic_scholar_search",
    "semantic_scholar_search_paginated",
    "semantic_scholar_paper",
    "semantic_scholar_paper_batch",
    "semantic_scholar_citations",
    "semantic_scholar_references",
    "survey_query_contexts",
    "survey_paper_context",
    "survey_enrich_crossref",
    "survey_enrich_content",
    "survey_write_step3_stats",
    "survey_analyze_corpus",
    "survey_generate_docs",
    "survey_validate_corpus",
    "survey_validate_phase_b",
    "crossref_work_by_doi",
    "arxiv_paper",
    "arxiv_full_text",
)

INSTRUCTIONS = (
    "Literature survey MCP for Cursor on Ubuntu (paperSearch). "
    "Use survey_query_contexts for seed discovery, survey_paper_context for snowballing, "
    "semantic_scholar_search_paginated for keyword pagination, and survey_* tools for "
    "enrich/analyze/generate/validate. Prefer Semantic Scholar then OpenAlex then Crossref. "
    "Do not run parallel Semantic Scholar or OpenAlex jobs (shared api.lock)."
)


def _survey_tools() -> list[Tool]:
    tools: list[Tool] = []
    missing: list[str] = []
    for name in SURVEY_TOOL_NAMES:
        tool = _full_mcp._tool_manager.get_tool(name)
        if tool is None:
            missing.append(name)
            continue
        tools.append(tool)
    if missing:
        raise RuntimeError(f"Survey MCP missing tools on full server: {missing}")
    return tools


mcp = FastMCP(
    name="paperSearch",
    instructions=INSTRUCTIONS,
    tools=_survey_tools(),
    lifespan=server_lifespan,
    log_level="INFO",
)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
