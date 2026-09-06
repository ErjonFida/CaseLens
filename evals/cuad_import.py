import argparse
import json
import logging
import random
import re
import unicodedata
from pathlib import Path

from . import CORPUS_DIR, DATASET_DIR, EVAL_ROOT

logger = logging.getLogger("evals.cuad_import")

TEMPLATES = {
    "Governing Law":            ("Which law governs the {party} agreement?", "semantic"),
    "Agreement Date":           ("What is the date of the {party} agreement?", "exact_term"),
    "Effective Date":           ("When does the {party} agreement become effective?", "exact_term"),
    "Expiration Date":          ("When does the {party} agreement expire?", "exact_term"),
    "Renewal Term":             ("How long is the renewal term in the {party} agreement?", "exact_term"),
    "Parties":                  ("Who are the parties to the {party} agreement?", "exact_term"),
    "Notice Period To Terminate Renewal": ("How much notice is needed to stop the {party} agreement renewing?", "semantic"),
    "Termination For Convenience": ("Can either side walk away from the {party} agreement without cause?", "semantic"),
    "Cap On Liability":         ("Is there a limit on how much either side can be liable for under the {party} agreement?", "semantic"),
    "Uncapped Liability":       ("Which liabilities are uncapped in the {party} agreement?", "semantic"),
    "Insurance":               ("What insurance must be carried under the {party} agreement?", "semantic"),
    "Audit Rights":            ("What rights of inspection exist under the {party} agreement?", "semantic"),
    "Warranty Duration":       ("How long do the warranties last in the {party} agreement?", "semantic"),
    "Non-Compete":             ("What restrictions on competing does the {party} agreement impose?", "semantic"),
    "Exclusivity":             ("Is any exclusivity granted in the {party} agreement?", "semantic"),
    "Anti-Assignment":         ("Can the {party} agreement be transferred to someone else?", "semantic"),
    "Change Of Control":       ("What happens to the {party} agreement if one side is acquired?", "semantic"),
    "IP Ownership Assignment": ("Who owns intellectual property created under the {party} agreement?", "semantic"),
    "License Grant":           ("What licence is granted in the {party} agreement?", "semantic"),
    "Revenue/Profit Sharing":  ("How is revenue shared under the {party} agreement?", "semantic"),
    "Minimum Commitment":      ("What minimum commitment does the {party} agreement require?", "exact_term"),
    "Post-Termination Services": ("What obligations survive termination of the {party} agreement?", "semantic"),
    "Source Code Escrow":      ("Does the {party} agreement provide for source code escrow?", "semantic"),
    "Liquidated Damages":      ("Does the {party} agreement provide for liquidated damages?", "semantic"),
    "Third Party Beneficiary": ("Does anyone outside the {party} agreement have rights under it?", "semantic"),
}


def normalize(text: str) -> str:

    return re.sub(r"\s+", " ", text).casefold().strip()


def fold_name(name: str) -> str:

    stripped = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).casefold().strip()


def contract_label(title: str) -> str:

    head = re.split(r"_\d|\s+-\s+", title)[0]
    head = head.split("_")[0].strip(" ,.-")
    head = re.sub(r"(?i)(inc|corp|ltd|llc|plc|co|sa|nv|holdings)\.?$", "", head).strip(" ,.-")
    if head.isupper() and len(head) > 4:
        head = head.title()
    return head or title[:24]


def load_pages(path: Path, cache: dict) -> list[str]:

    key = path.name
    if key in cache:
        return cache[key]
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        pages = [normalize(page.extract_text() or "") for page in pdf.pages]
    cache[key] = pages
    return pages


def locate(answer: str, pages: list[str]) -> int | None:

    target = normalize(answer)
    if not target:
        return None

    for page_no, text in enumerate(pages, start=1):
        if target in text:
            return page_no

    words = target.split()
    for length in (14, 10, 7, 5):
        if len(words) <= length:
            continue
        prefix = " ".join(words[:length])
        for page_no, text in enumerate(pages, start=1):
            if prefix in text:
                return page_no
    return None


