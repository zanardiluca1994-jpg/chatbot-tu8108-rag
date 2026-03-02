.PHONY: install build-index run eval eval-full test clean

## Installa le dipendenze nel virtualenv attivo
install:
	pip install -r requirements.txt

## Costruisce l'indice FAISS dal PDF (eseguire una volta sola)
build-index:
	python scripts/build_index.py

## Avvia il chatbot Streamlit
run:
	streamlit run src/visualization/app.py

## Valutazione rapida (B0 + B1 + B_full, senza query rewriting)
eval:
	python scripts/eval_baseline.py --no-rewrite

## Valutazione completa (include B_full_rw con query rewriting LLM)
eval-full:
	python scripts/eval_baseline.py

## Esegue i test unitari
test:
	pytest tests/ -v

## Rimuove cache Python
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	echo "Cache rimossa."
