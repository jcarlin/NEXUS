"""LangGraph Entity Resolution Agent — deterministic post-ingestion pipeline.

Runs entity deduplication, coreference resolution, merge execution,
org-hierarchy inference, and defined-term linking as a linear StateGraph.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from app.entities.resolver import RESOLVABLE_TYPES

logger = structlog.get_logger(__name__)


def _replace(existing: list, new: list) -> list:
    """Reducer that replaces a list field wholesale."""
    return new


# Confident thresholds: auto-merge without review
CONFIDENT_FUZZY_THRESHOLD = 90
CONFIDENT_COSINE_THRESHOLD = 0.95


class ResolutionState(TypedDict, total=False):
    """State schema for the Entity Resolution Agent."""

    # Input
    matter_id: str
    entity_type: str | None

    # Pipeline data
    entities: Annotated[list[dict[str, Any]], _replace]
    fuzzy_matches: Annotated[list[dict[str, Any]], _replace]
    embedding_matches: Annotated[list[dict[str, Any]], _replace]
    all_matches: Annotated[list[dict[str, Any]], _replace]
    merge_groups: Annotated[list[dict[str, Any]], _replace]

    # Output
    uncertain_merges: Annotated[list[dict[str, Any]], _replace]
    merges_performed: int
    hierarchy_edges_created: int
    linked_terms: int
    entity_types_processed: Annotated[list[str], _replace]


def create_resolution_nodes(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a dict of node callables for the resolution pipeline.

    Parameters
    ----------
    settings:
        Dict with keys ``neo4j_uri``, ``neo4j_user``, ``neo4j_password``,
        and optionally ``enable_coreference_resolution``, ``postgres_url``.
    """

    def _get_driver():
        from neo4j import AsyncGraphDatabase

        return AsyncGraphDatabase.driver(
            settings["neo4j_uri"],
            auth=(settings["neo4j_user"], settings["neo4j_password"]),
        )

    # --- Node: extract ---

    async def extract(state: dict) -> dict:
        """Fetch entities from Neo4j grouped by type."""
        from app.entities.graph_service import GraphService

        driver = _get_driver()
        try:
            gs = GraphService(driver)
            entity_type = state.get("entity_type")

            if entity_type:
                types_to_process = [entity_type]
            else:
                records = await gs._run_query("MATCH (e:Entity) RETURN DISTINCT e.type AS type")
                types_to_process = [r["type"] for r in records if r.get("type") and r["type"] in RESOLVABLE_TYPES]

            all_entities: list[dict[str, Any]] = []
            for etype in types_to_process:
                entities = await gs.get_all_entities_by_type(etype)
                all_entities.extend(entities)

            logger.info(
                "resolution.extract.complete",
                types=len(types_to_process),
                entities=len(all_entities),
            )
            return {
                "entities": all_entities,
                "entity_types_processed": types_to_process,
            }
        finally:
            await driver.close()

    # --- Node: deduplicate ---

    async def deduplicate(state: dict) -> dict:
        """Run fuzzy + embedding matching, split confident vs uncertain."""
        from app.entities.resolver import EntityResolver

        entities = state.get("entities", [])
        if len(entities) < 2:
            return {
                "fuzzy_matches": [],
                "embedding_matches": [],
                "all_matches": [],
                "uncertain_merges": [],
            }

        resolver = EntityResolver()
        fuzzy_matches = resolver.find_fuzzy_matches(entities)

        # Split into confident vs uncertain
        confident = []
        uncertain = []
        for m in fuzzy_matches:
            match_dict = {
                "name_a": m.name_a,
                "name_b": m.name_b,
                "entity_type": m.entity_type,
                "score": m.score,
                "method": m.method,
            }
            if m.score >= CONFIDENT_FUZZY_THRESHOLD:
                confident.append(match_dict)
            else:
                uncertain.append(match_dict)

        logger.info(
            "resolution.deduplicate.complete",
            fuzzy_total=len(fuzzy_matches),
            confident=len(confident),
            uncertain=len(uncertain),
        )
        return {
            "fuzzy_matches": [
                {
                    "name_a": m.name_a,
                    "name_b": m.name_b,
                    "entity_type": m.entity_type,
                    "score": m.score,
                    "method": m.method,
                }
                for m in fuzzy_matches
            ],
            "embedding_matches": [],
            "all_matches": confident,
            "uncertain_merges": uncertain,
        }

    # --- Node: resolve_coreferences ---

    async def resolve_coreferences(state: dict) -> dict:
        """Run coreference resolution (feature-flagged, no-op if disabled)."""
        if not settings.get("enable_coreference_resolution", False):
            logger.info("resolution.coreference.skipped", reason="feature_disabled")
            return {}

        # Coreference resolution operates on document text, not on entity names.
        # In the resolution pipeline context it's a no-op placeholder for future
        # integration where resolved text feeds back into entity extraction.
        logger.info("resolution.coreference.complete")
        return {}

    # --- Node: llm_resolve ---

    async def llm_resolve(state: dict) -> dict:
        """Use LLM to resolve entities that fuzzy matching can't handle.

        Feature-flagged via ``enable_llm_entity_resolution``.  Uses Instructor +
        the analysis-tier LLM (Gemini Flash) for structured merge decisions.
        Handles OCR corruption, partial→full name matching, and abbreviations.
        """
        # Check DB override first (admin UI toggle), fall back to settings dict
        llm_er_enabled = settings.get("enable_llm_entity_resolution", False)
        postgres_url = settings.get("postgres_url")
        if not llm_er_enabled and postgres_url:
            from sqlalchemy import text as sa_text
            from sqlalchemy.ext.asyncio import create_async_engine as _create_engine

            _eng = _create_engine(postgres_url)
            try:
                from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

                async with _AsyncSession(_eng) as _db:
                    row = (
                        await _db.execute(
                            sa_text(
                                "SELECT enabled FROM feature_flag_overrides "
                                "WHERE flag_name = 'enable_llm_entity_resolution'"
                            )
                        )
                    ).first()
                    if row:
                        llm_er_enabled = row[0]
            finally:
                await _eng.dispose()

        if not llm_er_enabled:
            logger.info("resolution.llm_resolve.skipped", reason="feature_disabled")
            return {}

        # Collect entities not yet in a confident match group
        all_matches = state.get("all_matches", [])
        entities = state.get("entities", [])

        if not entities:
            return {}

        # Build set of already-matched entity names
        matched_names: set[str] = set()
        for m in all_matches:
            matched_names.add(m["name_a"])
            matched_names.add(m["name_b"])

        # Group unmatched entities by type
        unmatched_by_type: dict[str, list[dict]] = {}
        for ent in entities:
            if ent["name"] not in matched_names and ent.get("type") in RESOLVABLE_TYPES:
                unmatched_by_type.setdefault(ent["type"], []).append(ent)

        if not unmatched_by_type:
            logger.info("resolution.llm_resolve.skipped", reason="no_unmatched_entities")
            return {}

        # Get LLM client via tier resolver (analysis tier = cheapest)
        from app.entities.prompts import ENTITY_RESOLUTION_PROMPT

        postgres_url = settings.get("postgres_url")
        if not postgres_url:
            logger.warning("resolution.llm_resolve.skipped", reason="no_postgres_url")
            return {}

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from app.llm_config.resolver import resolve_llm_config

        engine = create_async_engine(postgres_url)
        try:
            async with AsyncSession(engine) as db:
                llm_config = await resolve_llm_config("analysis", db)
        finally:
            await engine.dispose()

        # Build Instructor client from the resolved LLM config
        import instructor
        from pydantic import BaseModel, Field

        class EntityMergeGroup(BaseModel):
            canonical: str = Field(description="Best canonical form of the name")
            aliases: list[str] = Field(description="Other names referring to the same entity")
            confidence: float = Field(ge=0, le=1)

        class EntityMergeResponse(BaseModel):
            groups: list[EntityMergeGroup] = Field(default_factory=list)

        if llm_config.provider == "gemini":
            import google.genai

            client = instructor.from_genai(
                google.genai.Client(api_key=llm_config.api_key),
                mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
            )
        elif llm_config.provider == "anthropic":
            import anthropic

            client = instructor.from_anthropic(anthropic.Anthropic(api_key=llm_config.api_key))
        else:
            import openai

            client = instructor.from_openai(
                openai.OpenAI(api_key=llm_config.api_key, base_url=llm_config.base_url or None)
            )

        new_matches: list[dict] = []
        batch_size = 50

        for entity_type, type_entities in unmatched_by_type.items():
            # Sort by mention count descending so the LLM sees the most important first
            sorted_ents = sorted(type_entities, key=lambda e: e.get("mention_count", 0), reverse=True)

            # Process in batches
            for i in range(0, len(sorted_ents), batch_size):
                batch = sorted_ents[i : i + batch_size]
                name_list = "\n".join(f"- {ent['name']} (mentions: {ent.get('mention_count', 1)})" for ent in batch)

                prompt = ENTITY_RESOLUTION_PROMPT.format(
                    entity_type=entity_type,
                    name_list=name_list,
                )

                try:
                    result = client.chat.completions.create(
                        model=llm_config.model,
                        messages=[{"role": "user", "content": prompt}],
                        response_model=EntityMergeResponse,
                        max_retries=2,
                    )

                    for group in result.groups:
                        if group.confidence < 0.8 or len(group.aliases) == 0:
                            continue
                        # Create pairwise matches from the group
                        for alias in group.aliases:
                            new_matches.append(
                                {
                                    "name_a": group.canonical,
                                    "name_b": alias,
                                    "entity_type": entity_type,
                                    "score": group.confidence * 100,  # normalize to 0-100 scale
                                    "method": "llm",
                                }
                            )

                except Exception:
                    logger.error(
                        "resolution.llm_resolve.batch_failed",
                        entity_type=entity_type,
                        batch_start=i,
                        batch_size=len(batch),
                    )

        # Merge new LLM matches into the confident matches
        existing = state.get("all_matches", [])
        logger.info(
            "resolution.llm_resolve.complete",
            new_matches=len(new_matches),
            types_processed=list(unmatched_by_type.keys()),
        )
        return {"all_matches": existing + new_matches}

    # --- Node: merge ---

    async def merge(state: dict) -> dict:
        """Compute merge groups from confident matches and execute merges."""
        from app.entities.graph_service import GraphService
        from app.entities.resolver import EntityMatch, EntityResolver

        all_matches = state.get("all_matches", [])
        if not all_matches:
            return {"merge_groups": [], "merges_performed": 0}

        resolver = EntityResolver()
        match_objects = [
            EntityMatch(
                name_a=m["name_a"],
                name_b=m["name_b"],
                entity_type=m["entity_type"],
                score=m["score"],
                method=m["method"],
            )
            for m in all_matches
        ]
        groups = resolver.compute_merge_groups(match_objects)

        driver = _get_driver()
        try:
            gs = GraphService(driver)
            total_merges = 0

            for group in groups:
                for alias in group.aliases:
                    try:
                        await gs.merge_entities(group.canonical, alias, group.entity_type, matter_id=state["matter_id"])
                        total_merges += 1
                        logger.info(
                            "resolution.merged",
                            canonical=group.canonical,
                            alias=alias,
                        )
                    except Exception:
                        logger.error(
                            "resolution.merge_failed",
                            canonical=group.canonical,
                            alias=alias,
                        )

            logger.info(
                "resolution.merge.complete",
                groups=len(groups),
                merges=total_merges,
            )
            return {
                "merge_groups": [
                    {
                        "canonical": g.canonical,
                        "aliases": g.aliases,
                        "entity_type": g.entity_type,
                    }
                    for g in groups
                ],
                "merges_performed": total_merges,
            }
        finally:
            await driver.close()

    # --- Node: infer_hierarchy ---

    async def infer_hierarchy(state: dict) -> dict:
        """Infer REPORTS_TO from email communication patterns."""
        from app.entities.graph_service import GraphService

        matter_id = state.get("matter_id", "")
        if not matter_id:
            return {"hierarchy_edges_created": 0}

        postgres_url = settings.get("postgres_url")
        if not postgres_url:
            logger.info("resolution.hierarchy.skipped", reason="no_postgres_url")
            return {"hierarchy_edges_created": 0}

        from sqlalchemy.ext.asyncio import create_async_engine

        from app.analytics.service import AnalyticsService

        engine = create_async_engine(postgres_url)
        try:
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(engine) as db:
                entries = await AnalyticsService.infer_org_hierarchy(db, matter_id)

            if not entries:
                return {"hierarchy_edges_created": 0}

            driver = _get_driver()
            try:
                gs = GraphService(driver)
                created = 0
                for entry in entries:
                    try:
                        await gs.create_temporal_relationship(
                            source_name=entry.person_name,
                            target_name=entry.reports_to_name,
                            rel_type="REPORTS_TO",
                            matter_id=matter_id,
                        )
                        created += 1
                    except Exception:
                        logger.error(
                            "resolution.hierarchy_edge_failed",
                            person=entry.person_name,
                            reports_to=entry.reports_to_name,
                        )

                logger.info(
                    "resolution.hierarchy.complete",
                    edges_created=created,
                )
                return {"hierarchy_edges_created": created}
            finally:
                await driver.close()
        finally:
            await engine.dispose()

    # --- Node: link_defined_terms ---

    async def link_defined_terms(state: dict) -> dict:
        """Bridge M9b case defined terms to graph entities via ALIAS_OF edges."""
        from app.entities.graph_service import GraphService

        matter_id = state.get("matter_id", "")
        if not matter_id:
            return {"linked_terms": 0}

        postgres_url = settings.get("postgres_url")
        if not postgres_url:
            logger.info("resolution.link_terms.skipped", reason="no_postgres_url")
            return {"linked_terms": 0}

        from sqlalchemy.ext.asyncio import create_async_engine

        from app.cases.service import CaseService

        engine = create_async_engine(postgres_url)
        try:
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(engine) as db:
                ctx = await CaseService.get_full_context(db, matter_id)

            if ctx is None:
                return {"linked_terms": 0}

            defined_terms = ctx.get("defined_terms", [])
            if not defined_terms:
                return {"linked_terms": 0}

            driver = _get_driver()
            try:
                gs = GraphService(driver)
                linked = 0
                for term in defined_terms:
                    term_name = term.get("term") or term.get("name", "")
                    canonical = term.get("canonical_name") or term.get("definition", "")
                    if not term_name or not canonical:
                        continue

                    try:
                        await gs.create_alias_edge(
                            term=term_name,
                            canonical_name=canonical,
                            entity_type="person",
                            matter_id=matter_id,
                        )
                        linked += 1
                    except Exception:
                        logger.error(
                            "resolution.link_term_failed",
                            term=term_name,
                            canonical=canonical,
                        )

                logger.info("resolution.link_terms.complete", linked=linked)
                return {"linked_terms": linked}
            finally:
                await driver.close()
        finally:
            await engine.dispose()

    # --- Node: present_uncertain ---

    async def present_uncertain(state: dict) -> dict:
        """Persist uncertain merges for lawyer review."""
        from app.entities.graph_service import GraphService

        uncertain = state.get("uncertain_merges", [])
        if not uncertain:
            return {}

        driver = _get_driver()
        try:
            gs = GraphService(driver)
            # Group by entity name
            by_entity: dict[str, list[dict]] = {}
            for m in uncertain:
                by_entity.setdefault(m["name_a"], []).append(m)
                by_entity.setdefault(m["name_b"], []).append(m)

            for entity_name, candidates in by_entity.items():
                # Determine entity type from first candidate
                entity_type = candidates[0].get("entity_type", "person")
                try:
                    await gs.mark_pending_merge(
                        entity_name=entity_name,
                        entity_type=entity_type,
                        merge_candidates=candidates,
                        matter_id=state.get("matter_id"),
                    )
                except Exception:
                    logger.error(
                        "resolution.present_uncertain_failed",
                        entity=entity_name,
                    )

            logger.info(
                "resolution.present_uncertain.complete",
                flagged_entities=len(by_entity),
            )
        finally:
            await driver.close()

        return {}

    # Wrap all nodes with agent audit logging
    from app.common.agent_logging import log_agent_node

    postgres_url = settings.get("postgres_url")

    return {
        "extract": log_agent_node("entity_resolution", "extract", postgres_url=postgres_url)(extract),
        "deduplicate": log_agent_node("entity_resolution", "deduplicate", postgres_url=postgres_url)(deduplicate),
        "resolve_coreferences": log_agent_node("entity_resolution", "resolve_coreferences", postgres_url=postgres_url)(
            resolve_coreferences
        ),
        "llm_resolve": log_agent_node("entity_resolution", "llm_resolve", postgres_url=postgres_url)(llm_resolve),
        "merge": log_agent_node("entity_resolution", "merge", postgres_url=postgres_url)(merge),
        "infer_hierarchy": log_agent_node("entity_resolution", "infer_hierarchy", postgres_url=postgres_url)(
            infer_hierarchy
        ),
        "link_defined_terms": log_agent_node("entity_resolution", "link_defined_terms", postgres_url=postgres_url)(
            link_defined_terms
        ),
        "present_uncertain": log_agent_node("entity_resolution", "present_uncertain", postgres_url=postgres_url)(
            present_uncertain
        ),
    }


