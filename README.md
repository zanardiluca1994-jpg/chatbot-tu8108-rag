# Chatbot TU 81/08 – D.Lgs. 81/2008 Sicurezza sul Lavoro (RAG)

Sistema RAG per interrogare in linguaggio naturale il **Testo Unico sulla Sicurezza sul Lavoro (D.Lgs. 81/2008)**.
Ogni risposta cita obbligatoriamente l'articolo e il comma di riferimento. Valutato su 20 domande di test con ground truth.

![Chat con query rewriting e citazioni articoli](screenshots/chat.png)

---

## Risultati

| Metrica | Baseline | Finale | Var % |
|---------|:--------:|:------:|:-----:|
| Hit Rate@5 | 0.45 | **0.80** ✅ | +78% |
| MRR | 0.34 | **0.67** | +97% |
| Faithfulness (1–5) | 3.40 | **4.00** | +18% |
| Relevance (1–5) | 2.65 | **4.00** | +51% |
| Fallback (domande senza risposta) | 2/20 | **0/20** | −100% |

Progressione completa in 5 run di tuning documentata in [`outputs/eval/comparison_report.md`](outputs/eval/comparison_report.md).

---

## Screenshot

| Chat + query rewriting | Fonti consultate | Sidebar + feedback |
|:---------------------:|:----------------:|:-----------------:|
| ![](screenshots/chat.png) | ![](screenshots/sources.png) | ![](screenshots/sidebar.png) |

> La query viene riscritta automaticamente con terminologia giuridica prima del retrieval (visibile in corsivo sotto la domanda). Le fonti mostrano i 5 articoli recuperati con estratto del testo. Il sidebar traccia il feedback utente per sessione.

---

## Il problema

Il D.Lgs. 81/2008 è composto da 306 articoli + 47 allegati tecnici. Un RSPP (Responsabile Servizio Prevenzione e Protezione) deve spesso rispondere rapidamente a domande su obblighi, sanzioni e procedure senza sfogliare manualmente 198 pagine.

**Problema tecnico:** costruire una pipeline RAG che recuperi i chunk normativi corretti e generi risposte ancorate al testo, citando sempre articolo e comma.

---

## Architettura

```
PDF (198 pag.)
    │
    ▼ pypdfium2 + chunking per articolo
8.990 chunk (1 per articolo/comma)
    │
    ▼ sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
FAISS index (384 dim, 21 MB su disco)
    │
Query utente
    │
    ├── Query rewriting LLM (terminologia giuridica TU 81/08)
    │
    ├── BM25 (rank-bm25)   ─┐
    └── FAISS semantica    ─┤ RRF fusion (w=0.4 / 0.6)
                            │
                        Top-20 candidati
                            │
                        Cross-encoder (ms-marco-MiniLM-L-6-v2)
                            │
                        Top-5 chunk
                            │
                        gpt-4o-mini → Risposta con [art. X, comma Y]
```

---

## Stack tecnologico

| Componente | Tecnologia | Note |
|-----------|-----------|------|
| PDF parsing | `pypdfium2` | Page-by-page, basso consumo RAM |
| Chunking | Custom — per articolo | Unità normativa atomica |
| Embedding | `sentence-transformers` `paraphrase-multilingual-MiniLM-L12-v2` | Multilingue, ottimale per italiano |
| Vector store | `faiss-cpu` | Locale persistito, nessuna infrastruttura |
| Retrieval | BM25 (`rank-bm25`) + FAISS semantica + RRF fusion | Ibrido: match esatto + semantica |
| Re-ranking | `CrossEncoder` `ms-marco-MiniLM-L-6-v2` | 2° stage, +25% HR@5 vs solo hybrid |
| LLM | `gpt-4o-mini` via `openai` | temperature=0, streaming |
| Interfaccia | `streamlit` | Chat, fonti espandibili, feedback 👍/👎 |
| Eval | Custom LLM-as-judge (`gpt-4o-mini`) | Hit Rate@1/@5, MRR, Faithfulness, Relevance |

---

## Decisioni chiave e trade-off

**Chunking per articolo invece di sliding window**
L'articolo è l'unità giuridica atomica. Spezzarlo per dimensione produrrebbe chunk privi di contesto normativo autonomo e citazioni inutilizzabili.

**Retrieval ibrido BM25 + semantica**
BM25 funziona meglio su acronimi tecnici precisi (DVR, RSPP, DPI). La semantica copre sinonimi e query colloquiali. RRF fusion li combina senza richiedere calibrazione manuale dei pesi.

**Cross-encoder come secondo stage**
Il reranker ha portato HR@1 da 0.30 a 0.60 (+100%) e HR@5 da 0.60 a 0.80 (+33%) senza modificare il retrieval base. Costo: +1.5s di latenza media.

**Query rewriting in produzione, non nell'eval**
Il test set usa terminologia tecnica precisa — il rewriting la diluisce e peggiora il retrieval (HR@5: 0.60 → 0.55). In produzione, dove le query sono colloquiali, il beneficio si inverte. Il rewriting è attivo solo nell'app Streamlit.

---

## Come eseguirlo

### Prerequisiti
- Python 3.10+
- Chiave API OpenAI

### Setup

```bash
git clone <repo-url>
cd 02_chatbot_documentazione_rag

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

make install
```

### Configurazione

```bash
cp .env.example .env
# Inserire OPENAI_API_KEY in .env
```

### Avvio

```bash
make build-index   # Una sola volta — costruisce l'indice FAISS (~2 min)
make run           # Avvia il chatbot Streamlit
```

