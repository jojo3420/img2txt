#!/usr/bin/env python3
"""AI Hub 라벨 구조 인스펙션 도구.

데이터 반입 직후 라벨 어댑터를 확정하기 위해 확장자 분포와
샘플 구조(JSON 최상위 키 / 텍스트 미리보기)를 보고한다.
결과 출력은 CLI 결과물이므로 print를 사용한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PREVIEW_CHARS: int = 300
DEFAULT_SAMPLE_COUNT: int = 3


def _sample_entry(path: Path) -> dict:
	"""파일 1개의 구조 요약을 만든다."""
	raw = path.read_text(encoding="utf-8", errors="replace")
	if path.suffix.lower() == ".json":
		try:
			data = json.loads(raw)
			keys = sorted(data.keys()) if isinstance(data, dict) else None
			return {
				"name": path.name,
				"kind": "json",
				"top_level_keys": keys,
				"preview": raw[:PREVIEW_CHARS],
			}
		except json.JSONDecodeError:
			pass
	return {
		"name": path.name,
		"kind": "text",
		"top_level_keys": None,
		"preview": raw[:PREVIEW_CHARS],
	}


def inspect_dir(label_dir: Path, sample_count: int = DEFAULT_SAMPLE_COUNT) -> dict:
	"""라벨 디렉터리의 확장자 분포와 샘플 구조를 요약한다.

	Args:
		label_dir: 라벨 디렉터리.
		sample_count: 구조를 덤프할 샘플 파일 수.

	Returns:
		extension_counts / total_files / samples 요약 dict.
	"""
	files = sorted(p for p in label_dir.glob("*") if p.is_file())
	extension_counts: dict[str, int] = {}
	for p in files:
		ext = p.suffix.lower()
		extension_counts[ext] = extension_counts.get(ext, 0) + 1
	samples = [_sample_entry(p) for p in files[:sample_count]]
	return {
		"extension_counts": extension_counts,
		"total_files": len(files),
		"samples": samples,
	}


def main(argv: list[str] | None = None) -> int:
	"""CLI 진입점: 요약을 JSON으로 출력한다."""
	parser = argparse.ArgumentParser(description="라벨 구조 인스펙션")
	parser.add_argument("label_dir", type=Path, help="라벨 디렉터리 경로")
	parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLE_COUNT, help="샘플 수")
	args = parser.parse_args(argv)

	if not args.label_dir.is_dir():
		print(f"디렉터리 없음: {args.label_dir}", file=sys.stderr)
		return 1
	result = inspect_dir(args.label_dir, args.samples)
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	sys.exit(main())
