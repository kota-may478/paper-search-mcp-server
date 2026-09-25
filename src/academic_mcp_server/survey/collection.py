from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from academic_mcp_server.survey.api_gateway import fetch_ss_abstract, polite_sleep, survey_api_lock
from academic_mcp_server.survey.enrich import enrich_crossref
from academic_mcp_server.survey.master_list import load_survey_config, master_list_path, save_master_list
from academic_mcp_server.survey.paths import final_ledger_path, resolve_obsidian_dir

_OBS = resolve_obsidian_dir()
STEP2_STATS = "_step2_stats.json"
WORKFLOW_PHASE_A_ANALYSIS = _OBS / "01_Private/Tool/prompt/survey_workflow_step3plus.prompt.md"
WORKFLOW_PHASE_B = _OBS / "01_Private/Tool/prompt/survey_workflow_phase_b.prompt.md"
HANDOFF_PHASE_A_CONTINUE = "handoff_step3.prompt.md"
HANDOFF_PHASE_B = "handoff_phase_b.prompt.md"
JSON_FENCE = "```json"
JSON_FENCE_END = "```"


def _ss_identifier_from_entry(entry: dict) -> str | None:
    for key in ("ss_paper_id", "source_id", "paper_id", "semantic_scholar_id"):
        val = str(entry.get(key) or "").strip()
        if val:
            if val.startswith(("DOI:", "arXiv:", "CorpusId:", "corpusId:")):
                return val
            return val
    ck = str(entry.get("candidate_key") or "").strip()
    if ck.startswith("SS:"):
        return ck[3:]
    if ck.startswith("DOI:"):
        return "DOI:" + ck[4:]
    if ck.startswith("arXiv:"):
        return "arXiv:" + ck[6:]
    return None


def enrich_abstracts_semantic_scholar(ml: list[dict]) -> dict[str, int]:
    filled = 0
    with survey_api_lock():
        for entry in ml:
            if (entry.get("abstract") or "").strip():
                continue
            ident = _ss_identifier_from_entry(entry)
            if not ident:
                continue
            abstract = fetch_ss_abstract(ident)
            if abstract:
                entry["abstract"] = abstract
                entry["abstract_source"] = "semantic_scholar"
                filled += 1
            polite_sleep()
    return {"abstracts_filled": filled}


def _in_step(entry: dict, step: str) -> bool:
    return step in (entry.get('discovered_in') or [])


def _not_in_steps(entry: dict, steps: list[str]) -> bool:
    return not any(s in (entry.get('discovered_in') or []) for s in steps)


def _fmt_authors(authors: list, max_n: int = 5) -> str:
    if not authors:
        return '-'
    if len(authors) >= max_n + 1:
        return ", ".join(authors[:max_n]) + " et al."
    return "; ".join(authors)


def _entry_md(entry: dict) -> str:
    lines: list[str] = []
    title = entry.get("title") or "(no title)"
    ck = entry.get("candidate_key") or ""
    doi = ck[4:] if ck.startswith("DOI:") else ""
    arxiv = ck[6:] if ck.startswith("arXiv:") else ""
    url = f"https://doi.org/{doi}" if doi else (f"https://arxiv.org/abs/{arxiv}" if arxiv else "")
    title_link = f"[{title}]({url})" if url else title
    lines.append(f"**{title_link}**")
    lines.append(f"- Authors: {_fmt_authors(entry.get('authors') or [])}")
    lines.append(f"- Year: {entry.get('year') or '-'}")
    lines.append(f"- Venue: {entry.get('venue') or '-'}")
    abstract = (entry.get("abstract") or "").strip()
    if abstract:
        lines.append(f"- Abstract: {abstract}")
    lines.append(f"- candidate_key: {ck!r}")
    oa = (entry.get("openalex_id") or "").strip()
    if oa:
        lines.append(f"- openalex_id: {oa!r}")
    cr = (entry.get("crossref_metadata") or "").strip()
    if cr:
        lines.append(f"- crossref_metadata: {cr}")
    disc = ", ".join(entry.get("discovered_in") or []) or "-"
    lines.append(f"- discovered_in: {disc}")
    sq = entry.get("seed_or_query") or []
    sqs = ", ".join(str(s) for s in sq) or "-"
    lines.append(f"- seed_or_query: {sqs}")
    lines.append(f"- content_basis: {entry.get('content_basis') or '-'}")
    lines.append(f"- relevance: {entry.get('relevance') or '-'}")
    lines.append(f"- relation_strength: {entry.get('relation_strength') or '-'}")
    return "\n".join(lines)


