from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from academic_mcp_server.survey.api_gateway import (
    assert_exclusive_survey_api_jobs,
    survey_api_lock,
    survey_auth_status,
)
from academic_mcp_server.survey.bootstrap import add_bootstrap_arguments, run_bootstrap
from academic_mcp_server.survey.analysis import analyze_corpus
from academic_mcp_server.survey.content_acquisition import enrich_content
from academic_mcp_server.survey.enrich import enrich_crossref
from academic_mcp_server.survey.generate import generate_docs
from academic_mcp_server.survey.stats import write_step3_stats
from academic_mcp_server.survey.phase_b_validate import validate_phase_b_article
from academic_mcp_server.survey.validate import validate_survey

SURVEY_CONFIG_SCHEMA = """
survey_config.json example:
{
  "survey_name": "inFlight_InductivePowerTransfer",
  "target_word": "in-flight IPT",
  "article_number": 301,
  "ledger_number": 302,
  "topics_module": "academic_mcp_server.survey.topics_inflight_ipt (REQUIRED — set at bootstrap; wrong/missing module yields IPT headings or validate failure)",
  "vault_root": "/home/user/Obsidian",
  "vault_survey_dir": "/home/user/Obsidian/02_HFLab/00_Idea/Survey/MySurvey",
  "python_survey_dir": "/home/user/01_Private/Program/python_ForObsidian/vault_mirror/...",
  "tags": ["survey", "HFLab"],
  "ledger_tags": ["survey", "HFLab", "ledger"]
,
  "strong_relation_criteria": {"mode": "default", "required_all": [], "required_any_groups": [], "notes": ""},
  "step6_seed_limit": 100
}
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Literature survey mirror workflow CLI",
        epilog=SURVEY_CONFIG_SCHEMA,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_enrich = sub.add_parser("enrich", help="Crossref/OpenAlex enrich for DOI entries")
    p_enrich.add_argument("mirror_dir", type=Path)
    p_enrich.add_argument("--scope", choices=["strong", "all", "collection"], default="strong")

    p_an = sub.add_parser("analyze", help="Quantitative corpus analysis")
    p_an.add_argument("mirror_dir", type=Path)

    p_gen = sub.add_parser("generate", help="Generate Obsidian article skeleton + ledger")
    p_gen.add_argument("mirror_dir", type=Path)

    p_content = sub.add_parser(
        "enrich-content",
        help="Fetch abstracts: pre_screening=all entries before Step 5; strong=kept+strong (Step 5.5/8)",
    )
    p_content.add_argument("mirror_dir", type=Path)
    p_content.add_argument(
        "--scope",
        choices=["pre_screening", "strong"],
        default="pre_screening",
        help="pre_screening (Step 4.5, default) or strong (Step 5.5/8)",
    )

    p_stats = sub.add_parser("step3-stats", help="Write _step3_stats.json after Step 3")
    p_stats.add_argument("mirror_dir", type=Path)

    p_val = sub.add_parser("validate", help="Validate strong-only References invariant")
    p_val.add_argument("mirror_dir", type=Path)
    p_val.add_argument("--article", type=Path, default=None)

    p_val_b = sub.add_parser(
        "validate-phase-b",
        help="Phase B gate: markdown tables, ref links, strong-only References",
    )
    p_val_b.add_argument("mirror_dir", type=Path)
    p_val_b.add_argument("--article", type=Path, default=None)
    p_val_b.add_argument(
        "--no-corpus",
        action="store_true",
        help="Skip master-list / strong-only References checks",
    )

    sub.add_parser("auth-status", help="Show SS/OpenAlex credential and cache lock configuration")

    p_boot = sub.add_parser("bootstrap", help="Create survey mirror dir, survey_config.json, and step scripts")
    add_bootstrap_arguments(p_boot)

    args = parser.parse_args()

    if args.command == "auth-status":
        print(json.dumps(survey_auth_status(), ensure_ascii=False, indent=2))
        return
    if args.command == "bootstrap":
        run_bootstrap(args)
        return

    mirror = args.mirror_dir.expanduser().resolve()
    if args.command == "enrich":
        assert_exclusive_survey_api_jobs("survey-cli enrich")
        with survey_api_lock():
            result = enrich_crossref(mirror, scope=args.scope)
        print(json.dumps(result, ensure_ascii=False))
    elif args.command == "analyze":
        result = analyze_corpus(mirror)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "generate":
        result = generate_docs(mirror)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "enrich-content":
        assert_exclusive_survey_api_jobs("survey-cli enrich-content")
        with survey_api_lock():
            result = enrich_content(mirror, scope=args.scope)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "step3-stats":
        result = write_step3_stats(mirror)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "validate":
        result = validate_survey(mirror, article_path=args.article)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            sys.exit(1)
    elif args.command == "validate-phase-b":
        art = args.article
        if art is None:
            from academic_mcp_server.survey.master_list import load_survey_config

            cfg = load_survey_config(mirror)
            name = cfg.get("survey_name", "survey")
            vault = Path(cfg.get("vault_survey_dir", mirror))
            art = vault / f"{name}.md"
        result = validate_phase_b_article(
            art,
            mirror_dir=mirror,
            check_corpus=not args.no_corpus,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            sys.exit(1)


if __name__ == "__main__":
    main()
