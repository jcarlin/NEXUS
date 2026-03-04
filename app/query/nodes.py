"""LangGraph node functions for the investigation query pipeline.

**V1 nodes** (``create_nodes_v1``): Factory that returns the 9-node chain.
**Agentic nodes** (``case_context_resolve``, ``verify_citations``,
``generate_follow_ups_agentic``, ``audit_log_hook``, ``build_system_prompt``):
Standalone async functions used by the agentic parent graph.

Helper functions (``_format_chat_history``, ``_format_context``,
``_format_graph_context``) are module-level exports used by both variants
and the streaming router.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import TYPE_CHECKING, Any

import structlog

from app.query.prompts import (
    CLASSIFY_PROMPT,
    FOLLOWUP_PROMPT,
    INVESTIGATION_SYSTEM_PROMPT,
    REWRITE_PROMPT,
    SYNTHESIS_PROMPT,
    VERIFY_CLAIMS_PROMPT,
    VERIFY_JUDGMENT_PROMPT,
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
# V1 Node factory (preserved for feature-flag fallback)
# ------------------------------------------------------------------


def create_nodes_v1(
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
            node_name="classify",
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
        case_context = state.get("_case_context", "")

        history = _format_chat_history(messages)
        case_context_block = f"{case_context}\n\n" if case_context else ""
        prompt = REWRITE_PROMPT.format(history=history, query=query, case_context=case_context_block)

        rewritten = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
            node_name="rewrite",
        )

        rewritten = rewritten.strip()
        if not rewritten:
            rewritten = query

        logger.debug("node.rewrite", original=query, rewritten=rewritten)
        return {"rewritten_query": rewritten}

    # --- retrieve ---

    async def retrieve(state: dict) -> dict:
        """Run hybrid retrieval (text + graph) in parallel."""
        from app.dependencies import get_settings

        query = state.get("rewritten_query") or state["original_query"]
        filters = state.get("_filters")
        exclude_privilege = state.get("_exclude_privilege", [])

        settings = get_settings()
        text_results, graph_results = await retriever.retrieve_all(
            query,
            text_limit=settings.retrieval_text_limit,
            graph_limit=settings.retrieval_graph_limit,
            filters=filters,
            exclude_privilege_statuses=exclude_privilege or None,
            prefetch_multiplier=settings.retrieval_prefetch_multiplier,
            entity_threshold=settings.query_entity_threshold,
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
        """Rerank text results via cross-encoder (if enabled) or score sort, then visual rerank."""
        from app.dependencies import get_reranker, get_settings

        text_results = state.get("text_results", [])
        settings = get_settings()

        # Try cross-encoder reranking when feature flag is on.
        # Acceptable degradation: reranking is an optional quality
        # improvement; falling back to score-based sorting still
        # returns valid results.
        sorted_results = None
        if settings.enable_reranker:
            try:
                reranker = get_reranker()
                if reranker is not None:
                    query = state.get("rewritten_query") or state.get("original_query", "")
                    result = reranker.rerank(
                        query,
                        text_results,
                        top_n=settings.reranker_top_n,
                    )
                    if inspect.isawaitable(result):
                        sorted_results = await result
                    else:
                        sorted_results = result
                    logger.debug("node.rerank.cross_encoder", count=len(sorted_results))
            except Exception:
                logger.warning("node.rerank.cross_encoder_failed", exc_info=True)

        # Fallback: score-based sorting
        if sorted_results is None:
            sorted_results = sorted(
                text_results,
                key=lambda r: r.get("score", 0),
                reverse=True,
            )[: settings.reranker_top_n]

        # Visual reranking (feature-flagged, experimental).
        # Acceptable degradation: visual reranking is optional enrichment
        # that supplements text-based results.  Failure falls back to
        # text-only ranking which is fully functional.
        visual_results: list[dict[str, Any]] = []
        if settings.enable_visual_embeddings:
            try:
                query = state.get("rewritten_query") or state.get("original_query", "")
                sorted_results = await retriever.rerank_visual(
                    query,
                    sorted_results,
                    weight=settings.visual_rerank_weight,
                    top_n=settings.visual_rerank_top_n,
                    filters=state.get("_filters"),
                )
                visual_results = [r for r in sorted_results if r.get("_visual_reranked")]
                logger.debug("node.rerank.visual", reranked=len(visual_results))
            except Exception:
                logger.warning("node.rerank.visual_failed", exc_info=True)

        # Build fused_context for synthesis
        fused_context = sorted_results

        # Build source_documents for the response
        source_documents: list[dict[str, Any]] = []
        for result in sorted_results:
            source_documents.append(
                {
                    "id": result.get("id", ""),
                    "filename": result.get("source_file", "unknown"),
                    "page": result.get("page_number"),
                    "chunk_text": result.get("chunk_text", ""),
                    "relevance_score": round(result.get("score", 0), 4),
                    "preview_url": None,
                    "download_url": None,
                }
            )

        logger.debug("node.rerank", fused_count=len(fused_context))
        return {
            "fused_context": fused_context,
            "source_documents": source_documents,
            "visual_results": visual_results,
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
            # Acceptable degradation: one entity's graph lookup failing
            # should not prevent returning results for other entities.
            try:
                connections = await graph_service.get_entity_connections(
                    entity_name,
                    limit=10,
                    exclude_privilege_statuses=state.get("_exclude_privilege") or None,
                )
                new_graph.extend(connections)
            except Exception:
                logger.warning(
                    "node.graph_lookup.entity_error",
                    entity=entity_name,
                    exc_info=True,
                )

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
            node_name="reformulate",
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
        """Generate the answer with citations from evidence and graph context."""
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
        except (RuntimeError, LookupError):
            # get_stream_writer() raises when called outside a streaming
            # context (e.g. during non-streaming /query calls).  Acceptable
            # degradation: tokens are still accumulated in full_response.
            writer = lambda x: None  # noqa: E731

        query = state.get("rewritten_query") or state["original_query"]
        fused = state.get("fused_context", [])
        graph_results = state.get("graph_results", [])

        context = _format_context(fused)
        graph_context = _format_graph_context(graph_results)
        case_context = state.get("_case_context", "")
        case_context_block = f"{case_context}\n\n" if case_context else ""

        prompt = SYNTHESIS_PROMPT.format(
            context=context,
            graph_context=graph_context,
            query=query,
            case_context=case_context_block,
        )

        full_response = ""
        async for token in llm.stream(
            [
                {"role": "system", "content": "You are a legal investigation analyst."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.1,
            node_name="synthesize",
        ):
            full_response += token
            writer({"type": "token", "text": token})

        response = full_response.strip()

        # Acceptable degradation: entity extraction on the response is
        # optional enrichment for the UI entity panel.  The core response
        # text and citations are already complete at this point.
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
                    entities_mentioned.append(
                        {
                            "name": ent.text,
                            "type": ent.type,
                            "kg_id": None,
                            "connections": 0,
                        }
                    )
        except Exception:
            logger.warning("node.synthesize.entity_extraction_failed", exc_info=True)

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
            node_name="generate_follow_ups",
        )

        # Parse lines — take first 3 non-empty lines
        lines = [line.strip().lstrip("0123456789.-) ") for line in raw.strip().splitlines() if line.strip()]
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


# Backward-compatible alias
create_nodes = create_nodes_v1


# ------------------------------------------------------------------
# Agentic node functions (M10)
# ------------------------------------------------------------------


def build_system_prompt(state: dict) -> list:
    """Build system prompt with dynamic case context injection.

    Passed as the ``prompt`` parameter to ``create_react_agent``.
    Returns ``[SystemMessage, ...user/assistant messages]`` so LangGraph's
    callable-prompt path receives a proper message list (the string path
    does this conversion automatically, but the callable path does not).
    """
    from langchain_core.messages import SystemMessage

    case_context = state.get("_case_context", "")
    case_context_block = f"\n\n{case_context}" if case_context else ""
    system_text = INVESTIGATION_SYSTEM_PROMPT.format(case_context=case_context_block)
    messages = state.get("messages", [])
    return [SystemMessage(content=system_text)] + messages


async def case_context_resolve(state: dict) -> dict:
    """Load case context for the matter and classify query tier.

    - Loads case context via ``CaseContextResolver``
    - Builds a term map for alias resolution
    - Expands references in the user's query
    - Classifies the query tier (fast / standard / deep)
    """
    from app.dependencies import get_db

    filters = state.get("_filters", {}) or {}
    matter_id = filters.get("matter_id", "")

    case_context_text = ""
    term_map: dict[str, str] = {}

    if matter_id:
        # Acceptable degradation: case context (M9b) is optional enrichment
        # that improves query quality but is not required for retrieval.
        # The module may not exist if the cases feature is not deployed.
        try:
            from app.cases.context_resolver import CaseContextResolver

            db_gen = get_db()
            db = await db_gen.__anext__()
            try:
                ctx = await CaseContextResolver.get_context_for_matter(db, matter_id)
                if ctx:
                    case_context_text = CaseContextResolver.format_context_for_prompt(ctx)
                    term_map = CaseContextResolver.build_term_map(ctx)
            finally:
                try:
                    await db_gen.aclose()
                except GeneratorExit:
                    pass
        except ImportError:
            logger.debug("node.case_context_resolve.skipped", reason="module_not_available")
        except Exception:
            logger.warning("node.case_context_resolve.failed", exc_info=True)

    # Classify tier based on query complexity heuristic
    original_query = state.get("original_query", "")
    tier = _classify_tier(original_query)

    # Determine if verification should be skipped (fast tier)
    from app.dependencies import get_settings

    settings = get_settings()
    skip_verification = tier == "fast" or not settings.enable_citation_verification

    logger.debug(
        "node.case_context_resolve",
        has_context=bool(case_context_text),
        term_count=len(term_map),
        tier=tier,
    )

    return {
        "_case_context": case_context_text,
        "_term_map": term_map,
        "_tier": tier,
        "_skip_verification": skip_verification,
    }


def _classify_tier(query: str) -> str:
    """Lightweight heuristic tier classification.

    - **fast**: Short factual queries (< 15 words, no analytical markers)
    - **deep**: Complex analytical queries (multi-clause, comparison words)
    - **standard**: Everything else
    """
    words = query.split()
    word_count = len(words)
    query_lower = query.lower()

    deep_markers = [
        "compare",
        "contrast",
        "analyze",
        "relationship between",
        "pattern",
        "timeline of",
        "all mentions",
        "summarize all",
        "how does",
        "what is the connection",
        "explain the",
    ]

    if any(marker in query_lower for marker in deep_markers) or word_count > 30:
        return "deep"
    if word_count <= 15 and "?" in query:
        return "fast"
    return "standard"


async def _decompose_claims(
    llm: LLMClient,
    response: str,
    source_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Decompose an LLM response into atomic cited claims.

    Builds evidence text from *source_docs*, asks the LLM to split the
    response into individual factual assertions, and parses the result.

    Returns an empty list when the LLM call fails or yields unparseable
    output (acceptable degradation — citation verification is optional).
    """
    evidence_text = "\n".join(
        f"[{d.get('filename', '?')}, p{d.get('page', '?')}]: {d.get('chunk_text', '')[:300]}" for d in source_docs[:10]
    )

    decompose_prompt = VERIFY_CLAIMS_PROMPT.format(
        response=response[:2000],
        evidence=evidence_text[:3000],
    )

    # Acceptable degradation: citation verification is optional quality
    # enrichment (can be disabled via ENABLE_CITATION_VERIFICATION).
    # If the LLM call fails, we return an empty claims list rather than
    # failing the entire query.
    try:
        claims_raw = await llm.complete(
            [{"role": "user", "content": decompose_prompt}],
            max_tokens=2000,
            temperature=0.0,
            node_name="verify_claims_decompose",
        )
    except Exception:
        logger.warning("node.verify_citations.decompose_failed", exc_info=True)
        return []

    claims = _parse_claims(claims_raw)
    if not claims:
        logger.debug("node.verify_citations.no_claims_parsed")
    return claims


