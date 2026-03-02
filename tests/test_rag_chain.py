"""
test_rag_chain.py – Test unitari per le funzioni pure di rag_chain.py.
Non richiedono connessione a OpenAI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.rag_chain import _build_context, _build_user_message


class TestBuildContext:
    def _make_chunk(self, articolo: str, intestazione: str, text: str) -> dict:
        return {
            "text": text,
            "metadata": {"articolo": articolo, "intestazione": intestazione},
        }

    def test_single_chunk(self):
        chunk = self._make_chunk("17", "Art. 17 – Obblighi non delegabili", "Il datore di lavoro non può delegare...")
        context = _build_context([chunk])
        assert "Art. 17" in context
        assert "Il datore di lavoro non può delegare" in context

    def test_multiple_chunks_separated(self):
        chunks = [
            self._make_chunk("17", "Art. 17", "Testo art 17"),
            self._make_chunk("28", "Art. 28", "Testo art 28"),
        ]
        context = _build_context(chunks)
        assert "Testo art 17" in context
        assert "Testo art 28" in context
        # Devono essere separati da riga vuota
        assert "\n\n" in context

    def test_fallback_header_when_no_intestazione(self):
        chunk = {
            "text": "Contenuto articolo",
            "metadata": {"articolo": "55"},
        }
        context = _build_context([chunk])
        assert "Art. 55" in context

    def test_empty_chunks(self):
        assert _build_context([]) == ""


class TestBuildUserMessage:
    def test_contains_query(self):
        msg = _build_user_message("Chi è il RSPP?", "Art. 17 – Testo")
        assert "Chi è il RSPP?" in msg

    def test_contains_context(self):
        msg = _build_user_message("domanda", "Art. 17 – Testo dell'articolo")
        assert "Art. 17 – Testo dell'articolo" in msg

    def test_structure(self):
        msg = _build_user_message("Domanda test", "Contesto test")
        assert "Domanda" in msg
        assert "Contesto" in msg