def _load_step2_stats(mirror: Path):
    path = mirror / STEP2_STATS
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def render_ledger_collection(ml: list[dict], cfg: dict, step2_stats, enrich_result: dict) -> str:
    name = cfg.get("survey_name", "survey")
    tags = cfg.get("ledger_tags") or cfg.get("tags") or []
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    today = date.today().isoformat()
    seeds = [e for e in ml if _in_step(e, "step1_seed")]
    step2_only = [e for e in ml if _in_step(e, "step2_snowball") and _not_in_steps(e, ["step1_seed"])]
    lines = [
        "---",
        f"number: {cfg.get('ledger_number', 0)}",
        f"title: {name}_Ledger_Collection",
        "tags:",
        tag_lines,
        f"created: {today}",
        "status: WIP",
        "phase: collection",
        "---",
        "",
        f"# {name} — Collection Ledger (Phase A checkpoint)",
        "",
        f"Phase A continues through Step 9; this file is a snapshot after Steps 1–2 (pre-screening). Final ledger: {name}_Ledger.md under the survey ledger store (see survey workflow; not in Obsidian vault).",
        "",
        f"- Total entries: **{len(ml)}**",
        f"- Step 1 seeds: **{len(seeds)}**",
        f"- Step 2 snowball (unique): **{len(step2_only)}**",
        f"- enrich (scope=collection): {json.dumps(enrich_result, ensure_ascii=False)}",
        "",
    ]
    if step2_stats is not None:
        lines += ["## Step 2 snowball stats (_step2_stats.json)", "", JSON_FENCE, json.dumps(step2_stats, ensure_ascii=False, indent=2), JSON_FENCE_END, ""]
    lines += ["---", "", "## 1. Seeds (Step 1)", ""]
    for e in seeds:
        lines.append(_entry_md(e))
        lines.append("")
    lines += ["---", "", "## 2. Step 2 snowball (unique)", ""]
    for e in step2_only:
        lines.append(_entry_md(e))
        lines.append("")
    return "\n".join(lines)


def _strong_criteria_lines(cfg: dict, target: str) -> list[str]:
    return [
        line
        for line in (
            __import__(
                "academic_mcp_server.survey.strong_relation_criteria",
                fromlist=["format_markdown_block"],
            ).format_markdown_block(cfg.get("strong_relation_criteria"), target).splitlines()
        )
    ]


def render_handoff(cfg: dict, mirror: Path, vault: Path, ledger_path: Path) -> str:
    """Phase A continuation handoff for Cursor (Steps 3–8 + Step 9 skeleton)."""
    name = cfg.get("survey_name", "survey")
    target = cfg.get("target_word", "")
    wf = WORKFLOW_PHASE_A_ANALYSIS
    article = vault / f"{name}.md"
    final_ledger = final_ledger_path(cfg, name)
    step6_limit = int(cfg.get("step6_seed_limit") or 100)
    finalize_script = _OBS / "01_Private/Tool/scripts/survey_analysis_finalize.py"
    return "\n".join([
        "# Survey handoff — Phase A (continue from Step 3)",
        "",
        "Continue **Phase A** after Steps 1–2 + collection finalize. **Executor: Cursor.**",
        "Do not redo Steps 1–2 unless the user explicitly resets the mirror.",
        "",
        "## Paths",
        f"- Mirror directory: {mirror}",
        f"- Master list: {mirror / '_working_master_list.json'}",
        f"- survey_config.json: {mirror / 'survey_config.json'}",
        f"- Collection ledger (checkpoint): {ledger_path}",
        f"- Workflow prompt (Steps 3–8 + Step 9 skeleton): {wf}",
        f"- Target article (skeleton): {article}",
        f"- Final ledger (end of Phase A): {final_ledger}",
        f"- Phase B handoff (after Phase A completes): {vault / HANDOFF_PHASE_B}",
        "",
        "## Survey parameters",
        f"- survey_name: {name}",
        f"- target_word: {target}",
        f"- article_number: {cfg.get('article_number')}",
        f"- ledger_number: {cfg.get('ledger_number')}",
        f"- step6_seed_limit: {step6_limit}",
        "",
        "## Strong relation minimum conditions",
        *_strong_criteria_lines(cfg, target),
        "",
        "## Instructions (Cursor Phase A — do not write Japanese prose)",
        "1. Read the workflow prompt above and execute **Steps 3–8**, then **Step 9 skeleton only**.",
        "2. Use `_working_master_list.json` as the authoritative deduplication source.",
        "3. Step 3 is title-only for all; **no** abstract API in Step 3.",
        "4. After Step 4: `survey-cli enrich-content <mirror>` (default scope **pre_screening**) for **all** entries, then `step45_reextract_keywords.py` (Step 4.5).",
        "5. Step 5 / 7 screening must use title **and** abstract (and P/A/O/M keywords).",
        "6. After Step 5: `survey-cli enrich-content <mirror> --scope strong` for any strong papers still on title_only; re-extract strong keywords (Step 5.5).",
        f"7. Step 6.0: `step6_select_seeds.py` → review `_step6_selected_seeds.json` (max **{step6_limit}** strong non-seeds).",
        "8. Step 6: `step6_snowball.py` on selected seeds only; Step 7 classifies new Step 6 hits.",
        "9. Step 9: `analyze` → `generate` → final `{name}_Ledger.md` → `validate` (`ok: true`).",
        "10. **Leave** generator TODO / stubs in Sections 1, 2, 6–8.",
        "11. **Do not** write Japanese narrative prose — that is **Phase B (Claude Code)**.",
        "12. When validate passes, run:",
        f"    python3 {finalize_script} {mirror}",
        f"11. Hand off to Claude Code with `{HANDOFF_PHASE_B}` + `survey_workflow_phase_b.prompt.md`.",
        "",
    ])


