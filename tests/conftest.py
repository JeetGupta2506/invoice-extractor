import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LABELLED = ROOT / "data" / "sample_pack" / "labelled"


def gold_files():
    return sorted(LABELLED.glob("L*.json")) if LABELLED.exists() else []


needs_samples = pytest.mark.skipif(not LABELLED.exists(), reason="sample pack not in data/sample_pack")


@pytest.fixture
def gold():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in gold_files()}
