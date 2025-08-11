import logging
from datetime import datetime
from stroke_lookup import load_char_to_stroke_cache, format_name_strokes_prompt

logging.basicConfig(level=logging.INFO)

# 天干與地支
HEAVENLY_STEMS = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
EARTHLY_BRANCHES = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]

# 天干對應五行
STEM_FIVE_ELEMENTS = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水"
}

# 地支對應五行（主氣）
BRANCH_FIVE_ELEMENTS = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水"
}

def calculate_bazi(year: int, month: int, day: int, hour: int):
    """
    簡化版八字計算（萬年曆簡化演算法）
    - 年柱：根據年份計算天干地支
    - 月柱、日柱、時柱：簡化推算（未完全對齊專業命理，但足夠用於演示與 RAG 輸入）
    """
    # 年柱
    year_gan = HEAVENLY_STEMS[(year - 4) % 10]
    year_zhi = EARTHLY_BRANCHES[(year - 4) % 12]

    # 月柱（簡化：固定以立春為年首）
    month_index = (month + 1) % 12
    month_gan = HEAVENLY_STEMS[( (year - 4) * 12 + month_index + 2 ) % 10]
    month_zhi = EARTHLY_BRANCHES[(month + 1) % 12]

    # 日柱（簡化：用固定基準日計算差值）
    base_date = datetime(1900, 1, 1)
    target_date = datetime(year, month, day)
    day_diff = (target_date - base_date).days
    day_gan = HEAVENLY_STEMS[(day_diff + 10) % 10]
    day_zhi = EARTHLY_BRANCHES[(day_diff + 12) % 12]

    # 時柱（每 2 小時一支）
    hour_index = (hour + 1) // 2 % 12
    hour_gan = HEAVENLY_STEMS[(HEAVENLY_STEMS.index(day_gan) * 2 + hour_index) % 10]
    hour_zhi = EARTHLY_BRANCHES[hour_index]

    bazi = [
        (year_gan, year_zhi),
        (month_gan, month_zhi),
        (day_gan, day_zhi),
        (hour_gan, hour_zhi)
    ]
    return bazi

def analyze_five_elements(bazi):
    """計算五行分佈與缺失"""
    counts = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    for gan, zhi in bazi:
        counts[STEM_FIVE_ELEMENTS[gan]] += 1
        counts[BRANCH_FIVE_ELEMENTS[zhi]] += 1
    missing = [elem for elem, cnt in counts.items() if cnt == 0]
    return counts, missing

def build_fortune_prompt(name: str, year: int, month: int, day: int, hour: int, rag_context: str = ""):
    """整合姓名筆畫 + 八字 + 五行分析成 RAG 輸入"""
    # 載入筆畫快取（只需啟動時載一次）
    load_char_to_stroke_cache()
    stroke_prompt = format_name_strokes_prompt(name)

    # 八字計算
    bazi = calculate_bazi(year, month, day, hour)
    bazi_str = " ".join([f"{gan}{zhi}" for gan, zhi in bazi])

    # 五行分析
    five_elem_counts, missing = analyze_five_elements(bazi)
    five_elem_str = "、".join([f"{k}:{v}" for k, v in five_elem_counts.items()])
    missing_str = "無" if not missing else "、".join(missing)

    # 合併成 prompt
    prompt_parts = [
        stroke_prompt,
        f"生辰八字：{bazi_str}",
        f"五行分佈：{five_elem_str}",
        f"五行缺失：{missing_str}"
    ]
    if rag_context:
        prompt_parts.append(f"檢索資料：\n{rag_context}")
    return "\n".join(prompt_parts)

# 測試
if __name__ == "__main__":
    test_prompt = build_fortune_prompt("黃子軒", 1995, 8, 11, 15, "這裡是RAG檢索到的內容")
    print(test_prompt)
