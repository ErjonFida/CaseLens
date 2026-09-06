from dataclasses import dataclass

K_VALUES = (1, 3, 5, 10)


@dataclass
class QuestionResult:
    question_id: str
    category: str
    retrieved: list[tuple[str, int]]      # (filename, page) in rank order
    relevant: set[tuple[str, int]]
    latency_ms: float

    @property
    def scored(self) -> bool:
        return bool(self.relevant)

    def recall_at(self, k: int) -> float:
        if not self.relevant:
            return 0.0
        found = self.relevant & set(self.retrieved[:k])
        return len(found) / len(self.relevant)

    def hit_at(self, k: int) -> float:
        if not self.relevant:
            return 0.0
        return 1.0 if self.relevant & set(self.retrieved[:k]) else 0.0

    def reciprocal_rank(self) -> float:
        for rank, key in enumerate(self.retrieved, start=1):
            if key in self.relevant:
                return 1.0 / rank
        return 0.0

    def first_relevant_rank(self) -> int | None:
        for rank, key in enumerate(self.retrieved, start=1):
            if key in self.relevant:
                return rank
        return None


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def aggregate(results: list[QuestionResult]) -> dict:
    scored = [r for r in results if r.scored]

    def block(rows: list[QuestionResult]) -> dict:
        if not rows:
            return {}
        out: dict[str, float | int] = {"questions": len(rows)}
        for k in K_VALUES:
            out[f"recall@{k}"] = _mean([r.recall_at(k) for r in rows])
            out[f"hit@{k}"] = _mean([r.hit_at(k) for r in rows])
        out["mrr"] = _mean([r.reciprocal_rank() for r in rows])
        out["p50_latency_ms"] = _percentile([r.latency_ms for r in rows], 50)
        out["p95_latency_ms"] = _percentile([r.latency_ms for r in rows], 95)
        return out

    by_category: dict[str, dict] = {}
    for category in sorted({r.category for r in results}):
        rows = [r for r in scored if r.category == category]
        if rows:
            by_category[category] = block(rows)

    unanswerable = [r for r in results if not r.scored]

    return {
        "overall": block(scored),
        "by_category": by_category,
        "unanswerable_questions": len(unanswerable),
        "scored_questions": len(scored),
    }


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(round((pct / 100) * (len(ordered) - 1))), len(ordered) - 1)
    return round(ordered[index], 2)


def failures(results: list[QuestionResult], k: int = 5) -> list[dict]:

    out = []
    for r in results:
        if r.scored and r.hit_at(k) == 0.0:
            out.append(
                {
                    "question_id": r.question_id,
                    "category": r.category,
                    "expected": sorted(f"{f}:p{p}" for f, p in r.relevant),
                    "retrieved": [f"{f}:p{p}" for f, p in r.retrieved[:k]],
                }
            )
    return out
