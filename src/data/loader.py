"""
loader.py – Parsing e chunking del TU 81/08
Estrae il testo dal PDF e lo divide per articolo.
"""

import re
import pypdfium2 as pdfium
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


def load_pdf(pdf_path: str | Path) -> str:
    """Estrae il testo grezzo dal PDF pagina per pagina."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")

    logger.info(f"Caricamento PDF: {pdf_path.name}")
    pages = []
    pdf = pdfium.PdfDocument(str(pdf_path))
    for i in range(len(pdf)):
        page = pdf[i]
        textpage = page.get_textpage()
        text = textpage.get_text_range()
        if text and text.strip():
            pages.append(text)
        textpage.close()
        page.close()
    pdf.close()

    full_text = "\n".join(pages)
    logger.info(f"Estratte {len(pages)} pagine, {len(full_text)} caratteri totali")
    return full_text


def split_by_article(text: str, max_chars: int = 2000) -> list[Chunk]:
    """
    Divide il testo in chunk per articolo.
    Pattern: 'Art. 123 - Titolo' oppure 'Articolo 123'
    Se un articolo supera max_chars, lo suddivide per comma.
    """
    # Pattern per intestazione articolo
    article_pattern = re.compile(
        r"(Art(?:icolo)?\.?\s+\d+\s*[-–—]?\s*[^\n]*)",
        re.IGNORECASE
    )

    splits = article_pattern.split(text)
    chunks = []

    i = 1  # splits[0] è il testo prima del primo articolo (intro, indice)
    while i < len(splits) - 1:
        header = splits[i].strip()
        body = splits[i + 1].strip() if i + 1 < len(splits) else ""
        i += 2

        # Estrai numero articolo dall'intestazione
        num_match = re.search(r"\d+", header)
        article_num = num_match.group() if num_match else "?"

        full_text = f"{header}\n{body}"

        if len(full_text) <= max_chars:
            chunks.append(Chunk(
                text=full_text,
                metadata={
                    "articolo": article_num,
                    "intestazione": header,
                    "tipo": "articolo"
                }
            ))
        else:
            # Suddivide per comma se l'articolo è troppo lungo
            sub_chunks = _split_by_comma(header, body, article_num, max_chars)
            chunks.extend(sub_chunks)

    logger.info(f"Generati {len(chunks)} chunk da {len(splits) // 2} articoli trovati")
    return chunks


def _split_by_comma(header: str, body: str, article_num: str, max_chars: int) -> list[Chunk]:
    """Suddivide un articolo lungo per comma (1., 2., 3. …)."""
    comma_pattern = re.compile(r"(?=\n\s*\d+\.\s)")
    parts = comma_pattern.split(body)

    sub_chunks = []
    buffer = f"{header}\n"
    comma_num = 0

    for part in parts:
        if len(buffer) + len(part) <= max_chars:
            buffer += part
        else:
            if buffer.strip():
                sub_chunks.append(Chunk(
                    text=buffer.strip(),
                    metadata={
                        "articolo": article_num,
                        "intestazione": header,
                        "comma_da": comma_num,
                        "tipo": "articolo_parte"
                    }
                ))
            buffer = f"{header} (continua)\n{part}"
            comma_num += 1

    if buffer.strip():
        sub_chunks.append(Chunk(
            text=buffer.strip(),
            metadata={
                "articolo": article_num,
                "intestazione": header,
                "comma_da": comma_num,
                "tipo": "articolo_parte"
            }
        ))

    return sub_chunks


def load_and_chunk(pdf_path: str | Path, max_chars: int = 2000) -> list[Chunk]:
    """Entry point principale: carica il PDF e restituisce i chunk."""
    text = load_pdf(pdf_path)
    chunks = split_by_article(text, max_chars=max_chars)
    return chunks


if __name__ == "__main__":
    import sys
    pdf = Path("data/raw/TU-81-08-Ed.-Gennaio-2025-1.pdf")
    chunks = load_and_chunk(pdf)
    print(f"\nTotale chunk: {len(chunks)}")
    print("\n--- Primo chunk ---")
    print(chunks[0].text[:300])
    print(f"\nMetadata: {chunks[0].metadata}")
    print("\n--- Chunk #10 ---")
    if len(chunks) > 10:
        print(chunks[10].text[:300])
        print(f"\nMetadata: {chunks[10].metadata}")
