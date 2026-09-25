import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import ollama
from sqlalchemy import select

from config import settings
from database import SyncSessionLocal
from legal_api.models import User
from ocr import extract_document_pages
from vector_store import SYSTEM_PROMPT, LegalVectorStore, estimate_tokens, format_chunks, format_pages
from . import CORPUS_DIR, DATASET_DIR, EVAL_TENANT_EMAIL, REPORT_DIR
from . import dataset as gold
from .corpus import build_embedder
from .cuad_import import fold_name, normalize
from .judge import GOOD, JUDGE_MODEL, judge_many

logger = logging.getLogger("evals.faithfulness")

ABSTAIN = re.compile(
    r"(cannot|can't|could not|unable to) (be )?(find|locate|determine)|not (found|mentioned|specified|stated|provided|"
    r"included|present|contained|addressed)|do(es)? not (contain|specify|mention|state|provide|address|include|outline|"
    r"designate|grant|impose|require|explicitly|expressly)|no (information|mention|provision|clause|reference|blanket|"
    r"specific|explicit|express|such)|there (is|are) no\b|is not in the (provided )?(context|document)|"
    r"provided (document|context)s?,? \*{0,2}no\*{0,2}\b",
    re.I,
)
PAGE = re.compile(r"\bp(?:age|\.)?\s*:?\s*(\d{1,4})\b", re.I)
STOP = set("the a an of to in on for and or by with is are be as at from that this any all such shall will".split())


MARKDOWN = re.compile(r"[*_`#>|]+")


def content_words(text: str) -> set[str]:
    return {w for w in normalize(MARKDOWN.sub(" ", text)).split() if len(w) > 2 and w not in STOP}


def supported(answer: str, spans: list[str]) -> float:
    """Best content-word overlap between the answer and any annotated span."""
    got = content_words(answer)
    best = 0.0
    for span in spans:
        want = content_words(span)
        if want:
            best = max(best, len(want & got) / len(want))
    return best


def load_spans(cuad_path: Path) -> dict[tuple[str, str], list[str]]:
    payload = json.loads(cuad_path.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], list[str]] = {}
    for entry in payload["data"]:
        key = fold_name(entry["title"])
        for qa in entry["paragraphs"][0]["qas"]:
            m = re.search(r'related to "([^"]+)"', qa["question"])
            if m:
                out[(key, m.group(1))] = [a["text"] for a in qa["answers"]]
    return out


def page_texts(path: Path, cache: dict) -> list[dict]:
    if path.name not in cache:
        cache[path.name] = extract_document_pages(str(path))
    return cache[path.name]


def ask_gemini(model: str, context: str, question: str) -> tuple[str, float, int]:
    import os
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    llm = genai.GenerativeModel(model_name=model, system_instruction=SYSTEM_PROMPT.format(context=context))
    t0 = time.perf_counter()
    for attempt in range(6):
        try:
            r = llm.generate_content(question, generation_config={"temperature": 0})
            break
        except Exception as e:  # rate limits on the free tier: back off and retry
            if attempt == 5 or "429" not in str(e) and "quota" not in str(e).lower():
                raise
            time.sleep(10 * (attempt + 1))
    parts = r.candidates[0].content.parts if r.candidates else []
    text = "".join(getattr(p, "text", "") for p in parts if not getattr(p, "thought", False))
    return text, (time.perf_counter() - t0) * 1000, r.usage_metadata.prompt_token_count


def ask(model: str, num_ctx: int, context: str, question: str, think: bool | None = None,
        provider: str = "ollama") -> tuple[str, float, int]:
    if provider == "gemini":
        return ask_gemini(model, context, question)
    t0 = time.perf_counter()
    r = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
                  {"role": "user", "content": question}],
        options={"num_ctx": num_ctx, "temperature": 0},
        # None leaves a model's default; False turns a thinking model's
        # reasoning off, which is how the app would call it for latency.
        **({} if think is None else {"think": think}),
    )
    return r["message"]["content"], (time.perf_counter() - t0) * 1000, r.get("prompt_eval_count") or 0


def clause_of(note: str) -> str:
    m = re.search(r"CUAD (?:clause: |marks ')([^']+)", note or "")
    return m.group(1).strip() if m else ""


