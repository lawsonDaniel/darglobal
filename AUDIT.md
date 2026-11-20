# Audit of the first version, and what changed

Scope: the first version of the chatbot (hand-written agent loop, `app/agent.py`, `app/tools.py`, `app/main.py`, `app/static/index.html`, `Dockerfile`), reviewed on 19 Nov 2026. Each finding lists the problem, its effect, and the fix in this version. Status is checked by tests in `tests/`.

Severity: **High** = exploitable or produces wrong answers in normal use. **Medium** = real risk with some effort or in edge cases. **Low** = hardening.

## Security

| # | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| S1 | High | `/api/chat` accepted the whole conversation from the browser, including `assistant` turns, with no cap on the number of messages. A caller could plant fake assistant statements and send arbitrarily large payloads. | Conversation history is kept on the server. A request carries one message (max 1,500 characters) and an opaque random session id. History is capped at 12 messages, sessions expire after 2 hours, and at most 2,000 are kept. | `test_server_side_sessions`, `test_session_store_bounds` |
| S2 | High | Rate limiting used the first `X-Forwarded-For` entry, which the client controls. Rotating that header gave unlimited requests and could drain the free model quota. | The client IP is taken from the entry our own proxy appends (`TRUSTED_PROXY_HOPS`, 1 on Render). Limits apply per IP per minute and per day, plus a global daily cap and a cap on concurrent chats. | `test_spoofed_forwarded_for_does_not_bypass_limits`, `test_rate_limit_per_ip`, `test_global_daily_cap` |
| S3 | Medium | No request body size limit. | 8 KB cap with HTTP 413, also enforced for chunked uploads. | `test_input_limits` |
| S4 | Medium | No security headers. The page used inline script and styles, so a CSP could not be strict. | The JS and CSS moved to static files. A strict Content-Security-Policy (`script-src 'self'`, no inline code, `frame-ancestors 'none'`) is added, plus `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS, COOP and CORP. The `Server` header is removed and API responses are `no-store`. | `test_security_headers` |
| S5 | Medium | Personal data flowed freely. E-mails, card numbers or phone numbers typed by users went to the third-party model. The model could print any phone number, for example an agent's number found through web search. | LangChain `PIIMiddleware` redacts e-mails, card numbers and phone numbers in user input before it reaches the model. The output check allows only the official company numbers. | `test_tool_loop_checks_and_input_redaction`, `test_phones` |
| S6 | Medium | Web search results reached the model with only a textual warning, a prompt-injection path. | The system prompt treats tool and web text as data. The tools are read-only, so injected text cannot trigger an action. Output checks require links, phone numbers and figures to come from evidence. Web search is capped at 2 calls per question, and `site` is validated as a bare domain. | `test_web_search_tool`, `test_links` |
| S7 | Low | `/docs` and `/openapi.json` were public. | Off unless `ENABLE_DOCS=1`. | `test_docs_are_off_by_default` |
| S8 | Low | Dependencies were version ranges, not pins. | Exact pins, the versions the tests ran with. A multi-stage image keeps compilers out of the runtime stage. The container runs as a non-root user. Compose runs it read-only with `no-new-privileges` and all capabilities dropped. | clean-install run (see below) |
| S9 | Low | `uvicorn --forwarded-allow-ips='*'` trusted proxy headers from anyone. | Removed; IP handling is S2. | `test_client_ip_rules` |

## Reliability

| # | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| R1 | High | Bad tool arguments crashed the request. `int(limit)` on text raised `ValueError`, which nothing caught, so the user got HTTP 500. Prices sent as text raised `TypeError`. | Every tool has a Pydantic schema with types, ranges and enums. Invalid arguments go back to the model as a readable error so it can retry. | tool validation in `app/lc_tools.py` |
| R2 | Medium | A single question had no overall deadline: up to 5 tool rounds × 3 models × 60 s. | 90 s deadline per question, at most 6 model calls and 10 tool calls (2 web searches). | `test_call_limit_still_answers_from_tool_results` |
| R3 | Medium | The agent loop was hand-written, including provider error parsing and fallback. | Rebuilt on LangChain `create_agent`. Middleware handles fallback across free models, call limits and PII redaction. A no-tools fallback keeps working when no model supports tool calling. | `test_falls_back_to_second_model`, `test_no_tool_models_use_retrieval_fallback` |
| R4 | Low | A rejected API key and an outage looked the same to the user. | A rejected key gives a configuration error and outages give a busy message. Neither leaks upstream details. | `test_bad_key_is_a_config_error`, `test_all_models_down_is_busy`, `test_errors_are_generic` |

## Accuracy

| # | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| A1 | High | Nothing checked the final answer. The model could invent prices, links or phone numbers. | Every reply is checked against this turn's tool results. Unknown links are removed and non-official numbers are replaced. Figures not found in the evidence trigger one rewrite, and anything still unverified is flagged to the user. | `test_unsupported_figure_triggers_one_rewrite`, `tests/test_guards.py` |
| A2 | Medium | DarGlobal details were free text ("Studio, 1, 2, 3", sizes in sqm, sqft or no unit, "Q4 2026"), so they could not be filtered. | Normalised fields: bedrooms min/max, sizes in sqm (sqft converted, unit-less flagged), completion year, completed and sold-out flags. New filters: `min_bedrooms`, `completion_by_year`, `status`. | `test_parse_bedrooms_and_sizes`, `test_project_filters` |
| A3 | Medium | Word-overlap matching missed descriptive questions ("homes by the sea"). Arabic spelling variants (ة/ه, أ/ا) did not match. | Hybrid retrieval over 306 documents: vector search (LangChain `InMemoryVectorStore`, WordLlama embeddings) plus BM25 keywords, fused by reciprocal rank, with Arabic normalisation. On 40 test questions: **hit@1 0.90, hit@3 1.00** (vector alone 0.65 / 0.80, keywords alone 0.90 / 0.975). | `test_hybrid_quality_floor` |
| A4 | Low | An ambiguous project name silently returned the first match. | Other equally good matches are returned alongside it. | `test_get_project_and_ambiguity` |
| A5 | Low | There was no way to look up a listing by its number. | `get_wasalt_listing` tool. | `test_listing_and_stats` |

## Remaining risks

- Free models vary in quality, and `openrouter/free` may route to a different model per call, so answers are not deterministic. The checks catch invented links, numbers and figures, not every wrong sentence.
- OpenRouter's free tier allows about 50 requests a day per account; one answer uses 2 to 4.
- Rate limits and sessions are in memory: they reset on restart and are per instance. That is fine for one free instance; several instances would need Redis.
- The data is a snapshot (18-19 Nov 2026), and Wasalt is a sample of the first results page per city.
- Live answer quality depends on the model and was not measured here (no key in this environment). Run `python -m eval.run_qa` with your key (15 questions, about 45 requests).

## How this was verified

- 36 automated tests (`pytest`), including the real LangChain agent against a fake OpenRouter server.
- A clean install from `requirements.txt` in a new virtual environment: the index was built, then the server was run from a read-only directory. Health, headers, docs-off and the missing-key path were checked. Memory was about 140 MB after start-up.
- Retrieval quality measured with `python -m eval.run_retrieval`.
