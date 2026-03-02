"""
indexer.py – Embedding e costruzione indice FAISS per il TU 81/08.
Carica i chunk da loader.py, genera gli embedding con sentence-transformers
e persiste l'indice FAISS + i metadati su disco.
"""

import json
import pickle
from pathlib import Path

import faiss
import numpy as np
import yaml
from loguru import logger
from sentence_transformers import SentenceTransformer

from src.data.loader import Chunk, load_and_chunk


def _load_config(config_path: str | Path = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_index(
    pdf_path: str | Path,
    config_path: str | Path = "config/config.yaml",
    force_rebuild: bool = False,
) -> tuple[faiss.Index, list[Chunk]]:
    """
    Costruisce (o carica) l'indice FAISS per il PDF indicato.

    Returns:
        (index, chunks) — indice FAISS e lista di chunk con metadati.
    """
    cfg = _load_config(config_path)
    persist_path = Path(cfg["vector_store"]["persist_path"])
    index_file = persist_path / "index.faiss"
    chunks_file = persist_path / "chunks.pkl"

    # --- Carica da cache se disponibile ---
    if not force_rebuild and index_file.exists() and chunks_file.exists():
        logger.info(f"Indice trovato su disco: {persist_path} — carico dalla cache.")
        index = faiss.read_index(str(index_file))
        with open(chunks_file, "rb") as f:
            chunks = pickle.load(f)
        logger.info(f"Caricati {len(chunks)} chunk, {index.ntotal} vettori.")
        return index, chunks

    # --- Parsing e chunking ---
    logger.info("Avvio parsing e chunking del PDF…")
    max_chars = cfg["chunking"]["max_chunk_size"]
    chunks = load_and_chunk(pdf_path, max_chars=max_chars)
    logger.info(f"Totale chunk generati: {len(chunks)}")

    # --- Embedding ---
    model_name = cfg["embedding"]["model"]
    device = cfg["embedding"]["device"]
    logger.info(f"Caricamento modello embedding: {model_name}")
    model = SentenceTransformer(model_name, device=device)

    texts = [c.text for c in chunks]
    logger.info(f"Generazione embedding per {len(texts)} chunk…")
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,   # cosine similarity → inner product
    )
    embeddings = np.array(embeddings, dtype=np.float32)
    logger.info(f"Embedding shape: {embeddings.shape}")

    # --- Costruzione indice FAISS (IndexFlatIP = cosine con vettori normalizzati) ---
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    logger.info(f"Indice FAISS costruito: {index.ntotal} vettori, dim={dim}")

    # --- Persistenza ---
    persist_path.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_file))
    with open(chunks_file, "wb") as f:
        pickle.dump(chunks, f)
    logger.info(f"Indice salvato in: {persist_path}")

    return index, chunks


def load_index(
    config_path: str | Path = "config/config.yaml",
) -> tuple[faiss.Index, list[Chunk]]:
    """Carica l'indice FAISS già costruito. Lancia FileNotFoundError se non esiste."""
    cfg = _load_config(config_path)
    persist_path = Path(cfg["vector_store"]["persist_path"])
    index_file = persist_path / "index.faiss"
    chunks_file = persist_path / "chunks.pkl"

    if not index_file.exists() or not chunks_file.exists():
        raise FileNotFoundError(
            f"Indice non trovato in {persist_path}. "
            "Esegui prima: python scripts/build_index.py"
        )

    index = faiss.read_index(str(index_file))
    with open(chunks_file, "rb") as f:
        chunks = pickle.load(f)

    logger.info(f"Indice caricato: {index.ntotal} vettori, {len(chunks)} chunk.")
    return index, chunks


if __name__ == "__main__":
    import sys

    pdf = Path("data/raw/TU-81-08-Ed.-Gennaio-2025-1.pdf")
    index, chunks = build_index(pdf, force_rebuild=True)
    print(f"\nIndice costruito: {index.ntotal} vettori")
    print(f"Chunk totali: {len(chunks)}")
    print(f"\n--- Chunk #0 ---\n{chunks[0].text[:200]}")
    print(f"Metadata: {chunks[0].metadata}")
