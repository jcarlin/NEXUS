"""GraphRAG community detection and summarization (T3-10).

Detects entity communities via Neo4j GDS Louvain, builds a 2-tier hierarchy,
and generates LLM summaries for each community cluster.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.entities.graph_service import GraphService

logger = structlog.get_logger(__name__)


class CommunityDetector:
    """Static methods for community detection, hierarchy building, and summarization."""

    @staticmethod
    async def detect_communities(
        matter_id: str,
        graph_service: GraphService,
    ) -> list[dict]:
        """Run Louvain community detection on the entity subgraph via Neo4j GDS.

        Steps:
        1. Project the entity subgraph for the matter into GDS
        2. Run Louvain algorithm
        3. Stream results and group entities by community
        4. Drop the projected graph
        """
        driver = graph_service._driver
        graph_name = f"nexus_community_{matter_id.replace('-', '_')}"

        async with driver.session() as session:
            # Drop existing projection if any
            try:
                await session.run(f"CALL gds.graph.drop('{graph_name}', false)")
            except Exception:
                logger.warning("community.graph_drop_failed", graph_name=graph_name, exc_info=True)

            # Project the entity subgraph for this matter
            project_cypher = """
                CALL gds.graph.project.cypher(
                    $graph_name,
                    'MATCH (e:Entity {matter_id: $matter_id}) RETURN id(e) AS id',
                    'MATCH (e1:Entity {matter_id: $matter_id})-[r]->(e2:Entity {matter_id: $matter_id}) RETURN id(e1) AS source, id(e2) AS target, type(r) AS type',
                    {parameters: {matter_id: $matter_id}}
                )
            """
            await session.run(
                project_cypher,
                graph_name=graph_name,
                matter_id=matter_id,
            )

            # Run Louvain
            louvain_cypher = """
                CALL gds.louvain.stream($graph_name)
                YIELD nodeId, communityId
                WITH gds.util.asNode(nodeId) AS node, communityId
                RETURN node.name AS name, node.type AS type, communityId
                ORDER BY communityId
            """
            result = await session.run(louvain_cypher, graph_name=graph_name)
            records = await result.data()

            # Clean up projection
            try:
                await session.run(f"CALL gds.graph.drop('{graph_name}', false)")
            except Exception:
                logger.warning("community.graph_cleanup_failed", graph_name=graph_name, exc_info=True)

        # Group by community
        communities: dict[int, dict] = {}
        for record in records:
            cid = record["communityId"]
            if cid not in communities:
                communities[cid] = {
                    "id": str(uuid.uuid4()),
                    "matter_id": matter_id,
                    "level": 0,
                    "parent_id": None,
                    "entity_names": [],
                    "relationship_types": [],
                    "summary": None,
                    "entity_count": 0,
                }
            communities[cid]["entity_names"].append(record["name"])
            communities[cid]["entity_count"] += 1

        logger.info(
            "communities.detected",
            matter_id=matter_id,
            community_count=len(communities),
        )
        return list(communities.values())

    @staticmethod
    def build_hierarchy(
        communities: list[dict],
        min_size: int = 3,
    ) -> list[dict]:
        """Merge small communities into parent clusters (2 tiers).

        Communities with fewer than ``min_size`` entities are merged into
        a single parent community at level 1.
        """
        large = [c for c in communities if c["entity_count"] >= min_size]
        small = [c for c in communities if c["entity_count"] < min_size]

        # Create parent for small communities
        if small:
            parent_id = str(uuid.uuid4())
            parent = {
                "id": parent_id,
                "matter_id": small[0]["matter_id"] if small else None,
                "level": 1,
                "parent_id": None,
                "entity_names": [],
                "relationship_types": [],
                "summary": None,
                "entity_count": 0,
            }
            for s in small:
                s["parent_id"] = parent_id
                s["level"] = 0
                parent["entity_names"].extend(s["entity_names"])
                parent["entity_count"] += s["entity_count"]
            large.append(parent)

        for c in large:
            if "parent_id" not in c:
                c["parent_id"] = None

        return large + small

    @staticmethod
    async def summarize_community(
        community: dict,
        llm: LLMClient,
        graph_service: GraphService | None = None,
    ) -> str:
        """Generate LLM summary for a community."""
        from app.analytics.community_prompts import COMMUNITY_SUMMARY_PROMPT

        entity_names = ", ".join(community.get("entity_names", [])[:20])
        rel_types = ", ".join(community.get("relationship_types", [])[:10]) or "unknown"

        # Build entity details
        entity_details = "\n".join(f"- {name}" for name in community.get("entity_names", [])[:20])

        prompt = COMMUNITY_SUMMARY_PROMPT.format(
            entity_names=entity_names,
            relationship_types=rel_types,
            entity_details=entity_details,
        )

        summary = await llm.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        return summary.strip()
