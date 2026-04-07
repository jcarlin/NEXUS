"""LangGraph tool wrappers for the agentic investigation pipeline.

Each tool is a thin ``@tool``-decorated async function that wraps an existing
service.  Security-scoped fields (``matter_id``, privilege filters) are
injected from graph state via ``InjectedState`` so the LLM never sees them.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import time as _time_obj
from typing import Annotated, Any

import structlog
from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import InjectedState
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db_utils import parse_email_date
from app.query.overrides import resolve_flag, resolve_param
from app.query.trace import emit_tool_trace, reset_override_usage

logger = structlog.get_logger(__name__)


def _normalize_date_bound(raw: str, *, end_of_day: bool) -> str:
    """Parse a date string and return a Qdrant-compatible ISO 8601 timestamp.

    Accepts ``YYYY-MM-DD``, ISO 8601, or RFC 2822. When *end_of_day* is
    ``True`` and the input contains no time component (midnight), the
    returned value is shifted to the last microsecond of the day so an
    upper bound like ``2020-03-31`` is inclusive of all of March 31.

    Raises ``ValueError`` on unparseable input — temporal_search must not
    silently ignore a malformed bound.
    """
    dt = parse_email_date(raw)
    if dt is None:
        raise ValueError(f"Invalid date bound: {raw!r}")
    if end_of_day and dt.time() == _time_obj(0, 0, 0):
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt.isoformat()


@asynccontextmanager
async def _tool_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async DB session scoped to a tool call."""
    from app.dependencies import get_db

    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        yield db
    finally:
        try:
            await db_gen.aclose()
        except Exception as e:
            logger.warning("tool.db_session_cleanup_failed", error=str(e))


# ---------------------------------------------------------------------------
# Real tools (wrapping existing services)
# ---------------------------------------------------------------------------


