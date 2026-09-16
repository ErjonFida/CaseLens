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

## Next

Query rewriting toward clause language, for the 56 questions that name no
document. Three levers have now been measured against the unscoped set —
lexical fusion, cross-encoder reranking, and embedding models — and none
moved it. The remaining hypothesis is that the *questions* are the problem:
conversational phrasing embeds far from the clause that answers it, and
rewriting closes that distance without touching the corpus.
