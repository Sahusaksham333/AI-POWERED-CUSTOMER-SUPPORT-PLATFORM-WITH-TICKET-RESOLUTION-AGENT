# SupportPilot — AI Ticket Resolution Agent

A local-first starter codebase for multilingual support-ticket classification, multi-label tagging, TextCNN benchmarking, retrieval-augmented generation (RAG), and human-reviewed response drafting. It is adapted to the provided CSV schema (`subject`, `body`, `answer`, `type`, `queue`, `priority`, `language`, `tag_1`–`tag_8`).

> **Important scope note:** this is an MVP scaffold, not a certified enterprise helpdesk. It does not automatically resolve tickets or perform system changes. Generated responses are drafts. Human review remains necessary, particularly for security incidents and widespread outages. The sample knowledge article is illustrative only and must be replaced with approved organizational documentation.

## Stack

- **Supervised multilingual NLP:** `FacebookAI/xlm-roberta-base` for `queue`, `type`, or `priority` classification.
- **Multi-label tagging:** XLM-RoBERTa with sigmoid outputs, trained over the most common tags in `tag_1`…`tag_8`.
- **CNN benchmark:** a custom PyTorch TextCNN uses XLM-R tokenizer IDs. This is a text CNN; the provided CSV has no image labels. An image CNN would require a separate image dataset.
- **RAG:** multilingual MiniLM embeddings + persistent Chroma collection.
- **Local LLM:** Gemma via native Ollama for grounded response drafting.
- **App:** FastAPI + SQLite + Streamlit.
- **Optional integrations:** explicitly invoked Jira Cloud and SMTP endpoints; credentials remain in `.env`.

## 1. Prerequisites

