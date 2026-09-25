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


LEDGER_STORE_DIRNAME = "51_Research_LedgerFile"


def resolve_ledger_store_root() -> Path:
    """Directory for final {survey_name}_Ledger.md files (outside Obsidian vault)."""
    if os.environ.get("SURVEY_LEDGER_STORE_ROOT"):
        root = Path(os.environ["SURVEY_LEDGER_STORE_ROOT"]).expanduser()
    else:
        insync = Path.home() / "Insync"
        root = insync / "02_Work" / "01_Survey" / LEDGER_STORE_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def resolve_article_dir(cfg: dict) -> str:
    """Vault-relative survey directory (e.g. 02_Work/01_Survey/.../MySurvey)."""
    raw = (cfg.get("article_dir") or "").strip().strip("/")
    if raw:
        return raw
    vault_root = Path(cfg.get("vault_root") or resolve_obsidian_dir()).expanduser().resolve()
    vault_survey = Path(cfg.get("vault_survey_dir", "")).expanduser().resolve()
    try:
        return vault_survey.relative_to(vault_root).as_posix()
    except ValueError:
        return vault_survey.name


def final_ledger_path(cfg: dict, survey_name: str | None = None) -> Path:
    """Path for Step 9 final ledger Markdown (not synced into Obsidian vault)."""
    name = survey_name or cfg.get("survey_name") or "survey"
    store_root = Path(cfg.get("ledger_store_dir") or resolve_ledger_store_root()).expanduser()
    article_dir = resolve_article_dir(cfg)
    path = store_root / article_dir / f"{name}_Ledger.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()
