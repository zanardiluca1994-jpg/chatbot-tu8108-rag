"""
rag_chain.py – Prompt assembly e chiamata a OpenAI.
Riceve i chunk dal retriever, costruisce il prompt e genera la risposta
con citazione obbligatoria articolo + comma.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Generator

import yaml
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI

load_dotenv()


SYSTEM_PROMPT = """Sei un assistente specializzato nel Testo Unico sulla Sicurezza \
sul Lavoro (D.Lgs. 81/2008). Rispondi ESCLUSIVAMENTE sulla base degli articoli forniti nel contesto.

Regole di risposta:
1. Usa SOLO le informazioni contenute negli articoli del contesto — non aggiungere nulla che non sia esplicitamente scritto nel testo fornito
2. Cita sempre articolo e comma tra parentesi quadre: [art. 17, comma 1, lett. a)]
3. Se più articoli coprono la risposta, sintetizzali citando ciascuno con il relativo riferimento
4. Rispondi in italiano, in modo preciso e conciso — l'utente è un professionista della sicurezza
5. Se nessuno degli articoli forniti è pertinente alla domanda, rispondi esattamente:
   "Non ho trovato questa informazione nel TU 81/08 tra gli articoli disponibili.\""""

FALLBACK_MESSAGE = (
    "Non ho trovato questa informazione nel TU 81/08 tra gli articoli disponibili. "
    "Il sistema copre: obblighi dei soggetti, valutazione dei rischi, DPI, "
    "luoghi di lavoro, agenti fisici/chimici/biologici, cantieri, sanzioni."
)


def _load_config(config_path: str | Path = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_context(chunks: list[dict]) -> str:
    """Costruisce il blocco di contesto da inserire nel prompt."""
    parts = []
    for chunk in chunks:
        meta = chunk["metadata"]
        art = meta.get("articolo", "?")
        header = meta.get("intestazione", f"Art. {art}")
        parts.append(f"--- {header} ---\n{chunk['text']}")
    return "\n\n".join(parts)


def _build_user_message(query: str, context: str) -> str:
    return f"""Contesto normativo (articoli del TU 81/08):

{context}

Domanda: {query}"""


def _log_query(
    query: str,
    chunks: list[dict],
    response: str,
    latency_s: float,
    fallback: bool,
    log_path: str | Path,
) -> None:
    """Salva la query e la risposta in formato JSONL per monitoraggio."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "query": query,
        "articoli_recuperati": [c["metadata"].get("articolo") for c in chunks],
        "n_chunks": len(chunks),
        "fallback": fallback,
        "latency_s": round(latency_s, 3),
        "response_preview": response[:200],
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class RAGChain:
    """
    Pipeline RAG completa: contesto → prompt → OpenAI → risposta.

    Uso:
        chain = RAGChain()
        # Risposta completa
        answer = chain.answer(query, chunks)
        # Streaming
        for token in chain.answer_stream(query, chunks):
            print(token, end="", flush=True)
    """

    def __init__(self, config_path: str | Path = "config/config.yaml"):
        cfg = _load_config(config_path)
        llm_cfg = cfg["llm"]

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            raise ValueError(
                "OPENAI_API_KEY non configurata. "
                "Modifica il file .env con la tua chiave API."
            )

        self.client = OpenAI(api_key=api_key)
        self.model: str = llm_cfg["model"]
        self.temperature: float = llm_cfg["temperature"]
        self.max_tokens: int = llm_cfg["max_tokens"]
        self.log_path: str = cfg["logging"]["queries_path"]

        logger.info(f"RAGChain inizializzata. Modello: {self.model}")

    def rewrite_query(self, query: str) -> str:
        """
        Riscrive la query usando terminologia giuridica del TU 81/08
        per migliorare il match con gli articoli dell'indice.
        """
        system = (
            "Sei un esperto di D.Lgs. 81/2008 (Testo Unico Sicurezza sul Lavoro). "
            "Riscrivi la query dell'utente usando la terminologia giuridica esatta del TU 81/08 "
            "per ottimizzare la ricerca negli articoli del testo. "
            "Espandi concetti generali con i termini tecnici specifici: "
            "datore di lavoro, dirigente, preposto, lavoratore, RSPP, RLS, medico competente, "
            "DVR, DPI, valutazione dei rischi, servizio prevenzione protezione, ecc. "
            "Restituisci SOLO la query riscritta, su una sola riga, senza spiegazioni."
        )
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            max_tokens=80,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
        )
        rewritten = response.choices[0].message.content.strip()
        logger.debug(f"Query rewrite: '{query}' → '{rewritten}'")
        return rewritten

    def answer(self, query: str, chunks: list[dict]) -> str:
        """
        Genera una risposta completa (non streaming).

        Args:
            query: domanda dell'utente
            chunks: lista di chunk dal retriever (lista vuota → fallback)

        Returns:
            Testo della risposta.
        """
        start = time.time()
        fallback = len(chunks) == 0

        if fallback:
            _log_query(query, chunks, FALLBACK_MESSAGE, time.time() - start, True, self.log_path)
            return FALLBACK_MESSAGE

        context = _build_context(chunks)
        user_msg = _build_user_message(query, context)

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )

        text = response.choices[0].message.content
        latency = time.time() - start
        logger.info(f"Risposta generata in {latency:.2f}s")
        _log_query(query, chunks, text, latency, False, self.log_path)

        return text

    def answer_stream(self, query: str, chunks: list[dict]) -> Generator[str, None, None]:
        """
        Genera la risposta in streaming (token per token).
        Usato dall'interfaccia Streamlit.

        Yields:
            Token di testo man mano che vengono generati.
        """
        if len(chunks) == 0:
            yield FALLBACK_MESSAGE
            _log_query(query, [], FALLBACK_MESSAGE, 0.0, True, self.log_path)
            return

        context = _build_context(chunks)
        user_msg = _build_user_message(query, context)
        start = time.time()
        full_response = []

        stream = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_response.append(delta)
                yield delta

        latency = time.time() - start
        logger.info(f"Risposta streaming completata in {latency:.2f}s")
        _log_query(query, chunks, "".join(full_response), latency, False, self.log_path)


if __name__ == "__main__":
    from src.data.indexer import load_index
    from src.models.retriever import HybridRetriever

    index, chunks = load_index()
    retriever = HybridRetriever(index, chunks)
    chain = RAGChain()

    query = "Quali sono gli obblighi non delegabili del datore di lavoro?"
    print(f"Query: {query}\n")

    retrieved = retriever.retrieve(query)
    print(f"Chunk recuperati: {len(retrieved)}\n")

    print("Risposta (streaming):")
    for token in chain.answer_stream(query, retrieved):
        print(token, end="", flush=True)
    print()
