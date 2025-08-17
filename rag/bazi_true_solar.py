from __future__ import annotations

import os
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

GAN = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
ZHI = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]

STEM_FIVE = {
    "甲":"木","乙":"木","丙":"火","丁":"火","戊":"土",
    "己":"土","庚":"金","辛":"金","壬":"水","癸":"水"
}
BRANCH_FIVE = {
    "子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火",
    "午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"
}

@dataclass
class FourPillars:
    year: tuple[str, str]
    month: tuple[str, str]
    day: tuple[str, str]
    hour: tuple[str, str]

def equation_of_time_minutes(d: datetime) -> float:
    """修正時間方程"""
    try:
        n = int(d.strftime("%j"))
        B = (n - 1) * 360 / 365.0
        E = 4 * (0.017 * math.sin(math.radians(B)) + 0.4281 * math.cos(math.radians(B)))
        return E
    except Exception as e:
        logger.error(f"Equation of time error: {str(e)}")
        return 0.0

def true_solar_datetime(
    dt_local: datetime,
    longitude_deg: float,
) -> datetime:
    """將當地民用時間換算為真太陽時（修正經度符號：東經負，西經正）"""
    try:
        if dt_local.tzinfo is None:
            raise ValueError("dt_local 必須是具時區資訊的 aware datetime")
        if not -180 <= longitude_deg <= 180:
            raise ValueError("經度必須在 -180 到 180 之間")

        # 網站符號系統：東經負，西經正
        L_loc = -longitude_deg if longitude_deg > 0 else abs(longitude_deg)  # 東經負，西經正

        dst = dt_local.dst() or timedelta(0)
        dt_standard = dt_local - dst

        utc_off = dt_standard.utcoffset() or timedelta(0)
        tz_hours = utc_off.total_seconds() / 3600.0

        # L_st = (時區 - 0) * 15，東經負，西經正
        L_st = -15.0 * tz_hours if tz_hours > 0 else 15.0 * abs(tz_hours)

        longitude_correction_min = 4.0 * (L_st - L_loc)

        eot_min = equation_of_time_minutes(dt_standard)

        delta_min = longitude_correction_min + eot_min

        dt_true = dt_standard + timedelta(minutes=delta_min)

        return dt_true.astimezone(dt_local.tzinfo)
    except Exception as e:
        logger.error(f"True solar time error: {str(e)}")
        raise

@lru_cache(maxsize=50)
def calc_four_pillars_with_true_solar(
    year: int,
    month: int,
    day: int,
    hour: int,
    tz_name: str,
    longitude_deg: float,
) -> FourPillars:
    """計算四柱"""
    try:
        if not (1900 <= year <= 2100):
            raise ValueError("年份必須在 1900-2100 之間")
        if not (1 <= month <= 12) or not (1 <= day <= 31) or not (0 <= hour <= 23):
            raise ValueError("日期/時間無效")

        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            fallback_tz = os.getenv("DEFAULT_TZ", "Asia/Taipei")
            logger.warning(f"Invalid timezone {tz_name}, using fallback {fallback_tz}")
            tz = ZoneInfo(fallback_tz)

        dt_local = datetime(year, month, day, hour, tzinfo = tz)

        dt_true = true_solar_datetime(dt_local, longitude_deg)

        Y, M, D = dt_true.year, dt_true.month, dt_true.day
        HH = dt_true.hour

        # 年柱：近似立春調整
        lichun_month, lichun_day = 2, 4 if Y % 4 == 0 else 3
        if M < lichun_month or (M == lichun_month and D < lichun_day):
            Y -= 1

        # 月柱：近似節氣調整
        jieqi = [None, (2, 4), (3, 5), (4, 5), (5, 5), (6, 6), (7, 7), (8, 7), (9, 7), (10, 8), (11, 7), (12, 7)]
        jieqi_month, jieqi_day = jieqi[M]
        if D < jieqi_day:
            M -= 1
            if M == 0:
                M = 12
                Y -= 1

        # 日柱：子時切日
        day_for_hour_tg = 0  # 預設
        if HH == 23:
            prev_dt = dt_true - timedelta(days=1)
            Y, M, D = prev_dt.year, prev_dt.month, prev_dt.day

        # 簡化干支計算（基於基準年 1984 甲子）
        base_year = 1984
        year_cycle = (Y - base_year) % 60
        y_gan = year_cycle % 10
        y_zhi = year_cycle % 12

        base_day = datetime(1984, 1, 1).toordinal()
        day_cycle = (datetime(Y, M, D).toordinal() - base_day) % 60
        d_gan = day_cycle % 10
        d_zhi = day_cycle % 12
        day_for_hour_tg = d_gan

        # 時柱
        hour_zhi = HH // 2 % 12
        hour_gan = (day_for_hour_tg * 2 + hour_zhi + (1 if HH % 2 == 1 else 0)) % 10

        # 月干支簡化
        month_zhi = (M + 2) % 12  # 寅為1月起
        month_gan = (y_gan * 2 + month_zhi) % 10

        logger.info("Calculated four pillars successfully")
        return FourPillars(
            year=(GAN[y_gan], ZHI[y_zhi]),
            month=(GAN[month_gan], ZHI[month_zhi]),
            day=(GAN[d_gan], ZHI[d_zhi]),
            hour=(GAN[hour_gan], ZHI[hour_zhi]),
        )
    except Exception as e:
        logger.error(f"Four pillars calculation error: {str(e)}")
        raise

def bazi_five_elements_summary(fp: FourPillars) -> tuple[dict[str,int], list[str], list[str]]:
    """計算五行分佈"""
    counts = {"木":0,"火":0,"土":0,"金":0,"水":0}
    for gan, zhi in [fp.year, fp.month, fp.day, fp.hour]:
        counts[STEM_FIVE[gan]] += 1
        counts[BRANCH_FIVE[zhi]] += 1
    max_v = max(counts.values())
    min_v = min(counts.values())
    strongest = [k for k, v in counts.items() if v == max_v]
    weakest   = [k for k, v in counts.items() if v == min_v]
    return counts, strongest, weakest

@lru_cache(maxsize = 50)
def format_bazi_report(year:int, month:int, day:int, hour:int, tz_name:str, longitude_deg:float) -> str:
    """產出可直接餵給 RAG 的資訊"""
    fp = calc_four_pillars_with_true_solar(year, month, day, hour, tz_name, longitude_deg)
    counts, strongest, weakest = bazi_five_elements_summary(fp)

    bazi_str = " ".join([f"{g}{z}" for g, z in [fp.year, fp.month, fp.day, fp.hour]])
    cnt_str = "、".join([f"{k}:{v}" for k, v in counts.items()])
    strong_str = "、".join(strongest) if strongest else "無"
    weak_str   = "、".join(weakest) if weakest else "無"

    return (
        f"四柱（以立春為年界、節氣為月界，真太陽時修正）：{bazi_str}\n"
        f"五行分佈：{cnt_str}\n"
        f"強旺五行：{strong_str}\n"
        f"衰弱五行：{weak_str}"
    )