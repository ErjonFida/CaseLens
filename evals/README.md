# Retrieval evaluation

Runs offline. Embeddings come from a local Ollama model and are cached by content
hash, so re-running costs nothing and a chunking sweep only re-embeds what changed.

## Running it

```bash
python -m evals.corpus                       # index evals/corpus/ (destructive)
python -m evals.run --label my-experiment    # writes evals/reports/my-experiment.json
python -m evals.run --label scoped --retriever scoped
```

`--retriever` selects `dense` (default) or `scoped`.

Sweeping chunk parameters:

```bash
python -m evals.corpus --chunk-size 500 --overlap 75
python -m evals.run --label chunk-500-75
```

## Layout

| Path | |
|---|---|
| `corpus/` | Documents under test. Not committed. |
| `datasets/gold.jsonl` | Questions and ground truth. Committed. |
| `datasets/gold.example.jsonl` | The format, annotated. |
| `reports/` | One report per run, named by `--label`. |
| `cuad_import.py` | Builds the gold set from CUAD annotations. |

## The corpus

69 contracts from [CUAD](https://www.atticusprojectai.org/cuad) (CC BY 4.0). The
PDFs are gitignored, so reproduce the corpus by downloading CUAD, copying the
files named in `gold.jsonl` into `corpus/`, then:

```bash
python -m evals.cuad_import --cuad path/to/CUAD_v1.json --out evals/datasets/gold.jsonl
```

Questions are generated per contract rather than copied from CUAD — its prompts
are identical across all 510 contracts, so reused verbatim they could not identify
which document is meant. Ground-truth pages are found by locating each annotated
span in the document, not from CUAD's character offsets, which index a different
text extraction. `is_impossible` annotations supply the `unanswerable` questions.

## Two rules that are not obvious

**Ground truth is `(filename, page)`, never a chunk id.** Chunk ids belong to the
chunking configuration, and chunking is the first thing you change — labelling by
chunk id invalidates the dataset on the first sweep, and the resulting movement
looks like a retrieval change rather than broken labels.

**Unanswerable questions are excluded from recall and MRR, not scored zero.** There
is no relevant page to find, so the retriever cannot be wrong about finding one.

A gold entry naming a document outside the corpus fails the run rather than scoring
zero: a mistyped filename and a real retrieval failure are indistinguishable once
averaged.

## Results so far

| Retriever | recall@5 | MRR |
|---|---:|---:|
| `dense` | 0.340 | 0.298 |
| `scoped` | 0.702 | 0.562 |

Read `scoped` with its caveat: `cuad_import` templates every question as
"the {party} agreement", so all 100 name their contract by construction. 67 of
the 74 single-document questions scope, none wrongly; the 7 that abstain name
a party with several contracts in the corpus. Real queries name a document
less often, so this gap overstates what users would see.

**Scoping went from 40 to 67 correct without touching a model.** After
hybrid, reranking, and two embedding models had all failed to move the
`semantic` category, a one-minute diagnostic showed 34 of 74 questions were
*abstaining* from scoping on a tie: `ts_rank_cd` weighted "agreement" (in all
69 filenames) equally with the party name (in one). IDF-weighting the match
and dropping the stemmer took `semantic` from 0.500 to 0.644 — more than every
model experiment combined. A second diagnostic over the 17 remaining
single-document misses found page 1 in the top 5 for 10 of them: the party
name in the question was pulling the cover page in. Removing the title span
from the query before embedding took `semantic` to 0.750 and recall@5 to
0.702. Two more general-looking rules were tried on the way - strip only words
rare in document bodies, then also words common in filenames - and both
scored 0.66: multi-word names are built from ordinary words, so name-ness is
a property of the phrase, not the word. The span rule scores the same as
stripping everything and keeps a topic word's own mention. The lesson is the order of operations: read which questions fail and
why before reaching for a bigger model.

**The labels were checked, not assumed.** The same 17 misses were tested
against the CUAD answer spans to see whether the retrieved page also held the
clause. Two did — spans straddling a page boundary, labelled with the page
they start on. That is 0.02 against a noise floor of about ±0.03 on 100
questions, so the labels are left alone and the artifact is noted here rather
than tuned away. Every other miss is a genuine ranking failure within the
right document.

**Hybrid retrieval was measured and rejected.** A `tsvector` channel fused by
reciprocal rank scored recall@5 0.126; lexical alone scored 0.051. Once the
party name is removed the remaining terms appear in all 69 contracts, and the
party name is not in the chunk bodies — it is in the filename. Name-scoping came out of that
failure, which is the argument for measuring each step separately.

**Cross-encoder reranking was measured and rejected.** Two off-the-shelf
rerankers rescored the top-50 dense candidates from the scoped path:

| | scoped | + `ms-marco-MiniLM-L-6-v2` | + `mxbai-rerank-base-v1` |
|---|---:|---:|---:|
| recall@5 | **0.536** | 0.509 | 0.515 |
| MRR | 0.437 | 0.412 | **0.466** |
| exact_term | 0.716 | 0.806 | 0.645 |
| semantic | 0.500 | 0.383 | 0.494 |
| p50 latency | 99ms | 809ms | 5,970ms |

Neither beats name-scoping on recall@5, and they move the categories in
opposite directions — one lifts `exact_term` and sinks `semantic`, the other
the reverse. Two models trained on the same web-passage data disagreeing that
sharply might be domain mismatch. mxbai has MRR gain
but costs sixty times the latency on CPU.

The premise was that the 0.536 → 0.636 gap (recall@5 to recall@50) was an
ordering problem a reranker could close. It is not: for the 44 scoped
questions the pool already holds the whole document, and dense distance
orders those pages better than either cross-encoder did. The gap lives in the
56 unscoped questions, whose correct page is not in the pool at all — and a
reranker cannot add what retrieval missed.

Re-tested after name-scoping reached 0.702, in the cleanest setting
available: the gold document handed over, so the pool is the whole contract
and the only job is ordering its pages.

| document given | recall@5 | MRR | ms/query |
|---|---:|---:|---:|
| dense | **0.767** | 0.628 | 81 |
| + `ms-marco-MiniLM-L-6-v2` | 0.699 | 0.642 | 778 |
| + `mxbai-rerank-base-v1` | 0.733 | 0.609 | 5,417 |

Both still lose, with `exact_term` suffering most each time. Given one
contract and asked only to order its pages, a web-trained cross-encoder
orders them worse than L2 distance on nomic vectors.

**The embedding model swap was measured and rejected.** Two Qwen3 models
against the same scoped path, each with its own query instruction:

| scoped | `nomic-embed-text` | `qwen3-embedding:0.6b` @768 | `qwen3-embedding:4b` @2560 |
|---|---:|---:|---:|
| recall@5 | **0.536** | 0.512 | 0.517 |
| MRR | **0.437** | 0.377 | 0.410 |
| exact_term | 0.716 | 0.742 | **0.755** |
| semantic | **0.500** | 0.428 | 0.428 |
| p50 latency | 99ms | 232ms | 341ms |

Unlike the rerankers, the two Qwen models agree: better on `exact_term`,
identically worse on `semantic`. Going from 0.6b to 4b at native width bought
MRR and nothing on the paraphrase questions, which are 43 of the 100. The
loss is a property of the model family on these questions, not of size.

Reproducible by config — `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS`, then
`python -m evals.corpus` — so both reports are committed. Migration 005 made
the column width-agnostic for this; a further model comparison needs no
schema change.

**Re-tested after name-scoping and title stripping, the result changed.**
Under the current pipeline the embedder mostly orders pages within one
contract given a short residual query, and there `qwen3-embedding:4b` is a
trade rather than a loss: recall@5 0.688 vs 0.702, but recall@10 0.749 vs
0.721 and MRR 0.604 vs 0.566, with `semantic` up 0.062 and `exact_term` down
0.096 (`reports/scoped-qwen3-4b.json` now holds this run; the earlier one is in `ac84efe`). Nomic is the stronger
exact matcher, Qwen is the stronger paraphrase matcher.

**Fusing the two** by reciprocal rank inside the scoped document is the one
combination the evidence supports — two decent signals with different
strengths, unlike the lexical channel, which was noise. Measured ad hoc with
both models' vectors in the same column (migration 005): flat at k=5, but
recall@10 0.721 → 0.793 auto-scoped and 0.802 → 0.873 with the document
given, MRR +0.07 in both. The gain is at k=10, which is what the chat path
should send. Not shipped: it doubles index writes and adds a 2.5 GB resident
model and ~250ms per query.

**Multiple selected documents, one question each.** Simulating a picker where
the user selects 5 documents and asks about one of them (20 seeded draws):
searching all 5 with the title stripped scores 0.373 at k=5 — the stripped
query no longer says which contract, and each of the 5 has the clause.
Matching the name against the *selection* and narrowing to that one document
scores 0.860 (0.931 at k=10 fused). A selection is a candidate set, not a
scope: the name match still runs inside it, and a title is never stripped
while the scope holds more than one document.

## Answer-time faithfulness

Retrieval recall says whether the right page reached the model.
`evals/faithfulness.py` measures what the generator does with it: whether the
answer holds the annotated clause, whether the cited page is right, and - the
production question - whether the model says so when the clause is absent or
the page was not retrieved, or answers anyway.

```bash
python -m evals.faithfulness --cuad path/to/CUAD_v1.json --max-doc-tokens 6000
python -m evals.faithfulness --cuad path/to/CUAD_v1.json --provider gemini --model gemini-3.8-flash --max-doc-tokens 40000 --conditions rag10,full
python -m evals.faithfulness --cuad path/to/CUAD_v1.json --regrade evals/reports/faithfulness-*.json
```

Each question is answered three ways: from the chunks retrieval returns at
k=5 (shipped) and k=10, and from the whole document with page markers. Only
documents that fit the model's context are used, so the whole-document
condition is measured where it is viable. `gemma4:e4b` answered the 24
questions whose document is under 6k tokens (19 answerable, 5 where CUAD marks
the clause absent); `gemini-3.8-flash` answered the same 24, and the 73 whose
document is under 40k.

### Graded results

All 290 answers were graded outside the harness one verdict
and a written justification each, recorded next to the question, the CUAD
span and the answer in
[`reports/faithfulness-grading-graded.xlsx`](reports/faithfulness-grading-graded.xlsx).
*Good* is a correct answer or a correct decline, over all answers.

| | correct | partial | wrong | declined rightly | declined wrongly | good |
|---|---:|---:|---:|---:|---:|---:|
| Gemma, 5 chunks | 15 | 4 | 0 | 4 | 1 | 0.792 |
| Gemma, 10 chunks | 16 | 2 | 1 | 4 | 1 | **0.833** |
| Gemma, whole document | 14 | 6 | 1 | 3 | 0 | 0.708 |
| Gemini, 5 chunks | 15 | 2 | 0 | 6 | 1 | 0.875 |
| Gemini, 10 chunks | 17 | 2 | 0 | 5 | 0 | **0.917** |
| Gemini, whole document | 17 | 2 | 0 | 5 | 0 | **0.917** |
| Gemini up to 40k, 10 chunks | 45 | 7 | 1 | 14 | 6 | 0.808 |
| Gemini up to 40k, whole document | 56 | 9 | 2 | 6 | 0 | **0.849** |

At 24 and 73 questions one answer moves these rates by 4 and 1.4 points, so
differences of two or three answers are direction, not size. What holds:

- **Ten chunks beat five for both models** - one more correct answer in 19
  for Gemma, two for Gemini. The final k=5 should be k=10 regardless of
  model.
- **For Gemma, retrieval beats the whole document** even when it fits: 20
  good answers to 17, the gap made of partial answers. A 4B model extracts
  less reliably from 6k tokens of contract than from ten focused chunks.
- **For Gemini, the whole document ties on small documents and wins on
  larger ones.** The mechanism is refusals: from ten chunks it declined six
  questions whose answer was in the context it was given (a date on the
  page, both parties named) and retrieval missed the gold page for 7 of 64.
  From the whole document, no wrongful declines.
- **The whole document's one real error is substitution.** Asked whether
  outsiders have rights under a contract with no such clause (q091), Gemini
  offered the indemnification section instead. Gemma made the same kind of
  error on q097, offering assignment restrictions for change of control. It
  is the failure a legal tool can least afford, and a prompt problem this
  harness can measure a fix for.
- **Local and hosted are in the same range.** On the same 24 questions at ten
  chunks Gemini gave 22 good answers to Gemma's 20. A 4B model on a laptop CPU is a viable offline deployment for this
  task but it is not ahead of a hosted model.

So the branch is model-relative: the whole document when
`document_tokens <= 0.6 x context budget`, retrieval otherwise. Gemini gets
the document, local Gemma gets retrieval, with no provider-specific code.

### How far to trust the automatic grader

The harness grades deterministically, content-word overlap with the CUAD
span after stripping markdown, a regex over cited page numbers, and a phrase
list for declining. A small judge model would share the answering
model's blind spots. Against the graded answers:

| automatic signal | precision | recall |
|---|---:|---:|
| overlap >= 0.5 means correct | 0.91 | 0.85 |
| decline phrase means declined | 0.59 | 0.91 |

The overlap proxy is fit for comparing conditions within one model.