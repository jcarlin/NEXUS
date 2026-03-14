"""Prompt templates for community summarization (T3-10)."""

COMMUNITY_SUMMARY_PROMPT = """You are analyzing a community of entities from a legal document corpus.

Community members: {entity_names}
Relationship types between members: {relationship_types}
Entity details:
{entity_details}

Write a concise 2-3 sentence summary describing:
1. Who the key entities are and their roles
2. How they are connected (relationship patterns)
3. What this community likely represents in the legal context

Summary:"""
