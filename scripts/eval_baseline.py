"""
eval_baseline.py – Valutazione comparativa B0, B1, pipeline completa.

Metriche calcolate:
  Retrieval  → Hit Rate@1, Hit Rate@5, MRR (Mean Reciprocal Rank)
  Generazione → Faithfulness (1-5), Relevance (1-5) via OpenAI-as-judge
  Performance → Latenza media per baseline

Baseline:
  B0       → LLM puro (nessun contesto RAG, solo conoscenza del modello)
  B1       → RAG con top-1 (un solo chunk recuperato)
  B_full   → Pipeline completa (top-5 hybrid BM25 + semantica)
  B_full_rw → B_full + query rewriting LLM prima del retrieval

Output:
  outputs/eval/results_<timestamp>.csv  – risultati per domanda
  outputs/eval/summary_<timestamp>.json – metriche aggregate per baseline

Uso:
    python scripts/eval_baseline.py
    python scripts/eval_baseline.py --subset 5     # testa solo le prime N domande
    python scripts/eval_baseline.py --no-judge     # salta LLM-as-judge (più veloce)
    python scripts/eval_baseline.py --no-rewrite   # salta baseline B_full_rw
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI

# Aggiunge la root al path per importare i moduli src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.indexer import load_index
from src.models.rag_chain import RAGChain
from src.models.retriever import HybridRetriever

load_dotenv()

# ── Costanti ──────────────────────────────────────────────────────────────────

TEST_SET_PATH = Path("data/eval/test_set.json")
OUTPUT_DIR = Path("outputs/eval")

JUDGE_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT_B0 = """Sei un esperto di diritto del lavoro italiano, specializzato nel
D.Lgs. 81/2008 (Testo Unico sulla Sicurezza sul Lavoro). Rispondi alla domanda
in modo preciso e conciso, citando gli articoli pertinenti. Rispondi in italiano."""

JUDGE_PROMPT_TEMPLATE = """Sei un valutatore esperto di sistemi RAG per normativa della sicurezza sul lavoro.

DOMANDA: {query}

RISPOSTA ATTESA (ground truth):
{ground_truth}

RISPOSTA GENERATA:
{answer}

CONTESTO FORNITO AL MODELLO (se assente = baseline B0):
{context_preview}

Valuta la risposta generata su due dimensioni (scala 1-5):

1. FEDELTÀ (faithfulness): la risposta è fedele al contesto fornito? Non introduce informazioni inventate?
   - 5 = completamente fedele, nessuna allucinazione
   - 4 = fedele con piccole imprecisioni non fuorvianti
   - 3 = parzialmente fedele, qualche informazione non verificabile nel contesto
   - 2 = diverse informazioni non supportate dal contesto
   - 1 = allucinazioni evidenti o contraddizioni col contesto

2. RILEVANZA (relevance): la risposta risponde alla domanda in modo completo e accurato?
   - 5 = risposta completa, accurata, con articoli corretti
   - 4 = risposta buona con piccole lacune
   - 3 = risposta parziale o con imprecisioni sugli articoli
   - 2 = risposta incompleta o con errori sui contenuti normativi
   - 1 = risposta non pertinente o errata

