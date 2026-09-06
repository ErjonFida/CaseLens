# Retrieval evaluation

Measures the retriever the application actually ships: `DenseRetriever` calls the
same `query_similar_context` the API calls, so these numbers describe the running
system rather than a reimplementation of it.

Runs offline. Embeddings come from a local Ollama model and are cached by content
hash, so re-running costs nothing and a chunking sweep only re-embeds what changed.

## Running it

```bash
python -m evals.corpus                       # index evals/corpus/ (destructive)
python -m evals.run --label my-experiment    # writes evals/reports/my-experiment.json
```

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

## Next

`HybridRetriever` in `retrievers.py` is a stub. The plan is a `tsvector` column and
GIN index alongside the vector channel, fused by reciprocal rank, then reranked.
Measure each step separately — the interesting claim is not "hybrid is better" but
which categories move.