### Valutazione

```bash
make eval          # Valutazione rapida (B0 + B1 + B_full)
make eval-full     # Include baseline con query rewriting
```

### Test

```bash
make test          # 19 test unitari sulle funzioni pure
```

---

## Struttura del progetto

```
02_chatbot_documentazione_rag/
├── config/
│   └── config.yaml              # Tutti i parametri (no hardcoding)
├── data/
│   ├── raw/                     # PDF sorgente (TU 81/08, 198 pag.)
│   └── eval/
│       └── test_set.json        # 27 domande con ground truth
├── src/
│   ├── data/
│   │   ├── loader.py            # Parser PDF + chunking per articolo
│   │   └── indexer.py           # Embedding + FAISS (build e load)
│   ├── models/
│   │   ├── retriever.py         # HybridRetriever: BM25 + FAISS + RRF + reranker
│   │   └── rag_chain.py         # RAGChain: prompt assembly + streaming OpenAI
│   └── visualization/
│       └── app.py               # Streamlit UI con feedback 👍/👎
├── scripts/
│   ├── build_index.py           # Script one-shot per costruire l'indice
│   └── eval_baseline.py         # Valutazione comparativa B0/B1/B_full
├── tests/
│   ├── test_retriever.py        # Test su tokenize, expand_query, RRF fusion
│   └── test_rag_chain.py        # Test su build_context, build_user_message
├── outputs/
│   ├── models/faiss_index/      # Indice FAISS persistito (21 MB)
│   ├── eval/                    # CSV + JSON + comparison_report.md
│   └── logs/
│       ├── queries.jsonl        # Log strutturato di ogni query
│       └── feedback.jsonl       # Log feedback utente 👍/👎
├── Makefile
├── requirements.txt
└── .env.example
```

---

## Limiti noti

- **Domande multi-hop**: il sistema recupera bene singoli articoli ma fatica su domande che richiedono di incrociare 3+ articoli distanti (es. "Come si coordina il SPP con il medico competente nei cantieri temporanei?").
- **Allegati tecnici**: il TU 81/08 contiene 47 allegati con tabelle e schemi. Il chunking per articolo li tratta come testo piano — le tabelle perdono struttura in fase di parsing.
- **Copertura corpus**: il sistema copre solo il TU 81/08 Ed. Gennaio 2025. Circolari INAIL, interpelli ministeriali e norme UNI/ISO richiamate non sono incluse.
- **Lingua**: il sistema è ottimizzato per italiano. Query in inglese vengono gestite ma con qualità retrieval degradata.
- **Faithfulness**: 4.00/5 — sotto il target 4.25. Il modello occasionalmente sintetizza informazioni al di là del contesto fornito su argomenti correlati ben noti (es. sanzioni generali vs specifiche).

---

## Retrospettiva

### Cosa ha funzionato

**Il chunking per articolo è stata la scelta giusta.** Il TU 81/08 ha una struttura gerarchica precisa (Titolo → Capo → Articolo → Comma → Lettera) e l'articolo è l'unità citabile per legge. Un approccio sliding window avrebbe prodotto chunk che spezzano una norma a metà, rendendo le citazioni inutilizzabili.

**Il retrieval ibrido + reranker ha avuto l'impatto maggiore.** Passare da solo semantica a BM25+semantica+RRF ha portato HR@5 da ~0.45 a 0.60. Aggiungere il cross-encoder lo ha portato a 0.75, e aumentare `top_k_candidates` a 20 ha raggiunto il target 0.80. Ogni step è stato guidato da dati di eval.

**LLM-as-judge come metrica di qualità** ha permesso di misurare faithfulness e relevance su ogni run senza annotazione manuale. Il costo marginale (gpt-4o-mini per 20 domande) è trascurabile.

### Cosa non ha funzionato come atteso

**Il query rewriting peggiora le metriche sul test set.** Le 20 domande di test sono già formulate con terminologia giuridica precisa. Il rewriting le rende più lunghe e verbose, diluendo il segnale BM25 e l'embedding semantico. Il vantaggio del rewriting esiste solo in produzione, dove le query sono colloquiali — ma questo non si misura sul test set corrente. Ho aggiunto 7 query informali per misurarlo correttamente nella prossima eval.

**La stima iniziale dei chunk era sbagliata di 25×.** Il TU ha 306 articoli, ma ogni comma e lettera è un chunk separato: il risultato è 8.990 chunk. Non un problema operativo, ma un errore di pianificazione da non ripetere.

### Cosa farei diversamente

Partirei dall'eval prima del codice. Ho scritto il test set solo dopo aver costruito la pipeline, ma avere 20 domande con ground truth prima avrebbe guidato le scelte architetturali (es. avrei capito subito che il chunking per comma era necessario, non per articolo intero).

---

## Configurazione parametri (config.yaml)

```yaml
chunking:
  strategy: per_articolo
  max_chunk_size: 2000          # char — articoli lunghissimi suddivisi per comma

embedding:
  model: paraphrase-multilingual-MiniLM-L12-v2
  device: cpu

retrieval:
  top_k: 5
  bm25_weight: 0.4
  semantic_weight: 0.6
  min_similarity: 0.55          # sotto soglia → fallback senza chiamata LLM

reranker:
  enabled: true
  model: cross-encoder/ms-marco-MiniLM-L-6-v2
  top_k_candidates: 20

llm:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.0
  max_tokens: 1024
  streaming: true
```