async def _verify_single_claim(
    llm: LLMClient,
    retriever: HybridRetriever,
    claim: dict[str, Any],
    filters: dict[str, Any] | None,
    exclude_privilege: list[str],
) -> dict[str, Any]:
    """Run independent retrieval and judge whether evidence supports *claim*.

    Returns the *claim* dict with ``verification_status`` and ``claim_index``
    added.  On failure, sets status to ``"unverified"`` (acceptable
    degradation — individual claim verification failure should not prevent
    other claims from being verified).
    """
    claim_text = claim.get("claim_text", "")

    try:
        # Independent retrieval for verification
        verification_results = await retriever.retrieve_text(
            claim_text,
            limit=5,
            filters=filters,
            exclude_privilege_statuses=exclude_privilege or None,
        )

        verification_evidence = "\n".join(
            f"[{r.get('source_file', '?')}, p{r.get('page_number', '?')}]: {r.get('chunk_text', '')[:200]}"
            for r in verification_results[:3]
        )

        # Judge claim
        judgment_prompt = VERIFY_JUDGMENT_PROMPT.format(
            claim_text=claim_text,
            filename=claim.get("filename", "unknown"),
            page_number=claim.get("page_number", "?"),
            evidence=verification_evidence or "(no supporting evidence found)",
        )

        judgment_raw = await llm.complete(
            [{"role": "user", "content": judgment_prompt}],
            max_tokens=300,
            temperature=0.0,
            node_name="verify_claims_judge",
        )

        # Parse judgment (simple heuristic)
        supported = "supported" in judgment_raw.lower() or "true" in judgment_raw.lower()[:50]
        claim["verification_status"] = "verified" if supported else "flagged"

    except Exception:
        logger.warning(
            "node.verify_citations.claim_error",
            claim_index=claim.get("claim_index"),
            exc_info=True,
        )
        claim["verification_status"] = "unverified"

    return claim


