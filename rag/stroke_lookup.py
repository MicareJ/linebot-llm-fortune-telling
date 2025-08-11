import os
import json
import logging
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO)

# 檔案路徑設定
CNS_UNICODE_BMP_PATH = "data/Unicode/CNS2UNICODE_Unicode BMP.txt"
CNS_STROKE_PATH = "data/CNS_Stroke_Table.txt"
CACHE_PATH = "data/char_stroke_cache.json"

# 快取字典
char_to_stroke: Dict[str, int] = {}


def _normalize_hex(s: str) -> str:
    """清理 Unicode hex 格式"""
    s = s.strip().upper()
    if s.startswith("U+"):
        s = s[2:]
    if s.startswith("0X"):
        s = s[2:]
    return s


def load_cns_unicode_mapping(path: str) -> Dict[str, str]:
    """載入 BMP 對照表 (Unicode -> CNS)"""
    mapping = {}
    if not os.path.exists(path):
        logging.error(f"CNS Unicode BMP 對照表不存在: {path}")
        return mapping

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                parts = line.split()
            if len(parts) < 2:
                continue

            cns_code = parts[0].strip()
            unicode_hex = _normalize_hex(parts[1])

            try:
                ch = chr(int(unicode_hex, 16))
            except:
                continue

            mapping[ch] = cns_code
    return mapping


def load_cns_stroke_mapping(path: str) -> Dict[str, int]:
    """載入 CNS -> 筆畫數 對照"""
    mapping = {}
    if not os.path.exists(path):
        logging.error(f"CNS 筆畫數檔不存在: {path}")
        return mapping

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.strip().split()
            if len(parts) >= 2:
                cns_code, stroke = parts[:2]
                try:
                    mapping[cns_code] = int(stroke)
                except:
                    continue
    return mapping


def build_char_to_stroke_cache():
    """建立 char -> stroke 快取"""
    unicode_to_cns = load_cns_unicode_mapping(CNS_UNICODE_BMP_PATH)
    cns_to_stroke = load_cns_stroke_mapping(CNS_STROKE_PATH)

    mapping = {}
    for ch, cns in unicode_to_cns.items():
        mapping[ch] = cns_to_stroke.get(cns, -1)

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False)

    return mapping


def load_char_to_stroke_cache():
    """載入快取，如果沒有則建立"""
    global char_to_stroke
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            char_to_stroke = json.load(f)
    else:
        char_to_stroke = build_char_to_stroke_cache()


def get_name_stroke_info(name: str) -> List[Tuple[str, int]]:
    """查詢姓名的每個字筆畫數"""
    return [(ch, char_to_stroke.get(ch, -1)) for ch in name]


def format_name_strokes_prompt(name: str) -> str:
    """格式化成適合給 LLM 的輸入字串"""
    strokes = get_name_stroke_info(name)
    lines = ["姓名筆畫分析："]
    for ch, s in strokes:
        lines.append(f"字：{ch} → 筆畫數：{s if s != -1 else '未知'}")
    return "\n".join(lines)

