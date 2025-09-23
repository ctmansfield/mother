# mother (Nostromo)

A motherly, warm-but-firm nudging LLM. Local model on your main box; API+worker on the coach VM.

- Model: local Ollama (llama3.1:8b) via OpenAI-compatible API
- DB: Postgres at 192.168.1.225:55432
- Services (VM): FastAPI (`api.py`) and worker (nudges), via Docker Compose