Rispondi ESCLUSIVAMENTE con JSON (niente altro testo):
{{"faithfulness": <int 1-5>, "relevance": <int 1-5>, "note": "<breve motivazione>"}}"""


# ── Funzioni di retrieval ─────────────────────────────────────────────────────

def get_retrieved_articles(chunks: list[dict]) -> list[str]:
    """Estrae i numeri di articolo dai chunk recuperati."""
    return [str(c["metadata"].get("articolo", "?")) for c in chunks]


def hit_rate_at_k(retrieved_articles: list[str], expected: list[str], k: int) -> int:
    """1 se almeno un articolo atteso è nei top-k recuperati, 0 altrimenti."""
    top_k = retrieved_articles[:k]
    return int(any(art in top_k for art in expected))


def mrr_score(retrieved_articles: list[str], expected: list[str]) -> float:
    """Reciprocal Rank: 1/posizione del primo articolo atteso trovato."""
    for rank, art in enumerate(retrieved_articles, 1):
        if art in expected:
            return 1.0 / rank
    return 0.0


# ── LLM-as-judge ──────────────────────────────────────────────────────────────

def judge_answer(
    query: str,
    answer: str,
    ground_truth: str,
    chunks: list[dict],
    client: OpenAI,
) -> dict:
    """
    Usa OpenAI come giudice per valutare faithfulness e relevance.
    Restituisce {'faithfulness': int, 'relevance': int, 'note': str}.
    """
    context_preview = (
        " | ".join(
            f"Art. {c['metadata'].get('articolo','?')}: {c['text'][:120]}…"
            for c in chunks
        )
        if chunks
        else "Nessun contesto (B0)"
    )

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        ground_truth=ground_truth,
        answer=answer,
        context_preview=context_preview,
    )

    try:
        response = client.chat.completions.create(
            model=JUDGE_MODEL,
            max_tokens=300,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        # Estrae JSON anche se il modello aggiunge testo
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.warning(f"Judge fallito: {e}")

    return {"faithfulness": -1, "relevance": -1, "note": "judge_error"}


# ── Baseline B0 ───────────────────────────────────────────────────────────────

def run_b0(
    questions: list[dict],
    client: OpenAI,
    use_judge: bool,
) -> list[dict]:
    """B0: LLM puro senza contesto RAG."""
    results = []
    logger.info(f"[B0] Avvio su {len(questions)} domande…")

    for q in questions:
        start = time.time()
        response = client.chat.completions.create(
            model=JUDGE_MODEL,
            max_tokens=512,
            temperature=0.0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_B0},
                {"role": "user", "content": q["domanda"]},
            ],
        )
        answer = response.choices[0].message.content
        latency = time.time() - start

        row = {
            "id": q["id"],
            "domanda": q["domanda"],
            "categoria": q["categoria"],
            "baseline": "B0",
            "answer": answer,
            "latency_s": round(latency, 3),
            "hit_rate_1": None,
            "hit_rate_5": None,
            "mrr": None,
        }

        if use_judge:
            scores = judge_answer(q["domanda"], answer, q["risposta_attesa"], [], client)
            row.update(scores)
        else:
            row.update({"faithfulness": None, "relevance": None, "note": "skipped"})

        results.append(row)
        logger.debug(f"  [{q['id']:02d}] B0 | latency={latency:.2f}s")

    return results


# ── Baseline B1 e pipeline completa ───────────────────────────────────────────

def run_rag(
    questions: list[dict],
    retriever: HybridRetriever,
    chain: RAGChain,
    client: OpenAI,
    top_k_override: int | None,
    label: str,
    use_judge: bool,
    use_rewrite: bool = False,
) -> list[dict]:
    """
    Esegue retrieval + generazione per B1 (top_k_override=1)
    o per la pipeline completa (top_k_override=None → usa config).
    Se use_rewrite=True, riscrive la query con terminologia TU 81/08 prima del retrieval.
    """
    results = []
    logger.info(f"[{label}] Avvio su {len(questions)} domande…")

    for q in questions:
        # Rewriting opzionale della query prima del retrieval
        if use_rewrite:
            search_query = chain.rewrite_query(q["domanda"])
            logger.debug(f"  Rewrite: '{q['domanda'][:50]}' → '{search_query[:60]}'")
        else:
            search_query = q["domanda"]

        # Retrieval
        chunks = retriever.retrieve(search_query)
        if top_k_override is not None:
            chunks = chunks[:top_k_override]

        retrieved_arts = get_retrieved_articles(chunks)

        # Hit Rate e MRR (solo per baseline con RAG)
        hr1 = hit_rate_at_k(retrieved_arts, q["articoli_attesi"], 1)
        hr5 = hit_rate_at_k(retrieved_arts, q["articoli_attesi"], 5)
        mrr = mrr_score(retrieved_arts, q["articoli_attesi"])

        # Generazione
        start = time.time()
        answer = chain.answer(q["domanda"], chunks)
        latency = time.time() - start

        row = {
            "id": q["id"],
            "domanda": q["domanda"],
            "query_riscritta": search_query if use_rewrite else "",
            "categoria": q["categoria"],
            "baseline": label,
            "answer": answer,
            "articoli_recuperati": ", ".join(retrieved_arts),
            "articoli_attesi": ", ".join(q["articoli_attesi"]),
            "latency_s": round(latency, 3),
            "hit_rate_1": hr1,
            "hit_rate_5": hr5,
            "mrr": round(mrr, 4),
        }

        if use_judge:
            scores = judge_answer(q["domanda"], answer, q["risposta_attesa"], chunks, client)
            row.update(scores)
        else:
            row.update({"faithfulness": None, "relevance": None, "note": "skipped"})

        results.append(row)
        logger.debug(
            f"  [{q['id']:02d}] {label} | HR@1={hr1} HR@5={hr5} "
            f"MRR={mrr:.3f} latency={latency:.2f}s"
        )

    return results


# ── Report ────────────────────────────────────────────────────────────────────

def compute_summary(results: list[dict]) -> dict:
    """Calcola metriche aggregate per un set di risultati."""
    df = pd.DataFrame(results)

    summary = {
        "n_domande": len(df),
        "latency_media_s": round(df["latency_s"].mean(), 3),
    }

    if df["hit_rate_1"].notna().any():
        summary["hit_rate_1"] = round(df["hit_rate_1"].mean(), 4)
        summary["hit_rate_5"] = round(df["hit_rate_5"].mean(), 4)
        summary["mrr"] = round(df["mrr"].mean(), 4)

    if df.get("faithfulness") is not None and df["faithfulness"].notna().any():
        valid = df[df["faithfulness"] != -1]
        if not valid.empty:
            summary["faithfulness_media"] = round(valid["faithfulness"].mean(), 2)
            summary["relevance_media"] = round(valid["relevance"].mean(), 2)

    return summary


def print_report(summaries: dict[str, dict]) -> None:
    """Stampa tabella comparativa delle metriche per baseline."""
    has_rw = "B_full_rw" in summaries
    col_w = 18

    total_cols = 4 + (1 if has_rw else 0)
    sep_len = col_w * total_cols

    print("\n" + "=" * sep_len)
    print("RISULTATI VALUTAZIONE – Chatbot TU 81/08")
    print("=" * sep_len)

    headers = ["Metrica", "B0 (LLM puro)", "B1 (top-1)", "B_full (top-5)"]
    if has_rw:
        headers.append("B_full_rw")
    print("".join(h.ljust(col_w) for h in headers))
    print("-" * sep_len)

    baselines = ["B0", "B1", "B_full"] + (["B_full_rw"] if has_rw else [])
    metrics = [
        ("Hit Rate@1",        [None, "hit_rate_1", "hit_rate_1", "hit_rate_1"]),
        ("Hit Rate@5",        [None, "hit_rate_5", "hit_rate_5", "hit_rate_5"]),
        ("MRR",               [None, "mrr",        "mrr",        "mrr"]),
        ("Faithfulness",      ["faithfulness_media"] * 4),
        ("Relevance",         ["relevance_media"] * 4),
        ("Latenza media (s)", ["latency_media_s"] * 4),
    ]

    for label, keys in metrics:
        vals = []
        for b, key in zip(baselines, keys):
            if key is None:
                vals.append("—")
            else:
                v = summaries.get(b, {}).get(key)
                vals.append(f"{v:.3f}" if isinstance(v, float) else ("—" if v is None else str(v)))
        parts = [label.ljust(col_w)] + [v.ljust(col_w) for v in vals]
        print("".join(parts))

    print("=" * sep_len)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Valutazione baseline RAG – TU 81/08")
    parser.add_argument("--subset", type=int, default=None,
                        help="Testa solo le prime N domande del test set")
    parser.add_argument("--no-judge", action="store_true",
                        help="Salta LLM-as-judge (calcola solo metriche retrieval)")
    parser.add_argument("--no-rewrite", action="store_true",
                        help="Salta baseline B_full_rw (query rewriting LLM)")
    args = parser.parse_args()

    # ── Setup ─────────────────────────────────────────────────────────────────
    logger.info("Caricamento test set…")
    questions = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    if args.subset:
        questions = questions[: args.subset]
    logger.info(f"Domande da valutare: {len(questions)}")

    logger.info("Caricamento indice FAISS…")
    index, chunks_store = load_index()

    logger.info("Inizializzazione retriever e chain…")
    retriever = HybridRetriever(index, chunks_store)
    chain = RAGChain()
    client = chain.client          # riusa il client OpenAI già inizializzato

    use_judge = not args.no_judge
    use_rewrite = not args.no_rewrite

    # ── Esecuzione baseline ───────────────────────────────────────────────────
    results_b0    = run_b0(questions, client, use_judge)
    results_b1    = run_rag(questions, retriever, chain, client,
                            top_k_override=1, label="B1", use_judge=use_judge)
    results_bfull = run_rag(questions, retriever, chain, client,
                            top_k_override=None, label="B_full", use_judge=use_judge)

    all_results = results_b0 + results_b1 + results_bfull
    summaries = {
        "B0":     compute_summary(results_b0),
        "B1":     compute_summary(results_b1),
        "B_full": compute_summary(results_bfull),
    }

    if use_rewrite:
        results_bfull_rw = run_rag(questions, retriever, chain, client,
                                   top_k_override=None, label="B_full_rw",
                                   use_judge=use_judge, use_rewrite=True)
        all_results += results_bfull_rw
        summaries["B_full_rw"] = compute_summary(results_bfull_rw)

    # ── Salvataggio ───────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(all_results)
    csv_path = OUTPUT_DIR / f"results_{ts}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    logger.info(f"Risultati salvati: {csv_path}")

    json_path = OUTPUT_DIR / f"summary_{ts}.json"
    json_path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Summary salvato: {json_path}")

    # ── Report ────────────────────────────────────────────────────────────────
    print_report(summaries)

    print(f"\nFile salvati:")
    print(f"  {csv_path}")
    print(f"  {json_path}")


if __name__ == "__main__":
    main()
