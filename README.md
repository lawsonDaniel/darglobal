# DarGlobal Property Assistant

An AI chatbot for **DarGlobal's 38 projects** and **villas for sale in nine Saudi cities on Wasalt.sa**, built on public data collected for this assignment. It uses a **LangChain agent** on free OpenRouter models, a **vector index** of all the data, checks every answer against the data before showing it, and is packaged with Docker.

- **Live URL:** https://darglobal-production-7f7e890b.up.railway.app
- **Stack:** Python 3.13, LangChain 1.5 (`create_agent` + middleware), FastAPI, WordLlama embeddings, BM25, Docker
- **Model:** `nvidia/nemotron-3-ultra-550b-a55b:free` on OpenRouter, falling back to `nvidia/nemotron-3.5-super-vl:free`, then `openrouter/free`
- **Audit of the first version and fixes:** [AUDIT.md](AUDIT.md)

## What it can answer

| Ask about | Example |
|---|---|
| DarGlobal projects by country, brand, status, bedrooms, completion | "Trump-branded projects completing by 2029" |
| One project in detail | "Tell me about The Astera" |
| Descriptive questions | "Homes by the sea", "family resort for kids" |
| Saudi villas by city, district, price, size, bedrooms | "Villas in Riyadh under 2M SAR with 5+ bedrooms" |
| City comparisons and one listing | "Compare median prices across cities", "listing 5971799" |
| Contacts | "How can I contact DarGlobal?" |
| Arabic | "فلل للبيع في الخبر بأقل من مليون ونصف" |
| Anything not in the data (web search, optional) | "DarGlobal's latest results" |

## How it works

```
Browser ─► FastAPI  (rate limits, sessions, CSP)
              │
              ▼
        LangChain agent (create_agent)
          middleware: model fallback · call limits · PII redaction of user input
              │ tool calls (validated by Pydantic)
              ├─► structured tools ── filters, rankings, medians, contacts (Python, exact)
              ├─► search_knowledge ── hybrid retrieval: vectors + BM25 over 306 documents
              └─► web_search ─────── Tavily or Firecrawl, only when the data has no answer
              │
              ▼
        Answer checks ── links, phone numbers and figures must match the tool results
              │           (one rewrite if a figure is unsupported)
              ▼
           Reply + sources
```

### Agent (LangChain)
- `create_agent` with 11 read-only tools, plus `web_search` when a search key is set. Every argument is validated by a Pydantic schema; invalid arguments go back to the model as an error it can fix.
- Middleware:
  - `ModelFallbackMiddleware` tries the next free model on errors or rate limits.
  - `ModelCallLimitMiddleware` (6 calls) and `ToolCallLimitMiddleware` (10 calls, 2 web searches) cap each question.
  - `PIIMiddleware` redacts e-mails, card numbers and phone numbers in user messages before they reach the third-party model.
- If no available model supports tool calling, a fallback answers from rule-picked tool results plus retrieved documents.

### Vector index
- `app/knowledge.py` turns the data into 306 LangChain `Document`s: 38 projects, 245 listings, 9 city summaries, 4 Wasalt projects, the company profile, 6 press headlines, 2 contact records and the dataset notes.
- **Embeddings:** WordLlama (256 dimensions). Its 16 MB weights ship inside the pip package, so the index builds offline at Docker build time and the app stays around 140 MB of RAM. The free Render plan allows 512 MB.
- **Store:** LangChain `InMemoryVectorStore`, saved to `data/index/` by `python -m app.build_index`. A content fingerprint triggers a rebuild if the data or documents change.
- **Hybrid search:** vector similarity plus BM25 keywords, merged by reciprocal rank fusion. Arabic text is normalised (أ/إ/آ → ا, ة → ه, diacritics removed). Arabic queries rely on keywords, since the embedding model is English-centric.
- **Measured** on 40 test questions (`python -m eval.run_retrieval`):

  | Search | hit@1 | hit@3 |
  |---|---|---|
  | Vectors only | 0.65 | 0.80 |
  | BM25 only | 0.90 | 0.975 |
  | **Hybrid** | **0.90** | **1.00** |

### Accuracy
1. **Numbers come from Python, not the model.** Prices, counts, medians and filters are computed by the tools. Free-text DarGlobal fields are normalised: bedrooms, sizes in sqm, completion year, status flags.
2. **Every answer is checked** (`app/guards.py`):
   - **Links:** links not found in the data or in this turn's tool results are removed.
   - **Phone numbers:** only the official company numbers may appear.
   - **Figures:** prices and counts must match the evidence, allowing for rounding ("2.15M") and simple differences. Otherwise the model rewrites once, and anything still unverified is flagged to the user.
3. **Grounding rules:** cite links, say SAR, flag that Wasalt is a sample, add "Source: Wasalt.sa", and say when the data has no answer. Temperature is 0.1.
4. **Evals:**
   - `eval/run_retrieval.py` measures search quality offline.
   - `eval/run_qa.py` runs 15 live questions (facts, contacts, Arabic, off-topic, prompt injection) against the agent or a deployed URL.