async def verify_citations(state: dict) -> dict:
    """Decompose the agent's response into cited claims and verify each.

    Uses the Chain-of-Verification (CoVe) pattern:
    1. Decompose response into atomic claims with cited sources
    2. For each claim, run independent retrieval to find verification evidence
    3. Judge whether the evidence supports the claim

    Skipped for fast-tier queries (``_skip_verification=True``).
    """
    if state.get("_skip_verification", False):
        logger.debug("node.verify_citations.skipped", reason="fast_tier")
        return {"cited_claims": []}

    response = state.get("response", "")
    if not response:
        return {"cited_claims": []}

    from app.dependencies import get_llm, get_retriever
    from app.dependencies import get_settings as _get_settings

    llm = get_llm()
    retriever = get_retriever()

    # Stage 1: Decompose response into claims
    source_docs = state.get("source_documents", [])
    claims = await _decompose_claims(llm, response, source_docs)
    if not claims:
        return {"cited_claims": []}

    # Stage 2+3: Verify each claim with independent retrieval
    filters = state.get("_filters")
    exclude_privilege = state.get("_exclude_privilege", [])
    max_claims = _get_settings().max_claims_to_verify

    tasks = []
    for i, claim in enumerate(claims[:max_claims]):
        if not claim.get("claim_text", ""):
            continue
        claim["claim_index"] = i
        tasks.append(_verify_single_claim(llm, retriever, claim, filters, exclude_privilege))

    verified_claims: list[dict[str, Any]] = list(await asyncio.gather(*tasks))

    logger.debug(
        "node.verify_citations",
        total_claims=len(verified_claims),
        verified=sum(1 for c in verified_claims if c.get("verification_status") == "verified"),
        flagged=sum(1 for c in verified_claims if c.get("verification_status") == "flagged"),
    )

    return {"cited_claims": verified_claims}


