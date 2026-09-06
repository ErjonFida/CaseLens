import json
from dataclasses import dataclass, field
from pathlib import Path

CATEGORIES = (
    "exact_term",
    "semantic",        
    "multi_document", 
    "unanswerable",    
)


def normalize_filename(name: str) -> str:
    "Fold a filename for comparison."
    return name.strip().casefold()


@dataclass(frozen=True)
class Evidence:

    filename: str
    page: int

    def key(self) -> tuple[str, int]:
        return (normalize_filename(self.filename), self.page)


@dataclass(frozen=True)
class GoldQuestion:
    id: str
    question: str
    category: str
    relevant: tuple[Evidence, ...] = field(default_factory=tuple)
    note: str = ""

    @property
    def is_answerable(self) -> bool:
        return self.category != "unanswerable" and bool(self.relevant)

    def relevant_keys(self) -> set[tuple[str, int]]:
        return {e.key() for e in self.relevant}


def _parse_evidence(entries, filename: str, line_no: int) -> list[Evidence]:

    evidence: list[Evidence] = []
    for entry in entries:
        if "filename" not in entry or "page" not in entry:
            raise ValueError(
                f"{filename}:{line_no} has a relevant entry missing 'filename' or 'page'"
            )
        pages = entry["page"]
        pages = pages if isinstance(pages, list) else [pages]
        if not pages:
            raise ValueError(f"{filename}:{line_no} has a relevant entry with an empty page list")
        for page in pages:
            try:
                page_no = int(page)
            except (TypeError, ValueError):
                raise ValueError(
                    f"{filename}:{line_no} has page {page!r}, which is not a page number. "
                    f"Use an integer, or a list of integers for evidence spanning pages."
                ) from None
            if page_no < 1:
                raise ValueError(f"{filename}:{line_no} has page {page_no}; pages are 1-indexed")
            evidence.append(Evidence(filename=str(entry["filename"]), page=page_no))
    return evidence


def load(path: Path) -> list[GoldQuestion]:
    questions: list[GoldQuestion] = []
    seen_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name}:{line_no} is not valid JSON: {e}") from e

            for required in ("id", "question", "category"):
                if required not in raw:
                    raise ValueError(f"{path.name}:{line_no} is missing '{required}'")

            qid = str(raw["id"])
            if qid in seen_ids:
                raise ValueError(f"{path.name}:{line_no} duplicates question id '{qid}'")
            seen_ids.add(qid)

            category = raw["category"]
            if category not in CATEGORIES:
                raise ValueError(
                    f"{path.name}:{line_no} has unknown category '{category}'. "
                    f"Expected one of {', '.join(CATEGORIES)}"
                )

            evidence = tuple(_parse_evidence(raw.get("relevant", []), path.name, line_no))
            
            if category == "unanswerable" and evidence:
                raise ValueError(
                    f"{path.name}:{line_no} is marked unanswerable but lists evidence"
                )
            if category != "unanswerable" and not evidence:
                raise ValueError(
                    f"{path.name}:{line_no} is answerable but lists no evidence"
                )

            questions.append(
                GoldQuestion(
                    id=qid,
                    question=str(raw["question"]),
                    category=category,
                    relevant=evidence,
                    note=str(raw.get("note", "")),
                )
            )
            

    if not questions:
        raise ValueError(f"{path} contains no questions")
    return questions


def summarise(questions: list[GoldQuestion]) -> dict[str, int]:
    counts = {c: 0 for c in CATEGORIES}
    for q in questions:
        counts[q.category] += 1
    return counts