@tool
async def vector_search(
    query: str,
    limit: int = 20,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Search legal documents by semantic similarity.

    Use for content questions, finding mentions of specific topics, locating
    evidence about events, agreements, or communications.
    """
    import time as _time

    from app.dependencies import get_retriever

    _t0 = _time.perf_counter()
    reset_override_usage()
    try:
        retriever = get_retriever()

        # HyDE: generate hypothetical document for dense retrieval (T2-6)
        from app.dependencies import get_settings

        settings = get_settings()

        # Adaptive retrieval depth (T3-13)
        overrides = state.get("_retrieval_overrides")
        if resolve_flag("enable_adaptive_retrieval_depth", settings, overrides):
            adaptive_limit = state.get("_adaptive_text_limit")
            if adaptive_limit:
                limit = adaptive_limit

        hyde_vector: list[float] | None = None
        if resolve_flag("enable_hyde", settings, overrides):
            from app.dependencies import get_embedder, get_llm
            from app.query.hyde import generate_hypothetical_document

            try:
                llm = get_llm()
                hypothetical = await generate_hypothetical_document(
                    query,
                    llm,
                    matter_context=state.get("_case_context", ""),
                )
                embedder = get_embedder()
                raw_hyde_vector = await embedder.embed_query(hypothetical)
                # Blend HyDE embedding with original query embedding to reduce
                # semantic drift from the hypothetical document.
                blend = resolve_param("hyde_blend_ratio", settings, overrides)
                if blend < 1.0:
                    query_vector = await embedder.embed_query(query)
                    hyde_vector = [blend * h + (1.0 - blend) * q for h, q in zip(raw_hyde_vector, query_vector)]
                else:
                    hyde_vector = raw_hyde_vector
            except Exception:
                logger.warning("tool.vector_search.hyde_failed", exc_info=True)

        # Multi-query expansion (T1-1)
        if resolve_flag("enable_multi_query_expansion", settings, overrides):
            from app.dependencies import get_llm
            from app.query.multi_query import expand_query

            llm = get_llm()
            variants = await expand_query(
                query,
                llm,
                term_map=state.get("_term_map"),
                count=int(resolve_param("multi_query_count", settings, overrides)),
            )
            if variants:
                import asyncio

                # Run original + variants in parallel
                all_queries = [query] + variants
                coros = [
                    retriever.retrieve_text(
                        q,
                        limit=limit,
                        filters=state.get("_filters"),
                        exclude_privilege_statuses=state.get("_exclude_privilege") or None,
                        dataset_doc_ids=state.get("_dataset_doc_ids"),
                        hyde_vector=hyde_vector,
                    )
                    for q in all_queries
                ]
                all_results = await asyncio.gather(*coros, return_exceptions=True)

                # Merge and deduplicate by chunk ID, keep highest score.
                # Weight original query results higher than variants to prevent
                # off-topic variant results from polluting the merged set.
                seen: dict[str, dict] = {}
                for idx, batch in enumerate(all_results):
                    if isinstance(batch, BaseException):
                        continue
                    weight = 1.0 if idx == 0 else 0.7  # Original=1.0x, variants=0.7x
                    for r in batch:
                        rid = r.get("id", "")
                        weighted_score = r.get("score", 0) * weight
                        if rid not in seen or weighted_score > seen[rid].get("score", 0):
                            seen[rid] = {**r, "score": weighted_score}
                results = sorted(seen.values(), key=lambda r: r.get("score", 0), reverse=True)[:limit]
            else:
                results = await retriever.retrieve_text(
                    query,
                    limit=limit,
                    filters=state.get("_filters"),
                    exclude_privilege_statuses=state.get("_exclude_privilege") or None,
                    dataset_doc_ids=state.get("_dataset_doc_ids"),
                    hyde_vector=hyde_vector,
                )
        else:
            results = await retriever.retrieve_text(
                query,
                limit=limit,
                filters=state.get("_filters"),
                exclude_privilege_statuses=state.get("_exclude_privilege") or None,
                dataset_doc_ids=state.get("_dataset_doc_ids"),
                hyde_vector=hyde_vector,
            )
    except Exception as exc:
        logger.warning("tool.error", tool="vector_search", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})
    # Return structured results for the agent to reason over
    formatted = [
        {
            "id": r.get("id", ""),
            "filename": r.get("source_file", "unknown"),
            "page": r.get("page_number"),
            "text": r.get("chunk_text", "")[:500],
            "score": round(r.get("score", 0), 4),
            "document_date": r.get("document_date"),
        }
        for r in results[:limit]
    ]
    _duration = round((_time.perf_counter() - _t0) * 1000, 1)
    emit_tool_trace(
        name="vector_search",
        label=f"Searched {len(formatted)} chunks",
        duration_ms=_duration,
        args_summary={
            "limit": limit,
            "hyde": resolve_flag("enable_hyde", settings, overrides),
            "multi_query": resolve_flag("enable_multi_query_expansion", settings, overrides),
        },
        result_summary={"chunks_returned": len(formatted)},
    )
    return json.dumps(formatted, default=str)


@tool
async def graph_query(
    entity_name: str,
    limit: int = 20,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Query the knowledge graph for entity relationships and connections.

    Use for questions like "Who communicated with X?", "What entities are
    connected to Y?", or "Show relationships for Z".
    """
    import time as _time

    from app.dependencies import get_graph_service

    _t0 = _time.perf_counter()
    reset_override_usage()
    try:
        # Adaptive retrieval depth (T3-13)
        from app.dependencies import get_settings

        settings = get_settings()
        overrides = state.get("_retrieval_overrides")
        if resolve_flag("enable_adaptive_retrieval_depth", settings, overrides):
            adaptive_limit = state.get("_adaptive_graph_limit")
            if adaptive_limit:
                limit = adaptive_limit

        gs = get_graph_service()
        filters = state.get("_filters", {})
        matter_id = filters.get("matter_id", "")
        connections = await gs.get_entity_connections(
            entity_name,
            limit=limit,
            exclude_privilege_statuses=state.get("_exclude_privilege") or None,
            matter_id=matter_id,
        )
    except Exception as exc:
        logger.warning("tool.error", tool="graph_query", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})
    _duration = round((_time.perf_counter() - _t0) * 1000, 1)
    result_count = len(connections) if isinstance(connections, list) else 0
    emit_tool_trace(
        name="graph_query",
        label=f"Queried graph for '{entity_name}'",
        duration_ms=_duration,
        args_summary={"entity": entity_name, "limit": limit},
        result_summary={"connections_returned": result_count},
    )
    return json.dumps(connections, default=str)


