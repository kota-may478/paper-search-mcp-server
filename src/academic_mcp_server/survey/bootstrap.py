"""Bootstrap a survey mirror directory (canonical implementation)."""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
from pathlib import Path
from typing import Any

from academic_mcp_server.survey.paths import (
    final_ledger_path,
    resolve_ledger_store_root,
    resolve_mcp_survey_src,
    resolve_mirror_root,
    resolve_obsidian_dir,
    resolve_shared_python_dir,
)

DEFAULT_STRONG_RELATION_CRITERIA: dict[str, Any] = {
    "mode": "default",
    "required_all": [],
    "required_any_groups": [],
    "notes": "",
}


def normalize_strong_relation_criteria(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return dict(DEFAULT_STRONG_RELATION_CRITERIA)
    mode = (raw.get("mode") or "default").strip()
    required_all = [str(x).strip() for x in (raw.get("required_all") or []) if str(x).strip()]
    groups: list[list[str]] = []
    for group in raw.get("required_any_groups") or []:
        if isinstance(group, str):
            terms = [t.strip() for t in group.split(",") if t.strip()]
        else:
            terms = [str(t).strip() for t in group if str(t).strip()]
        if terms:
            groups.append(terms)
    notes = str(raw.get("notes") or "").strip()
    return {
        "mode": mode if mode in ("default", "custom_minimum") else "default",
        "required_all": required_all,
        "required_any_groups": groups,
        "notes": notes,
    }


def load_strong_relation_criteria_file(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return normalize_strong_relation_criteria(json.load(f))


def copy_if_missing(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    if src.is_file():
        shutil.copy2(src, dst)
        print(f"Copied {src.name} -> {dst}")


def write_hydrate_stub(dst: Path) -> None:
    if dst.exists():
        return
    stub = """#!/usr/bin/env python3
# hydrate template stub — replace with survey-specific hydrate script.
import sys
print("hydrate_and_screen stub: implement or copy from an existing survey.")
sys.exit(0)
"""
    dst.write_text(stub, encoding="utf-8")
    dst.chmod(0o755)
    print(f"Wrote hydrate stub -> {dst}")


def write_run_survey_steps(survey_dir: Path, mcp_survey_src: Path, shared_dir: Path) -> None:
    survey_s = str(survey_dir)
    shared_s = str(shared_dir)
    mcp_s = str(mcp_survey_src)
    run_lines = [
        "#!/usr/bin/env python3",
        "import os",
        "import subprocess",
        "import sys",
        "from pathlib import Path",
        f'SURVEY_DIR = Path(r"{survey_s}")',
        f'SHARED = Path(r"{shared_s}")',
        f'MCP_SRC = Path(r"{mcp_s}")',
        "PY = sys.executable",
        "ENV = os.environ.copy()",
        'ENV["PYTHONPATH"] = str(MCP_SRC)',
        'CLI = [PY, "-m", "academic_mcp_server.survey.cli"]',
        "optional = [",
        '    ("step4_keyword_search", SHARED / "step4_keyword_search.py"),',
        '    ("step4_post_screen", SURVEY_DIR / "step4_post_screen.py"),',
        "]",
        "for label, script in optional:",
        "    if not script.is_file():",
        '        print(f"Skip {label}: missing {script}")',
        "        continue",
        '    print(f"=== {label} ===")',
        "    args = [PY, str(script)]",
        '    if script.name.startswith("step4"):',
        "        args.append(str(SURVEY_DIR))",
        "    rc = subprocess.run(args, env=ENV)",
        "    if rc.returncode != 0:",
        "        sys.exit(rc.returncode)",
        "api_steps = [",
        '    ("enrich_content", CLI + ["enrich-content", str(SURVEY_DIR)]),',
        '    ("enrich_strong", CLI + ["enrich", str(SURVEY_DIR), "--scope", "strong"]),',
        "]",
        "local_steps = [",
        '    ("analyze", CLI + ["analyze", str(SURVEY_DIR)]),',
        '    ("generate", CLI + ["generate", str(SURVEY_DIR)]),',
        '    ("validate", CLI + ["validate", str(SURVEY_DIR)]),',
        "]",
        'print("=== API steps (SS/OpenAlex — one at a time, do not run in parallel) ===")',
        "for label, args in api_steps:",
        '    print(f"=== {label} ===")',
        "    rc = subprocess.run(args, env=ENV)",
        "    if rc.returncode != 0:",
        "        sys.exit(rc.returncode)",
        "for label, args in local_steps:",
        '    print(f"=== {label} ===")',
        "    subprocess.run(args, check=False, env=ENV)",
        'print("Done. Run survey-local gen_article_*.py when it overrides generate with richer sections.")',
    ]
    out = survey_dir / "run_survey_steps.py"
    out.write_text(chr(10).join(run_lines) + chr(10), encoding="utf-8")
    out.chmod(0o755)
    print(f"Wrote {out}")


def add_bootstrap_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--article-dir",
        required=True,
        help="Relative path under vault_mirror, e.g. 02_Work/01_Survey/.../MySurvey",
    )
    parser.add_argument("--survey-name", required=True)
    parser.add_argument("--target-word", required=True)
    parser.add_argument("--article-number", type=int, required=True)
    parser.add_argument("--ledger-number", type=int, required=True)
    parser.add_argument(
        "--strong-relation-criteria-file",
        type=Path,
        default=None,
        help="JSON file: mode, required_all, required_any_groups, notes",
    )
    parser.add_argument(
        "--topics-module",
        required=True,
        help="Python module for Section 4–8 taxonomy, e.g. academic_mcp_server.survey.topics_dwpt_robots",
    )


def run_bootstrap(args: argparse.Namespace) -> Path:
    vault_root = resolve_obsidian_dir()
    mirror_root = resolve_mirror_root()
    shared_dir = resolve_shared_python_dir()
    mcp_survey_src = resolve_mcp_survey_src()

    survey_dir = (mirror_root / args.article_dir).resolve()
    survey_dir.mkdir(parents=True, exist_ok=True)
    vault_survey_dir = (vault_root / args.article_dir).resolve()

    if args.strong_relation_criteria_file:
        strong_criteria = load_strong_relation_criteria_file(args.strong_relation_criteria_file)
    else:
        strong_criteria = dict(DEFAULT_STRONG_RELATION_CRITERIA)

    topics_module = args.topics_module.strip()
    try:
        importlib.import_module(topics_module)
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Cannot import --topics-module {topics_module!r}: {exc}") from exc

    cfg = {
        "survey_name": args.survey_name,
        "target_word": args.target_word,
        "article_number": args.article_number,
        "ledger_number": args.ledger_number,
        "article_dir": args.article_dir.strip().strip("/"),
        "ledger_store_dir": str(resolve_ledger_store_root()),
        "vault_root": str(vault_root),
        "vault_survey_dir": str(vault_survey_dir),
        "python_survey_dir": str(survey_dir),
        "shared_python_dir": str(shared_dir),
        "mcp_survey_src": str(mcp_survey_src),
        "strong_relation_criteria": strong_criteria,
        "topics_module": topics_module,
        "step6_seed_limit": 100,
    }
    cfg_path = survey_dir / "survey_config.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(f"Wrote {cfg_path}")
    print(f"Final ledger (Step 9): {final_ledger_path(cfg)}")

    copy_if_missing(shared_dir / "step4_keyword_search.py", survey_dir / "step4_keyword_search.py")
    copy_if_missing(shared_dir / "step6_select_seeds.py", survey_dir / "step6_select_seeds.py")
    copy_if_missing(shared_dir / "step6_snowball.py", survey_dir / "step6_snowball.py")
    write_hydrate_stub(survey_dir / "hydrate_and_screen.py")
    write_run_survey_steps(survey_dir, mcp_survey_src, shared_dir)
    print(f"Survey mirror ready: {survey_dir}")
    return survey_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a survey mirror directory")
    add_bootstrap_arguments(parser)
    args = parser.parse_args(argv)
    run_bootstrap(args)


if __name__ == "__main__":
    main()
