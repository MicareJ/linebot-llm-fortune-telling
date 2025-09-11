import os
import json
import re
from typing import Dict, List, Tuple
from functools import lru_cache
from dotenv import load_dotenv

from core.logger_config import setup_logger

load_dotenv()

logger = setup_logger('stroke_lookup')

# 從環境變數讀取路徑
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CNS_UNICODE_BMP_PATH = os.path.join(BASE_DIR, "data", "CNS2UNICODE_Unicode_BMP.txt")
CNS_STROKE_PATH = os.path.join(BASE_DIR, "data", "CNS_stroke.txt")
CACHE_PATH = os.path.join(BASE_DIR, "data", "char_stroke_cache.json")

# 全局快取字典
char_to_stroke: Dict[str, int] = {}

def _normalize_hex(s: str) -> str:
    """清理 Unicode hex 格式"""
    s = s.strip().upper()
    if s.startswith("U+"):
        s = s[2:]
    if s.startswith("0X"):
        s = s[2:]
    if not re.match(r'^[0-9A-F]+$', s):
        raise ValueError(f"Invalid hex string: {s}")
    return s

def load_cns_unicode_mapping(path: str) -> Dict[str, str]:
    """載入 BMP 對照表 (Unicode -> CNS)"""
    mapping = {}
    try:
        if not os.path.exists(path) or not os.access(path, os.R_OK):
            logger.error(f"CNS Unicode BMP 對照表不存在或無讀取權限: {path}")
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
                except ValueError:
                    logger.warning(f"Invalid Unicode hex: {unicode_hex}")
                    continue

                mapping[ch] = cns_code
        logger.info(f"Loaded {len(mapping)} Unicode to CNS mappings")
        return mapping
    except Exception as e:
        logger.error(f"Error loading Unicode mapping: {str(e)}")
        return {}

def load_cns_stroke_mapping(path: str) -> Dict[str, int]:
    """載入 CNS -> 筆畫數 對照"""
    mapping = {}
    try:
        if not os.path.exists(path) or not os.access(path, os.R_OK):
            logger.error(f"CNS 筆畫數檔不存在或無讀取權限: {path}")
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
                    except ValueError:
                        logger.warning(f"Invalid stroke count: {stroke} for {cns_code}")
                        continue
        logger.info(f"Loaded {len(mapping)} CNS to stroke mappings")
        return mapping
    except Exception as e:
        logger.error(f"Error loading stroke mapping: {str(e)}")
        return {}

def build_char_to_stroke_cache():
    """建立 char -> stroke 快取"""
    try:
        unicode_to_cns = load_cns_unicode_mapping(CNS_UNICODE_BMP_PATH)
        cns_to_stroke = load_cns_stroke_mapping(CNS_STROKE_PATH)

        if not unicode_to_cns or not cns_to_stroke:
            raise ValueError("Mapping files are empty or invalid")

        mapping = {}
        for ch, cns in unicode_to_cns.items():
            mapping[ch] = cns_to_stroke.get(cns, -1)

        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(mapping, f, ensure_ascii=False)
            logger.info(f"Built and saved stroke cache with {len(mapping)} entries")
        except Exception as e:
            logger.error(f"Error saving cache: {str(e)}")
        return mapping
    except Exception as e:
        logger.error(f"Error building cache: {str(e)}")
        return {}

def load_char_to_stroke_cache():
    """載入快取，如果沒有則建立（模組層級呼叫一次）"""
    global char_to_stroke
    try:
        if os.path.exists(CACHE_PATH) and os.access(CACHE_PATH, os.R_OK):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                char_to_stroke = json.load(f)
            logger.info(f"Loaded stroke cache with {len(char_to_stroke)} entries")
        else:
            logger.warning("Cache not found, building new one")
            char_to_stroke = build_char_to_stroke_cache()
    except Exception as e:
        logger.error(f"Error loading cache: {str(e)}")
        char_to_stroke = {}

# 模組載入時自動載入快取
load_char_to_stroke_cache()

@lru_cache(maxsize=100)
def get_name_stroke_info(name: str) -> List[Tuple[str, int]]:
    """查詢姓名的每個字筆畫數"""
    return [(ch, char_to_stroke.get(ch, -1)) for ch in name]