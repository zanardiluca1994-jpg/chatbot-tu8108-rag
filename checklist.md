# Checklist – Chatbot Documentazione Interna (RAG)

Per approfondimenti su ogni punto → `vademecum/requirements_rag.md`

---

## Checklist Pre-sviluppo

Da completare **prima di scrivere codice**. Se un punto è N/A, motivarlo.

### A. Dati e Documenti
- [ ] **A1** — Formati supportati definiti e parser scelto per ciascuno
- [ ] **A1** — Gestione PDF scansionati decisa (OCR sì/no)
- [ ] **A2** — Volume stimato (n° documenti, pagine medie) documentato
- [ ] **A2** — Vector store scelto in base al volume
- [ ] **A2** — Costo embedding stimato (se si usa API a pagamento)
- [ ] **A3** — Frequenza di aggiornamento del corpus definita
- [ ] **A3** — Strategia di re-indicizzazione scelta (full rebuild / incrementale)
- [ ] **A4** — Struttura interna dei documenti analizzata (sezioni, tabelle, metadati)
- [ ] **A4** — Strategia di chunking definita (`chunk_size`, `overlap`, metodo)
- [ ] **A4** — Metadata da salvare per ogni chunk elencati
- [ ] **A5** — Requisiti di controllo accessi chiariti (libero / per ruolo / per utente)
- [ ] **A5** — Presenza di dati personali o sensibili verificata (implicazioni GDPR)

### B. Utenti e Casi d'Uso
- [ ] **B1** — Archetipo utente principale identificato (operativo / manager / analista / API)
- [ ] **B1** — Formato e lunghezza delle risposte definiti per l'archetipo scelto
- [ ] **B2** — Tipi di domande attese classificati (fattuale / procedurale / comparativa / analitica)
- [ ] **B2** — top-k configurato in base al tipo di domanda prevalente
- [ ] **B2** — 5–10 domande di esempio raccolte per test del sistema
- [ ] **B3** — Numero di utenti simultanei stimato
- [ ] **B3** — Architettura di deployment scelta in base al carico

### C. Qualità e Affidabilità
- [ ] **C1** — Livello di tolleranza alle allucinazioni definito
- [ ] **C1** — Temperature impostata in base alla criticità dei dati
- [ ] **C1** — Soglia di similarity per fallback definita
- [ ] **C1** — Comportamento di fallback progettato (messaggio, topic disponibili)
- [ ] **C2** — Livello di citazione delle fonti scelto (0–5)
- [ ] **C2** — Metadata necessari per le citazioni inclusi nel piano di indicizzazione
- [ ] **C3** — Gestione domande fuori dominio definita (soglia / classificazione intent)
- [ ] **C3** — Logging dei fallback pianificato

### D. Architettura e Infrastruttura
- [ ] **D1** — Architettura scelta (full cloud / ibrida / on-premise) e motivata
- [ ] **D1** — Stack tecnologico completo documentato in `config/config.yaml`
- [ ] **D2** — Latenza target definita e streaming abilitato se necessario
- [ ] **D3** — Budget operativo mensile stimato per scenario di utilizzo atteso
- [ ] **D4** — Integrazioni con sistemi esistenti identificate e livello definito
- [ ] **D4** — Autenticazione pianificata (nessuna / API key / OAuth)

### E. Retrieval e Chunking
- [ ] **E1** — Strategia di retrieval scelta (semantica / BM25 / ibrida)
- [x] **E1** — Re-ranking valutato: escluso nella fase iniziale, aggiunto solo se Hit Rate@5 < 80%
- [ ] **E2** — Terminologia di dominio censita (acronimi, codici, sigle)
- [ ] **E2** — Synonym expansion o BM25 pianificato se necessario
- [ ] **E1** — Test set per valutazione Hit Rate@5 pianificato

### F. Manutenzione e Monitoraggio
- [ ] **F1** — Gestore post-deploy identificato (tecnico / non tecnico / automatico)
- [ ] **F1** — Script o UI di gestione corpus pianificata
- [ ] **F1** — Documentazione operativa inclusa nel piano
- [ ] **F2** — Logging strutturato (JSONL) pianificato fin dall'inizio
- [ ] **F2** — Meccanismo di feedback utente progettato
- [ ] **F2** — Frequenza di valutazione qualità definita (manuale o RAGAS)

### Setup tecnico
- [x] Struttura cartelle professionale creata
- [x] Ambiente virtuale creato (installazione requirements pending: VS Build Tools)
- [x] `config/config.yaml` con tutti i parametri (no hardcoding)
- [x] `.env.example` con tutte le variabili d'ambiente necessarie
- [x] `.gitignore` configurato (`.env`, `data/raw/`, vector store)
- [x] Repository Git inizializzato (commit: d7c8745)
- [x] `README.md` con obiettivo, stack, istruzioni di esecuzione
- [x] Baseline definita: B0 (LLM senza RAG) + B1 (RAG con top-1) → confronto con pipeline completa

---

## Checklist di chiusura progetto

Da completare **prima di considerare il progetto finito**.

### Codice e struttura
- [ ] Struttura cartelle ordinata e coerente con lo standard
- [ ] Codice modulare in `src/`, notebook solo per EDA/prototipazione
- [ ] Naming convention rispettata su tutti i file (lowercase, underscore, ISO date)
- [ ] Nessun parametro hardcodato (tutto in `config/config.yaml`)
- [ ] Nessuna API key nel codice (solo in `.env`)
- [ ] Logging al posto dei `print()` nel codice finale
- [ ] Docstring su tutte le funzioni principali

### Pipeline RAG
- [ ] Parser funzionante sui formati previsti
- [ ] Chunking verificato su documenti reali (chunk coerenti, no troncature su concetti chiave)
- [ ] Metadata salvati correttamente su ogni chunk (`source`, `page`, almeno)
- [ ] Retrieval testato: Hit Rate@5 calcolato su set di domande di esempio
- [ ] Soglia di similarity calibrata sul corpus reale
- [ ] Fallback funzionante su domande fuori dominio
- [ ] Citazione delle fonti presente nell'output

### Qualità e robustezza
- [ ] Test minimi presenti ed eseguibili (`tests/`)
- [ ] Seed random fissato dove applicabile
- [ ] Sistema testato con documenti diversi da quelli usati in sviluppo
- [ ] RAGAS calcolato su mini test set (o valutazione manuale documentata)

### Deploy e visibilità
- [ ] App Streamlit avviabile con un solo comando
- [ ] Script `run.py` o istruzioni chiare nel README
- [ ] Output visibile e condivisibile (demo, screenshot, video)

### Documentazione
- [ ] `README.md` completo con tutte le sezioni (obiettivo, dataset, metodologia, risultati, impatto, istruzioni)
- [ ] Sezione "Limiti noti" nel README con esempi di domande fuori dominio
- [ ] Retrospettiva scritta (cosa ha funzionato, cosa rifarei, cosa ho imparato)
- [ ] Progetto pubblicato su GitHub con descrizione e tag

---

> **Test finale:** apri il repo come se fossi un recruiter.
> In 60 secondi capisci cosa fa, perché serve e che valore ha?
> Se sì → è pronto.
