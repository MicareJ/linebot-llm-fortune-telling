from functools import lru_cache
from typing import Dict
from .stroke_lookup import load_char_to_stroke_cache, get_name_stroke_info, validate_name

from core.logger_config import setup_logger

logger = setup_logger('name_fivegrid_wuxing')

def stroke_to_wuxing(stroke: int) -> str:
    """根據筆畫數判斷五行"""
    if stroke < 0:
        return "未知"
    last = stroke % 10
    if last in (1, 2): return "木"
    if last in (3, 4): return "火"
    if last in (5, 6): return "土"
    if last in (7, 8): return "金"
    if last in (9, 0): return "水"
    return "未知"

@lru_cache(maxsize=100)
def analyze_name_five_grid(name: str) -> Dict[str, any]:
    """計算姓名五格和五行"""
    try:
        load_char_to_stroke_cache()  # 確保快取載入

        if not validate_name(name) or len(name) < 2:
            raise ValueError("姓名至少需為兩字，且為繁體中文")

        stroke_info = get_name_stroke_info(name)

        # 檢查是否有未知筆畫
        if any(s == -1 for ch, s in stroke_info):
            logger.warning(f"Unknown stroke count for characters in {name}")

        surname = name[0]
        given = name[1:]

        surname_strokes = sum(s for ch, s in stroke_info if ch == surname)
        given_strokes = sum(s for ch, s in stroke_info if ch in given)

        tian = surname_strokes + 1
        ren = stroke_info[0][1] + stroke_info[1][1]
        di = given_strokes if len(given) > 1 else given_strokes + 1
        zong = surname_strokes + given_strokes
        wai = zong - ren if zong - ren > 0 else 1  # 防負值

        grids = {"天格": tian, "人格": ren, "地格": di, "外格": wai, "總格": zong}
        wuxing = {k: stroke_to_wuxing(v) for k, v in grids.items()}

        logger.info(f"Analyzed five grids for name: {name}")
        return {"grids": grids, "wuxing": wuxing}
    except Exception as e:
        logger.error(f"Five grid analysis error: {str(e)}")
        raise

def format_fivegrid_wuxing_prompt(name: str) -> str:
    """格式化五格和五行分析為 LLM 輸入"""
    try:
        data = analyze_name_five_grid(name)
        lines = ["姓名五格＆五行分析："]
        for key in ("天格", "人格", "地格", "外格", "總格"):
            lines.append(f"{key}：{data['grids'][key]}（{data['wuxing'][key]}）")
        return "\n".join(lines)
    except ValueError as e:
        logger.error(f"Format prompt error: {str(e)}")
        return "姓名輸入無效，請使用繁體中文（至少兩字）"