### Security
- **Sessions:** history is kept on the server. The browser holds only a random session id and sends one message at a time (max 1,500 characters, 8 KB body).
- **Rate and cost limits:** per IP per minute and per day, a global daily cap and a concurrency limit. The client IP comes from the proxy-appended `X-Forwarded-For` entry, so a spoofed header doesn't bypass the limits.
- **Browser protections:** strict Content-Security-Policy (no inline script), `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, HSTS. API responses are `no-store`, `/docs` is off, and errors are generic.
- **Personal data:** user PII is redacted before it reaches the model. No agent or owner contact details are stored or shown.
- **Prompt injection:** tools are read-only. Web and tool text is treated as data, and the output checks above catch links, numbers and figures that did not come from the evidence.
- **Container:** non-root, compilers only in the build stage, exact dependency pins. Compose runs it read-only with all capabilities dropped.

## The data

Collected 18-19 Nov 2026 with Firecrawl from public pages (see `scraper/README.md`).

| File | Rows | What |
|---|---|---|
| `darglobal_projects.json` | 38 | Every project on darglobal.co.uk/projects: country, location, property types, completion, bedrooms, unit sizes, status, brand partner, URL |
| `wasalt_villas.json` | 245 | Villas for sale: first results page of nine Saudi cities. Price (SAR), area, SAR/sqm, bedrooms, district, facing, street width, URL |
| `wasalt_city_summary.json` | 9 | Result counts Wasalt shows per city (16,618 in total) and medians of the collected rows |
| `wasalt_projects.json` | 4 | Projects on Wasalt's Riyadh villas page, with "from" prices |
| `contacts.json` | | DarGlobal WhatsApp (+971 800 40409), phone shown to US visitors, register-interest form; Wasalt customer service (8001233227) |
| `darglobal_company.json` | | Company profile: London Stock Exchange listing, 11 brand partners, recent press links |
| `meta.json` | | Collection date, method, limits |

**Limits:**
- **Wasalt is a sample.** It's the newest listings per city, not the full market. Wasalt's AI policy disallows scraping its internal search results.
- **No DarGlobal prices.** DarGlobal's pages show no prices or payment plans.
- **Company contacts only.** No contact details of individual Wasalt agents or owners were collected; the bot points to the listing page.
- **Non-commercial use only**, for this assignment. Wasalt content is attributed as "Source: Wasalt.sa".

## Run it

```bash
cp .env.example .env              # add OPENROUTER_API_KEY (and optionally TAVILY_API_KEY)
docker compose up --build         # http://localhost:8000
```

Without Docker:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.build_index         # build the vector index
pytest -q                         # 36 tests; no keys needed (OpenRouter and search are faked)
python -m eval.run_retrieval      # retrieval quality
uvicorn app.main:app --reload
python -m eval.run_qa             # live answer eval (needs OPENROUTER_API_KEY; ~45 requests)
```

## Deploy (Render, free plan)

1. Push this folder to a **private** GitHub repo.
2. On render.com choose **New → Blueprint** and pick the repo; it reads `render.yaml`.
3. In the Environment tab, set:
   - `OPENROUTER_API_KEY`
   - `APP_URL` (your Render URL)
   - optionally `TAVILY_API_KEY` or `FIRECRAWL_API_KEY` for web search
4. Open `https://<service>.onrender.com/api/health`. It should show `"key_set": true`, the index source, and the web search provider.
5. Run `python -m eval.run_qa --url https://<service>.onrender.com` to test the live deployment.

**Free-tier notes:**
- Render's free plan sleeps when idle, so the first request takes 30-60 s.
- OpenRouter's free models allow about 50 requests a day per account (more after a one-time credit top-up). Each answer uses 2-4.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | (required) | OpenRouter key |
| `OPENROUTER_MODELS` | `nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3.5-super-vl:free,openrouter/free` | Models tried in order |
| `TAVILY_API_KEY` / `FIRECRAWL_API_KEY` | (off) | Turn on web search |
| `RATE_LIMIT_PER_MIN` / `RATE_LIMIT_PER_DAY` | 8 / 60 | Per-IP limits |
| `GLOBAL_LIMIT_PER_DAY` | 400 | Total chats per day (protects the free quota) |
| `MAX_CONCURRENT_CHATS` | 4 | Parallel chats |
| `TRUSTED_PROXY_HOPS` | 1 | Proxies in front (Render: 1; local: 0) |
| `VERIFY_ANSWERS` | 1 | Rewrite answers with unverified figures |
| `ENABLE_DOCS` | 0 | Expose `/docs` |

## API

- `POST /api/chat` takes `{"message": "...", "session_id": "..."}` and returns `{"session_id", "reply", "sources", "mode", "model", "tools_used", "checks"}`.
- `POST /api/reset` takes `{"session_id": "..."}` and forgets that conversation.
- `GET /api/health` returns data counts, index, models, whether the key is set, and the web search provider.

## Project layout

```
app/
  main.py          FastAPI app, routes
  agent.py         LangChain agent, middleware, no-tools fallback, answer checks
  lc_tools.py      LangChain tools with Pydantic schemas
  tools.py         data functions (filters, stats, normalisation)
  knowledge.py     data -> LangChain Documents
  embeddings.py    WordLlama embeddings for LangChain
  retrieval.py     hybrid vector + BM25 search, index persistence
  build_index.py   builds data/index at Docker build time
  guards.py        link, phone and figure checks
  security.py      client IP, rate limits, body cap, security headers
  sessions.py      server-side conversation memory
  websearch.py     optional Tavily / Firecrawl search
  rules.py         context picking for the no-tools fallback
  static/          chat page (HTML, CSS, JS; no inline code)
data/processed/    the dataset
eval/              retrieval and live-answer evaluations
tests/             36 tests
```
