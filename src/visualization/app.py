"""
app.py – Interfaccia Streamlit per il Chatbot TU 81/08.
Avvia con: streamlit run src/visualization/app.py
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

# Aggiunge la root del progetto al path (necessario per Streamlit)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

from src.data.indexer import load_index
from src.models.rag_chain import RAGChain
from src.models.retriever import HybridRetriever


def _load_config(config_path: str | Path = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Inizializzazione (eseguita una volta sola grazie a st.cache_resource) ──────

@st.cache_resource(show_spinner="Caricamento indice e modelli…")
def init_pipeline():
    """Carica indice FAISS, retriever e catena RAG."""
    index, chunks = load_index()
    retriever = HybridRetriever(index, chunks)
    chain = RAGChain()
    return retriever, chain


# ── Layout ─────────────────────────────────────────────────────────────────────

def main():
    cfg = _load_config()
    st.set_page_config(
        page_title=cfg["app"]["title"],
        page_icon=cfg["app"]["page_icon"],
        layout="centered",
    )

    st.title(f"{cfg['app']['page_icon']} {cfg['app']['title']}")
    st.caption(
        "Consulta il D.Lgs. 81/2008 in linguaggio naturale. "
        "Le risposte citano sempre l'articolo e il comma di riferimento."
    )

    # Inizializza pipeline
    try:
        retriever, chain = init_pipeline()
    except FileNotFoundError as e:
        st.error(
            f"**Indice non trovato.**\n\n{e}\n\n"
            "Esegui prima dalla root del progetto:\n"
            "```bash\npython scripts/build_index.py\n```"
        )
        st.stop()
    except ValueError as e:
        st.error(f"**Errore configurazione API:**\n\n{e}")
        st.stop()

    # ── Cronologia messaggi in session state ───────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostra cronologia
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                if msg.get("chunks"):
                    _show_sources(msg["chunks"])
                _show_feedback_buttons(i)

    # ── Input utente ───────────────────────────────────────────────────────────
    if query := st.chat_input("Es: Quali sono gli obblighi non delegabili del datore di lavoro?"):
        # Messaggio utente
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        # Rewriting query + recupero chunk
        with st.spinner("Ricerca articoli rilevanti…"):
            search_query = chain.rewrite_query(query)
            if search_query.lower() != query.lower():
                st.caption(f"🔍 Ricerca con: *{search_query}*")
            chunks = retriever.retrieve(search_query)

        # Risposta in streaming
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""

            for token in chain.answer_stream(query, chunks):
                full_response += token
                response_placeholder.markdown(full_response + "▌")

            response_placeholder.markdown(full_response)

            # Fonti
            if chunks:
                _show_sources(chunks)

        # Salva in cronologia e mostra feedback
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": full_response,
                "chunks": chunks,
                "feedback": None,
            }
        )
        _show_feedback_buttons(len(st.session_state.messages) - 1)

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Informazioni")
        st.markdown(
            "**Documento:** D.Lgs. 81/2008\n\n"
            "**Edizione:** Gennaio 2025\n\n"
            f"**Modello:** `{cfg['llm']['model']}`\n\n"
            f"**Retrieval:** BM25 + Semantica (top-{cfg['retrieval']['top_k']})"
        )

        st.divider()

        # Bottone per cancellare la cronologia
        if st.button("🗑️ Nuova conversazione", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.divider()

        ups = sum(1 for m in st.session_state.messages if m.get("feedback") == "up")
        downs = sum(1 for m in st.session_state.messages if m.get("feedback") == "down")
        if ups + downs > 0:
            st.markdown(f"**Feedback sessione:** 👍 {ups} · 👎 {downs}")
            st.divider()

        st.caption(
            "⚠️ Questo strumento è un ausilio alla consultazione. "
            "Verifica sempre le disposizioni sul testo ufficiale."
        )


def _log_feedback(msg_idx: int, msg: dict, vote: str) -> None:
    """Salva il feedback utente (👍/👎) in outputs/logs/feedback.jsonl."""
    log_path = Path("outputs/logs/feedback.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Recupera la query precedente (il messaggio utente prima di questo assistente)
    messages = st.session_state.messages
    prev_query = ""
    if msg_idx > 0 and messages[msg_idx - 1]["role"] == "user":
        prev_query = messages[msg_idx - 1]["content"]

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vote": vote,
        "query": prev_query,
        "response_preview": msg.get("content", "")[:200],
        "articoli": [c["metadata"].get("articolo") for c in msg.get("chunks", [])],
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _show_feedback_buttons(msg_idx: int) -> None:
    """Mostra pulsanti 👍/👎 e gestisce il voto per il messaggio dato."""
    msg = st.session_state.messages[msg_idx]
    current = msg.get("feedback")

    if current is None:
        cols = st.columns([1, 1, 8])
        if cols[0].button("👍", key=f"up_{msg_idx}", help="Risposta utile"):
            st.session_state.messages[msg_idx]["feedback"] = "up"
            _log_feedback(msg_idx, msg, "up")
            st.rerun()
        if cols[1].button("👎", key=f"down_{msg_idx}", help="Risposta non utile"):
            st.session_state.messages[msg_idx]["feedback"] = "down"
            _log_feedback(msg_idx, msg, "down")
            st.rerun()
    else:
        icon = "👍" if current == "up" else "👎"
        st.caption(f"{icon} Feedback registrato")


def _show_sources(chunks: list[dict]) -> None:
    """Mostra gli articoli recuperati in un expander."""
    if not chunks:
        return

    labels = []
    for c in chunks:
        art = c["metadata"].get("articolo", "?")
        header = c["metadata"].get("intestazione", f"Art. {art}")
        labels.append(header[:60])

    with st.expander(f"📄 Fonti consultate ({len(chunks)} articoli)", expanded=False):
        for i, (chunk, label) in enumerate(zip(chunks, labels), 1):
            st.markdown(f"**{i}. {label}**")
            st.markdown(
                f"<small>{chunk['text'][:300]}…</small>",
                unsafe_allow_html=True,
            )
            if i < len(chunks):
                st.divider()


if __name__ == "__main__":
    main()