def build_resolution_graph(
    settings: dict[str, Any] | None = None,
) -> StateGraph:
    """Construct the (uncompiled) Entity Resolution ``StateGraph``.

    Parameters
    ----------
    settings:
        Settings dict passed to ``create_resolution_nodes()``.
        If None, a minimal default is used (for compile-only testing).
    """
    if settings is None:
        settings = {}

    nodes = create_resolution_nodes(settings)

    graph = StateGraph(ResolutionState)

    graph.add_node("extract", nodes["extract"])
    graph.add_node("deduplicate", nodes["deduplicate"])
    graph.add_node("resolve_coreferences", nodes["resolve_coreferences"])
    graph.add_node("llm_resolve", nodes["llm_resolve"])
    graph.add_node("merge", nodes["merge"])
    graph.add_node("infer_hierarchy", nodes["infer_hierarchy"])
    graph.add_node("link_defined_terms", nodes["link_defined_terms"])
    graph.add_node("present_uncertain", nodes["present_uncertain"])

    # Linear chain
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "deduplicate")
    graph.add_edge("deduplicate", "resolve_coreferences")
    graph.add_edge("resolve_coreferences", "llm_resolve")
    graph.add_edge("llm_resolve", "merge")
    graph.add_edge("merge", "infer_hierarchy")
    graph.add_edge("infer_hierarchy", "link_defined_terms")
    graph.add_edge("link_defined_terms", "present_uncertain")
    graph.add_edge("present_uncertain", END)

    return graph