def _parse_claims(raw: str) -> list[dict[str, Any]]:
    """Best-effort parse claims from LLM output."""
    # Try JSON parsing first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to find JSON array in the response
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    return []


async def generate_follow_ups_agentic(state: dict) -> dict:
    """Generate follow-up questions for the agentic pipeline.

    Extracts the response from the last AI message in state, then uses
    the same prompt pattern as v1.
    """
    from app.dependencies import get_llm

    llm = get_llm()

    # Extract response from the last AI message
    response = state.get("response", "")
    if not response:
        # Fall back to last AI message content
        messages = state.get("messages", [])
        for msg in reversed(messages):
            content = ""
            if hasattr(msg, "content"):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
            elif isinstance(msg, dict):
                content = msg.get("content", "")
            role = getattr(msg, "type", None) or (msg.get("role") if isinstance(msg, dict) else None)
            if role in ("ai", "assistant") and content:
                response = content
                break

    if not response:
        return {"follow_up_questions": []}

    query = state.get("original_query", "")
    entities = state.get("entities_mentioned", [])
    entity_names = ", ".join((e.get("name", "") if isinstance(e, dict) else str(e)) for e in entities[:10])

    prompt = FOLLOWUP_PROMPT.format(
        query=query,
        response=response[:2000],
        entities=entity_names or "none detected",
    )

    # Acceptable degradation: follow-up questions are non-essential UX
    # enrichment.  The core response and citations are already returned.
    try:
        raw = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
            node_name="generate_follow_ups",
        )
    except Exception:
        logger.warning("node.generate_follow_ups_agentic.failed", exc_info=True)
        return {"follow_up_questions": []}

    lines = [line.strip().lstrip("0123456789.-) ") for line in raw.strip().splitlines() if line.strip()]
    follow_ups = [line for line in lines if len(line) > 10][:3]

    logger.debug("node.generate_follow_ups_agentic", count=len(follow_ups))
    return {"follow_up_questions": follow_ups}


