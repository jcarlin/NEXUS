"""LangGraph Case Setup Agent for extracting case intelligence from complaints.

The agent parses the anchor document and runs 4 LLM extraction calls
to populate claims, parties, defined terms, and timeline.  Results
are then written to Neo4j as party nodes linked to claims.

``build_case_setup_graph()`` returns an uncompiled ``StateGraph``.
``create_case_setup_nodes()`` returns a dict of node callables.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

logger = structlog.get_logger(__name__)


def _replace(existing: list, new: list) -> list:
    """Reducer that replaces a list field wholesale."""
    return new


class CaseSetupState(TypedDict, total=False):
    """State schema for the Case Setup Agent graph."""

    matter_id: str
    anchor_document_id: str
    case_context_id: str
    minio_path: str
    document_text: str
    claims: Annotated[list[dict[str, Any]], _replace]
    parties: Annotated[list[dict[str, Any]], _replace]
    defined_terms: Annotated[list[dict[str, Any]], _replace]
    timeline: Annotated[list[dict[str, Any]], _replace]
    error: str | None


def create_case_setup_nodes(llm_settings: dict[str, Any]) -> dict[str, Any]:
    """Return a dict of node callables for the Case Setup Agent.

    Parameters
    ----------
    llm_settings:
        Dict with keys: ``api_key``, ``model``, ``provider``,
        ``minio_endpoint``, ``minio_access_key``, ``minio_secret_key``,
        ``minio_bucket``, ``minio_use_ssl``,
        ``neo4j_uri``, ``neo4j_user``, ``neo4j_password``.
    """

    def _get_instructor_client():
        """Create an Instructor-patched LLM client."""
        import instructor

        provider = llm_settings.get("provider", "anthropic")
        if provider == "anthropic":
            import anthropic

            return instructor.from_anthropic(anthropic.Anthropic(api_key=llm_settings["api_key"]))
        else:
            import openai

            return instructor.from_openai(openai.OpenAI(api_key=llm_settings["api_key"]))

    def _extract_with_instructor(prompt: str, response_model: type):
        """Run a single Instructor extraction call."""
        client = _get_instructor_client()
        provider = llm_settings.get("provider", "anthropic")
        model = llm_settings.get("model", "claude-sonnet-4-5-20250929")

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_model": response_model,
        }
        if provider == "anthropic":
            kwargs["max_tokens"] = 4096

        return client.chat.completions.create(**kwargs)

    # --- Node: parse_anchor_doc ---

    def parse_anchor_doc(state: dict) -> dict:
        """Download from MinIO and parse the anchor document."""
        from app.ingestion.parser import DocumentParser

        minio_path = state["minio_path"]

        # Download from MinIO using sync boto3
        import boto3
        from botocore.config import Config as BotoConfig

        scheme = "https" if llm_settings.get("minio_use_ssl", False) else "http"
        endpoint_url = f"{scheme}://{llm_settings['minio_endpoint']}"

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=llm_settings["minio_access_key"],
            aws_secret_access_key=llm_settings["minio_secret_key"],
            config=BotoConfig(signature_version="s3v4"),
            region_name="us-east-1",
        )

        resp = s3.get_object(
            Bucket=llm_settings.get("minio_bucket", "documents"),
            Key=minio_path,
        )
        file_bytes = resp["Body"].read()

        # Parse with DocumentParser
        filename = minio_path.rsplit("/", 1)[-1]
        suffix = Path(filename).suffix

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            parser = DocumentParser()
            parse_result = parser.parse(tmp_path, filename)
        finally:
            tmp_path.unlink(missing_ok=True)

        document_text = parse_result.text
        logger.info(
            "case_setup.parsed",
            text_length=len(document_text),
            pages=parse_result.page_count,
        )

        return {"document_text": document_text}

    # --- Node: extract_claims ---

    def extract_claims(state: dict) -> dict:
        """Extract claims from the complaint using Instructor."""
        from app.cases.prompts import EXTRACT_CLAIMS_PROMPT
        from app.cases.schemas import ExtractedClaimList

        document_text = state.get("document_text", "")
        if not document_text.strip():
            return {"claims": []}

        prompt = EXTRACT_CLAIMS_PROMPT.format(document_text=document_text)
        result = _extract_with_instructor(prompt, ExtractedClaimList)

        claims = [c.model_dump() for c in result.claims]
        logger.info("case_setup.claims_extracted", count=len(claims))
        return {"claims": claims}

    # --- Node: extract_parties ---

    def extract_parties(state: dict) -> dict:
        """Extract parties from the complaint using Instructor."""
        from app.cases.prompts import EXTRACT_PARTIES_PROMPT
        from app.cases.schemas import ExtractedPartyList

        document_text = state.get("document_text", "")
        if not document_text.strip():
            return {"parties": []}

        prompt = EXTRACT_PARTIES_PROMPT.format(document_text=document_text)
        result = _extract_with_instructor(prompt, ExtractedPartyList)

        parties = [p.model_dump() for p in result.parties]
        logger.info("case_setup.parties_extracted", count=len(parties))
        return {"parties": parties}

    # --- Node: extract_defined_terms ---

    def extract_defined_terms(state: dict) -> dict:
        """Extract defined terms from the complaint using Instructor."""
        from app.cases.prompts import EXTRACT_DEFINED_TERMS_PROMPT
        from app.cases.schemas import ExtractedDefinedTermList

        document_text = state.get("document_text", "")
        if not document_text.strip():
            return {"defined_terms": []}

        prompt = EXTRACT_DEFINED_TERMS_PROMPT.format(document_text=document_text)
        result = _extract_with_instructor(prompt, ExtractedDefinedTermList)

        terms = [t.model_dump() for t in result.terms]
        logger.info("case_setup.terms_extracted", count=len(terms))
        return {"defined_terms": terms}

    # --- Node: build_timeline ---

    def build_timeline(state: dict) -> dict:
        """Extract a timeline of events from the complaint."""
        from app.cases.prompts import EXTRACT_TIMELINE_PROMPT
        from app.cases.schemas import ExtractedTimeline

        document_text = state.get("document_text", "")
        if not document_text.strip():
            return {"timeline": []}

        prompt = EXTRACT_TIMELINE_PROMPT.format(document_text=document_text)
        result = _extract_with_instructor(prompt, ExtractedTimeline)

        events = [e.model_dump() for e in result.events]
        logger.info("case_setup.timeline_built", count=len(events))
        return {"timeline": events}

    # --- Node: populate_graph ---

    def populate_graph(state: dict) -> dict:
        """Create Neo4j nodes for parties and link them to claims."""
        import asyncio

        async def _populate():
            from neo4j import AsyncGraphDatabase

            driver = AsyncGraphDatabase.driver(
                llm_settings["neo4j_uri"],
                auth=(llm_settings["neo4j_user"], llm_settings["neo4j_password"]),
            )

            try:
                matter_id = state.get("matter_id", "")
                parties = state.get("parties", [])
                claims = state.get("claims", [])

                async with driver.session() as session:
                    # Create party nodes
                    for party in parties:
                        await session.run(
                            """
                            MERGE (e:Entity {name: $name, matter_id: $matter_id})
                            ON CREATE SET
                                e.type = 'person',
                                e.case_party = true,
                                e.party_role = $role,
                                e.description = $description,
                                e.aliases = $aliases
                            ON MATCH SET
                                e.case_party = true,
                                e.party_role = $role,
                                e.description = $description,
                                e.aliases = $aliases
                            """,
                            {
                                "name": party["name"],
                                "matter_id": matter_id,
                                "role": party.get("role", "unknown"),
                                "description": party.get("description", ""),
                                "aliases": party.get("aliases", []),
                            },
                        )

                    # Link parties to claims via INVOLVED_IN relationship
                    for claim in claims:
                        claim_label = claim.get("claim_label", "")
                        # Create claim node
                        await session.run(
                            """
                            MERGE (c:Claim {claim_number: $claim_number, matter_id: $matter_id})
                            ON CREATE SET
                                c.label = $claim_label,
                                c.text = $claim_text
                            """,
                            {
                                "claim_number": claim["claim_number"],
                                "matter_id": matter_id,
                                "claim_label": claim_label,
                                "claim_text": claim.get("claim_text", ""),
                            },
                        )

                logger.info(
                    "case_setup.graph_populated",
                    parties=len(parties),
                    claims=len(claims),
                )
            finally:
                await driver.close()

        asyncio.run(_populate())
        return {}

    return {
        "parse_anchor_doc": parse_anchor_doc,
        "extract_claims": extract_claims,
        "extract_parties": extract_parties,
        "extract_defined_terms": extract_defined_terms,
        "build_timeline": build_timeline,
        "populate_graph": populate_graph,
    }


def build_case_setup_graph(llm_settings: dict[str, Any] | None = None) -> StateGraph:
    """Construct and return the (uncompiled) Case Setup Agent ``StateGraph``.

    Parameters
    ----------
    llm_settings:
        Settings dict passed to ``create_case_setup_nodes()``.
        If None, a minimal default is used (for compile-only testing).
    """
    if llm_settings is None:
        llm_settings = {}

    nodes = create_case_setup_nodes(llm_settings)

    graph = StateGraph(CaseSetupState)

    graph.add_node("parse_anchor_doc", nodes["parse_anchor_doc"])
    graph.add_node("extract_claims", nodes["extract_claims"])
    graph.add_node("extract_parties", nodes["extract_parties"])
    graph.add_node("extract_defined_terms", nodes["extract_defined_terms"])
    graph.add_node("build_timeline", nodes["build_timeline"])
    graph.add_node("populate_graph", nodes["populate_graph"])

    # Linear chain
    graph.add_edge(START, "parse_anchor_doc")
    graph.add_edge("parse_anchor_doc", "extract_claims")
    graph.add_edge("extract_claims", "extract_parties")
    graph.add_edge("extract_parties", "extract_defined_terms")
    graph.add_edge("extract_defined_terms", "build_timeline")
    graph.add_edge("build_timeline", "populate_graph")
    graph.add_edge("populate_graph", END)

    return graph
