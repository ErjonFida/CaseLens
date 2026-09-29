import argparse
import logging
import secrets
import sys
from pathlib import Path

import bcrypt
from sqlalchemy import select

from database import SyncSessionLocal
from legal_api.models import User
from ocr import extract_document_pages
from vector_store import LegalVectorStore

DEMO_EMAIL = "demo@example.com"

DEMO_CONTRACTS = {
    "SCOUTCAMINC_05_12_2020": "Scoutcam Services Agreement.pdf",
    "OFGBANCORP_03_28_2007": "OFG Bancorp Outsourcing Agreement.pdf",
    "TRANSMONTAIGNEPARTNERSLLC_03_13_2020": "Transmontaigne Partners Services Agreement.pdf",
    "MERITLIFEINSURANCECO_06_19_2020": "Merit Life Insurance Master Services Agreement.pdf",
    "MSCIINC_02_28_2008": "MSCI Intellectual Property Agreement.pdf",
}


def find_contracts(folder: Path) -> dict[str, Path]:
    found = {}
    for prefix, name in DEMO_CONTRACTS.items():
        matches = [p for p in folder.rglob("*") if p.is_file() and p.name.upper().startswith(prefix)]
        if not matches:
            sys.exit(f"No contract starting {prefix} under {folder}")
        found[name] = matches[0]
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the shared read-only demo account.")
    parser.add_argument("folder", type=Path, help="A folder holding CUAD's contract PDFs, searched recursively")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    contracts = find_contracts(args.folder)

    session = SyncSessionLocal()
    store = LegalVectorStore()
    try:
        user = session.execute(select(User).where(User.email == DEMO_EMAIL)).scalar_one_or_none()
        if user is None:
            # A password nobody knows: the demo is entered through /api/demo only.
            unusable = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()
            user = User(email=DEMO_EMAIL, password_hash=unusable, is_demo=True)
            session.add(user)
            session.commit()
        elif not user.is_demo:
            sys.exit(f"{DEMO_EMAIL} exists and is not the demo account; refusing to touch it")

        for name, path in contracts.items():
            store.delete_document(name, user, session)
            pages = extract_document_pages(str(path))
            store.add_document_pages(name, pages, user, session)
            print(f"indexed {name}: {len(pages)} pages")
    finally:
        session.close()


if __name__ == "__main__":
    main()
