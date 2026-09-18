from __future__ import annotations

import asyncio
import logging
import re
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, cast

from mcp.server.fastmcp import Context, FastMCP

from academic_mcp_server.common.config import AppConfig
from academic_mcp_server.common.models import Paper, PaperCollectionResponse, SUPPORTED_SOURCES, PaperSource, SourceError, UnifiedSearchResponse
from academic_mcp_server.common.normalize import first_text, normalize_limit, normalize_offset, normalize_text, sort_papers_for_display
from academic_mcp_server.connectors import ArxivConnector, CrossrefConnector, OpenAlexConnector, SemanticScholarConnector
from academic_mcp_server.connectors.semantic_scholar import SemanticScholarRateLimitError
from academic_mcp_server.survey.analysis import analyze_corpus
from academic_mcp_server.survey.content_acquisition import enrich_strong_content
from academic_mcp_server.survey.enrich import enrich_crossref
from academic_mcp_server.survey.generate import generate_docs
from academic_mcp_server.survey.stats import write_step3_stats
from academic_mcp_server.survey.validate import validate_survey


LOGGER = logging.getLogger(__name__)
_TITLE_NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class ServerRuntime:
    config: AppConfig
    semantic_scholar: SemanticScholarConnector
    arxiv: ArxivConnector
    crossref: CrossrefConnector
    openalex: OpenAlexConnector

    async def aclose(self) -> None:
        await asyncio.gather(
            self.semantic_scholar.aclose(),
            self.arxiv.aclose(),
            self.crossref.aclose(),
            self.openalex.aclose(),
        )


@asynccontextmanager
async def server_lifespan(_: FastMCP) -> AsyncIterator[ServerRuntime]:
    config = AppConfig.from_env()
    config_state_message = (
        "Starting paperSearch with config state: "
        f"semantic_scholar_api_key={'present' if config.semantic_scholar_api_key else 'absent'}, "
        f"contact_email={'present' if config.contact_email else 'absent'}"
    )
    LOGGER.info(config_state_message)
    print(config_state_message, file=sys.stderr, flush=True)
    runtime = ServerRuntime(
        config=config,
        semantic_scholar=SemanticScholarConnector(config),
        arxiv=ArxivConnector(config),
        crossref=CrossrefConnector(config),
        openalex=OpenAlexConnector(config),
    )
    try:
        yield runtime
    finally:
        await runtime.aclose()


mcp = FastMCP(
    name="paperSearch",
    instructions=(
        "Full academic paper-search MCP (all connectors). Cursor/Ubuntu surveys should "
        "use python -m academic_mcp_server.survey.mcp (paperSearch survey profile). "
        "Search academic papers across Semantic Scholar, arXiv, and Crossref."
    ),
    lifespan=server_lifespan,
    log_level="INFO",
)


def build_server() -> FastMCP:
    return mcp


def _get_runtime(ctx: Context) -> ServerRuntime:
    runtime = ctx.request_context.lifespan_context
    if not isinstance(runtime, ServerRuntime):
        raise RuntimeError("Server runtime is unavailable.")
    return runtime


def _require_context(ctx: Context | None) -> Context:
    if ctx is None:
        raise RuntimeError("Tool context is unavailable.")
    return ctx


def _normalize_sources(sources: list[str] | None) -> list[PaperSource]:
    if not sources:
        return list(SUPPORTED_SOURCES)

    normalized_sources: list[PaperSource] = []
    for source in sources:
        if source not in SUPPORTED_SOURCES:
            supported = ", ".join(SUPPORTED_SOURCES)
            raise ValueError(f"Unsupported source '{source}'. Supported sources: {supported}.")
        typed_source = cast(PaperSource, source)
        if typed_source not in normalized_sources:
            normalized_sources.append(typed_source)

    return normalized_sources


def _normalize_recommendation_pool(pool: str) -> str:
    normalized_pool = pool.strip().lower()
    if normalized_pool not in {"recent", "all-cs"}:
        raise ValueError("pool must be either 'recent' or 'all-cs'.")
    return normalized_pool


def _should_fallback_to_crossref_references(paper: Paper) -> bool:
    return bool(paper.doi and (paper.reference_count or 0) > 0)


def _extract_doi_candidate(identifier: str) -> str | None:
    normalized = identifier.strip()
    if not normalized:
        return None
    if normalized.lower().startswith("https://doi.org/"):
        normalized = normalized[16:]
    elif normalized.lower().startswith("http://doi.org/"):
        normalized = normalized[15:]
    if "/" not in normalized or " " in normalized:
        return None
    return normalized


def _normalize_title_key(title: str | None) -> str | None:
    normalized = normalize_text(title)
    if not normalized:
        return None
    key = _TITLE_NORMALIZATION_PATTERN.sub("", normalized.casefold())
    return key or None


def _extract_arxiv_identifier(paper: Paper) -> str | None:
    raw_arxiv_id = paper.external_ids.get("ArXiv")
    if isinstance(raw_arxiv_id, list):
        return first_text(raw_arxiv_id)
    return normalize_text(raw_arxiv_id)


async def _find_matching_arxiv_paper(
    runtime: ServerRuntime,
    *,
    paper: Paper,
    ctx: Context,
) -> tuple[Paper | None, str | None]:
    explicit_arxiv_id = _extract_arxiv_identifier(paper)
    if explicit_arxiv_id:
        try:
            return await runtime.arxiv.get_paper(arxiv_id=explicit_arxiv_id), "external_id"
        except Exception as exc:
            ctx.info(
                "Explicit arXiv identifier lookup failed; falling back to title search",
                arxiv_id=explicit_arxiv_id,
                error=str(exc),
            )

    title_key = _normalize_title_key(paper.title)
    if not title_key:
        return None, None

    search = await runtime.arxiv.search(query=paper.title, limit=5)
    for candidate in search.items:
        if _normalize_title_key(candidate.title) == title_key:
            return candidate, "title_exact_normalized"
    return None, None


