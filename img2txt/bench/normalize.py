from __future__ import annotations

import re
import unicodedata

# 부호 매핑 상수 (스펙 5.3)
_PUNCTUATION_MAP: dict[str, str] = {
    '“': '"',  # LEFT DOUBLE QUOTATION MARK
    '”': '"',  # RIGHT DOUBLE QUOTATION MARK
    '‘': "'",  # LEFT SINGLE QUOTATION MARK
    '’': "'",  # RIGHT SINGLE QUOTATION MARK
    '–': '-',  # EN DASH
    '—': '-',  # EM DASH
    '‑': '-',  # NON-BREAKING HYPHEN
    '…': '...',  # HORIZONTAL ELLIPSIS
}

# 전각 → 반각 매핑
_FULLWIDTH_TO_HALFWIDTH: dict[str, str] = {
    chr(0xFF10 + i): str(i) for i in range(10)  # ０～９ → 0～9
}
# 전각 대문자
for i in range(26):
    _FULLWIDTH_TO_HALFWIDTH[chr(0xFF21 + i)] = chr(0x41 + i)  # Ａ～Ｚ → A～Z
# 전각 소문자
for i in range(26):
    _FULLWIDTH_TO_HALFWIDTH[chr(0xFF41 + i)] = chr(0x61 + i)  # ａ～ｚ → a～z


def normalize_strict(text: str) -> str:
    """NFC 유니코드 정규화 + 공백/줄바꿈 정리.

    Args:
        text: 입력 텍스트.

    Returns:
        정규화된 텍스트 (부호 매핑 제외).
    """
    # 1. NFC 정규화 (한글 자모 조합)
    nfc_text = unicodedata.normalize("NFC", text)

    # 2. 줄바꿈 → 공백
    with_spaces = nfc_text.replace("\n", " ")

    # 3. 연속 공백 → 단일 공백
    normalized = re.sub(r" +", " ", with_spaces)

    # 4. 앞뒤 공백 제거
    return normalized.strip()


def normalize_lenient(text: str) -> str:
    """strict 정규화 + 부호 매핑 (스펙 5.3).

    Args:
        text: 입력 텍스트.

    Returns:
        정규화된 텍스트 (부호 매핑 포함).
    """
    # 1. strict 먼저 적용
    strict_result = normalize_strict(text)

    # 2. 부호 매핑: 유니코드 문장부호 → ASCII
    result = strict_result
    for unicode_char, ascii_char in _PUNCTUATION_MAP.items():
        result = result.replace(unicode_char, ascii_char)

    # 3. 전각 숫자/문자 → 반각
    for fullwidth, halfwidth in _FULLWIDTH_TO_HALFWIDTH.items():
        result = result.replace(fullwidth, halfwidth)

    return result
