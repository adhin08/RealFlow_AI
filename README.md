# 🚀 RealFlow AI

**AI-powered n8n workflow generator**

Turn natural language into production-ready n8n automations in seconds.

```
"Send a Slack message when a new Shopify order comes in"
    ↓
[Complete n8n workflow JSON with validation]
```

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🧠 **2,057 Templates** | Prebuilt Chroma DB (1,927 V3 + 130 V2 fallback) |
| ✅ **Validation** | Schema checks + n8n operation validator |
| 📊 **Confidence Scores** | Confidence + explanation per workflow |
| 🔌 **REST API + CLI** | Generate via FastAPI or local script |
| ⚡ **n8n Upload/Test** | Optional upload + test-run (if N8N_URL/API key set) |
| 🧭 **RAG Routing** | Service/category-aware reranking |

---

## 🚀 Quick Start

> Requires Python 3.10+ and `pip`. The vector store (`chroma_db/`) is already bundled—no extra ingest needed.

### 1) Install
```bash
pip install -r requirements.txt
```

### 2) Configure env
```bash
# LLM (one of)
export OPENROUTER_API_KEY="your-key"   # recommended, has free models
# or
export OPENAI_API_KEY="your-openai-key"

# Optional: for n8n upload/test
export N8N_URL="http://localhost:5678"
export N8N_API_KEY="your-n8n-api-key"

# Optional: force RAG version (defaults to v3)
export RAG_VERSION="v3"
```

### 3) Run the CLI
```bash
python src/ai_build_and_test.py "Send Telegram message when new Shopify order" \
  --top-k 3 --rag-version v3
# List free OpenRouter models:
python src/ai_build_and_test.py --list-models
```

Outputs land in `generated_workflows/` (JSON) and `generated_workflows/last_prompt.txt`.

### 4) Run the API
```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000
# Swagger UI: http://localhost:8000/docs
```

### 5) Deploy on Render (optional)
- `render.yaml` is included.
- Build: `pip install -r requirements.txt`
- Start: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Set env vars in Render dashboard: `OPENROUTER_API_KEY`, `N8N_URL`, `N8N_API_KEY`, `RAG_VERSION=v3`
- Persist the vector store by mounting a disk to `chroma_db/` (paid plans) or ship the prebuilt folder.

---

## 🧠 RAG Data (what’s included)
- `chroma_db/` ships with:
  - `n8n_workflows_v3`: **1,927** workflows (default)
  - `n8n_workflows`: **130** workflows (v2 fallback)
- The API sets `RAG_VERSION=v3` automatically; the CLI respects `--rag-version`.
- Rebuilding the DB (advanced): place raw `.json` workflows in the repo (e.g., `workflows/`) then run:
  ```bash
  python -m src.rag_v3.pipeline
  ```
  This regenerates `data/template_descriptions_v3.jsonl` and ingests into `chroma_db/n8n_workflows_v3`. (Raw workflow files are not included in this repo.)

---

## 📁 Project Structure

```
.
├── src/                     # Source
│   ├── api.py               # FastAPI server
│   ├── ai_build_and_test.py # CLI entrypoint
│   ├── rag.py               # Retrieval + prompt builder
│   ├── ai_builder.py        # Prompt + LLM helpers
│   ├── validator.py         # Workflow validation + confidence
│   ├── n8n_client.py        # n8n upload/test helpers
│   ├── metadata_utils.py    # Reranking + parsing helpers
│   └── rag_v3/              # Data pipeline (optional rebuild)
│       ├── pipeline.py      # Orchestrates scan/sanitize/ingest
│       ├── scanner.py       # Finds workflow JSONs
│       ├── sanitizer.py     # Strips sensitive fields
│       └── metadata_extractor.py
├── chroma_db/               # Prebuilt Chroma collections (v2 + v3)
├── frontend/index.html      # Simple landing page (served at `/`)
├── output/                  # Sample generated workflow logs
├── render.yaml              # Render deployment config
├── requirements.txt
└── README.md
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Static landing page (if `frontend/index.html` exists) |
| GET | `/health` | Health + RAG info (`workflow_count` from Chroma) |
| POST | `/generate` | Generate workflow |
| GET | `/workflow/{id}` | Get a generated workflow |
| GET | `/workflows` | List recent generated workflows |

Example:
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"query": "Send Slack message when new email received"}'
```

---

## 🛠️ CLI Options (subset)

```bash
python src/ai_build_and_test.py "your query" [options]
  --top-k N          Number of reference workflows (default: 3)
  --rag-version v3   Choose RAG version (default: v3)
  --model MODEL      LLM model (default auto-picks best free OpenRouter model)
  --no-upload        Skip n8n upload even if configured
  --test-run         Attempt a test execution after upload
  --list-models      Show available free OpenRouter models
```

---

## 📝 License

MIT

