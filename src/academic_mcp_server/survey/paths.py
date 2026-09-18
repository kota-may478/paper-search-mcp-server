"""Resolve paper-search-mcp-server and vault_mirror paths (Ubuntu/Insync first)."""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIRNAME = "paper-search-mcp-server"
LEGACY_REPO_DIRNAME = "academic-mcp-server-copilot"


def resolve_program_dir() -> Path:
    if os.environ.get("PROGRAM_DIR"):
        return Path(os.environ["PROGRAM_DIR"])
    insync = Path.home() / "Insync" / "01_Private" / "Program"
    if insync.is_dir():
        return insync
    return Path.home() / "01_Private" / "Program"


def resolve_obsidian_dir() -> Path:
    if os.environ.get("OBSIDIAN_DIR"):
        return Path(os.environ["OBSIDIAN_DIR"])
    insync = Path.home() / "Insync" / "Obsidian"
    if insync.is_dir():
        return insync
    return Path.home() / "Obsidian"


def resolve_repo_dir() -> Path:
    program = resolve_program_dir()
    for name in (REPO_DIRNAME, LEGACY_REPO_DIRNAME):
        candidate = program / name
        if candidate.is_dir():
            return candidate
    return program / REPO_DIRNAME


def resolve_mcp_survey_src() -> Path:
    return resolve_repo_dir() / "src"


def resolve_mirror_root() -> Path:
    return resolve_program_dir() / "python_ForObsidian" / "vault_mirror"


def resolve_shared_python_dir() -> Path:
    if os.environ.get("SURVEY_SHARED_PYTHON_DIR"):
        return Path(os.environ["SURVEY_SHARED_PYTHON_DIR"])
    return resolve_mirror_root() / ".python" / "survey"