def _with_abstract_fallback(base_paper: Paper, fallback_paper: Paper, fallback_source: str) -> Paper:
    if fallback_paper.abstract is None:
        return base_paper

    merged_metadata = dict(base_paper.source_metadata)
    merged_metadata["abstract_fallback_source"] = fallback_source
    return base_paper.model_copy(
        update={
            "abstract": fallback_paper.abstract,
            "source_metadata": merged_metadata,
            "pdf_url": base_paper.pdf_url or fallback_paper.pdf_url,
            "url": base_paper.url or fallback_paper.url,
        }
    )


def _infer_title_only_summary(paper: Paper) -> str:
    segments = [f"This paper likely investigates: {paper.title}."]
    if paper.primary_subject:
        segments.append(f"The likely subject area is {paper.primary_subject}.")
    if paper.venue:
        segments.append(f"It appears to be published in {paper.venue}.")
    segments.append(
        "This understanding is inferred from the title and sparse metadata only, so it is low-confidence."
    )
    return " ".join(segments)


def _build_content_assessment(
    paper: Paper,
    *,
    arxiv_match: dict[str, Any] | None,
    arxiv_full_text_result: dict[str, Any] | None,
) -> dict[str, Any]:
    if arxiv_full_text_result is not None:
        summary = paper.abstract or normalize_text(arxiv_full_text_result.get("full_text", "")[:1200])
        return {
            "basis": "full_text",
            "confidence": "high",
            "summary": summary,
            "requires_explicit_disclosure": False,
            "article_note": None,
            "evidence": {
                "abstract_available": paper.abstract is not None,
                "arxiv_match_found": arxiv_match is not None,
                "full_text_available": True,
            },
        }

    if paper.abstract:
        return {
            "basis": "abstract",
            "confidence": "medium",
            "summary": paper.abstract,
            "requires_explicit_disclosure": False,
            "article_note": None,
            "evidence": {
                "abstract_available": True,
                "arxiv_match_found": arxiv_match is not None,
                "full_text_available": False,
            },
        }

    return {
        "basis": "title_only",
        "confidence": "low",
        "summary": _infer_title_only_summary(paper),
        "requires_explicit_disclosure": True,
        "article_note": (
            "Only the title and sparse metadata could be checked for this paper; "
            "no public abstract or full text was available during the survey."
        ),
        "evidence": {
            "abstract_available": False,
            "arxiv_match_found": arxiv_match is not None,
            "full_text_available": False,
        },
    }


def _score_survey_candidate(paper: Paper) -> int:
    title = (paper.title or "").casefold()
    publication_types = " ".join(paper.publication_types).casefold()
    score = 0
    if any(keyword in title for keyword in ("survey", "review", "systematic", "overview")):
        score += 100
    if any(keyword in publication_types for keyword in ("review", "survey")):
        score += 80
    if paper.abstract:
        score += 20
    if paper.doi:
        score += 10
    if paper.citation_count:
        score += min(paper.citation_count, 50)
    return score


def _paper_identifier_for_survey_context(paper: Paper) -> str | None:
    if paper.source == "semantic_scholar":
        return paper.source_id
    if paper.doi:
        return paper.doi
    return None


def _build_pending_relation_response(
    *,
    kind: str,
    identifier: str,
    limit: int,
    offset: int,
    message: str,
    retry_after_seconds: float | None,
) -> PaperCollectionResponse:
    return PaperCollectionResponse(
        source="semantic_scholar",
        kind=kind,
        identifier=identifier,
        limit=limit,
        offset=offset,
        items=[],
        response_metadata={
            "status": "pending_rate_limited",
            "provider": "semantic_scholar",
            "blocking_closure": True,
            "message": message,
            "retry_after_seconds": retry_after_seconds,
        },
    )


def _build_remaining_relation_queue(
    *,
    relation_name: str,
    relation_response: PaperCollectionResponse,
) -> dict[str, Any] | None:
    if relation_response.next_offset is None:
        return None

    current_offset = relation_response.offset or 0
    items_returned = len(relation_response.items)
    total = relation_response.total
    remaining_items_estimate: int | None = None
    if total is not None:
        remaining_items_estimate = max(total - relation_response.next_offset, 0)

    return {
        "relation": relation_name,
        "identifier": relation_response.identifier,
        "offset": current_offset,
        "limit": relation_response.limit,
        "next_offset": relation_response.next_offset,
        "items_returned": items_returned,
        "total": total,
        "remaining_items_estimate": remaining_items_estimate,
        "queue_exhausted": False,
        "status": "has_more_pages",
    }


def _select_survey_candidates(papers: list[Paper], *, limit: int) -> list[Paper]:
    ranked_candidates = sorted(
        enumerate(papers),
        key=lambda item: (-_score_survey_candidate(item[1]), item[0]),
    )

    selected: list[Paper] = []
    seen_keys: set[str] = set()
    for _, paper in ranked_candidates:
        dedupe_key = paper.doi or f"{paper.source}:{paper.source_id}"
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        selected.append(paper)
        if len(selected) >= limit:
            break
    return selected