def render_handoff_phase_b(cfg: dict, mirror: Path, vault: Path) -> str:
    """Phase B handoff for Claude Code (Japanese article prose only)."""
    name = cfg.get("survey_name", "survey")
    target = cfg.get("target_word", "")
    wf = WORKFLOW_PHASE_B
    article = vault / f"{name}.md"
    final_ledger = final_ledger_path(cfg, name)
    return "\n".join([
        "# Survey handoff — Phase B (Claude Code: Japanese article)",
        "",
        "**Phase A (Cursor)** completed: master list screened, skeleton article and final ledger written, validate passed.",
        "**Executor: Claude Code.** Write **Japanese prose only** — do not redo literature collection or screening.",
        "",
        "## Paths",
        f"- Workflow prompt: {wf}",
        f"- Target article: {article}",
        f"- Final ledger: {final_ledger}",
        f"- Mirror (read-only unless fixing a factual error): {mirror / '_working_master_list.json'}",
        "",
        "## Survey parameters",
        f"- survey_name: {name}",
        f"- target_word: {target}",
        f"- article_number: {cfg.get('article_number')}",
        "",
        "## Strong relation minimum conditions",
        *_strong_criteria_lines(cfg, target),
        "",
        "## Instructions",
        "1. Read `survey_workflow_phase_b.prompt.md` and follow Phase B rules.",
        "2. Replace all TODO / stub text in Sections **1**, **2**, **6**, **7**, **8** with detailed Japanese.",
        "3. Expand Section 5 matrix commentary to 4–6 sentences per matrix if the skeleton is shorter.",
        "4. Improve References one-line Japanese summaries where content is available.",
        "5. Do **not** alter Section 3–5 tables except factual corrections.",
        "6. **Mandatory last step** — Phase B validation (`ok: true` required):",
        f"   python3 {_OBS / '01_Private/Tool/scripts/survey_validate_phase_b.py'} {mirror}",
        "   Checks: pipe-table column alignment; canonical [Rxxx](#^refRxxx); ^ref block IDs; strong-only References.",
        "7. Fix all validation **errors** before reporting completion.",
        "",
    ])


def analysis_finalize(mirror_dir: Path, *, overwrite: bool = True) -> dict:
    """After Cursor Phase A (validate ok), write handoff_phase_b.prompt.md for Claude Code."""
    mirror = mirror_dir.expanduser().resolve()
    cfg = load_survey_config(mirror)
    vault = Path(cfg.get("vault_survey_dir", mirror))
    handoff_path = vault / HANDOFF_PHASE_B
    vault.mkdir(parents=True, exist_ok=True)
    if overwrite or not handoff_path.is_file():
        handoff_path.write_text(render_handoff_phase_b(cfg, mirror, vault), encoding="utf-8")
    return {
        "mirror_dir": str(mirror),
        "handoff_phase_b_path": str(handoff_path),
        "workflow_phase_b_prompt": str(WORKFLOW_PHASE_B),
        "survey_name": cfg.get("survey_name"),
    }


def collection_finalize(mirror_dir: Path) -> dict:
    mirror = mirror_dir.expanduser().resolve()
    cfg = load_survey_config(mirror)
    enrich_result = enrich_crossref(mirror, scope="collection")
    ml_path = master_list_path(mirror)
    with open(ml_path, encoding="utf-8") as f:
        ml: list[dict] = json.load(f)
    step2_stats = _load_step2_stats(mirror)
    phase_a_meta = {
        **enrich_result,
        "abstracts_filled": 0,
        "abstract_policy": "deferred_to_step_5_5_strong_only",
    }
    name = cfg.get("survey_name", "survey")
    vault = Path(cfg.get("vault_survey_dir", mirror))
    ledger_path = vault / f"{name}_Ledger_Collection.md"
    handoff_path = vault / HANDOFF_PHASE_A_CONTINUE
    vault.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(render_ledger_collection(ml, cfg, step2_stats, phase_a_meta), encoding="utf-8")
    if not handoff_path.is_file():
        handoff_path.write_text(render_handoff(cfg, mirror, vault, ledger_path), encoding="utf-8")
    return {
        "mirror_dir": str(mirror),
        "ledger_collection_path": str(ledger_path),
        "handoff_path": str(handoff_path),
        "entries": len(ml),
        "enrich": phase_a_meta,
        "step2_stats_present": step2_stats is not None,
    }
