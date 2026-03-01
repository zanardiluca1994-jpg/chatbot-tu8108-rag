# Chatbot su Documentazione Interna (RAG)

## Obiettivo
Sistema di Q&A su documenti aziendali (procedure operative, SLA fornitori, specifiche tecniche) che risponde a domande in linguaggio naturale. L'utente carica i propri PDF e interroga il sistema come se stesse parlando con un esperto che ha letto tutti i documenti.

**Problema reale:** recuperare informazioni da documentazione aziendale richiede tempo e dipende dalla conoscenza individuale.
**Problema tecnico:** costruire un pipeline RAG che recupera i chunk rilevanti e genera una risposta contestualizzata.

---

## Tipo AI
RAG – Retrieval-Augmented Generation

## Difficoltà
⭐⭐☆☆☆

---

## Dataset
- Documenti PDF aziendali (procedure, contratti, SLA, specifiche)
- Posizione: `data/raw/`
- Formato atteso: `.pdf`, `.txt`, `.docx`
- I documenti NON devono essere modificati: sono sola lettura

---

## Stack tecnologico
| Componente | Libreria |
|-----------|---------|
| LLM | Claude API / OpenAI API |
| Orchestrazione | LangChain |
| Vector store | ChromaDB |
| Embedding | sentence-transformers o OpenAI embeddings |
| Interfaccia | Streamlit |
| Configurazione | PyYAML + python-dotenv |

---

## Metodologia
1. **Ingestion** – caricamento e parsing dei PDF (`src/data/`)
2. **Chunking** – suddivisione dei testi in chunk ottimali (`src/features/`)
3. **Embedding** – trasformazione dei chunk in vettori (`src/features/`)
4. **Indicizzazione** – salvataggio nel vector store ChromaDB (`src/models/`)
5. **Retrieval** – recupero dei chunk più rilevanti alla query (`src/models/`)
6. **Generation** – generazione risposta tramite LLM con contesto (`src/models/`)
7. **Interfaccia** – app Streamlit per interazione utente (`src/visualization/`)

---

## Metrica di successo
- Risposta pertinente alla domanda (valutazione manuale su set di test)
- Fonte citata correttamente (il sistema indica da quale documento ha preso l'informazione)
- Latenza risposta < 5 secondi

---

## Risultati
*(da compilare al termine del progetto)*

---

## Impatto business
- Riduzione del tempo di ricerca informazioni nella documentazione
- Onboarding più rapido di nuovi colleghi
- Accesso democratizzato alla conoscenza aziendale

---

## Come eseguirlo

### 1. Setup ambiente
```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

### 2. Configurazione
```bash
cp .env.example .env
# Inserire la propria API key in .env
```

### 3. Aggiungere documenti
Copiare i PDF nella cartella `data/raw/`.

### 4. Eseguire la pipeline
```bash
python run.py
```

### 5. Avviare l'interfaccia
```bash
streamlit run src/visualization/app.py
```

---

## Struttura del progetto
```
02_chatbot_documentazione_rag/
├── data/
│   ├── raw/           # PDF originali (sola lettura)
│   ├── processed/     # testi estratti e chunk
│   └── external/      # dati da fonti terze
├── notebooks/         # esplorazione e prototipazione
├── src/
│   ├── data/          # caricamento e parsing PDF
│   ├── features/      # chunking ed embedding
│   ├── models/        # RAG pipeline (retrieval + generation)
│   └── visualization/ # app Streamlit
├── outputs/
│   ├── figures/
│   ├── reports/
│   └── models/        # vector store persistito
├── config/
│   └── config.yaml
├── tests/
├── README.md
├── requirements.txt
├── .env.example
└── .gitignore
```