@tool
async def temporal_search(
    query: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Search documents within a specific date range.

    Use for queries like "Between January and March 2020..." or
    "What happened before the agreement was signed?".
    Provide date_from and/or date_to in YYYY-MM-DD format.

    The date range is applied to each chunk's ``document_date`` payload
    (the real communication date — email Date header, etc.). Chunks
    without a ``document_date`` are excluded.
    """
    from app.dependencies import get_retriever

    try:
        retriever = get_retriever()
        filters: dict[str, Any] = dict(state.get("_filters") or {})
        date_range: dict[str, str] = {}
        if date_from:
            date_range["gte"] = _normalize_date_bound(date_from, end_of_day=False)
        if date_to:
            date_range["lte"] = _normalize_date_bound(date_to, end_of_day=True)

        results = await retriever.retrieve_text(
            query,
            limit=limit,
            filters=filters,
            date_range=date_range or None,
            exclude_privilege_statuses=state.get("_exclude_privilege") or None,
            dataset_doc_ids=state.get("_dataset_doc_ids"),
        )
    except Exception as exc:
        logger.warning("tool.error", tool="temporal_search", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})
    formatted = [
        {
            "id": r.get("id", ""),
            "filename": r.get("source_file", "unknown"),
            "page": r.get("page_number"),
            "text": r.get("chunk_text", "")[:500],
            "score": round(r.get("score", 0), 4),
            "document_date": r.get("document_date"),
        }
        for r in results[:limit]
    ]
    return json.dumps(formatted, default=str)


@tool
async def entity_lookup(
    name: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Look up a specific entity by name, with alias resolution.

    Use for "Who is Defendant A?", "What is the Agreement?", or
    any question about a specific person, organization, or defined term.
    Resolves aliases from the case context term map.
    """
    from app.dependencies import get_graph_service

    try:
        gs = get_graph_service()

        # Try alias resolution from case context term map
        term_map: dict[str, str] = state.get("_term_map", {})
        resolved_name = term_map.get(name.lower(), name)

        filters = state.get("_filters", {})
        matter_id = filters.get("matter_id", "")

        entity = await gs.get_entity_by_name(resolved_name)
        if entity is None and resolved_name != name:
            # Fallback to original name
            entity = await gs.get_entity_by_name(name)

        if entity is None:
            return json.dumps({"error": f"Entity '{name}' not found in knowledge graph."})

        # Also fetch connections
        connections = await gs.get_entity_connections(
            entity["name"],
            limit=10,
            exclude_privilege_statuses=state.get("_exclude_privilege") or None,
            matter_id=matter_id,
        )
        entity["connections"] = connections
    except Exception as exc:
        logger.warning("tool.error", tool="entity_lookup", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})
    return json.dumps(entity, default=str)