def build(cuad_path: Path, corpus_dir: Path, limit: int, seed: int) -> tuple[list[dict], dict]:
    payload = json.loads(cuad_path.read_text(encoding="utf-8"))
    entries = {e["title"]: e for e in payload["data"]}

    available = {
        fold_name(p.stem): p
        for p in corpus_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".pdf", ".txt"}
    }
    usable = {t: available[fold_name(t)] for t in entries if fold_name(t) in available}
    logger.info(f"{len(usable)} of {len(available)} corpus documents have CUAD annotations")

    rng = random.Random(seed)
    page_cache: dict = {}
    answerable: list[dict] = []
    impossible: list[dict] = []
    unlocatable = 0

    for title, path in sorted(usable.items()):
        entry = entries[title]
        qas = entry["paragraphs"][0]["qas"]
        party = contract_label(title)
        pages = load_pages(path, page_cache)

        for qa in qas:
            match = re.search(r'related to "([^"]+)"', qa["question"])
            if not match:
                continue
            clause = match.group(1)
            if clause not in TEMPLATES:
                continue
            template, category = TEMPLATES[clause]
            question = template.format(party=party)

            if qa["is_impossible"]:
                impossible.append(
                    {
                        "question": question,
                        "category": "unanswerable",
                        "relevant": [],
                        "note": f"CUAD marks '{clause}' absent from this contract",
                    }
                )
                continue

            located = sorted({p for a in qa["answers"] if (p := locate(a["text"], pages))})
            if not located:
                unlocatable += 1
                continue

            answerable.append(
                {
                    "question": question,
                    "category": category,
                    "relevant": [{"filename": path.name, "page": located}],
                    "note": f"CUAD clause: {clause}",
                }
            )

    rng.shuffle(answerable)
    rng.shuffle(impossible)

    n_unanswerable = max(1, limit // 7)
    n_multi = max(1, limit // 8)
    n_single = limit - n_unanswerable - n_multi

    selected = answerable[:n_single]
    multi = build_multi(answerable[n_single:], n_multi)
    selected.extend(multi)
    selected.extend(impossible[:n_unanswerable])

    for index, item in enumerate(selected, start=1):
        item["id"] = f"q{index:03d}"

    stats = {
        "documents_with_annotations": len(usable),
        "answerable_candidates": len(answerable),
        "unanswerable_candidates": len(impossible),
        "spans_not_locatable": unlocatable,
        "emitted": len(selected),
    }
    return selected, stats


def build_multi(pool: list[dict], count: int) -> list[dict]:

    by_clause: dict[str, list[dict]] = {}
    for item in pool:
        by_clause.setdefault(item["note"], []).append(item)

    out: list[dict] = []
    for clause, items in by_clause.items():
        if len(out) >= count:
            break
        if len(items) < 2:
            continue
        first, second = items[0], items[1]
        subject = clause.replace("CUAD clause: ", "").lower()
        a = contract_label(first["relevant"][0]["filename"])
        b = contract_label(second["relevant"][0]["filename"])
        if a == b:
            continue
        out.append(
            {
                "question": f"What do the {a} and {b} agreements each say about {subject}?",
                "category": "multi_document",
                "relevant": first["relevant"] + second["relevant"],
                "note": f"Comparison across two contracts on CUAD clause: {subject}",
            }
        )
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Build a gold set from CUAD annotations.")
    parser.add_argument("--cuad", type=Path, required=True, help="Path to CUAD_v1.json")
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    parser.add_argument("--out", type=Path, default=DATASET_DIR / "gold.jsonl")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    questions, stats = build(args.cuad, args.corpus, args.limit, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        fh.write("// Generated by evals.cuad_import from CUAD v1 expert annotations.\n")
        fh.write("// Ground truth pages are derived by locating each annotated span in the\n")
        fh.write("// document, so every label points at a page that was actually checked.\n")
        for item in questions:
            ordered = {
                "id": item["id"],
                "question": item["question"],
                "category": item["category"],
                "relevant": item["relevant"],
                "note": item["note"],
            }
            fh.write(json.dumps(ordered, ensure_ascii=False) + "\n")

    print()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print(f"\n  Written to {args.out}\n")


if __name__ == "__main__":
    main()
