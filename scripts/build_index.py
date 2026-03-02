"""
build_index.py – Costruisce l'indice FAISS dal PDF del TU 81/08.
Esegui una volta prima di avviare l'app.

Uso:
    python scripts/build_index.py
    python scripts/build_index.py --rebuild    # forza ricostruzione anche se l'indice esiste
"""

import argparse
import sys
from pathlib import Path

# Aggiunge la root al path per importare i moduli src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.data.indexer import build_index


def main():
    parser = argparse.ArgumentParser(description="Costruisce l'indice FAISS per il TU 81/08")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Forza la ricostruzione anche se l'indice esiste già",
    )
    parser.add_argument(
        "--pdf",
        default="data/raw/TU-81-08-Ed.-Gennaio-2025-1.pdf",
        help="Percorso al PDF (default: data/raw/TU-81-08-Ed.-Gennaio-2025-1.pdf)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error(f"PDF non trovato: {pdf_path}")
        sys.exit(1)

    logger.info(f"PDF: {pdf_path}")
    logger.info(f"Rebuild forzato: {args.rebuild}")

    index, chunks = build_index(pdf_path, force_rebuild=args.rebuild)

    print(f"\nIndice costruito con successo")
    print(f"  Vettori nell'indice: {index.ntotal}")
    print(f"  Chunk totali: {len(chunks)}")
    print(f"\nPuoi ora avviare l'app con:")
    print(f"  streamlit run src/visualization/app.py")


if __name__ == "__main__":
    main()