async def post_agent_extract(state: dict) -> dict:
    """Extract response, sources, and entities from agent messages.

    The ``create_react_agent`` subgraph only writes to ``messages``.
    This node bridges the gap by populating ``response``,
    ``source_documents``, and ``entities_mentioned`` from the message
    history so that downstream nodes (``verify_citations``,
    ``generate_follow_ups``, SSE sources event) have data to work with.
    """
    from langchain_core.messages import AIMessage, ToolMessage

    from app.query.service import _extract_text_from_content

    messages = state.get("messages", [])

    # 1. Extract response from the last AIMessage
    response = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            response = _extract_text_from_content(msg.content)
            if response:
                break

    # 2. Collect source_documents from ToolMessage results
    source_documents: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue

        # Tool results are either a list of docs or a single dict
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("id", "")
            filename = item.get("filename", "")
            if not doc_id or doc_id in seen_ids:
                continue
            if not filename:
                continue
            seen_ids.add(doc_id)
            source_documents.append(
                {
                    "id": doc_id,
                    "filename": filename,
                    "page": item.get("page"),
                    "chunk_text": item.get("text", ""),
                    "relevance_score": round(item.get("score", 0), 4),
                    "preview_url": None,
                    "download_url": None,
                }
            )

    # 3. Extract entities_mentioned from response text
    entities_mentioned: list[dict[str, Any]] = []
    if response:
        try:
            from app.dependencies import get_entity_extractor

            entity_extractor = get_entity_extractor()
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
                    entities_mentioned.append(
                        {
                            "name": ent.text,
                            "type": ent.type,
                            "kg_id": None,
                            "connections": 0,
                        }
                    )
        except Exception:
            logger.warning("node.post_agent_extract.entity_extraction_failed", exc_info=True)

    logger.debug(
        "node.post_agent_extract",
        response_len=len(response),
        source_count=len(source_documents),
        entity_count=len(entities_mentioned),
    )

    return {
        "response": response,
        "source_documents": source_documents,
        "entities_mentioned": entities_mentioned,
    }


async def audit_log_hook(state: dict) -> dict:
    """Post-model hook for ``create_react_agent``.

    Logs each LLM call to the ``ai_audit_log`` table, preserving the SOC 2
    audit trail even though the agent bypasses ``LLMClient``.
    """
    try:
        from app.dependencies import get_session_factory, get_settings

        settings = get_settings()
        if not settings.enable_ai_audit_logging:
            return {}

        from sqlalchemy import text as sa_text

        ctx = structlog.contextvars.get_contextvars()
        request_id = ctx.get("request_id")

        # Extract token usage from the last AI message
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else None

        input_tokens = None
        output_tokens = None
        if last_msg and hasattr(last_msg, "usage_metadata") and last_msg.usage_metadata:
            usage = last_msg.usage_metadata
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                sa_text("""
                    INSERT INTO ai_audit_log
                        (request_id, call_type, provider, model, node_name,
                         input_tokens, output_tokens, total_tokens,
                         latency_ms, status)
                    VALUES
                        (:request_id, 'agent_step', :provider, :model,
                         'investigation_agent', :input_tokens, :output_tokens,
                         :total_tokens, 0, 'success')
                """),
                {
                    "request_id": request_id,
                    "provider": "anthropic",
                    "model": settings.llm_model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None else None,
                },
            )
            await session.commit()
    except Exception:
        # Acceptable degradation: audit logging must not block user
        # requests or cause the query pipeline to fail.
        logger.warning("audit_log_hook.write_failed", exc_info=True)

    return {}  # Side-effect only — returning state writes to managed channels
