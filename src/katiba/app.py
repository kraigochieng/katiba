# src/katiba/app.py
import json
import textwrap

import streamlit as st
from google import genai
from google.genai import types
from neo4j import GraphDatabase

from katiba.constants import OUTPUT_DIR
from katiba.settings import gemini_settings, neo4j_settings

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Katiba — Constitution of Kenya",
    page_icon="🇰🇪",
    layout="wide",
)

st.title("🇰🇪 Katiba")
st.caption("Ask anything about the Constitution of Kenya 2010")

# ── Schema context for Cypher generation ─────────────────────────────────────

SCHEMA = """
Graph schema for the Constitution of Kenya 2010:

Nodes:
- (:Constitution {name, year, country})
- (:Chapter {chapter_number, chapter_name, has_parts})
- (:Part {part_number, part_name, chapter_number})
- (:Article {article_number, article_title, chapter_number, has_part, part_number})
- (:Clause {clause_number, article_number, text})

Relationships:
- (:Constitution)-[:HAS_CHAPTER]->(:Chapter)
- (:Chapter)-[:HAS_PART]->(:Part)
- (:Chapter)-[:HAS_ARTICLE]->(:Article)  [for chapters without parts]
- (:Part)-[:HAS_ARTICLE]->(:Article)     [for chapters with parts]
- (:Article)-[:HAS_CLAUSE]->(:Clause)
"""

CYPHER_PROMPT = textwrap.dedent("""
    You are a Cypher query generator for a Neo4j graph of the Constitution of Kenya 2010.

    {schema}

    Given the user's question, generate a Cypher query that retrieves the
    most relevant nodes and relationships to answer it.

    Rules:
    - Always RETURN the full path or individual nodes — never just counts
    - Use case-insensitive matching: toLower(n.text) CONTAINS toLower('keyword')
    - For article lookups, match on article_number or article_title
    - For topic searches, search clause text with CONTAINS
    - Limit results to 20 unless the question asks for everything
    - Return ONLY the Cypher query, no explanation, no markdown fences

    Question: {question}
""")

ANSWER_PROMPT = textwrap.dedent("""
    You are a constitutional law assistant for Kenya.
    The user asked: "{question}"

    Here are the relevant sections retrieved from the Constitution of Kenya 2010:
    {results}

    Provide a clear, accurate answer based strictly on the retrieved content.
    Cite specific article numbers and clause numbers where relevant.
    Be concise but complete. If the results don't fully answer the question, say so.
""")


# ── Neo4j connection (cached) ─────────────────────────────────────────────────


@st.cache_resource
def get_neo4j_driver():
    return GraphDatabase.driver(
        f"bolt://localhost:{neo4j_settings.neo4j_bolt_port}",
        auth=(
            neo4j_settings.neo4j_user,
            neo4j_settings.neo4j_password.get_secret_value(),
        ),
    )


# ── Gemini client (cached) ────────────────────────────────────────────────────


@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=gemini_settings.gemini_api_key.get_secret_value())


# ── Generate Cypher from question ─────────────────────────────────────────────


def generate_cypher(client: genai.Client, question: str) -> str:
    response = client.models.generate_content(
        model=gemini_settings.gemini_model,
        contents=CYPHER_PROMPT.format(schema=SCHEMA, question=question),
        config=types.GenerateContentConfig(temperature=0.0),
    )
    cypher = response.text.strip()
    # Strip markdown fences if model added them anyway
    if cypher.startswith("```"):
        cypher = "\n".join(cypher.split("\n")[1:-1])
    return cypher.strip()


# ── Run Cypher on Neo4j ───────────────────────────────────────────────────────


def run_cypher(driver, cypher: str) -> list[dict]:
    with driver.session() as session:
        result = session.run(cypher)
        return [dict(record) for record in result]


# ── Format results for LLM ───────────────────────────────────────────────────