def judge_records(records: list[dict], spans: dict, files: dict, model: str) -> None:
    questions = {q.id: q for q in gold.load(DATASET_DIR / "gold.jsonl")}
    cases = []
    for r in records:
        q = questions[r["question_id"]]
        absent = q.category == "clause_absent"
        path = None if absent else files.get(fold_name(Path(q.relevant[0].filename).stem))
        cases.append({
            "question": q.question,
            "clause_absent": absent,
            "spans": [] if absent or not path else spans.get((fold_name(path.stem), clause_of(q.note)), []),
            "pages": "" if absent else ", ".join(str(e.page) for e in q.relevant),
            "context_has_page": bool(r["context_has_page"]),
            "answer": r["answer"].strip(),
        })
    for r, verdict in zip(records, judge_many(cases, model)):
        r["judge"] = verdict


def run(cuad_path: Path, model: str, num_ctx: int, max_doc_tokens: int, conditions: list[str], label: str,
        think: bool | None = None, provider: str = "ollama", judge_model: str | None = None,
        only: set[str] | None = None) -> dict:
    spans = load_spans(cuad_path)
    session = SyncSessionLocal()
    embedder, cache = build_embedder()
    store = LegalVectorStore(embedder=embedder)
    user = session.execute(select(User).where(User.email == EVAL_TENANT_EMAIL)).scalar_one()
    files = {fold_name(p.stem): p for p in CORPUS_DIR.iterdir() if p.is_file()}
    pages_cache: dict = {}

    selected = []
    for q in gold.load(DATASET_DIR / "gold.jsonl"):
        if only and q.id not in only:
            continue
        if q.category in ("exact_term", "semantic"):
            filename = q.relevant[0].filename
        elif q.category == "clause_absent":
            matches = store.match_documents_by_name(q.question, user, session)
            if not matches or (len(matches) > 1 and matches[0][1] <= matches[1][1] * 1.5):
                continue
            filename = next(d.filename for d in user.documents if d.id == matches[0][0])
        else:
            continue
        path = files.get(fold_name(Path(filename).stem))
        if not path:
            continue
        pages = page_texts(path, pages_cache)
        tokens = estimate_tokens(pages)
        if tokens <= max_doc_tokens:
            selected.append((q, filename, path, pages, tokens))
    logger.info(f"{len(selected)} questions on documents <= {max_doc_tokens} tokens")

    records = []
    for q, filename, path, pages, tokens in selected:
        gold_spans = spans.get((fold_name(path.stem), clause_of(q.note)), [])
        gold_pages = {e.page for e in q.relevant}
        for cond in conditions:
            if cond == "full":
                context, has_page = format_pages(filename, pages), True
            else:
                k = int(cond[3:])
                hits = store.query_scoped_context(q.question, user, session, top_k=k)
                context = format_chunks(hits)
                has_page = any(
                    h["metadata"]["page"] in gold_pages
                    and gold.normalize_filename(h["metadata"]["filename"]) == gold.normalize_filename(filename)
                    for h in hits
                )
            answer, ms, prompt_tokens = ask(model, num_ctx, context, q.question, think, provider)
            cited = {int(n) for n in PAGE.findall(answer)}
            records.append({
                "question_id": q.id, "category": q.category, "condition": cond, "doc_tokens": tokens,
                "prompt_tokens": prompt_tokens, "latency_ms": round(ms),
                "context_has_page": has_page, "abstained": bool(ABSTAIN.search(answer)),
                "support": round(supported(answer, gold_spans), 2) if gold_spans else None,
                "cited_pages": sorted(cited), "cited_correct": bool(cited & gold_pages) if gold_pages else None,
                "answer": answer,
            })
            r = records[-1]
            logger.info(f"{q.id} {cond:6} {ms / 1000:5.1f}s  abstain={r['abstained']} "
                        f"support={r['support']} cited_ok={r['cited_correct']}")
    session.close()
    cache.close()

    if judge_model:
        judge_records(records, spans, files, judge_model)
    summary = summarise(records, conditions)
    return {
        "label": label, "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider, "model": model, "num_ctx": num_ctx, "max_doc_tokens": max_doc_tokens, "think": think,
        "system_prompt": SYSTEM_PROMPT, "summary": summary, "records": records,
    }