@tool
async def document_retrieval(
    document_id: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Retrieve full metadata and content chunks for a specific document.

    Use for "Summarize document X", "What does Exhibit A say?", or when
    you need the full content of a known document.
    """
    from app.dependencies import get_retriever

    try:
        retriever = get_retriever()
        # Search with document_id filter to get all chunks for this doc
        filters: dict[str, Any] = dict(state.get("_filters") or {})
        filters["document_id"] = document_id

        results = await retriever.retrieve_text(
            "",  # Empty query to get all chunks by filter
            limit=50,
            filters=filters,
            exclude_privilege_statuses=state.get("_exclude_privilege") or None,
        )
    except Exception as exc:
        logger.warning("tool.error", tool="document_retrieval", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})
    formatted = [
        {
            "id": r.get("id", ""),
            "filename": r.get("source_file", "unknown"),
            "page": r.get("page_number"),
            "text": r.get("chunk_text", "")[:500],
            "document_date": r.get("document_date"),
        }
        for r in results
    ]
    return json.dumps(formatted, default=str)


@tool
async def case_context(
    aspect: str = "all",
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Retrieve case-level context: claims, parties, defined terms, timeline.

    Use for "What are the claims?", "Who are the parties?", "What are the
    key dates?". Set aspect to 'claims', 'parties', 'terms', 'timeline',
    or 'all' for everything.
    """
    from app.cases.service import CaseService

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        async with _tool_db_session() as db:
            ctx = await CaseService.get_full_context(db, matter_id)
            if ctx is None:
                return json.dumps({"info": "No case context configured for this matter."})

            if aspect == "claims":
                return json.dumps(ctx.get("claims", []), default=str)
            elif aspect == "parties":
                return json.dumps(ctx.get("parties", []), default=str)
            elif aspect == "terms":
                return json.dumps(ctx.get("defined_terms", []), default=str)
            elif aspect == "timeline":
                return json.dumps(ctx.get("timeline", []), default=str)
            else:
                return json.dumps(
                    {
                        "claims": ctx.get("claims", []),
                        "parties": ctx.get("parties", []),
                        "defined_terms": ctx.get("defined_terms", []),
                        "timeline": ctx.get("timeline", []),
                    },
                    default=str,
                )
    except Exception as exc:
        logger.warning("tool.error", tool="case_context", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# M10b: Sentiment & hot doc tools
# ---------------------------------------------------------------------------


@tool
async def sentiment_search(
    query: str,
    min_score: float = 0.5,
    dimension: str = "pressure",
    limit: int = 10,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Search documents by sentiment dimension score.

    Use for "find documents showing pressure", "which emails express concealment",
    or any question about emotional tone in legal documents.
    Available dimensions: positive, negative, pressure, opportunity,
    rationalization, intent, concealment.
    """
    valid_dimensions = {
        "positive",
        "negative",
        "pressure",
        "opportunity",
        "rationalization",
        "intent",
        "concealment",
    }
    if dimension not in valid_dimensions:
        return json.dumps({"error": f"Invalid dimension '{dimension}'. Valid: {sorted(valid_dimensions)}"})

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        async with _tool_db_session() as db:
            from sqlalchemy import text

            col = f"sentiment_{dimension}"
            result = await db.execute(
                text(f"""
                    SELECT id, filename, document_type, {col}, hot_doc_score
                    FROM documents
                    WHERE matter_id = :matter_id AND {col} >= :min_score
                    ORDER BY {col} DESC
                    LIMIT :limit
                """),
                {"matter_id": matter_id, "min_score": min_score, "limit": limit},
            )
            rows = [dict(r._mapping) for r in result.all()]
            return json.dumps(rows, default=str)
    except Exception as exc:
        logger.warning("tool.error", tool="sentiment_search", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


@tool
async def hot_doc_search(
    min_score: float = 0.6,
    limit: int = 10,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Find hot documents ranked by composite risk score.

    Use for "find hot documents", "which documents have the highest risk score",
    or "show me legally significant documents".
    """
    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        async with _tool_db_session() as db:
            from sqlalchemy import text

            result = await db.execute(
                text("""
                    SELECT id, filename, document_type, hot_doc_score,
                           sentiment_pressure, sentiment_concealment, sentiment_intent
                    FROM documents
                    WHERE matter_id = :matter_id AND hot_doc_score >= :min_score
                    ORDER BY hot_doc_score DESC
                    LIMIT :limit
                """),
                {"matter_id": matter_id, "min_score": min_score, "limit": limit},
            )
            rows = [dict(r._mapping) for r in result.all()]
            return json.dumps(rows, default=str)
    except Exception as exc:
        logger.warning("tool.error", tool="hot_doc_search", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


@tool
async def context_gap_search(
    min_gap_score: float = 0.5,
    gap_type: str | None = None,
    limit: int = 10,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Find documents with missing context or incomplete communications.

    Use for "find emails with missing context", "which documents reference
    missing attachments", or "show incomplete communications".
    Optional gap_type filter: missing_attachment, prior_conversation,
    forward_reference, coded_language, unusual_terseness.
    """
    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        async with _tool_db_session() as db:
            from sqlalchemy import text

            params: dict = {"matter_id": matter_id, "min_gap_score": min_gap_score, "limit": limit}
            where = "matter_id = :matter_id AND context_gap_score >= :min_gap_score"
            if gap_type:
                where += " AND context_gaps @> CAST(:gap_filter AS jsonb)"
                params["gap_filter"] = json.dumps([{"gap_type": gap_type}])

            result = await db.execute(
                text(f"""
                    SELECT id, filename, document_type, context_gap_score, context_gaps
                    FROM documents
                    WHERE {where}
                    ORDER BY context_gap_score DESC
                    LIMIT :limit
                """),
                params,
            )
            rows = [dict(r._mapping) for r in result.all()]
            return json.dumps(rows, default=str)
    except Exception as exc:
        logger.warning("tool.error", tool="context_gap_search", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


@tool
async def communication_matrix(
    entity_name: str | None = None,
    person_b: str | None = None,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Analyze communication patterns between entities.

    Returns sender-recipient pairs with message counts. Optionally filter
    to communications involving a specific entity. When both entity_name
    and person_b are provided, also returns graph-level email details
    between the two people.
    """
    from app.analytics.service import AnalyticsService

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        async with _tool_db_session() as db:
            result = await AnalyticsService.get_communication_matrix(
                db,
                matter_id,
                entity_name=entity_name,
            )
            output = result.model_dump()

            # When both persons specified, enrich with graph-level email detail
            if entity_name and person_b:
                from app.dependencies import get_graph_service

                gs = get_graph_service()
                emails = await gs.get_communication_pairs(
                    entity_name,
                    person_b,
                    matter_id=matter_id,
                )
                output["graph_emails"] = emails

            return json.dumps(output, default=str)
    except Exception as exc:
        logger.warning("tool.error", tool="communication_matrix", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


@tool
async def topic_cluster(
    query: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Find topic clusters across the document corpus.

    Retrieves documents matching the query, then clusters them by topic
    using BERTopic. Returns topic labels and representative terms.
    """
    from app.analytics.clustering import TopicClusterer
    from app.dependencies import get_retriever, get_settings

    settings = get_settings()
    if not settings.enable_topic_clustering:
        return json.dumps({"info": "Topic clustering is not enabled. Set ENABLE_TOPIC_CLUSTERING=true."})

    try:
        retriever = get_retriever()
        results = await retriever.retrieve_text(
            query,
            limit=100,
            filters=state.get("_filters"),
            exclude_privilege_statuses=state.get("_exclude_privilege") or None,
        )
        texts = [r.get("chunk_text", "") for r in results if r.get("chunk_text")]

        if not texts:
            return json.dumps({"info": "No documents found for clustering."})

        clusterer = TopicClusterer(
            enabled=True,
            embedding_model=settings.bertopic_embedding_model,
            min_cluster_size=settings.bertopic_min_cluster_size,
        )
        clusters = clusterer.cluster(texts)
        return json.dumps([c.model_dump() for c in clusters], default=str)
    except Exception as exc:
        logger.warning("tool.error", tool="topic_cluster", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


@tool
async def network_analysis(
    metric: str = "degree",
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Analyze network centrality of entities in the knowledge graph.

    Computes centrality using Neo4j GDS. Supported metrics: degree,
    pagerank, betweenness. Returns ranked entities with scores.
    """
    from app.analytics.service import AnalyticsService
    from app.dependencies import get_graph_service, get_settings

    settings = get_settings()
    if not settings.enable_graph_centrality:
        return json.dumps(
            {
                "info": "Graph centrality is not enabled. Set ENABLE_GRAPH_CENTRALITY=true and install the Neo4j GDS plugin."
            }
        )

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        gs = get_graph_service()
        result = await AnalyticsService.get_network_centrality(
            gs,
            matter_id,
            metric,
        )
        return json.dumps(result.model_dump(), default=str)
    except Exception as exc:
        logger.warning("tool.error", tool="network_analysis", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# T1-10: Question decomposition tool
# ---------------------------------------------------------------------------


@tool
async def decompose_query(
    question: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Decompose a complex multi-part question into independent sub-questions.

    Use when the user asks a compound question with multiple distinct aspects
    (e.g., "Who knew about the deal, when did they learn, and what did they do?").
    Each sub-question gets independent retrieval for more comprehensive results.
    """
    from app.dependencies import get_settings

    settings = get_settings()
    overrides = state.get("_retrieval_overrides")
    if not resolve_flag("enable_question_decomposition", settings, overrides):
        return json.dumps({"info": "Question decomposition is not enabled."})

    from app.dependencies import get_llm, get_retriever
    from app.query.decomposer import decompose_question, retrieve_for_sub_questions

    try:
        llm = get_llm()
        result = await decompose_question(question, llm)

        if not result.is_complex or not result.sub_questions:
            return json.dumps(
                {
                    "is_complex": False,
                    "info": "Question is simple enough to answer directly.",
                }
            )

        # Retrieve for each sub-question
        retriever = get_retriever()
        merged = await retrieve_for_sub_questions(
            result.sub_questions,
            retriever,
            filters=state.get("_filters"),
            exclude_privilege=state.get("_exclude_privilege") or None,
            dataset_doc_ids=state.get("_dataset_doc_ids"),
        )

        formatted_sqs = [{"question": sq.question, "aspect": sq.aspect} for sq in result.sub_questions]
        formatted_results = [
            {
                "id": r.get("id", ""),
                "filename": r.get("source_file", "unknown"),
                "page": r.get("page_number"),
                "text": r.get("chunk_text", "")[:500],
                "score": round(r.get("score", 0), 4),
                "document_date": r.get("document_date"),
            }
            for r in merged[:20]
        ]

        return json.dumps(
            {
                "is_complex": True,
                "sub_questions": formatted_sqs,
                "results": formatted_results,
            },
            default=str,
        )

    except Exception as exc:
        logger.warning("tool.error", tool="decompose_query", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# T1-2: Text-to-Cypher tool
# ---------------------------------------------------------------------------


@tool
async def cypher_query(
    question: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Generate and execute a read-only Cypher query against the knowledge graph.

    Use for complex graph traversal questions like "show me the chain of
    communication between X and Y through intermediaries" or "find all
    entities within 3 hops of person Z". Only generates read-only queries.
    """
    from app.dependencies import get_settings

    settings = get_settings()
    overrides = state.get("_retrieval_overrides")
    if not resolve_flag("enable_text_to_cypher", settings, overrides):
        return json.dumps({"info": "Text-to-Cypher generation is not enabled."})

    from app.dependencies import get_graph_service, get_llm
    from app.query.cypher_generator import generate_cypher, validate_cypher_safety

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        llm = get_llm()
        cypher_result = await generate_cypher(question, matter_id, llm)

        # Validate safety before execution
        is_safe, reason = validate_cypher_safety(cypher_result.cypher)
        if not is_safe:
            logger.warning("tool.cypher_query.unsafe", reason=reason, cypher=cypher_result.cypher)
            return json.dumps({"error": f"Generated Cypher failed safety validation: {reason}"})

        # Execute the query
        gs = get_graph_service()
        results = await gs.execute_read_only(
            cypher_result.cypher,
            cypher_result.params,
            matter_id=matter_id,
        )

        logger.info(
            "tool.cypher_query.executed",
            cypher=cypher_result.cypher[:200],
            result_count=len(results),
        )

        return json.dumps(
            {
                "cypher": cypher_result.cypher,
                "explanation": cypher_result.explanation,
                "results": results[:50],
            },
            default=str,
        )

    except Exception as exc:
        logger.warning("tool.error", tool="cypher_query", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# T2-10: Text-to-SQL tool
# ---------------------------------------------------------------------------


@tool
async def structured_query(
    question: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Query the structured database for document metadata, counts, statistics, and date ranges.

    Use ONLY for metadata and aggregate questions like "How many documents were
    ingested?", "What document types are present?", "Show document counts by type",
    "When was the earliest document filed?", or "List documents by date range".

    Do NOT use this tool for questions about document content, what someone said
    or wrote, semantic meaning, or evidence about events. Use vector_search for
    those questions instead.
    """
    from app.dependencies import get_settings

    settings = get_settings()
    overrides = state.get("_retrieval_overrides")
    if not resolve_flag("enable_text_to_sql", settings, overrides):
        return json.dumps({"info": "Text-to-SQL generation is not enabled."})

    from app.dependencies import get_llm
    from app.query.sql_generator import (
        execute_sql,
        generate_sql,
        validate_sql_safety,
    )

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    try:
        llm = get_llm()
        sql_result = await generate_sql(question, matter_id, llm)

        # Validate safety before execution
        is_safe, reason = validate_sql_safety(sql_result.sql)
        if not is_safe:
            logger.warning(
                "tool.structured_query.unsafe",
                reason=reason,
                sql=sql_result.sql,
            )
            return json.dumps({"error": f"Generated SQL failed safety validation: {reason}"})

        # Execute the query
        rows = await execute_sql(sql_result.sql, matter_id)

        logger.info(
            "tool.structured_query.executed",
            sql=sql_result.sql[:200],
            result_count=len(rows),
        )

        return json.dumps(
            {
                "sql": sql_result.sql,
                "explanation": sql_result.explanation,
                "results": rows[:100],
            },
            default=str,
        )

    except Exception as exc:
        logger.warning("tool.error", tool="structured_query", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# T3-10: GraphRAG community context tool
# ---------------------------------------------------------------------------


@tool
async def get_community_context(
    entity_name: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Retrieve community context for an entity from GraphRAG communities.

    Use for understanding which community an entity belongs to, what other
    entities are in the same cluster, and the community summary describing
    relationships and themes.
    """
    from app.dependencies import get_settings

    settings = get_settings()
    if not settings.enable_graphrag_communities:
        return json.dumps({"info": "GraphRAG communities not enabled. Set ENABLE_GRAPHRAG_COMMUNITIES=true."})

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    if not matter_id:
        return json.dumps({"error": "No matter context available."})

    try:
        async with _tool_db_session() as db:
            from sqlalchemy import text

            # Find the community containing this entity (JSONB array search)
            result = await db.execute(
                text("""
                    SELECT id, entity_names, relationship_types,
                           summary, entity_count, level
                    FROM communities
                    WHERE matter_id = :matter_id
                      AND entity_names::jsonb @> :entity_filter::jsonb
                    LIMIT 1
                """),
                {
                    "matter_id": matter_id,
                    "entity_filter": json.dumps([entity_name]),
                },
            )
            row = result.mappings().first()

            if row is None:
                return json.dumps({"error": f"No community found containing entity '{entity_name}'."})

            entity_names = row["entity_names"]
            if isinstance(entity_names, str):
                entity_names = json.loads(entity_names)

            return json.dumps(
                {
                    "community_id": row["id"],
                    "members": entity_names,
                    "relationship_types": row["relationship_types"]
                    if not isinstance(row["relationship_types"], str)
                    else json.loads(row["relationship_types"]),
                    "summary": row["summary"],
                    "entity_count": row["entity_count"],
                    "level": row["level"],
                },
                default=str,
            )
    except Exception as exc:
        logger.warning("tool.error", tool="get_community_context", error=str(exc))
        return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"})


# ---------------------------------------------------------------------------
# Tool lists
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Agent clarification (human-in-the-loop)
# ---------------------------------------------------------------------------


@tool
async def ask_user(
    question: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Ask the user a clarifying question when the investigation hits ambiguity.

    Use this when you encounter: multiple entity matches for a name, unclear
    time ranges, too many results to narrow without guidance, or ambiguous
    references. You may only ask ONE question per investigation.
    """
    from langgraph.types import interrupt

    # Enforce at-most-one: count prior ask_user tool calls in messages.
    prior_asks = sum(
        1
        for m in state.get("messages", [])
        if hasattr(m, "tool_calls")
        for tc in (m.tool_calls or [])
        if tc.get("name") == "ask_user"
    )
    if prior_asks > 1:
        return "You have already asked a clarification question. Work with the information you have."

    answer = interrupt({"question": question})
    return f"User clarification: {answer}"


CLARIFICATION_TOOLS = [ask_user]

INVESTIGATION_TOOLS = [
    vector_search,
    graph_query,
    temporal_search,
    entity_lookup,
    document_retrieval,
    case_context,
    sentiment_search,
    hot_doc_search,
    context_gap_search,
    # Communication analytics (M10c)
    communication_matrix,
    topic_cluster,
    network_analysis,
    # Tier 1 maturity tools
    decompose_query,
    cypher_query,
    # Tier 2 maturity tools
    structured_query,
    # Tier 3 maturity tools
    get_community_context,
]