async def _search_survey_seed_papers(
    runtime: ServerRuntime,
    *,
    query: str,
    search_limit: int,
    ctx: Context,
) -> tuple[list[Paper], dict[str, Any]]:
    try:
        semantic_result = await runtime.semantic_scholar.search(query=query, limit=search_limit)
        if semantic_result.items:
            return semantic_result.items, {
                "primary": "semantic_scholar",
                "fallback_order": ["search_papers"],
                "resolved_source": "semantic_scholar",
                "result_count": len(semantic_result.items),
            }
    except Exception as exc:
        ctx.info("Semantic Scholar survey seed search failed; falling back to unified search", query=query, error=str(exc))

    fallback_result = await asyncio.gather(
        runtime.arxiv.search(query=query, limit=search_limit),
        runtime.crossref.search_works(query=query, limit=search_limit),
        return_exceptions=True,
    )
    items: list[Paper] = []
    errors: list[str] = []
    for source, result in zip(("arxiv", "crossref"), fallback_result, strict=True):
        if isinstance(result, Exception):
            errors.append(f"{source}: {result}")
            continue
        items.extend(result.items)

    return items, {
        "primary": "semantic_scholar",
        "fallback_order": ["search_papers"],
        "resolved_source": "fallback_search",
        "result_count": len(items),
        "errors": errors,
    }


async def _resolve_paper_and_doi(
    runtime: ServerRuntime,
    *,
    paper_id: str,
) -> tuple[Paper | None, str | None]:
    doi = _extract_doi_candidate(paper_id)
    semantic_scholar_paper: Paper | None = None
    if doi is not None:
        return None, doi

    try:
        semantic_scholar_paper = await runtime.semantic_scholar.get_paper(paper_id=paper_id)
    except Exception:
        return None, None

    return semantic_scholar_paper, semantic_scholar_paper.doi