def summarise(records: list[dict], conditions: list[str]) -> dict:
    def rate(rows, key):
        rows = [r for r in rows if r[key] is not None]
        return round(sum(bool(r[key]) for r in rows) / len(rows), 3) if rows else None
    summary = {}
    for cond in conditions:
        rows = [r for r in records if r["condition"] == cond]
        answerable = [r for r in rows if r["category"] != "clause_absent"]
        absent = [r for r in rows if r["category"] == "clause_absent"]
        missing = [r for r in answerable if not r["context_has_page"]]
        summary[cond] = {
            "questions": len(rows),
            "supported (overlap >= 0.5)": rate([dict(r, s=(r["support"] or 0) >= 0.5) for r in answerable], "s"),
            "cited page correct": rate(answerable, "cited_correct"),
            "abstained on answerable": rate(answerable, "abstained"),
            "abstained, clause absent": rate(absent, "abstained") if absent else None,
            "page missing from context": len(missing),
            "answered anyway when page missing": rate([dict(r, a=not r["abstained"]) for r in missing], "a") if missing else None,
            "p50 latency ms": sorted(r["latency_ms"] for r in rows)[len(rows) // 2] if rows else None,
        }
        judged = [r for r in rows if r.get("judge")]
        if judged:
            good = lambda rs: round(sum(r["judge"]["grade"] in GOOD for r in rs) / len(rs), 3) if rs else None
            summary[cond]["judged good"] = good(judged)
            summary[cond]["judged good, clause absent"] = good([r for r in judged if r["category"] == "clause_absent"])
            summary[cond]["judged wrong"] = sum(r["judge"]["grade"] == "wrong" for r in judged)
            summary[cond]["judged declined wrongly"] = sum(r["judge"]["grade"] == "abstain-wrong" for r in judged)
    return summary


def regrade(path: Path, cuad_path: Path | None = None, judge_model: str | None = None) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    spans = load_spans(cuad_path) if cuad_path and cuad_path.exists() else None
    if judge_model and spans is None:
        raise SystemExit("--judge needs --cuad pointing at CUAD_v1.json, for the annotated spans")
    questions = {q.id: q for q in gold.load(DATASET_DIR / "gold.jsonl")}
    files = {fold_name(p.stem): p for p in CORPUS_DIR.iterdir() if p.is_file()}
    for r in report["records"]:
        r["abstained"] = bool(ABSTAIN.search(r["answer"]))
        r["cited_pages"] = sorted({int(n) for n in PAGE.findall(r["answer"])})
        q = questions.get(r["question_id"])
        if spans is not None and q and q.relevant:
            path_ = files.get(fold_name(Path(q.relevant[0].filename).stem))
            gold_spans = spans.get((fold_name(path_.stem), clause_of(q.note)), []) if path_ else []
            r["support"] = round(supported(r["answer"], gold_spans), 2) if gold_spans else r["support"]
    if judge_model:
        judge_records(report["records"], spans, files, judge_model)
    report["summary"] = summarise(report["records"], list(report["summary"]))
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def print_summary(report: dict) -> None:
    conds = list(report["summary"])
    keys = [k for k in report["summary"][conds[0]] if k != "questions"]
    print(f"\n  {report['label']}  |  {report['model']}  docs <= {report['max_doc_tokens']} tokens\n")
    print(f"  {'':36}" + "".join(f"{c:>10}" for c in conds))
    print(f"  {'questions':36}" + "".join(f"{report['summary'][c]['questions']:>10}" for c in conds))
    for key in keys:
        print(f"  {key:36}" + "".join(f"{str(report['summary'][c][key]):>10}" for c in conds))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Answer-time faithfulness: retrieved chunks vs whole document.")
    parser.add_argument("--cuad", type=Path, required=True, help="Path to CUAD_v1.json, for the answer spans")
    parser.add_argument("--model", default=settings.llm_model_name if settings.LLM_PROVIDER == "ollama" else "gemma4:e4b")
    parser.add_argument("--num-ctx", type=int, default=settings.LLM_NUM_CTX)
    parser.add_argument("--max-doc-tokens", type=int, default=6000)
    parser.add_argument("--conditions", default="rag5,rag10,full")
    parser.add_argument("--label", default="faithfulness")
    parser.add_argument("--no-think", action="store_true", help="Disable a thinking model's reasoning pass")
    parser.add_argument("--provider", choices=("ollama", "gemini"), default="ollama")
    parser.add_argument("--regrade", type=Path, nargs="*", help="Re-score saved reports with the current grader, then exit")
    parser.add_argument("--judge", nargs="?", const=JUDGE_MODEL, default=None,
                        help=f"Also grade with the calibrated model judge (default {JUDGE_MODEL})")
    parser.add_argument("--only", default="", help="Comma-separated question ids, for a targeted run")
    args = parser.parse_args()

    if args.regrade:
        for path in args.regrade:
            print_summary(regrade(path, args.cuad, args.judge))
        return

    report = run(args.cuad, args.model, args.num_ctx, args.max_doc_tokens, args.conditions.split(","), args.label,
                 think=False if args.no_think else None, provider=args.provider, judge_model=args.judge,
                 only={q.strip() for q in args.only.split(",") if q.strip()} or None)
    print_summary(report)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{args.label}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Report written to {out}\n")


if __name__ == "__main__":
    main()
