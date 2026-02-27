"""LangGraph node functions for the investigation query pipeline.

``create_nodes()`` is a factory that accepts shared clients (LLM, retriever,
graph service, entity extractor) and returns a dict of async node functions.
Each node takes an ``InvestigationState`` and returns a partial state update.

Helper functions (``_format_chat_history``, ``_format_context``,
``_format_graph_context``) are module-level exports used by both the graph
nodes *and* the streaming router (which calls nodes directly).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

from app.query.prompts import (
    CLASSIFY_PROMPT,
    FOLLOWUP_PROMPT,
    REWRITE_PROMPT,
    SYNTHESIS_PROMPT,
)

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.entities.extractor import EntityExtractor
    from app.entities.graph_service import GraphService
    from app.query.retriever import HybridRetriever

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Formatting helpers (exported for use by streaming router)
# ------------------------------------------------------------------


def _format_chat_history(messages: list[dict[str, Any]]) -> str:
    """Format last 6 messages as ``User: ... / Assistant: ...`` pairs."""
    recent = messages[-6:] if len(messages) > 6 else messages
    lines: list[str] = []
    for msg in recent:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior conversation)"


def _format_context(fused: list[dict[str, Any]]) -> str:
    """Format fused retrieval results as numbered evidence blocks."""
    blocks: list[str] = []
    for i, doc in enumerate(fused, 1):
        filename = doc.get("source_file", "unknown")
        page = doc.get("page_number", "?")
        text = doc.get("chunk_text", "")
        blocks.append(f"[{i}] Source: {filename}, Page {page}\n{text}")
    return "\n\n".join(blocks) if blocks else "(no evidence retrieved)"


def _format_graph_context(graph_results: list[dict[str, Any]]) -> str:
    """Format graph connections as a bullet list."""
    lines: list[str] = []
    for conn in graph_results:
        source = conn.get("source", "?")
        rel = conn.get("relationship_type", "?")
        target = conn.get("target", "?")
        lines.append(f"- {source} --[{rel}]--> {target}")
    return "\n".join(lines) if lines else "(no graph connections found)"


# ------------------------------------------------------------------
# Node factory
# ------------------------------------------------------------------


def create_nodes(
    llm: LLMClient,
    retriever: HybridRetriever,
    graph_service: GraphService,
    entity_extractor: EntityExtractor,
) -> dict[str, Any]:
    """Return a dict of async node functions keyed by node name.

    Each node is an async callable ``(state: InvestigationState) -> dict``
    returning a partial state update.
    """

    # --- classify ---

    async def classify(state: dict) -> dict:
        """Classify query type: factual / analytical / exploratory / timeline."""
        query = state["original_query"]
        prompt = CLASSIFY_PROMPT.format(query=query)

        raw = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.0,
        )

        # Extract just the category word
        category = raw.strip().lower().split()[0] if raw.strip() else "factual"
        valid = {"factual", "analytical", "exploratory", "timeline"}
        if category not in valid:
            category = "factual"

        logger.debug("node.classify", query_type=category)
        return {"query_type": category}

    # --- rewrite ---

    async def rewrite(state: dict) -> dict:
        """Rewrite the query for retrieval — resolve pronouns and expand context."""
        query = state["original_query"]
        messages = state.get("messages", [])

        history = _format_chat_history(messages)
        prompt = REWRITE_PROMPT.format(history=history, query=query)

        rewritten = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
        )

        rewritten = rewritten.strip()
        if not rewritten:
            rewritten = query

        logger.debug("node.rewrite", original=query, rewritten=rewritten)
        return {"rewritten_query": rewritten}

    # --- retrieve ---

    async def retrieve(state: dict) -> dict:
        """Run hybrid retrieval (text + graph) in parallel."""
        query = state.get("rewritten_query") or state["original_query"]
        filters = state.get("_filters")
        exclude_privilege = state.get("_exclude_privilege", [])

        text_results, graph_results = await retriever.retrieve_all(
            query,
            text_limit=20,
            graph_limit=20,
            filters=filters,
            exclude_privilege_statuses=exclude_privilege or None,
        )

        logger.debug(
            "node.retrieve",
            text_count=len(text_results),
            graph_count=len(graph_results),
        )
        return {
            "text_results": text_results,
            "graph_results": graph_results,
        }

    # --- rerank ---

    async def rerank(state: dict) -> dict:
        """Rerank text results via cross-encoder (if enabled) or score sort."""
        from app.config import Settings
        from app.dependencies import get_reranker, get_settings

        text_results = state.get("text_results", [])
        settings = get_settings()

        # Try cross-encoder reranking when feature flag is on
        sorted_results = None
        if settings.enable_reranker:
            try:
                reranker = get_reranker()
                if reranker is not None:
                    query = state.get("rewritten_query") or state.get("original_query", "")
                    sorted_results = reranker.rerank(
                        query,
                        text_results,
                        top_n=settings.reranker_top_n,
                    )
                    logger.debug("node.rerank.cross_encoder", count=len(sorted_results))
            except Exception:
                logger.warning("node.rerank.cross_encoder_failed", exc_info=True)

        # Fallback: score-based sorting
        if sorted_results is None:
            sorted_results = sorted(
                text_results,
                key=lambda r: r.get("score", 0),
                reverse=True,
            )[:settings.reranker_top_n]

        # Build fused_context for synthesis
        fused_context = sorted_results

        # Build source_documents for the response
        source_documents: list[dict[str, Any]] = []
        for result in sorted_results:
            source_documents.append({
                "id": result.get("id", ""),
                "filename": result.get("source_file", "unknown"),
                "page": result.get("page_number"),
                "chunk_text": result.get("chunk_text", ""),
                "relevance_score": round(result.get("score", 0), 4),
                "preview_url": None,
                "download_url": None,
            })

        logger.debug("node.rerank", fused_count=len(fused_context))
        return {
            "fused_context": fused_context,
            "source_documents": source_documents,
        }

    # --- check_relevance ---

    async def check_relevance(state: dict) -> dict:
        """Check if retrieved results are relevant (avg score > threshold)."""
        fused = state.get("fused_context", [])

        if not fused:
            logger.debug("node.check_relevance", result="not_relevant", reason="no_results")
            return {"_relevance": "not_relevant"}

        # Average score of top 5
        top_scores = [r.get("score", 0) for r in fused[:5]]
        avg_score = sum(top_scores) / len(top_scores) if top_scores else 0

        relevance = "relevant" if avg_score >= 0.3 else "not_relevant"
        logger.debug("node.check_relevance", avg_score=round(avg_score, 4), result=relevance)
        return {"_relevance": relevance}

    # --- graph_lookup ---

    async def graph_lookup(state: dict) -> dict:
        """Enrich graph context by extracting entities from top chunks."""
        fused = state.get("fused_context", [])
        existing_graph = state.get("graph_results", [])

        # Extract entities from top 5 chunks
        all_entities: set[str] = set()
        for chunk in fused[:5]:
            text = chunk.get("chunk_text", "")
            if text:
                entities = entity_extractor.extract(
                    text,
                    entity_types=["person", "organization", "location", "vehicle"],
                    threshold=0.5,
                )
                for ent in entities:
                    all_entities.add(ent.text)

        # Fetch connections for newly discovered entities
        new_graph: list[dict[str, Any]] = list(existing_graph)
        existing_sources = {conn.get("source", "") for conn in existing_graph}

        for entity_name in all_entities:
            if entity_name in existing_sources:
                continue
            try:
                connections = await graph_service.get_entity_connections(
                    entity_name, limit=10
                )
                new_graph.extend(connections)
            except Exception:
                logger.warning("node.graph_lookup.entity_error", entity=entity_name)

        logger.debug(
            "node.graph_lookup",
            chunk_entities=len(all_entities),
            total_connections=len(new_graph),
        )
        return {"graph_results": new_graph}

    # --- reformulate ---

    async def reformulate(state: dict) -> dict:
        """Try a different query angle when initial retrieval is irrelevant."""
        query = state.get("rewritten_query") or state["original_query"]

        prompt = (
            "The following search query did not return relevant results. "
            "Reformulate it using different keywords, broader terms, or an "
            "alternative angle. Keep the same intent.\n\n"
            f"Original query: {query}\n\nReformulated query:"
        )

        reformulated = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )

        reformulated = reformulated.strip()
        if not reformulated:
            reformulated = query

        logger.debug("node.reformulate", original=query, reformulated=reformulated)
        return {
            "rewritten_query": reformulated,
            "_reformulated": True,
        }

    # --- synthesize ---

    async def synthesize(state: dict) -> dict:
        """Generate the answer with citations from evidence and graph context.

        Uses ``get_stream_writer()`` to emit tokens on the custom channel
        when invoked via ``graph.astream()``.  When called via ``graph.ainvoke()``
        the writer is a no-op, so this node works for both paths.
        """
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except RuntimeError:
            # Outside of a runnable context (e.g., direct call in tests)
            writer = lambda x: None  # noqa: E731

        query = state.get("rewritten_query") or state["original_query"]
        fused = state.get("fused_context", [])
        graph_results = state.get("graph_results", [])

        context = _format_context(fused)
        graph_context = _format_graph_context(graph_results)

        prompt = SYNTHESIS_PROMPT.format(
            context=context,
            graph_context=graph_context,
            query=query,
        )

        full_response = ""
        async for token in llm.stream(
            [
                {"role": "system", "content": "You are a legal investigation analyst."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.1,
        ):
            full_response += token
            writer({"type": "token", "text": token})

        response = full_response.strip()

        # Extract entities from the response for linking
        entities_mentioned: list[dict[str, Any]] = []
        try:
            raw_entities = entity_extractor.extract(
                response,
                entity_types=["person", "organization", "location", "vehicle"],
                threshold=0.4,
            )
            seen_names: set[str] = set()
            for ent in raw_entities:
                name_lower = ent.text.lower()
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    entities_mentioned.append({
                        "name": ent.text,
                        "type": ent.type,
                        "kg_id": None,
                        "connections": 0,
                    })
        except Exception:
            logger.warning("node.synthesize.entity_extraction_failed")

        logger.debug(
            "node.synthesize",
            response_len=len(response),
            entities=len(entities_mentioned),
        )
        return {
            "response": response,
            "entities_mentioned": entities_mentioned,
        }

    # --- generate_follow_ups ---

    async def generate_follow_ups(state: dict) -> dict:
        """Generate 3 follow-up investigation questions."""
        query = state.get("original_query", "")
        response = state.get("response", "")
        entities = state.get("entities_mentioned", [])

        entity_names = ", ".join(e.get("name", "") for e in entities[:10])

        prompt = FOLLOWUP_PROMPT.format(
            query=query,
            response=response,
            entities=entity_names or "none detected",
        )

        raw = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )

        # Parse lines — take first 3 non-empty lines
        lines = [
            line.strip().lstrip("0123456789.-) ")
            for line in raw.strip().splitlines()
            if line.strip()
        ]
        follow_ups = [line for line in lines if len(line) > 10][:3]

        logger.debug("node.generate_follow_ups", count=len(follow_ups))
        return {"follow_up_questions": follow_ups}

    return {
        "classify": classify,
        "rewrite": rewrite,
        "retrieve": retrieve,
        "rerank": rerank,
        "check_relevance": check_relevance,
        "graph_lookup": graph_lookup,
        "reformulate": reformulate,
        "synthesize": synthesize,
        "generate_follow_ups": generate_follow_ups,
    }
