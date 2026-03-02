"""
test_retriever.py – Test unitari per le funzioni pure di retriever.py.
Non richiedono modelli o indici caricati.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.retriever import _tokenize, _expand_query, _rrf_fusion


class TestTokenize:
    def test_lowercase(self):
        assert _tokenize("Datore di Lavoro") == ["datore", "di", "lavoro"]

    def test_empty(self):
        assert _tokenize("") == []

    def test_already_lower(self):
        assert _tokenize("dvr rspp rls") == ["dvr", "rspp", "rls"]

    def test_preserves_split(self):
        tokens = _tokenize("art. 17 comma 1")
        assert len(tokens) == 4


class TestExpandQuery:
    def test_expands_dvr(self):
        result = _expand_query("Obblighi DVR datore")
        assert "documento valutazione rischi" in result

    def test_expands_rspp(self):
        result = _expand_query("Chi nomina il RSPP?")
        assert "responsabile servizio prevenzione protezione" in result

    def test_no_expansion_when_no_acronym(self):
        query = "obblighi del datore di lavoro"
        result = _expand_query(query)
        # La query originale è comunque presente
        assert query in result

    def test_case_insensitive_match(self):
        # La funzione usa query.upper() → espande sia maiuscolo che minuscolo
        result_lower = _expand_query("il dvr deve essere redatto")
        result_upper = _expand_query("il DVR deve essere redatto")
        assert "documento valutazione rischi" in result_lower
        assert "documento valutazione rischi" in result_upper


class TestRrfFusion:
    def test_basic_fusion(self):
        bm25 = [0, 1, 2]
        semantic = [2, 0, 1]
        results = _rrf_fusion(bm25, semantic, bm25_weight=0.4, semantic_weight=0.6)
        # Deve restituire lista di tuple (idx, score)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)

    def test_sorted_descending(self):
        bm25 = [0, 1, 2, 3]
        semantic = [0, 1, 2, 3]
        results = _rrf_fusion(bm25, semantic, bm25_weight=0.5, semantic_weight=0.5)
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_consistent_top_element(self):
        # Il chunk 0 è primo in entrambi i ranking → deve avere lo score più alto
        bm25 = [0, 1, 2]
        semantic = [0, 1, 2]
        results = _rrf_fusion(bm25, semantic, bm25_weight=0.5, semantic_weight=0.5)
        assert results[0][0] == 0

    def test_weights_influence(self):
        bm25 = [0, 1]      # chunk 0 primo per BM25
        semantic = [1, 0]  # chunk 1 primo per semantica
        # Con peso semantico molto alto, chunk 1 deve vincere
        results = _rrf_fusion(bm25, semantic, bm25_weight=0.01, semantic_weight=0.99)
        assert results[0][0] == 1
