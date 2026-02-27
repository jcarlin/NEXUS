"""NEXUS — Streamlit Dashboard.

Three-page app for investigating legal documents:
  1. Chat — multi-turn investigation queries
  2. Documents — browse and search ingested documents
  3. Entities — explore extracted entities and connections

Launch with:
    NEXUS_API_URL=http://localhost:8000 streamlit run frontend/app.py
"""

from __future__ import annotations

import os

import requests
import streamlit as st

API_URL = os.environ.get("NEXUS_API_URL", "http://localhost:8000")
API_BASE = f"{API_URL}/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict | None = None) -> dict | list | None:
    """GET request to the NEXUS API.  Returns parsed JSON or None on error."""
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        st.error(f"API error: {exc}")
        return None


def api_post(path: str, json: dict | None = None) -> dict | None:
    """POST request to the NEXUS API.  Returns parsed JSON or None on error."""
    try:
        resp = requests.post(f"{API_BASE}{path}", json=json, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        st.error(f"API error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Page 1: Chat
# ---------------------------------------------------------------------------

def chat_page() -> None:
    """Multi-turn investigation chat interface."""
    st.header("Investigation Chat")

    # --- Sidebar: thread management ---
    with st.sidebar:
        st.subheader("Chat Threads")

        if st.button("New Thread"):
            st.session_state.pop("thread_id", None)
            st.session_state.pop("messages", None)
            st.rerun()

        threads = api_get("/chats")
        if threads and isinstance(threads, dict) and threads.get("items"):
            for thread in threads["items"]:
                tid = thread.get("thread_id", thread.get("id", ""))
                label = f"Thread {str(tid)[:8]}..."
                if st.button(label, key=f"thread_{tid}"):
                    st.session_state["thread_id"] = str(tid)
                    # Load history
                    history = api_get(f"/chats/{tid}")
                    if history and isinstance(history, dict):
                        msgs = history.get("messages", [])
                        st.session_state["messages"] = [
                            {"role": m["role"], "content": m["content"]}
                            for m in msgs
                        ]
                    st.rerun()

    # --- Main area: conversation display ---
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- Chat input ---
    if prompt := st.chat_input("Ask a question about the documents..."):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Query the API
        payload = {"query": prompt}
        if "thread_id" in st.session_state:
            payload["thread_id"] = st.session_state["thread_id"]

        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                result = api_post("/query", json=payload)

            if result:
                response_text = result.get("response", "No response received.")
                st.markdown(response_text)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": response_text}
                )

                # Store thread_id for continuity
                if "thread_id" in result:
                    st.session_state["thread_id"] = result["thread_id"]

                # Source documents
                sources = result.get("source_documents", [])
                if sources:
                    with st.expander(f"Sources ({len(sources)})"):
                        for src in sources:
                            fname = src.get("filename", "unknown")
                            page = src.get("page", "?")
                            score = src.get("relevance_score", 0)
                            st.markdown(
                                f"- **{fname}** (p. {page}) — score: {score:.2f}"
                            )

                # Follow-up questions
                follow_ups = result.get("follow_up_questions", [])
                if follow_ups:
                    st.markdown("**Suggested follow-ups:**")
                    for fq in follow_ups:
                        if st.button(fq, key=f"fq_{hash(fq)}"):
                            st.session_state["messages"].append(
                                {"role": "user", "content": fq}
                            )
                            st.rerun()


# ---------------------------------------------------------------------------
# Page 2: Documents
# ---------------------------------------------------------------------------

def documents_page() -> None:
    """Browse and search ingested documents."""
    st.header("Document Browser")

    # --- Filters ---
    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("Search by filename", key="doc_search")
    with col2:
        doc_type = st.selectbox(
            "Document type",
            options=["All", "deposition", "flight_log", "correspondence",
                     "financial", "legal_filing", "email", "report", "image", "other"],
            key="doc_type_filter",
        )

    params: dict = {}
    if search_query:
        params["q"] = search_query
    if doc_type != "All":
        params["document_type"] = doc_type

    # --- Fetch documents ---
    data = api_get("/documents", params=params)
    if data is None:
        return

    items = data.get("items", [])
    total = data.get("total", 0)

    st.caption(f"Showing {len(items)} of {total} documents")

    if not items:
        st.info("No documents found.")
        return

    # --- Table display ---
    table_data = []
    for doc in items:
        table_data.append({
            "Filename": doc.get("filename", ""),
            "Type": doc.get("type", "—"),
            "Pages": doc.get("page_count", 0),
            "Chunks": doc.get("chunk_count", 0),
            "Entities": doc.get("entity_count", 0),
            "Created": doc.get("created_at", "")[:19],
        })
    st.dataframe(table_data, use_container_width=True)

    # --- Detail view ---
    st.subheader("Document Details")
    doc_options = {doc["filename"]: doc["id"] for doc in items}
    selected = st.selectbox("Select a document", options=list(doc_options.keys()))

    if selected:
        doc_id = doc_options[selected]
        detail = api_get(f"/documents/{doc_id}")
        if detail:
            c1, c2, c3 = st.columns(3)
            c1.metric("Pages", detail.get("page_count", 0))
            c2.metric("Chunks", detail.get("chunk_count", 0))
            c3.metric("Entities", detail.get("entity_count", 0))

            if detail.get("file_size_bytes"):
                size_mb = detail["file_size_bytes"] / (1024 * 1024)
                st.caption(f"File size: {size_mb:.2f} MB")

            if detail.get("content_hash"):
                st.caption(f"Hash: {detail['content_hash']}")

            # Download button
            dl = api_get(f"/documents/{doc_id}/download")
            if dl and "download_url" in dl:
                st.link_button("Download original", dl["download_url"])


# ---------------------------------------------------------------------------
# Page 3: Entities
# ---------------------------------------------------------------------------

def entities_page() -> None:
    """Explore extracted entities and their connections."""
    st.header("Entity Explorer")

    # --- Sidebar: graph stats ---
    with st.sidebar:
        st.subheader("Graph Statistics")
        stats = api_get("/graph/stats")
        if stats:
            st.metric("Total Nodes", stats.get("total_nodes", 0))
            st.metric("Total Edges", stats.get("total_edges", 0))

            node_counts = stats.get("node_counts", {})
            if node_counts:
                st.markdown("**Node types:**")
                for ntype, count in node_counts.items():
                    st.caption(f"  {ntype}: {count}")

    # --- Search ---
    search = st.text_input("Search entities", key="entity_search")
    params: dict = {}
    if search:
        params["q"] = search

    data = api_get("/entities", params=params)
    if data is None:
        return

    items = data.get("items", [])
    total = data.get("total", 0)

    st.caption(f"Found {total} entities")

    if not items:
        st.info("No entities found.")
        return

    # --- Entity cards ---
    cols = st.columns(3)
    for i, entity in enumerate(items):
        with cols[i % 3]:
            name = entity.get("name", "Unknown")
            etype = entity.get("type", "—")
            mentions = entity.get("mention_count", entity.get("mentions", 0))
            st.markdown(f"**{name}**")
            st.caption(f"Type: {etype} | Mentions: {mentions}")

            if st.button("Connections", key=f"conn_{name}_{i}"):
                st.session_state["selected_entity"] = name

    # --- Connection details ---
    if "selected_entity" in st.session_state:
        entity_name = st.session_state["selected_entity"]
        st.subheader(f"Connections for: {entity_name}")

        conn_data = api_get(f"/entities/{entity_name}/connections")
        if conn_data:
            connections = conn_data.get("connections", [])
            if connections:
                for conn in connections:
                    target = conn.get("target", conn.get("name", "?"))
                    rel = conn.get("relationship", conn.get("type", "—"))
                    st.markdown(f"- **{target}** ({rel})")
            else:
                st.info("No connections found.")


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------

pg = st.navigation([
    st.Page(chat_page, title="Chat", icon=":material/chat:"),
    st.Page(documents_page, title="Documents", icon=":material/description:"),
    st.Page(entities_page, title="Entities", icon=":material/hub:"),
])

st.set_page_config(page_title="NEXUS", page_icon=":material/search:", layout="wide")
pg.run()