def format_results(records: list[dict]) -> str:
    if not records:
        return "No results found."

    lines = []
    seen_clauses = set()

    for record in records:
        for key, value in record.items():
            # Handle Neo4j Node objects
            if hasattr(value, "labels"):
                labels = list(value.labels)
                props = dict(value)

                if "Clause" in labels:
                    uid = (props.get("article_number"), props.get("clause_number"))
                    if uid not in seen_clauses:
                        seen_clauses.add(uid)
                        lines.append(
                            f"Article {props.get('article_number')} "
                            f"Clause ({props.get('clause_number')}): "
                            f"{props.get('text', '')}"
                        )
                elif "Article" in labels:
                    lines.append(
                        f"Article {props.get('article_number')}: "
                        f"{props.get('article_title', '')}"
                    )
                elif "Chapter" in labels:
                    lines.append(
                        f"Chapter {props.get('chapter_number')}: "
                        f"{props.get('chapter_name', '')}"
                    )
            # Handle Path objects
            elif hasattr(value, "nodes"):
                for node in value.nodes:
                    props = dict(node)
                    labels = list(node.labels)
                    if "Clause" in labels:
                        uid = (props.get("article_number"), props.get("clause_number"))
                        if uid not in seen_clauses:
                            seen_clauses.add(uid)
                            lines.append(
                                f"Article {props.get('article_number')} "
                                f"Clause ({props.get('clause_number')}): "
                                f"{props.get('text', '')}"
                            )

    return "\n\n".join(lines) if lines else str(records[:5])


# ── Generate natural language answer ─────────────────────────────────────────


def generate_answer(client: genai.Client, question: str, results: str) -> str:
    response = client.models.generate_content(
        model=gemini_settings.gemini_model,
        contents=ANSWER_PROMPT.format(question=question, results=results),
        config=types.GenerateContentConfig(temperature=0.2),
    )
    return response.text.strip()


# ── Build traversal path display ──────────────────────────────────────────────


def build_path_display(records: list[dict]) -> str:
    """Build a simple text representation of the traversal path."""
    path_nodes = []
    seen = set()

    for record in records:
        for value in record.values():
            nodes_to_process = []
            if hasattr(value, "nodes"):
                nodes_to_process = list(value.nodes)
            elif hasattr(value, "labels"):
                nodes_to_process = [value]

            for node in nodes_to_process:
                props = dict(node)
                labels = list(node.labels)
                uid = node.id

                if uid in seen:
                    continue
                seen.add(uid)

                if "Constitution" in labels:
                    path_nodes.append(("Constitution", props.get("name", "")))
                elif "Chapter" in labels:
                    path_nodes.append(
                        (
                            "Chapter",
                            f"{props.get('chapter_number')}. {props.get('chapter_name', '')}",
                        )
                    )
                elif "Part" in labels:
                    path_nodes.append(
                        (
                            "Part",
                            f"Part {props.get('part_number')}: {props.get('part_name', '')}",
                        )
                    )
                elif "Article" in labels:
                    path_nodes.append(
                        (
                            "Article",
                            f"Art. {props.get('article_number')}: {props.get('article_title', '')}",
                        )
                    )
                elif "Clause" in labels:
                    path_nodes.append(
                        ("Clause", f"Clause ({props.get('clause_number')})")
                    )

    return path_nodes


# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_path" not in st.session_state:
    st.session_state.last_path = []

if "last_cypher" not in st.session_state:
    st.session_state.last_cypher = ""


# ── Layout ────────────────────────────────────────────────────────────────────

col_chat, col_path = st.columns([2, 1])

with col_chat:
    # Render chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if question := st.chat_input("Ask about the Constitution of Kenya..."):
        # Show user message
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Searching the constitution..."):
                try:
                    driver = get_neo4j_driver()
                    client = get_gemini_client()

                    # Step 1 — generate Cypher
                    cypher = generate_cypher(client, question)
                    st.session_state.last_cypher = cypher

                    # Step 2 — run against Neo4j
                    records = run_cypher(driver, cypher)

                    # Step 3 — build path display
                    st.session_state.last_path = build_path_display(records)

                    # Step 4 — format for LLM
                    formatted = format_results(records)

                    # Step 5 — generate answer
                    answer = generate_answer(client, question, formatted)

                    st.markdown(answer)
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": answer,
                        }
                    )

                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": error_msg,
                        }
                    )

with col_path:
    st.subheader("📍 Traversal Path")

    if st.session_state.last_path:
        # Show path as a visual chain
        colors = {
            "Constitution": "🏛️",
            "Chapter": "📖",
            "Part": "📑",
            "Article": "📄",
            "Clause": "📌",
        }

        for i, (label, text) in enumerate(st.session_state.last_path[:20]):
            icon = colors.get(label, "•")
            if i > 0:
                st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;↓", unsafe_allow_html=True)
            st.markdown(
                f"{icon} **{label}**  \n{text[:80]}{'...' if len(text) > 80 else ''}",
            )

    if st.session_state.last_cypher:
        with st.expander("🔍 Generated Cypher", expanded=False):
            st.code(st.session_state.last_cypher, language="cypher")