async def run_resolution_agent(
    matter_id: str,
    entity_type: str | None = None,
) -> dict:
    """Entry point: run the full entity resolution pipeline.

    Parameters
    ----------
    matter_id:
        The matter to resolve entities for.
    entity_type:
        Optional — resolve only this entity type.

    Returns
    -------
    Dict with ``merges_performed``, ``hierarchy_edges_created``,
    ``linked_terms``, ``uncertain_merges``, ``entity_types_processed``.
    """
    from app.config import Settings

    app_settings = Settings()

    settings = {
        "neo4j_uri": app_settings.neo4j_uri,
        "neo4j_user": app_settings.neo4j_user,
        "neo4j_password": app_settings.neo4j_password,
        "enable_coreference_resolution": app_settings.enable_coreference_resolution,
        "enable_llm_entity_resolution": app_settings.enable_llm_entity_resolution,
        "postgres_url": app_settings.postgres_url,
    }

    graph = build_resolution_graph(settings)
    compiled = graph.compile()

    initial_state: dict[str, Any] = {
        "matter_id": matter_id,
        "entity_type": entity_type,
    }

    result = await compiled.ainvoke(initial_state)

    summary = {
        "merges_performed": result.get("merges_performed", 0),
        "hierarchy_edges_created": result.get("hierarchy_edges_created", 0),
        "linked_terms": result.get("linked_terms", 0),
        "uncertain_merges": len(result.get("uncertain_merges", [])),
        "entity_types_processed": len(result.get("entity_types_processed", [])),
    }

    logger.info("resolution_agent.complete", **summary)
    return summary
