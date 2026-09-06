import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

EVAL_ROOT = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_ROOT / "corpus"
DATASET_DIR = EVAL_ROOT / "datasets"
REPORT_DIR = EVAL_ROOT / "reports"

EVAL_TENANT_EMAIL = "__evals__@localhost"
