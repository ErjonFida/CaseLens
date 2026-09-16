# CaseLens

**Retrieval over legal documents, with the retrieval actually measured.** Upload
contracts, court transcripts or scanned filings; ask questions in natural
language; get answers that cite the filename and page they came from. Documents
are private to the account that uploaded them.

The part worth looking at is `evals/`: a 100-question evaluation suite built from
expert clause annotations, which reports what the retriever actually finds rather
than asserting that it works.

| | |
|---|---|
| **Live demo** | _not yet deployed_ |
| **Evaluation suite** | [evals/README.md](evals/README.md) |
| **Current baseline** | recall@5 **0.702**, MRR **0.562** ([report](evals/reports/name-scoped.json)) |
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

**Retrieves and answers.** A question is embedded with the query-side encoding,
matched against the user's own chunks by vector distance, and the top matches are
passed to Gemini, which streams an answer citing filename and page.

**Isolates.** Every document and chunk belongs to a user, and both indexing and
retrieval filter on that owner. Cross-tenant isolation has negative tests in
`backend/test_e2e.py`.

---

## Evaluation

To measure retrieval quality the suite runs against the same
`query_similar_context` the API calls, so the numbers describe the shipped
retriever rather than a reimplementation of it.

**Corpus:** 69 commercial contracts from [CUAD](https://www.atticusprojectai.org/cuad)
(Contract Understanding Atticus Dataset), 5,574 chunks.

**Questions:** 100, derived from CUAD's clause annotations — labelled by law
students under attorney supervision. Ground truth is a `(filename, page)` pair
found by locating each annotated span in the document, so no label points at a
page nobody read. `is_impossible` annotations supply expert-verified
`unanswerable` questions.

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
`query_scoped_context`, which both API endpoints call. A
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

**Hybrid retrieval was tried and rejected.** A `tsvector` channel fused with
the vector channel by reciprocal rank scored recall@5 0.126, well under the
dense baseline. Lexical alone scored 0.051 — near chance — because once the
party name is removed the remaining terms ("date", "agreement", "governing
law") appear in all contracts, and the party name is absent from the chunk
bodies: it lives in the filename.

Anything claimed as an improvement will be measured against the committed
baseline report, one change at a time.

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

Embeddings run locally through Ollama by default, so indexing and the entire
evaluation suite cost nothing and work offline. Only answer generation calls an
API. Set `EMBEDDING_PROVIDER=gemini` to switch.

### Evaluation

```bash
python -m evals.corpus                      # index evals/corpus/
python -m evals.run --label my-experiment   # report to evals/reports/
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
      +--> Gemini -- streamed answer generation over retrieved context
```

| Layer | Choice |
|---|---|
| API | FastAPI, SQLAlchemy 2.0 async, Alembic |
| Database | PostgreSQL 16 with pgvector (`vector(768)`) |
| Embeddings | `nomic-embed-text` via Ollama, or `gemini-embedding-001`, Qwen3-embedding will also be tested |
| Generation | Gemma4:e4b local, Gemini, streamed |
| OCR | pdfplumber, Tesseract + pdf2image fallback |
| Frontend | Vite, React 19, TypeScript, Tailwind, Radix |
| Auth | bcrypt, PyJWT, HttpOnly cookies |

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

---

## Security

- Passwords hashed with bcrypt; sessions are signed JWTs (HS256) in `HttpOnly`
  cookies, `Secure` in production, `SameSite=Lax`.
- Documents and chunks carry an owner; indexing and retrieval both filter on it.
  Cross-tenant negative tests in `backend/test_e2e.py`.
- Per-IP sliding-window rate limits on auth (10/min) and query (30/min).
- Uploads are extension-allowlisted, size-capped, and filename-validated against
  path traversal.
- Logins from an unrecognised device fingerprint trigger an email alert.

See [Known limitations](#known-limitations) for what this does **not** do.

---

## Known limitations

Specific and current.

1. **No vector index.** Retrieval is an exact scan — correct and fast enough at
   5,574 chunks (~113ms p50), but it will not scale. An HNSW index is worth
   adding once there is a latency number to improve on.

2. **No query rewriting.** Retrieval is vector search, optionally scoped to one
   document by name. Hybrid lexical search, cross-encoder reranking, and two
   Qwen3 embedding models were each measured and rejected — see
   [evals/README.md](evals/README.md).

---

## Next

In order:

1. Query rewriting toward clause language, for the questions that name no
   document. Reranking and an embedding model swap were both measured and
   rejected first — see [evals/README.md](evals/README.md).
2. Chunking sweep.
3. Close limitations 1 and 2.

## Licence

MIT. CUAD is separately licensed CC BY 4.0 by the Atticus Project.
