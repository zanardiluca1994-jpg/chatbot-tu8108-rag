"""
retriever.py – Hybrid search per il TU 81/08.
Combina BM25 (match esatto) e ricerca semantica (FAISS) con RRF fusion.
"""

from pathlib import Path

import numpy as np
import yaml
from loguru import logger
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

import faiss
from src.data.loader import Chunk


# Sinonimi dei principali acronimi del TU 81/08
SYNONYMS_TU81: dict[str, list[str]] = {
    "DVR":   ["documento valutazione rischi", "valutazione dei rischi"],
    "DUVRI": ["documento unico valutazione rischi interferenziali"],
    "DPI":   ["dispositivi protezione individuale", "dispositivo di protezione"],
    "RSPP":  ["responsabile servizio prevenzione protezione"],
    "ASPP":  ["addetto servizio prevenzione protezione"],
    "RLS":   ["rappresentante lavoratori sicurezza"],
    "MC":    ["medico competente"],
    "SPP":   ["servizio prevenzione protezione"],
    "PS":    ["pronto soccorso"],
    "MOG":   ["modello organizzazione gestione"],
}


def _load_config(config_path: str | Path = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _expand_query(query: str) -> str:
    """Espande gli acronimi del TU 81/08 nella query per migliorare il BM25."""
    expanded = query
    for acronym, expansions in SYNONYMS_TU81.items():
        if acronym in query.upper():
            expanded += " " + " ".join(expansions)
    return expanded


def _tokenize(text: str) -> list[str]:
    """Tokenizzazione semplice lowercase per BM25."""
    return text.lower().split()


def _rrf_fusion(
    bm25_ranking: list[int],
    semantic_ranking: list[int],
    bm25_weight: float,
    semantic_weight: float,
    k: int = 60,
) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion.
    Restituisce lista di (chunk_idx, score) ordinata per score decrescente.
    """
    scores: dict[int, float] = {}

    for rank, idx in enumerate(bm25_ranking):
        scores[idx] = scores.get(idx, 0.0) + bm25_weight * (1.0 / (k + rank + 1))

    for rank, idx in enumerate(semantic_ranking):
        scores[idx] = scores.get(idx, 0.0) + semantic_weight * (1.0 / (k + rank + 1))

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    """
    Retriever ibrido BM25 + semantica con RRF fusion.

    Uso:
        retriever = HybridRetriever(index, chunks)
        results = retriever.retrieve("obblighi del datore di lavoro DVR")
    """

    def __init__(
        self,
        index: faiss.Index,
        chunks: list[Chunk],
        config_path: str | Path = "config/config.yaml",
    ):
        cfg = _load_config(config_path)

        self.chunks = chunks
        self.index = index
        self.top_k: int = cfg["retrieval"]["top_k"]
        self.bm25_weight: float = cfg["retrieval"]["bm25_weight"]
        self.semantic_weight: float = cfg["retrieval"]["semantic_weight"]
        self.min_similarity: float = cfg["retrieval"]["min_similarity"]

        # Modello embedding (deve essere lo stesso usato per costruire l'indice)
        model_name = cfg["embedding"]["model"]
        device = cfg["embedding"]["device"]
        logger.info(f"Caricamento modello embedding per retrieval: {model_name}")
        self.model = SentenceTransformer(model_name, device=device)

        # BM25 — tokenizza tutti i chunk al momento della costruzione
        logger.info("Costruzione indice BM25…")
        tokenized = [_tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)

        # Cross-encoder re-ranker (secondo stage)
        reranker_cfg = cfg.get("reranker", {})
        self.use_reranker: bool = reranker_cfg.get("enabled", False)
        self.reranker_candidates: int = reranker_cfg.get("top_k_candidates", 15)
        if self.use_reranker:
            reranker_model = reranker_cfg["model"]
            logger.info(f"Caricamento cross-encoder: {reranker_model}")
            self.reranker = CrossEncoder(reranker_model, device=device)
            logger.info("Cross-encoder pronto")

        logger.info(f"HybridRetriever pronto. Chunk totali: {len(chunks)}")

    def retrieve(self, query: str) -> list[dict]:
        """
        Recupera i top-k chunk più rilevanti per la query.

        Returns:
            Lista di dict con chiavi: text, metadata, score, rank.
            Lista vuota se nessun chunk supera min_similarity.
        """
        expanded_query = _expand_query(query)

        # --- BM25 ---
        bm25_scores = self.bm25.get_scores(_tokenize(expanded_query))
        bm25_ranking = np.argsort(bm25_scores)[::-1].tolist()

        # --- Semantica ---
        query_vec = self.model.encode(
            [query], normalize_embeddings=True
        ).astype(np.float32)
        n_candidates = min(len(self.chunks), self.top_k * 10)
        distances, indices = self.index.search(query_vec, n_candidates)
        semantic_scores = distances[0]           # inner product = cosine con vettori normalizzati
        semantic_ranking = indices[0].tolist()

        # Verifica soglia: se il miglior score semantico è sotto la soglia, fallback
        if len(semantic_scores) > 0 and float(semantic_scores[0]) < self.min_similarity:
            logger.info(
                f"Similarity massima {semantic_scores[0]:.3f} < {self.min_similarity} "
                "→ fallback attivato"
            )
            return []

        # --- RRF Fusion ---
        fused = _rrf_fusion(
            bm25_ranking,
            semantic_ranking,
            self.bm25_weight,
            self.semantic_weight,
        )

        # Primo stage: prendi più candidati se il re-ranker è attivo
        n_first_stage = self.reranker_candidates if self.use_reranker else self.top_k
        first_stage = fused[:n_first_stage]

        # --- Cross-encoder re-ranking (secondo stage) ---
        if self.use_reranker and first_stage:
            pairs = [(query, self.chunks[idx].text) for idx, _ in first_stage]
            ce_scores = self.reranker.predict(pairs)
            # Ri-ordina per score cross-encoder
            reranked = sorted(
                zip(first_stage, ce_scores.tolist()),
                key=lambda x: x[1],
                reverse=True,
            )
            results = []
            for rank, ((idx, rrf_score), ce_score) in enumerate(reranked[: self.top_k]):
                chunk = self.chunks[idx]
                results.append(
                    {
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                        "score": round(float(ce_score), 4),
                        "rrf_score": round(rrf_score, 6),
                        "rank": rank + 1,
                    }
                )
        else:
            results = []
            for rank, (idx, score) in enumerate(first_stage[: self.top_k]):
                chunk = self.chunks[idx]
                results.append(
                    {
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                        "score": round(score, 6),
                        "rank": rank + 1,
                    }
                )

        logger.debug(
            f"Query: '{query[:60]}' → {len(results)} chunk recuperati "
            f"(top score: {results[0]['score'] if results else 'n/a'})"
        )
        return results


if __name__ == "__main__":
    from src.data.indexer import load_index

    index, chunks = load_index()
    retriever = HybridRetriever(index, chunks)

    test_queries = [
        "Quali sono gli obblighi non delegabili del datore di lavoro?",
        "Sanzioni per mancata redazione del DVR",
        "Definizione di lavoratore ai sensi del TU 81/08",
        "Come si nomina il RSPP?",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        results = retriever.retrieve(q)
        if not results:
            print("→ FALLBACK: nessun chunk sopra la soglia di similarità")
        for r in results:
            print(f"  [{r['rank']}] Art. {r['metadata'].get('articolo','?')} "
                  f"| score={r['score']} | {r['text'][:100]}…")