- Windows 10/11
- Python 3.11 recommended
- NVIDIA driver for your RTX 4060 8 GB
- [Ollama for Windows](https://ollama.com/download/windows)
- The provided CSV, copied into `data/` or referenced with `SUPPORTPILOT_DATA_PATH`

The dataset itself is not embedded in this ZIP. This avoids duplicating a large data file and reduces the risk of committing customer-like text to source control.

## 2. Setup (PowerShell)

From the extracted `SupportPilot` project folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

Install a PyTorch wheel compatible with the active Windows/Python/CUDA configuration. This example uses the CUDA 13.0 wheel index; if no compatible wheel is offered, choose a supported configuration at https://pytorch.org/get-started/locally/.

```powershell
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
python -m pip install -r requirements.txt
```

Verify GPU availability:

```powershell
nvidia-smi
python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
```

If `torch.cuda.is_available()` is `False`, fix the PyTorch / driver combination before training. CPU training still works but will be much slower.

## 3. Configure data and local LLM

Run a quick environment check after dependency installation:

```powershell
python scripts/check_environment.py
```


Copy the file `aa_dataset-tickets-multi-lang-5-2-50-version.csv` into `data/`. To configure other paths and integrations, create `.env` from the template:

```powershell
Copy-Item .env.example .env
```

Then set or confirm these values in `.env`:

```dotenv
SUPPORTPILOT_DATA_PATH=data/aa_dataset-tickets-multi-lang-5-2-50-version.csv
SUPPORTPILOT_OLLAMA_MODEL=gemma3:4b
```

PowerShell can also set the CSV path for the current session:

```powershell
$env:SUPPORTPILOT_DATA_PATH = "C:\full\path\to\aa_dataset-tickets-multi-lang-5-2-50-version.csv"
```

Pull and verify Gemma:

```powershell
ollama pull gemma3:4b
ollama run gemma3:4b
```

In a second shell, run `ollama ps` to inspect which model is loaded and whether it is using the GPU. Gemma is an inference model here; the classification models are fine-tuned separately.

## 4. Train supervised models

Start with **one classifier**, typically `queue`:

```powershell
python training/train_classifier.py --target queue --epochs 3 --batch-size 4
```

Optional separate models:

```powershell
python training/train_classifier.py --target priority --epochs 3 --batch-size 4
python training/train_classifier.py --target type --epochs 3 --batch-size 4
python training/train_tags.py --top-tags 30 --epochs 3 --batch-size 4
```

The single-label classifier uses an 80/10/10 train/validation/test split. The held-out test set is only evaluated after checkpoint selection. The tag model uses a held-out test split and reports top-3 hit rate and overlap ratio. Evaluate per-class precision/recall too before deciding these models are production-ready.

**GPU guidance:** XLM-RoBERTa-base has approximately 278M parameters. The scripts use batch size 4, accumulation 4, a maximum length of 192 tokens, and FP16 when CUDA is available. If you run out of VRAM, use `--batch-size 2` or `--max-length 128`. Do not train a model at the same time as using Gemma on the 8 GB GPU.

Train the TextCNN benchmark (optional):

```powershell
python training/train_textcnn.py --target queue --epochs 4 --batch-size 32
```

The trained Hugging Face artifacts are saved under `artifacts/queue`, `artifacts/priority`, `artifacts/type`, and `artifacts/tags`. These artifacts are intentionally not bundled: they need to be trained for your local environment and are too large for a source-code-only package.

## 5. Index the knowledge base

Replace the sample article with approved company troubleshooting guides under `knowledge_base/`. Supported formats are `.md`, `.txt`, `.pdf`, and `.docx` (text PDFs only; scanned PDFs are not OCRed).

```powershell
python scripts/index_knowledge_base.py --reset
```

This downloads the multilingual embedding model the first time and writes the Chroma index to `artifacts/chroma`. Restart the API process after indexing if it was already running. Run the script again after updating approved knowledge articles. `--reset` rebuilds the collection; omit it to upsert newly indexed chunks without removing old chunks.

## 6. Start the app

Terminal 1 — API:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 — Streamlit dashboard:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app/dashboard.py
```

Open:

- Dashboard: http://localhost:8501
- Swagger API documentation: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

API endpoints:

- `POST /tickets/predict` — classify and tag a ticket.
- `POST /tickets/resolve` — retrieve knowledge articles and draft a response with Ollama.
- `GET /analytics` — dashboard metrics from local SQLite.
- `GET /tickets/{ticket_id}` — retrieve a stored ticket record.
- `POST /integrations/jira` — explicitly create a Jira issue for a stored ticket (optional configuration required).
- `POST /integrations/email` — explicitly send the response draft for a stored ticket (optional SMTP configuration required).

Example API payload:

```json
{
  "subject": "VPN connection fails after sign-in",
  "body": "I can access the internet, but the VPN client fails with an authentication error.",
  "language": "en"
}
```

The app does not infer labels with a fake model when trained artifacts are missing; the dashboard shows that the model is unavailable. `/tickets/resolve` may still draft a generic response through Ollama, but if no knowledge sources are retrieved it flags the ticket for human review. This is intentional.

## 7. GPU / memory behavior

By default, online classifier inference runs on **CPU**, leaving the 8 GB RTX 4060 available to Ollama/Gemma. This can make classification slower but reduces GPU memory contention when both transformer classifiers and a generative model are used in the same app. You may test GPU inference by setting:

```powershell
$env:SUPPORTPILOT_CLASSIFIER_DEVICE = "cuda"
```

Only do so after checking combined peak VRAM consumption and latency. Avoid loading many separate XLM-R checkpoints onto the GPU while Gemma is also resident. On an 8 GB card, use quantized Gemma and keep context sizes modest.

## 8. Optional Jira / email configuration

Copy `.env.example` to `.env`, then fill in only the service credentials you actually use. Do not commit `.env`. The endpoints are opt-in and are not called automatically.

For Jira Cloud, provide `SUPPORTPILOT_JIRA_BASE_URL`, `SUPPORTPILOT_JIRA_EMAIL`, `SUPPORTPILOT_JIRA_API_TOKEN`, and `SUPPORTPILOT_JIRA_PROJECT_KEY`. Ensure the token has only the minimum required permissions.

For email, provide `SUPPORTPILOT_SMTP_HOST`, `SUPPORTPILOT_SMTP_PORT`, `SUPPORTPILOT_SMTP_USERNAME`, `SUPPORTPILOT_SMTP_PASSWORD`, and `SUPPORTPILOT_SMTP_FROM`. Test using a development mailbox before real users.

## 9. Tests and code checks

```powershell
pytest -q
ruff check app training scripts tests
```

## 10. Data and model limitations

- The supplied dataset has `priority`, not a separately verified `severity` label. Do not report severity prediction performance without collecting or defining severity labels.
- Dataset historical `answer` text is not treated as verified ground truth for current resolutions. Ground responses in current, approved knowledge documents.
- Initial heuristic escalation flags are conservative rules, not a calibrated risk model. Tune and validate them with support engineers.
- No ticket-closing or system-changing action is automated. Jira issue creation and SMTP sending require explicit endpoint calls.
- Use an untouched, preferably time-based or duplicate-aware test set. Report macro-F1 and class-level recall, not just accuracy.
- For production, add authentication, authorization, rate limits, audit retention rules, secret management, observability, migrations, model versioning, and security review.