async def _get_semantic_scholar_references_with_fallback(
    runtime: ServerRuntime,
    *,
    paper_id: str,
    limit: int,
    offset: int,
    ctx: Context,
) -> PaperCollectionResponse:
    semantic_scholar_paper, doi = await _resolve_paper_and_doi(
        runtime,
        paper_id=paper_id,
    )
    if doi:
        try:
            openalex_result = await runtime.openalex.get_references(
                identifier=doi,
                limit=limit,
                offset=offset,
            )
            if openalex_result.items:
                ctx.info(
                    "OpenAlex primary provider for Semantic Scholar references",
                    paper_id=paper_id,
                    doi=doi,
                    openalex_items=len(openalex_result.items),
                )
                return PaperCollectionResponse(
                    source="semantic_scholar",
                    kind="references",
                    identifier=(
                        semantic_scholar_paper.source_id
                        if semantic_scholar_paper
                        else openalex_result.identifier
                    ),
                    limit=openalex_result.limit,
                    offset=openalex_result.offset,
                    next_offset=openalex_result.next_offset,
                    total=openalex_result.total,
                    items=openalex_result.items,
                )
        except Exception as exc:
            ctx.info(
                "OpenAlex references provider failed; falling back to Semantic Scholar",
                paper_id=paper_id,
                doi=doi,
                openalex_error=str(exc),
            )

    try:
        result = await runtime.semantic_scholar.get_references(
            paper_id=paper_id,
            limit=limit,
            offset=offset,
        )
    except SemanticScholarRateLimitError as exc:
        if doi:
            try:
                fallback = await runtime.crossref.get_work_references(
                    doi=doi,
                    limit=limit,
                    offset=offset,
                )
                if fallback.items:
                    ctx.info(
                        "Crossref fallback used after Semantic Scholar reference rate limit",
                        paper_id=paper_id,
                        doi=doi,
                        retry_after_seconds=exc.retry_after_seconds,
                    )
                    return PaperCollectionResponse(
                        source="semantic_scholar",
                        kind="references",
                        identifier=(
                            semantic_scholar_paper.source_id
                            if semantic_scholar_paper
                            else fallback.identifier
                        ),
                        limit=fallback.limit,
                        offset=fallback.offset,
                        next_offset=fallback.next_offset,
                        total=fallback.total,
                        items=fallback.items,
                        response_metadata={
                            "status": "fallback_crossref_after_rate_limit",
                            "provider": "crossref",
                            "blocking_closure": False,
                            "semantic_scholar_retry_after_seconds": exc.retry_after_seconds,
                        },
                    )
            except Exception as fallback_exc:
                ctx.info(
                    "Crossref fallback also failed after Semantic Scholar reference rate limit",
                    paper_id=paper_id,
                    doi=doi,
                    crossref_error=str(fallback_exc),
                )
        ctx.info(
            "Semantic Scholar references remain pending due to rate limit",
            paper_id=paper_id,
            doi=doi,
            retry_after_seconds=exc.retry_after_seconds,
        )
        return _build_pending_relation_response(
            kind="references",
            identifier=paper_id,
            limit=limit,
            offset=offset,
            message=str(exc),
            retry_after_seconds=exc.retry_after_seconds,
        )
    if result.items:
        return result

    paper = semantic_scholar_paper or await runtime.semantic_scholar.get_paper(paper_id=paper_id)
    if not _should_fallback_to_crossref_references(paper):
        return result

    try:
        fallback = await runtime.crossref.get_work_references(
            doi=paper.doi,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        ctx.info(
            "Crossref fallback for Semantic Scholar references failed",
            paper_id=paper.source_id,
            doi=paper.doi,
            crossref_error=str(exc),
        )
        return result
    if not fallback.items:
        return result

    ctx.info(
        "Crossref fallback for Semantic Scholar references",
        paper_id=paper.source_id,
        doi=paper.doi,
        semantic_scholar_reference_count=paper.reference_count,
        fallback_items=len(fallback.items),
    )
    return PaperCollectionResponse(
        source="semantic_scholar",
        kind="references",
        identifier=result.identifier or paper.source_id,
        limit=result.limit,
        offset=result.offset,
        next_offset=fallback.next_offset,
        total=fallback.total or paper.reference_count,
        items=fallback.items,
    )


async def _get_openalex_citations_fallback(
    runtime: ServerRuntime,
    *,
    paper_id: str,
    limit: int,
    offset: int,
    ctx: Context,
    semantic_scholar_error: Exception | None = None,
) -> PaperCollectionResponse | None:
    semantic_scholar_paper, doi = await _resolve_paper_and_doi(
        runtime,
        paper_id=paper_id,
    )

    if not doi:
        return None

    try:
        fallback = await runtime.openalex.get_citations(
            identifier=doi,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        ctx.info(
            "OpenAlex citations provider failed; falling back to Semantic Scholar",
            paper_id=paper_id,
            doi=doi,
            openalex_error=str(exc),
        )
        return None
    if not fallback.items:
        return None

    ctx.info(
        "OpenAlex primary provider for Semantic Scholar citations",
        paper_id=paper_id,
        doi=doi,
        openalex_items=len(fallback.items),
        semantic_scholar_error=str(semantic_scholar_error) if semantic_scholar_error else None,
    )
    return PaperCollectionResponse(
        source="semantic_scholar",
        kind="citations",
        identifier=(semantic_scholar_paper.source_id if semantic_scholar_paper else fallback.identifier),
        limit=fallback.limit,
        offset=fallback.offset,
        next_offset=fallback.next_offset,
        total=fallback.total,
        items=fallback.items,
    )


async def _get_semantic_scholar_citations_with_fallback(
    runtime: ServerRuntime,
    *,
    paper_id: str,
    limit: int,
    offset: int,
    ctx: Context,
) -> PaperCollectionResponse:
    openalex_result = await _get_openalex_citations_fallback(
        runtime,
        paper_id=paper_id,
        limit=limit,
        offset=offset,
        ctx=ctx,
    )
    if openalex_result is not None:
        return openalex_result

    semantic_scholar_error: Exception | None = None
    try:
        result = await runtime.semantic_scholar.get_citations(
            paper_id=paper_id,
            limit=limit,
            offset=offset,
        )
        if result.items:
            return result
    except SemanticScholarRateLimitError as exc:
        ctx.info(
            "Semantic Scholar citations remain pending due to rate limit",
            paper_id=paper_id,
            retry_after_seconds=exc.retry_after_seconds,
        )
        return _build_pending_relation_response(
            kind="citations",
            identifier=paper_id,
            limit=limit,
            offset=offset,
            message=str(exc),
            retry_after_seconds=exc.retry_after_seconds,
        )
    except Exception as exc:
        semantic_scholar_error = exc
        result = PaperCollectionResponse(
            source="semantic_scholar",
            kind="citations",
            identifier=paper_id,
            limit=limit,
            offset=offset,
            items=[],
        )

    if semantic_scholar_error is not None:
        raise semantic_scholar_error
    return result


async def _get_semantic_scholar_paper_with_fallback(
    runtime: ServerRuntime,
    *,
    paper_id: str,
    ctx: Context,
) -> Paper:
    doi = _extract_doi_candidate(paper_id)
    semantic_scholar_error: Exception | None = None
    try:
        semantic_scholar_paper = await runtime.semantic_scholar.get_paper(paper_id=paper_id)
        if semantic_scholar_paper.abstract or not semantic_scholar_paper.doi:
            return semantic_scholar_paper
        doi = semantic_scholar_paper.doi
        ctx.info(
            "Semantic Scholar paper lookup returned no abstract; trying OpenAlex enrichment",
            paper_id=paper_id,
            doi=doi,
        )
    except Exception as exc:
        semantic_scholar_error = exc

    if not doi:
        if semantic_scholar_error is not None:
            raise semantic_scholar_error
        raise semantic_scholar_error

    try:
        fallback = await runtime.openalex.get_work(identifier=doi)
        ctx.info(
            "OpenAlex fallback for Semantic Scholar paper lookup",
            paper_id=paper_id,
            doi=doi,
            semantic_scholar_error=str(semantic_scholar_error),
        )
        if semantic_scholar_error is None:
            return _with_abstract_fallback(semantic_scholar_paper, fallback, "openalex")
        return fallback
    except Exception as openalex_exc:
        ctx.info(
            "OpenAlex paper fallback failed; falling back to Crossref",
            paper_id=paper_id,
            doi=doi,
            openalex_error=str(openalex_exc),
        )
    crossref_paper = await runtime.crossref.get_work_by_doi(doi=doi)
    if semantic_scholar_error is None:
        return _with_abstract_fallback(semantic_scholar_paper, crossref_paper, "crossref")
    return crossref_paper


async def _build_survey_paper_context(
    runtime: ServerRuntime,
    *,
    paper_id: str,
    relation_limit: int,
    relation_offset: int,
    include_full_text: bool,
    max_full_text_characters: int,
    ctx: Context,
) -> dict[str, Any]:
    paper = await _get_semantic_scholar_paper_with_fallback(
        runtime,
        paper_id=paper_id,
        ctx=ctx,
    )
    references, citations = await asyncio.gather(
        _get_semantic_scholar_references_with_fallback(
            runtime,
            paper_id=paper.doi or paper.source_id,
            limit=relation_limit,
            offset=relation_offset,
            ctx=ctx,
        ),
        _get_semantic_scholar_citations_with_fallback(
            runtime,
            paper_id=paper.doi or paper.source_id,
            limit=relation_limit,
            offset=relation_offset,
            ctx=ctx,
        ),
    )

    arxiv_match: dict[str, Any] | None = None
    arxiv_full_text_result: dict[str, Any] | None = None
    arxiv_notes: list[str] = []
    try:
        matched_arxiv_paper, matched_by = await _find_matching_arxiv_paper(
            runtime,
            paper=paper,
            ctx=ctx,
        )
    except Exception as exc:
        matched_arxiv_paper = None
        matched_by = None
        arxiv_notes.append(f"arxiv_match_failed: {exc}")

    if matched_arxiv_paper is not None:
        arxiv_match = {
            "matched_by": matched_by,
            "paper": matched_arxiv_paper.model_dump(mode="json"),
        }
        if include_full_text:
            try:
                full_text = await runtime.arxiv.analyze_full_text(
                    arxiv_id=matched_arxiv_paper.source_id,
                    prefer="source",
                    max_characters=max_full_text_characters,
                )
                arxiv_full_text_result = full_text.model_dump(mode="json")
            except Exception as exc:
                arxiv_notes.append(f"arxiv_full_text_failed: {exc}")

    content_assessment = _build_content_assessment(
        paper,
        arxiv_match=arxiv_match,
        arxiv_full_text_result=arxiv_full_text_result,
    )

    pending_relations: list[dict[str, Any]] = []
    remaining_queues: list[dict[str, Any]] = []
    for relation_name, relation_response in (("references", references), ("citations", citations)):
        relation_metadata = relation_response.response_metadata
        if relation_metadata.get("blocking_closure"):
            pending_relations.append(
                {
                    "relation": relation_name,
                    "status": relation_metadata.get("status"),
                    "provider": relation_metadata.get("provider"),
                    "retry_after_seconds": relation_metadata.get("retry_after_seconds"),
                    "message": relation_metadata.get("message"),
                }
            )
        remaining_queue = _build_remaining_relation_queue(
            relation_name=relation_name,
            relation_response=relation_response,
        )
        if remaining_queue is not None:
            remaining_queues.append(remaining_queue)

    return {
        "query_paper_id": paper_id,
        "paper": paper.model_dump(mode="json"),
        "overview_strategy": {
            "primary": "semantic_scholar",
            "fallback_order": ["openalex", "crossref"],
            "resolved_source": paper.source,
        },
        "references": references.model_dump(mode="json"),
        "citations": citations.model_dump(mode="json"),
        "relation_strategy": {
            "references_primary": "openalex",
            "references_fallback_order": ["semantic_scholar", "crossref"],
            "citations_primary": "openalex",
            "citations_fallback_order": ["semantic_scholar"],
        },
        "relation_audit": {
            "pending_count": len(pending_relations),
            "pending_relations": pending_relations,
            "remaining_queue_count": len(remaining_queues),
            "remaining_queues": remaining_queues,
            "has_unfetched_relation_pages": bool(remaining_queues),
            "closure_blocked": bool(pending_relations or remaining_queues),
        },
        "arxiv_match": arxiv_match,
        "arxiv_full_text": arxiv_full_text_result,
        "content_assessment": content_assessment,
        "notes": arxiv_notes,
    }


@mcp.tool(
    name="semantic_scholar_search",
    description="Search Semantic Scholar papers by keyword query.",
)
async def semantic_scholar_search(query: str, limit: int = 10, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar search", query=query, limit=limit)
    result = await runtime.semantic_scholar.search(query=query, limit=limit)
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_paper",
    description="Fetch a single Semantic Scholar paper by paper ID, DOI, or other supported identifier.",
)
async def semantic_scholar_paper(paper_id: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar paper lookup", paper_id=paper_id)
    result = await _get_semantic_scholar_paper_with_fallback(
        runtime,
        paper_id=paper_id,
        ctx=ctx,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="survey_paper_context",
    description=(
        "Build a literature-survey context for one paper: use Semantic Scholar for the paper abstract, "
        "OpenAlex-first fallbacks for references and citations, and arXiv full text when the same paper is found on arXiv."
    ),
)
async def survey_paper_context(
    paper_id: str,
    relation_limit: int = 10,
    relation_offset: int = 0,
    include_full_text: bool = True,
    max_full_text_characters: int = 200000,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    normalized_relation_limit = normalize_limit(
        relation_limit,
        default=runtime.config.default_limit,
        maximum=20,
    )
    normalized_relation_offset = normalize_offset(relation_offset)
    ctx.info(
        "Survey paper context lookup",
        paper_id=paper_id,
        relation_limit=normalized_relation_limit,
        relation_offset=normalized_relation_offset,
        include_full_text=include_full_text,
        max_full_text_characters=max_full_text_characters,
    )
    return await _build_survey_paper_context(
        runtime,
        paper_id=paper_id,
        relation_limit=normalized_relation_limit,
        relation_offset=normalized_relation_offset,
        include_full_text=include_full_text,
        max_full_text_characters=max_full_text_characters,
        ctx=ctx,
    )


@mcp.tool(
    name="survey_query_contexts",
    description=(
        "Search papers for a literature-survey query, choose the most promising candidates, and build survey contexts for each in one batch. "
        "This reduces MCP round trips and keeps per-paper disclosure metadata together."
    ),
)
async def survey_query_contexts(
    query: str,
    search_limit: int = 10,
    paper_limit: int = 3,
    relation_limit: int = 10,
    relation_offset: int = 0,
    include_full_text: bool = True,
    max_full_text_characters: int = 200000,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    normalized_search_limit = normalize_limit(
        search_limit,
        default=runtime.config.default_limit,
        maximum=20,
    )
    normalized_paper_limit = normalize_limit(
        paper_limit,
        default=min(runtime.config.default_limit, 3),
        maximum=10,
    )
    normalized_relation_limit = normalize_limit(
        relation_limit,
        default=runtime.config.default_limit,
        maximum=20,
    )
    normalized_relation_offset = normalize_offset(relation_offset)
    ctx.info(
        "Survey query batch context lookup",
        query=query,
        search_limit=normalized_search_limit,
        paper_limit=normalized_paper_limit,
        relation_limit=normalized_relation_limit,
        relation_offset=normalized_relation_offset,
        include_full_text=include_full_text,
    )

    seed_papers, search_strategy = await _search_survey_seed_papers(
        runtime,
        query=query,
        search_limit=normalized_search_limit,
        ctx=ctx,
    )
    selected_papers = _select_survey_candidates(seed_papers, limit=normalized_paper_limit)

    contexts: list[dict[str, Any]] = []
    skipped_candidates: list[dict[str, Any]] = []
    title_only_papers: list[dict[str, Any]] = []
    pending_relation_jobs: list[dict[str, Any]] = []
    remaining_relation_queues: list[dict[str, Any]] = []
    for paper in selected_papers:
        paper_identifier = _paper_identifier_for_survey_context(paper)
        if paper_identifier is None:
            skipped_candidates.append(
                {
                    "paper": paper.model_dump(mode="json"),
                    "reason": "No DOI or Semantic Scholar identifier available for survey context resolution.",
                }
            )
            continue
        context_result = await _build_survey_paper_context(
            runtime,
            paper_id=paper_identifier,
            relation_limit=normalized_relation_limit,
            relation_offset=normalized_relation_offset,
            include_full_text=include_full_text,
            max_full_text_characters=max_full_text_characters,
            ctx=ctx,
        )
        context_result["selection"] = {
            "score": _score_survey_candidate(paper),
            "selected_from_query": query.strip(),
        }
        contexts.append(context_result)
        relation_audit = context_result.get("relation_audit") or {}
        pending_relation_jobs.extend(relation_audit.get("pending_relations") or [])
        remaining_relation_queues.extend(relation_audit.get("remaining_queues") or [])
        content_assessment = context_result.get("content_assessment") or {}
        if content_assessment.get("basis") == "title_only":
            title_only_papers.append(
                {
                    "query_paper_id": context_result.get("query_paper_id"),
                    "source": context_result["paper"].get("source"),
                    "source_id": context_result["paper"].get("source_id"),
                    "title": context_result["paper"].get("title"),
                    "doi": context_result["paper"].get("doi"),
                    "article_note": content_assessment.get("article_note"),
                    "summary": content_assessment.get("summary"),
                }
            )

    return {
        "query": query.strip(),
        "search_strategy": search_strategy,
        "batch_benefits": {
            "reduces_mcp_round_trips": True,
            "shares_server_side_cache": True,
            "can_reduce_duplicate_identifier_resolution": True,
            "upstream_request_count_guaranteed_lower": False,
        },
        "selected_count": len(contexts),
        "selected_contexts": contexts,
        "closure_audit": {
            "pending_relation_jobs": pending_relation_jobs,
            "pending_relation_count": len(pending_relation_jobs),
            "remaining_relation_queues": remaining_relation_queues,
            "remaining_relation_queue_count": len(remaining_relation_queues),
            "closure_blocked_by_pending_relations": bool(pending_relation_jobs),
            "closure_blocked_by_remaining_relation_pages": bool(remaining_relation_queues),
            "closure_blocked": bool(pending_relation_jobs or remaining_relation_queues),
        },
        "title_only_papers": title_only_papers,
        "title_only_count": len(title_only_papers),
        "skipped_candidates": skipped_candidates,
    }


@mcp.tool(
    name="semantic_scholar_paper_batch",
    description="Fetch multiple Semantic Scholar papers in one batch by paper IDs, DOI IDs, or other supported identifiers.",
)
async def semantic_scholar_paper_batch(
    paper_ids: list[str],
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar paper batch lookup", count=len(paper_ids))
    result = await runtime.semantic_scholar.get_papers_batch(paper_ids=paper_ids)
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_citations",
    description="Fetch papers that cite a Semantic Scholar paper.",
)
async def semantic_scholar_citations(
    paper_id: str,
    limit: int = 10,
    offset: int = 0,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar citations lookup", paper_id=paper_id, limit=limit, offset=offset)
    result = await _get_semantic_scholar_citations_with_fallback(
        runtime,
        paper_id=paper_id,
        limit=limit,
        offset=offset,
        ctx=ctx,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_references",
    description="Fetch papers referenced by a Semantic Scholar paper.",
)
async def semantic_scholar_references(
    paper_id: str,
    limit: int = 10,
    offset: int = 0,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar references lookup", paper_id=paper_id, limit=limit, offset=offset)
    result = await _get_semantic_scholar_references_with_fallback(
        runtime,
        paper_id=paper_id,
        limit=limit,
        offset=offset,
        ctx=ctx,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_author_search",
    description="Search Semantic Scholar authors by name.",
)
async def semantic_scholar_author_search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar author search", query=query, limit=limit, offset=offset)
    result = await runtime.semantic_scholar.search_authors(
        query=query,
        limit=limit,
        offset=offset,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_author",
    description="Fetch a single Semantic Scholar author by author ID.",
)
async def semantic_scholar_author(author_id: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar author lookup", author_id=author_id)
    result = await runtime.semantic_scholar.get_author(author_id=author_id)
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_author_papers",
    description="Fetch papers for a Semantic Scholar author.",
)
async def semantic_scholar_author_papers(
    author_id: str,
    limit: int = 10,
    offset: int = 0,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Semantic Scholar author papers lookup", author_id=author_id, limit=limit, offset=offset)
    result = await runtime.semantic_scholar.get_author_papers(
        author_id=author_id,
        limit=limit,
        offset=offset,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_recommended_papers",
    description="Fetch recommended papers for a single Semantic Scholar paper.",
)
async def semantic_scholar_recommended_papers(
    paper_id: str,
    limit: int = 10,
    pool: str = "recent",
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    normalized_pool = _normalize_recommendation_pool(pool)
    ctx.info(
        "Semantic Scholar recommended papers lookup",
        paper_id=paper_id,
        limit=limit,
        pool=normalized_pool,
    )
    result = await runtime.semantic_scholar.get_recommended_papers(
        paper_id=paper_id,
        limit=limit,
        pool=normalized_pool,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="semantic_scholar_recommend_from_examples",
    description="Fetch Semantic Scholar recommendations from positive and optional negative example papers.",
)
async def semantic_scholar_recommend_from_examples(
    positive_paper_ids: list[str],
    negative_paper_ids: list[str] | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info(
        "Semantic Scholar example-based recommendations lookup",
        positive_count=len(positive_paper_ids),
        negative_count=len(negative_paper_ids or []),
        limit=limit,
    )
    result = await runtime.semantic_scholar.recommend_from_examples(
        positive_paper_ids=positive_paper_ids,
        negative_paper_ids=negative_paper_ids,
        limit=limit,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="arxiv_search",
    description="Search arXiv papers and preprints through the Atom query API.",
)
async def arxiv_search(query: str, limit: int = 10, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("arXiv search", query=query, limit=limit)
    result = await runtime.arxiv.search(query=query, limit=limit)
    return result.model_dump(mode="json")


@mcp.tool(
    name="arxiv_paper",
    description="Fetch a single arXiv paper by arXiv ID or arXiv URL.",
)
async def arxiv_paper(arxiv_id: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("arXiv paper lookup", arxiv_id=arxiv_id)
    result = await runtime.arxiv.get_paper(arxiv_id=arxiv_id)
    return result.model_dump(mode="json")


@mcp.tool(
    name="arxiv_full_text",
    description=(
        "Download and analyze an arXiv paper's full text from source files or PDF. "
        "When source files are available, also extract figure and table captions. "
        "Set max_characters=0 to disable truncation."
    ),
)
async def arxiv_full_text(
    arxiv_id: str,
    prefer: str = "source",
    max_characters: int = 200000,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info(
        "arXiv full text analysis",
        arxiv_id=arxiv_id,
        prefer=prefer,
        max_characters=max_characters,
    )
    result = await runtime.arxiv.analyze_full_text(
        arxiv_id=arxiv_id,
        prefer=prefer,
        max_characters=max_characters,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="crossref_search_works",
    description="Search Crossref works metadata by free-text query.",
)
async def crossref_search_works(query: str, limit: int = 10, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Crossref works search", query=query, limit=limit)
    result = await runtime.crossref.search_works(query=query, limit=limit)
    return result.model_dump(mode="json")


@mcp.tool(
    name="crossref_work_by_doi",
    description="Fetch one Crossref work by DOI.",
)
async def crossref_work_by_doi(doi: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Crossref DOI lookup", doi=doi)
    result = await runtime.crossref.get_work_by_doi(doi=doi)
    return result.model_dump(mode="json")


@mcp.tool(
    name="crossref_journal_works",
    description="Fetch Crossref works for a journal ISSN, optionally narrowed by a query string.",
)
async def crossref_journal_works(
    issn: str,
    query: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Crossref journal works lookup", issn=issn, query=query, limit=limit)
    result = await runtime.crossref.get_journal_works(
        issn=issn,
        query=query,
        limit=limit,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="crossref_funder_works",
    description="Fetch Crossref works for a funder ID, optionally narrowed by a query string.",
)
async def crossref_funder_works(
    funder_id: str,
    query: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Crossref funder works lookup", funder_id=funder_id, query=query, limit=limit)
    result = await runtime.crossref.get_funder_works(
        funder_id=funder_id,
        query=query,
        limit=limit,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="crossref_type_works",
    description="Fetch Crossref works for a Crossref work type, optionally narrowed by a query string.",
)
async def crossref_type_works(
    type_id: str,
    query: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    ctx.info("Crossref type works lookup", type_id=type_id, query=query, limit=limit)
    result = await runtime.crossref.get_type_works(
        type_id=type_id,
        query=query,
        limit=limit,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="search_papers",
    description="Search across Semantic Scholar, arXiv, and Crossref with normalized output.",
)
async def search_papers(
    query: str,
    sources: list[str] | None = None,
    limit_per_source: int = 5,
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    selected_sources = _normalize_sources(sources)
    normalized_limit = normalize_limit(
        limit_per_source,
        default=runtime.config.default_limit,
        maximum=20,
    )
    ctx.info(
        "Unified paper search",
        query=query,
        sources=selected_sources,
        limit_per_source=normalized_limit,
    )

    requests: dict[PaperSource, asyncio.Future[Any] | Any] = {}
    if "semantic_scholar" in selected_sources:
        requests["semantic_scholar"] = runtime.semantic_scholar.search(
            query=query,
            limit=normalized_limit,
        )
    if "arxiv" in selected_sources:
        requests["arxiv"] = runtime.arxiv.search(query=query, limit=normalized_limit)
    if "crossref" in selected_sources:
        requests["crossref"] = runtime.crossref.search_works(
            query=query,
            limit=normalized_limit,
        )

    results = await asyncio.gather(*requests.values(), return_exceptions=True)

    merged_items = []
    errors: list[SourceError] = []
    for source, result in zip(requests.keys(), results, strict=True):
        if isinstance(result, Exception):
            errors.append(SourceError(source=source, message=str(result)))
            continue
        merged_items.extend(result.items)

    response = UnifiedSearchResponse(
        query=query.strip(),
        sources=selected_sources,
        limit_per_source=normalized_limit,
        items=sort_papers_for_display(merged_items),
        errors=errors,
    )
    return response.model_dump(mode="json")




@mcp.tool(
    name="semantic_scholar_search_paginated",
    description="Search Semantic Scholar with pagination until total or max_results.",
)
async def semantic_scholar_search_paginated(query: str, max_results: int = 500, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    runtime = _get_runtime(ctx)
    normalized_max = max(1, min(max_results, 3000))
    page_size = min(100, normalized_max)
    max_pages = max(1, min(30, (normalized_max + page_size - 1) // page_size))
    ctx.info("Semantic Scholar paginated search", query=query, max_results=normalized_max, max_pages=max_pages)
    result = await runtime.semantic_scholar.search_all_pages(query=query, page_size=page_size, max_pages=max_pages, max_results=normalized_max)
    return result.model_dump(mode="json")

@mcp.tool(name="survey_enrich_crossref", description="Enrich DOI entries in a survey mirror. scope: strong (kept+strong), all (kept), collection (all entries, pre-screening).")
async def survey_enrich_crossref(mirror_dir: str, scope: str = "strong", ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    ctx.info("Survey Crossref enrich", mirror_dir=mirror_dir, scope=scope)
    return await asyncio.to_thread(enrich_crossref, mirror_dir, scope)

@mcp.tool(
    name="survey_enrich_content",
    description="Fetch abstracts (SS then OpenAlex). scope=pre_screening: all entries before Step 5 (Step 4.5); scope=strong: kept+strong only (Step 5.5/8).",
)
async def survey_enrich_content(
    mirror_dir: str,
    scope: str = "pre_screening",
    ctx: Context | None = None,
) -> dict[str, Any]:
    ctx = _require_context(ctx)
    ctx.info("Survey content enrich", mirror_dir=mirror_dir, scope=scope)
    from academic_mcp_server.survey.content_acquisition import enrich_content

    return await asyncio.to_thread(enrich_content, mirror_dir, scope=scope)

@mcp.tool(name="survey_analyze_corpus", description="Quantitative survey corpus analysis.")
async def survey_analyze_corpus(mirror_dir: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    ctx.info("Survey corpus analysis", mirror_dir=mirror_dir)
    return await asyncio.to_thread(analyze_corpus, mirror_dir)

@mcp.tool(name="survey_generate_docs", description="Generate Obsidian survey article and ledger.")
async def survey_generate_docs(mirror_dir: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    ctx.info("Survey doc generation", mirror_dir=mirror_dir)
    return await asyncio.to_thread(generate_docs, mirror_dir)

@mcp.tool(name="survey_write_step3_stats", description="Write _step3_stats.json after Step 3 keyword extraction.")
async def survey_write_step3_stats(mirror_dir: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    ctx.info("Survey Step 3 stats", mirror_dir=mirror_dir)
    return await asyncio.to_thread(write_step3_stats, mirror_dir)

@mcp.tool(name="survey_validate_corpus", description="Validate strong-only References invariant and metadata completeness.")
async def survey_validate_corpus(mirror_dir: str, article_path: str = "", ctx: Context | None = None) -> dict[str, Any]:
    ctx = _require_context(ctx)
    ctx.info("Survey validate", mirror_dir=mirror_dir, article_path=article_path or None)
    ap = article_path.strip() or None
    return await asyncio.to_thread(validate_survey, mirror_dir, article_path=ap)


@mcp.tool(
    name="survey_validate_phase_b",
    description=(
        "Phase B gate: pipe-table column alignment, canonical [Rxxx](#^refRxxx) links, "
        "^ref block IDs, plus strong-only References (same as validate)."
    ),
)
async def survey_validate_phase_b(
    mirror_dir: str,
    article_path: str = "",
    check_corpus: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    from academic_mcp_server.survey.master_list import load_survey_config, resolve_python_mirror_dir
    from academic_mcp_server.survey.phase_b_validate import validate_phase_b_article

    ctx = _require_context(ctx)
    mirror = resolve_python_mirror_dir(mirror_dir)
    ap = article_path.strip()
    if not ap:
        cfg = load_survey_config(mirror)
        name = cfg.get("survey_name", "survey")
        vault = Path(cfg.get("vault_survey_dir", mirror))
        ap = str(vault / f"{name}.md")
    ctx.info("Survey validate Phase B", mirror_dir=str(mirror), article_path=ap)
    return await asyncio.to_thread(
        validate_phase_b_article,
        ap,
        mirror_dir=mirror,
        check_corpus=check_corpus,
    )

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()