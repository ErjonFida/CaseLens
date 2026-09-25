# CaseLens

**Retrieval over legal documents, with the retrieval actually measured.** Upload
contracts, court transcripts or scanned filings; ask questions in natural
language; get answers that cite the filename and page they came from. Documents
are private to the account that uploaded them.

The part worth looking at is `evals/`: a 100-question evaluation suite built from
expert clause annotations, which reports what the retriever actually finds and
what the model then does with it, rather than asserting that either works.

| | |
|---|---|
| **Live demo** | _not yet deployed_ |
| **Evaluation suite** | [evals/README.md](evals/README.md) |
| **Current baseline** | recall@5 **0.702**, MRR **0.562** ([report](evals/reports/name-scoped.json)) |
| **Graded answers** | local `gemma4:e4b` 20 of 24 good, Gemini 22 of 24 ([workbook](evals/reports/faithfulness-grading-graded.xlsx)) |
| **Local setup** | [Running it](#running-it) |

---

## What it does

**Ingests.** PDF, TXT and image uploads up to 25 MB. Digital PDFs are read with
pdfplumber; when a page yields almost no text the file is treated as scanned and
re-read through Tesseract, converted one page at a time so a large scan cannot
exhaust memory.

**Indexes.** Pages are split into overlapping chunks, embedded, and stored in
PostgreSQL with pgvector. Each chunk records the model that embedded it, so
changing embedding models hides stale vectors instead of silently comparing
across two different vector spaces.

**Retrieves and answers.** A question that names a document ("the Acme
agreement") is matched against the user's filenames, and the search is
restricted to that document with the name removed from the query. Users can
also select the documents a question is about; a selection is searched as a
whole unless the question names one of them. The ten nearest chunks go to the
model, which streams an answer citing filename and page. With Gemini, a single
scoped document under 40k tokens is sent whole instead of as chunks. Answers
come from Gemini or from Gemma running locally through Ollama.

**Isolates.** Every document and chunk belongs to a user, and indexing,
retrieval and document selection all filter on that owner. Cross-tenant isolation has negative tests in
`backend/test_e2e.py`.

---

## Evaluation

To measure retrieval quality the suite runs the same scoping and retrieval
code the API calls, so the numbers describe the shipped retriever rather than
a reimplementation of it.

**Corpus:** 69 commercial contracts from [CUAD](https://www.atticusprojectai.org/cuad)
(Contract Understanding Atticus Dataset), 5,574 chunks.

**Questions:** 100, derived from CUAD's clause annotations — labelled by law
students under attorney supervision. Ground truth is a `(filename, page)` pair
found by locating each annotated span in the document, so no label points at a
page nobody read. `is_impossible` annotations supply questions about clauses a
contract lacks, where the right answer is that the clause is not there.

`nomic-embed-text`, 1000/150 chunking. Name-scoped is what the API serves;
dense is kept as the comparison point every change is measured against.

| Metric | Dense | Name-scoped |
|---|---:|---:|
| recall@5 | 0.340 | **0.702** |
| recall@10 | 0.397 | 0.730 |
| MRR | 0.298 | **0.562** |
| exact_term | 0.419 | 0.790 |
| semantic | 0.321 | 0.750 |
| multi_document | 0.204 | 0.300 |
| latency p50 / p95 | 113ms / 161ms | 88ms / 108ms |

**Name-scoping** resolves the contract from the question before searching, in
`resolve_scope`, which both API endpoints call. A
question that says "the {party} agreement" is matched against filenames, and
when one document clearly wins, the vector search is restricted to it. Each
question word is worth 1 / (number of filenames containing it), so the party
name that appears in one filename outweighs "agreement", which appears in all
69 — equal weighting had let any two "... Services Agreement" files tie with
the one being asked about. Matching is substring containment on a
punctuation-stripped filename rather than token matching, because the corpus
mixes "MERITLIFEINSURANCECO_..." with "Principal Life Insurance Company - ...",
and because stemming breaks names ("BloomEnergy" stems to "bloomenergi").

Once a document is resolved, its title is removed from the query before it is
embedded. Those words have done their job, and left in they pull the cover
page — where the party name and "AGREEMENT" sit in large type — into slots the
clause should have; page 1 was in the top 5 for 10 of 17 right-document
misses. "When does the Scoutcam agreement become effective?" is searched
within the Scoutcam contract as "When does the become effective?", which reads
badly and embeds well: inside one document, the clause is the only thing left
to find. Only the title *span* goes — the contiguous run of matched words
ending at the last one — so a topic word that also sits in a filename keeps
its own mention: "the termination terms in the Acme Termination Agreement"
becomes "the termination terms in the".

67 of the 74 single-document questions scope, none to the wrong contract; the
7 that abstain name a party with several contracts in the corpus, where a tie
is the right answer. Everything else falls back to unrestricted dense search,
so nothing regresses when a query names no document. Scoping is also faster,
because the scan is smaller.

The gold set is templated from CUAD
categories, so every question names its contract by construction. Real queries
often do not, and those take the dense path and the dense number.

**Selecting documents.** Users can pick the documents a question is about. In a
simulation, five selected contracts and a question about one of them,
searching all five scores recall@5 0.373 once the title is stripped: the
stripped question no longer says which contract, and all five have the
clause. Matching the name inside the selection and narrowing to that document
scores 0.860. The picker ships with the second rule.

**Hybrid retrieval was tried and rejected.** A `tsvector` channel fused with
the vector channel by reciprocal rank scored recall@5 0.126, well under the
dense baseline. Lexical alone scored 0.051 — near chance — because once the
party name is removed the remaining terms ("date", "agreement", "governing
law") appear in all contracts, and the party name is absent from the chunk
bodies: it lives in the filename.

**Reranking and other embedders were measured too.** Two cross-encoder
rerankers ordered pages worse than plain vector distance, even with the right
document handed over. `qwen3-embedding:4b` trades literal matching for
paraphrase; fused with nomic by reciprocal rank it lifts recall@10 by 0.07,
and is not shipped because it means a second 2.5 GB model in memory.

Anything claimed as an improvement will be measured against the committed
baseline report, one change at a time.

### Answers

Recall says whether the right page reached the model;
[`evals/faithfulness.py`](evals/faithfulness.py) measures what the model does
with it. 290 answers, from the local `gemma4:e4b` and from Gemini, were each
graded against the CUAD annotations:

- The local 4B model is in the same range as the hosted one: 20 good answers
  to Gemini's 22 on the same 24 questions.
- Ten retrieved chunks beat five for both.
- For Gemini, reading the whole document beats retrieval on contracts up to
  40k tokens: it stops declining questions whose answer was in front of it.
  For Gemma the whole document is worse; it extracts less reliably from a full
  contract than from focused chunks. Both behaviours ship.
- The failure that matters is substitution: asked about a clause the contract
  lacks, a model answers with a nearby one. One line in the system prompt
  removed it from both shipped paths (Gemini 2 to 0, Gemma 1 to 0) without
  adding a wrongful decline.

Grading is deterministic where it can be and a model judge where it cannot:
no regex tells a supported "no" from an assertion. The judge agrees with the
graded answers on 94% of good/not-good calls, and its calibration, including
where it disagrees, is in [evals/README.md](evals/README.md).

---

## Running it

Requires Docker and [Ollama](https://ollama.com) with `nomic-embed-text` pulled.

```bash
ollama pull nomic-embed-text
cp .env.example .env          # set GEMINI_API_KEY for answer generation
docker compose up -d db       # PostgreSQL 16 + pgvector
cd backend ; alembic upgrade head
```

Then the API and the frontend:

```bash
cd backend && uvicorn main:app --reload      # http://localhost:8000/docs
cd frontend && npm install && npm run dev    # http://localhost:3000
```

Embeddings run locally through Ollama by default, so indexing and the
retrieval evaluation cost nothing and work offline. Only answer generation
calls an API; to run fully offline, `ollama pull gemma4:e4b` and set
`LLM_PROVIDER=ollama`. Set `EMBEDDING_PROVIDER=gemini` to embed with Gemini
instead.

### Evaluation

```bash
python -m evals.corpus                      # index evals/corpus/
python -m evals.run --label my-experiment   # report to evals/reports/
python -m evals.faithfulness --cuad path/to/CUAD_v1.json   # answer-level eval
```

See [evals/README.md](evals/README.md) for the gold-set format and how to
reproduce the corpus.

---

## Architecture

```text
React 19 + Vite + Tailwind (shadcn/Radix)
      |
      v
FastAPI  --  JWT auth - per-IP rate limits - streaming responses
      |
      +--> OCR pipeline -- pdfplumber, with page-by-page Tesseract fallback
      |
      +--> Embedding provider -- Ollama (local) or Gemini, swappable by config
      |
      +--> PostgreSQL 16 + pgvector -- chunks, embeddings, users, documents
      |
      +--> Answer generation -- Gemini, or Gemma locally via Ollama, streamed
```

| Layer | Choice |
|---|---|
| API | FastAPI, SQLAlchemy 2.0 async, Alembic |
| Database | PostgreSQL 16 with pgvector (untyped `vector`, width per embedding model) |
| Embeddings | `nomic-embed-text` via Ollama, or `gemini-embedding-001`; `qwen3-embedding` measured, not shipped |
| Generation | `gemma4:e4b` via Ollama, or Gemini (`gemini-flash-latest`); streamed |
| OCR | pdfplumber, Tesseract + pdf2image fallback |
| Frontend | Vite, React 19, TypeScript, Tailwind, Radix |
| Auth | bcrypt, PyJWT, Bearer tokens |

### Decisions worth explaining

**Chunks record their embedding model.** Vectors from different models occupy
different spaces, and comparing across them returns a ranking that is meaningless
but entirely plausible-looking. Queries filter on the active model.

**Embeddings default to a local model.** Beyond cost, this is what makes the
evaluation reproducible: a chunking sweep re-embeds the whole corpus, and doing
that against an API is slow, rate-limited and expensive. Vectors are cached by
content hash, so repeated runs only embed what changed.

**Ground truth is a page, never a chunk id.** Chunk ids are a property of the
chunking configuration, and chunking is the first thing you change — labelling by
chunk id invalidates the dataset on the first sweep, and the resulting movement
looks like a retrieval change rather than broken labels.

**The eval validates its own labels.** A gold entry naming a document not in the
corpus fails the run instead of scoring zero. A mistyped filename and a genuine
retrieval failure are indistinguishable once averaged.

**A selection is a candidate set, not a scope.** Searching every selected
document with the question's title stripped scored 0.373, because the stripped
question no longer says which contract. The name match runs inside the
selection first, and a title is only stripped once a single document is in
scope.

**Whole-document context is a per-provider setting.** A rule of "whatever fits
in 60% of the window" would have sent Gemma the small documents where it
measured worse, so the limit comes from the measurements instead: off for
Ollama, 40k tokens for Gemini.

**The API and the eval share one prompt.** The system prompt and context
formats are imported by both, so the answer-level eval measures the prompt
that ships.

---

## Security

- Passwords hashed with bcrypt; sessions are signed JWTs (HS256) sent as a
  Bearer header. There is no cookie authentication, so a cross-site request
  cannot authenticate (`backend/test_csrf.py`), and CORS is pinned to
  `ALLOWED_ORIGINS`.
- Documents and chunks carry an owner; indexing, retrieval and document
  selection all filter on it. Cross-tenant negative tests in
  `backend/test_e2e.py`.
- Rate limits on auth (10/min) and query (30/min) are counted in PostgreSQL,
  so they hold across workers. `X-Forwarded-For` is honoured only from
  `TRUSTED_PROXIES`, so a client cannot choose its own bucket
  (`backend/test_limits.py`).
- Uploads are extension-allowlisted, filename-validated against path
  traversal, and streamed to disk with the 25 MB cap enforced mid-stream.
- Logins from an unrecognised device fingerprint trigger an email alert.

See [Known limitations](#known-limitations) for what this does **not** do.

---

## Known limitations

Specific and current.

1. **No vector index.** Retrieval is an exact scan, correct and fast enough at
   5,574 chunks (~113ms p50), but it will not scale. An HNSW index is worth
   adding once there is a latency number to improve on.

2. **Substitution is reduced, not ruled out.** A prompt line removed it from
   both shipped paths in the eval, but for the local model the fix is
   probabilistic: a second sample of the same question led with the adjacent
   clause again.

3. **Tokens live in `localStorage`.** That rules out CSRF entirely, and leaves
   the token readable by any script injected into the origin.

4. **The gold set is small and templated.** 100 questions, each naming its
   contract. A change has to move four or five answers to clear the noise, and
   questions that name no document are under-represented.

---

## Next

In order:

1. Deploy, with Gemini answering.
2. Section headings carried into chunks, then query rewriting, for the
   remaining within-document misses.
3. A larger gold set, once retrieval stops moving.

## Licence

MIT. CUAD is separately licensed CC BY 4.0 by the Atticus Project.
