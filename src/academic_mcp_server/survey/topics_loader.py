"""Load survey topic taxonomies from survey_config.json topics_module."""
from __future__ import annotations

import importlib
import importlib.util
import re
from typing import Any, Callable

# Legacy default — only used when topics_module is explicitly omitted (deprecated).
LEGACY_DEFAULT_TOPICS_MODULE = "academic_mcp_server.survey.topics_ipt"

# Section 4 headings produced by IPT / in-flight-IPT topic modules (wrong domain for OMA surveys).
_IPT_SECTION4_MARKERS = (
    "ホバリングIPT",
    "RFハーベスティング",
    "コイル・磁気結合",
    "磁気共鳴・近接界理論",
    "RF/SWIPT",
    "補償・パワーエレクトロニクス",
)

_SECTION4_RE = re.compile(r"^## Section 4\b", re.MULTILINE)
_SECTION5_RE = re.compile(r"^## Section 5\b", re.MULTILINE)


class TopicsConfigError(ValueError):
    """survey_config.json is missing or has an invalid topics_module."""


def topics_module_from_cfg(cfg: dict[str, Any], *, required: bool = True) -> str:
    mod = str(cfg.get("topics_module") or "").strip()
    if mod:
        return mod
    if required:
        raise TopicsConfigError(
            "survey_config.json must set topics_module "
            "(e.g. academic_mcp_server.survey.topics_operational_modal_uav). "
            "Pass --topics-module to bootstrap_survey.py when creating a new survey."
        )
    return LEGACY_DEFAULT_TOPICS_MODULE


def import_topics_module(mod_name: str):
    try:
        return importlib.import_module(mod_name)
    except ModuleNotFoundError as exc:
        raise TopicsConfigError(f"topics_module not importable: {mod_name}") from exc


def load_topics_symbols(
    cfg: dict[str, Any],
    *,
    required: bool = True,
) -> tuple[list, dict, dict, dict, Callable]:
    mod_name = topics_module_from_cfg(cfg, required=required)
    mod = import_topics_module(mod_name)
    return (
        getattr(mod, "RESEARCH_GAPS", []),
        getattr(mod, "SEED_SUMMARIES", {}),
        getattr(mod, "TOPICS", {}),
        getattr(mod, "TOPIC_SUMMARIES", {}),
        getattr(mod, "assign_subtopics"),
    )


def list_topics_modules() -> list[str]:
    """Discover academic_mcp_server.survey.topics_* modules."""
    import academic_mcp_server.survey as survey_pkg

    names: list[str] = []
    prefix = getattr(survey_pkg, "__name__", "academic_mcp_server.survey")
    for modinfo in importlib.util.iter_modules(survey_pkg.__path__, prefix + "."):
        base = modinfo.name.rsplit(".", 1)[-1]
        if base.startswith("topics_"):
            names.append(modinfo.name)
    return sorted(names)


def extract_section4_markdown(article_text: str) -> str:
    m4 = _SECTION4_RE.search(article_text)
    if not m4:
        return ""
    m5 = _SECTION5_RE.search(article_text, m4.end())
    end = m5.start() if m5 else len(article_text)
    return article_text[m4.start() : end]


def validate_topic_taxonomy_alignment(cfg: dict[str, Any], article_text: str) -> list[str]:
    """
    Return validation errors when Section 4 headings disagree with topics_module domain.
    """
    errors: list[str] = []
    mod = str(cfg.get("topics_module") or "").strip()
    if not mod:
        errors.append(
            "survey_config.json missing topics_module — Section 4 may use legacy IPT taxonomy"
        )
        return errors

    s4 = extract_section4_markdown(article_text)
    if not s4:
        return errors

    mod_lower = mod.lower()
    # WPT-family taxonomies (IPT, in-flight IPT, robots WPT, …) share near-field
    # heading markers; only flag when a non-WPT module emits those headings.
    is_wpt_family_module = (
        "topics_ipt" in mod_lower
        or "inflight_ipt" in mod_lower
        or "topics_wpt" in mod_lower
        or "_wpt_" in mod_lower
        or "dwpt" in mod_lower
    )
    has_ipt_headings = any(marker in s4 for marker in _IPT_SECTION4_MARKERS)

    if not is_wpt_family_module and has_ipt_headings:
        errors.append(
            f"Section 4 contains IPT/WPT topic headings but topics_module is {mod!r}. "
            "Re-run analyze + generate after setting the correct topics_module."
        )

    if "operational_modal" in mod_lower and "OMA理論" not in s4 and has_ipt_headings:
        errors.append(
            "topics_module is operational_modal_uav but Section 4 lacks OMA topic headings"
        )

    return errors
