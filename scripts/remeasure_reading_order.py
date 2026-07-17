#!/usr/bin/env python3
"""읽기순서 지표 재측정 — 캐시된 baseline OCR 출력 재사용(OCR 재실행 없음).

각 세트: id순 CER(before) vs 읽기순서 CER(after) vs 놓침률 vs 추가율 micro 집계.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from img2txt.bench.aihub import _reading_order_words
from img2txt.bench.normalize import normalize_strict
from img2txt.bench.scoring import levenshtein, char_multiset_diff

REPORTS = Path("bench_data/reports")
LBL_ROOT = Path("bench_data/023.OCR 데이터(공공)/01-1.정식개방데이터/Validation/02.라벨링데이터")
SETS = {
    "2010": ("baseline-2010.jsonl", "VL_OCR(public)_AF_2010_5270218_0001"),
    "1990": ("baseline-AF_1990_5270218_0010.jsonl", "VL_OCR(public)_AF_1990_5270218_0010"),
    "1980": ("baseline-AF_1980_5350073_0002.jsonl", "VL_OCR(public)_AF_1980_5350073_0002"),
    "b1980": ("baseline-AF_b1980_5350073_0001.jsonl", "VL_OCR(public)_AF_b1980_5350073_0001"),
}


def _id_order_join(bbox: list) -> str:
    return " ".join(e["data"] for e in sorted(bbox, key=lambda e: e["id"]))


def _measure(jsonl: Path, lbl_dir: Path) -> dict:
    pages = {}
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("point") == "raw":
            pages[r["page_id"]] = r["normalized_output"]

    d_id = d_ro = ref_chars = 0
    miss = extra = ref_ms = 0
    n = 0
    for page_id, hyp in pages.items():
        lp = lbl_dir / f"{page_id}.json"
        if not lp.exists():
            continue
        bbox = json.loads(lp.read_text(encoding="utf-8"))["Bbox"]
        ref_id = normalize_strict(_id_order_join(bbox))
        ref_ro = normalize_strict(" ".join(_reading_order_words(bbox)))
        d_id += levenshtein(ref_id, hyp)
        d_ro += levenshtein(ref_ro, hyp)
        ref_chars += len(ref_id)
        m, e, t = char_multiset_diff(ref_ro, hyp)
        miss += m; extra += e; ref_ms += t
        n += 1
    return {
        "n": n,
        "cer_id": d_id / ref_chars if ref_chars else 0.0,
        "cer_ro": d_ro / ref_chars if ref_chars else 0.0,
        "miss": miss / ref_ms if ref_ms else 0.0,
        "extra": extra / ref_ms if ref_ms else 0.0,
    }


def main() -> None:
    rows = []
    for name, (jsonl, lbl) in SETS.items():
        jp = REPORTS / jsonl
        if not jp.exists():
            print(f"skip {name}: {jp} 없음")
            continue
        res = _measure(jp, LBL_ROOT / lbl)
        rows.append((name, res))
        print(f"{name} n={res['n']} cer_id={res['cer_id']:.4f} "
              f"cer_ro={res['cer_ro']:.4f} miss={res['miss']:.4f} extra={res['extra']:.4f}")


if __name__ == "__main__":
    main()
