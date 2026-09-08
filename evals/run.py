import argparse
import difflib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from database import SyncSessionLocal
from legal_api.models import Document, DocumentChunk, User
from vector_store import LegalVectorStore
from . import DATASET_DIR, EVAL_TENANT_EMAIL, REPORT_DIR
from . import dataset as gold
from . import metrics
from .corpus import build_embedder, corpus_fingerprint, CORPUS_DIR
from .metrics import QuestionResult
from .retrievers import DenseRetriever, NameScopedRetriever, TimedRetriever

logger = logging.getLogger("evals.run")

MAX_K = max(metrics.K_VALUES)


def _suggest(wanted: str, known: dict[str, str]) -> str:


    def tokens(name: str) -> set[str]:
        parts = re.split(r"[^a-z0-9]+", gold.normalize_filename(name))
        return {p for p in parts if len(p) >= 4}

    frequency: dict[str, int] = {}
    for name in known:
        for token in tokens(name):
            frequency[token] = frequency.get(token, 0) + 1
    threshold = max(2, len(known) // 5)

    def distinctive(name: str) -> set[str]:
        return {t for t in tokens(name) if frequency.get(t, 0) <= threshold}

    wanted_tokens = distinctive(wanted)
    candidates = difflib.get_close_matches(
        gold.normalize_filename(wanted), list(known), n=3, cutoff=0.4
    )
    for candidate in candidates:
        if wanted_tokens & distinctive(candidate):
            return f"  did you mean: {known[candidate]}"
    return ""


def verify_labels(questions, indexed_names: list[str]) -> None:

    known = {gold.normalize_filename(n): n for n in indexed_names}
    problems: list[str] = []

    for question in questions:
        for evidence in question.relevant:
            if gold.normalize_filename(evidence.filename) in known:
                continue
            problems.append(
                f"  {question.id}: no document named {evidence.filename!r}"
                f"{_suggest(evidence.filename, known)}"
            )

    if problems:
        raise SystemExit(
            "Gold set references documents that are not in the indexed corpus:\n"
            + "\n".join(problems)
            + "\n\nFilenames are matched exactly (case-insensitively) against the indexed "
            "document name. Copy them from the corpus directory rather than retyping."
        )


def run(dataset_path: Path, label: str, retriever_name: str = "dense") -> dict:
    
    questions = gold.load(dataset_path)
    logger.info(f"Loaded {len(questions)} questions: {gold.summarise(questions)}")

    session = SyncSessionLocal()
    embedder, cache = build_embedder()
    store = LegalVectorStore(embedder=embedder)

    try:
        user = session.query(User).filter_by(email=EVAL_TENANT_EMAIL).one_or_none()
        if user is None:
            raise SystemExit("No evaluation corpus indexed. Run: python -m evals.corpus")

        indexed_chunks = (
            session.query(DocumentChunk)
            .join(Document)
            .filter(Document.user_id == user.id, DocumentChunk.embedding_model == embedder.name)
            .count()
        )
        if indexed_chunks == 0:
            raise SystemExit(
                f"The corpus holds no chunks embedded by '{embedder.name}'. "
                f"The model changed since indexing - re-run: python -m evals.corpus"
            )
        indexed_names = [d.filename for d in session.query(Document).filter_by(user_id=user.id).all()]
        document_count = len(indexed_names)
        logger.info(f"Corpus: {document_count} documents, {indexed_chunks} chunks ({embedder.name})")

        verify_labels(questions, indexed_names)

        build = NameScopedRetriever if retriever_name == "scoped" else DenseRetriever
        retriever = TimedRetriever(build(store, user, session))

        results: list[QuestionResult] = []
        for q in questions:
            retrieved = retriever.search(q.question, MAX_K)
            results.append(
                QuestionResult(
                    question_id=q.id,
                    category=q.category,
                    retrieved=retrieved,
                    relevant=q.relevant_keys(),
                    latency_ms=retriever.last_latency_ms,
                )
            )

        report = {
            "label": label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "retriever": retriever.name,
            "config": {
                "embedding_model": embedder.name,
                "dimensions": embedder.dimensions,
                "corpus_documents": document_count,
                "corpus_chunks": indexed_chunks,
                "corpus_fingerprint": corpus_fingerprint(CORPUS_DIR),
                "dataset": dataset_path.name,
                "questions": len(questions),
                "categories": gold.summarise(questions),
            },
            "metrics": metrics.aggregate(results),
            "failures_at_5": metrics.failures(results, k=5),
            "cache": cache.stats,
        }
        return report
    finally:
        cache.close()
        session.close()


def print_report(report: dict) -> None:
    overall = report["metrics"]["overall"]
    print(f"\n  {report['label']}  |  {report['retriever']}")
    print(f"  {report['config']['corpus_documents']} documents, "
          f"{report['config']['questions']} questions\n")

    print("  Overall")
    for k in metrics.K_VALUES:
        print(f"    recall@{k:<3} {overall.get(f'recall@{k}', 0):.3f}      hit@{k:<3} {overall.get(f'hit@{k}', 0):.3f}")
    print(f"    MRR       {overall.get('mrr', 0):.3f}")
    print(f"    latency   p50 {overall.get('p50_latency_ms', 0):.0f}ms   p95 {overall.get('p95_latency_ms', 0):.0f}ms")

    by_category = report["metrics"]["by_category"]
    if by_category:
        print("\n  By category (recall@5)")
        for category, block in by_category.items():
            print(f"    {category:<16} {block.get('recall@5', 0):.3f}   ({block['questions']} questions)")

    misses = report["failures_at_5"]
    print(f"\n  Missed at k=5: {len(misses)}")
    for miss in misses[:5]:
        print(f"    {miss['question_id']} [{miss['category']}] expected {miss['expected']}")
    if len(misses) > 5:
        print(f"    ... and {len(misses) - 5} more (see the report file)")


def main() -> None:
    
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Run the retrieval evaluation.")
    parser.add_argument("--dataset", type=Path, default=DATASET_DIR / "gold.jsonl")
    parser.add_argument("--label", default="dense-baseline")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--retriever", choices=("dense", "scoped"), default="dense")
    args = parser.parse_args()

    if not args.dataset.exists():
        raise SystemExit(
            f"No gold set at {args.dataset}. Start from "
            f"{DATASET_DIR / 'gold.example.jsonl'} and write your own."
        )

    report = run(args.dataset, args.label, args.retriever)
    print_report(report)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = args.out or REPORT_DIR / f"{args.label}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Report written to {out}\n")


if __name__ == "__main__":
    main()
