#!/usr/bin/env python3
"""
بصمة الزمن في الذهب — Gold Time-of-Day Footprint
=================================================

يبحث عن الدقائق المحدّدة من اليوم التي تتحرك فيها شمعة الذهب — بمجرد افتتاحها —
في اتجاه واحد ثابت (صعود/هبوط) دون انعكاس يُذكر، بالاعتماد على الزمن فقط.

الاستخدام:
    python analyze_gold_time.py data/XAUUSD_ticks.csv

البيانات المتوقعة (CSV) — أحد الشكلين، والكود يكتشف الأعمدة تلقائياً:
    تيك:  time/timestamp/gmt time , bid , ask        (الأفضل والأدق)
    أو OHLC دقيقة: time/date , open , high , low , close   (تقريبي، بديل)

اقرأ PLAN.md للتفاصيل الكاملة والتعريفات.
"""

import sys
import os
import numpy as np
import pandas as pd

# ======================== الإعدادات (عدّلها هنا) ========================
SOURCE_TZ        = "UTC"               # ⚠️ توقيت السيرفر في ملف بياناتك (مثل: "UTC", "Etc/GMT-2", "Etc/GMT-3")
TARGET_TZ        = "America/New_York"  # التوقيت المرجعي (واعٍ بالتوقيت الصيفي) — لا تغيّره عادةً

MOVE_THRESHOLD   = 5.0     # الحركة المطلوبة في اتجاه واحد (دولار)
PURITY_THRESHOLD = 3.0     # أقصى ارتداد عكسي مسموح قبل تحقيق الحركة (دولار)
SUCCESS_RATE     = 0.90    # عتبة "الدقيقة الفائزة"
MIN_SAMPLES      = 200     # أقل عدد عينات مقبول لكل دقيقة

TIMEFRAMES       = [1, 5, 15]   # الفريمات بالدقائق
SPLIT_BY_WEEKDAY = False         # True = افصل التحليل حسب يوم الأسبوع أيضاً

OOS_TRAIN_FRACTION = 0.6   # نسبة بيانات التدريب (الباقي اختبار خارج العينة)
OUT_DIR          = "out"
# =======================================================================


def log(msg):
    print(f"[*] {msg}", flush=True)


# ----------------------------- تحميل البيانات -----------------------------
def load_data(path):
    log(f"قراءة الملف: {path}")
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    # اكتشاف عمود الوقت
    time_col = next((c for c in df.columns
                     if c in ("time", "timestamp", "datetime", "date", "gmt time", "local time")
                     or "time" in c or "date" in c), None)
    if time_col is None:
        raise ValueError(f"لم أجد عمود الوقت. الأعمدة: {list(df.columns)}")

    df["ts"] = pd.to_datetime(df[time_col], errors="coerce", utc=False)
    df = df.dropna(subset=["ts"]).reset_index(drop=True)

    # اكتشاف نوع البيانات: تيك (bid/ask) أم OHLC
    has_bidask = "bid" in df.columns and "ask" in df.columns
    has_ohlc   = all(c in df.columns for c in ("open", "high", "low", "close"))

    if has_bidask:
        log("نوع البيانات: تيك (bid/ask) — دقة عالية ✓")
        df["price"] = (pd.to_numeric(df["bid"], errors="coerce") +
                       pd.to_numeric(df["ask"], errors="coerce")) / 2.0
        df = df.dropna(subset=["price"])
        mode = "tick"
    elif "bid" in df.columns or "price" in df.columns or "close" in df.columns:
        col = "price" if "price" in df.columns else ("bid" if "bid" in df.columns else "close")
        log(f"نوع البيانات: تيك بعمود سعر واحد ('{col}')")
        df["price"] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["price"])
        mode = "tick"
    elif has_ohlc:
        log("نوع البيانات: OHLC (تقريبي) — التيك أدق، لكن سنكمل ⚠️")
        for c in ("open", "high", "low", "close"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        mode = "ohlc"
    else:
        raise ValueError(f"لم أتعرّف على شكل البيانات. الأعمدة: {list(df.columns)}")

    # توحيد التوقيت ثم التحويل إلى توقيت نيويورك (حل مصيدة DST)
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize(SOURCE_TZ, ambiguous="NaT", nonexistent="NaT")
    df = df.dropna(subset=["ts"])
    df["ts"] = df["ts"].dt.tz_convert(TARGET_TZ)

    df = df.sort_values("ts").reset_index(drop=True)
    log(f"عدد الصفوف بعد التنظيف: {len(df):,} | من {df['ts'].min()} إلى {df['ts'].max()}")
    return df, mode


# ----------------------------- تصنيف الشمعة -----------------------------
def classify_segment(prices, move, purity):
    """تُرجع 'up' / 'down' / 'none' حسب أيهما تحقّق أولاً (منطق المرور الأول)."""
    o = prices[0]
    up_hit   = np.flatnonzero(prices >= o + move)
    dn_break = np.flatnonzero(prices <= o - purity)
    dn_hit   = np.flatnonzero(prices <= o - move)
    up_break = np.flatnonzero(prices >= o + purity)

    t_up   = up_hit[0]   if up_hit.size   else np.inf  # وصل +5
    t_dnb  = dn_break[0] if dn_break.size else np.inf  # كسر -3 (عكس الصعود)
    t_dn   = dn_hit[0]   if dn_hit.size   else np.inf  # وصل -5
    t_upb  = up_break[0] if up_break.size else np.inf  # كسر +3 (عكس الهبوط)

    if t_up != np.inf and t_up < t_dnb:
        return 1   # up success
    if t_dn != np.inf and t_dn < t_upb:
        return -1  # down success
    return 0       # none


def build_candles_from_ticks(df, tf):
    """يبني، لكل شمعة بإطار tf دقيقة، (وقت الافتتاح، تصنيفها) من بيانات التيك."""
    bucket = df["ts"].dt.floor(f"{tf}min")
    codes, _ = pd.factorize(bucket)            # البيانات مرتّبة زمنياً => الأكواد متسلسلة
    prices = df["price"].to_numpy()
    ts_vals = df["ts"].to_numpy()

    # حدود المقاطع (بداية كل شمعة)
    change = np.flatnonzero(np.diff(codes)) + 1
    starts = np.concatenate(([0], change))
    ends   = np.concatenate((change, [len(codes)]))

    open_times, labels = [], []
    for s, e in zip(starts, ends):
        seg = prices[s:e]
        if seg.size == 0:
            continue
        open_times.append(ts_vals[s])
        labels.append(classify_segment(seg, MOVE_THRESHOLD, PURITY_THRESHOLD))

    out = pd.DataFrame({"open_time": pd.to_datetime(open_times), "label": labels})
    out["open_time"] = out["open_time"].dt.tz_convert(TARGET_TZ)
    return out


def build_candles_from_ohlc(df, tf):
    """بديل تقريبي من شموع الدقيقة (لا يعرف ترتيب High/Low داخل الشمعة)."""
    g = df.set_index("ts").resample(f"{tf}min")
    agg = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last")).dropna()
    o = agg["open"].to_numpy()
    up_ok = (agg["high"].to_numpy() - o >= MOVE_THRESHOLD) & (o - agg["low"].to_numpy() <= PURITY_THRESHOLD)
    dn_ok = (o - agg["low"].to_numpy() >= MOVE_THRESHOLD) & (agg["high"].to_numpy() - o <= PURITY_THRESHOLD)
    label = np.where(up_ok, 1, np.where(dn_ok, -1, 0))
    return pd.DataFrame({"open_time": agg.index, "label": label})


# ----------------------------- التجميع والتحليل -----------------------------
def aggregate(candles):
    c = candles.copy()
    c["minute_of_day"] = c["open_time"].dt.hour * 60 + c["open_time"].dt.minute
    c["weekday"] = c["open_time"].dt.weekday      # 0=الإثنين
    c["year"] = c["open_time"].dt.year
    keys = ["minute_of_day"] + (["weekday"] if SPLIT_BY_WEEKDAY else [])

    grp = c.groupby(keys)
    res = grp["label"].agg(
        n="count",
        up_rate=lambda x: (x == 1).mean(),
        down_rate=lambda x: (x == -1).mean(),
    ).reset_index()
    return c, res


def oos_validation(candles):
    """يقسم زمنياً: تدريب / اختبار خارج العينة، ويعيد النسب في كلٍّ منهما."""
    c = candles.sort_values("open_time").reset_index(drop=True)
    cut = int(len(c) * OOS_TRAIN_FRACTION)
    train, test = c.iloc[:cut], c.iloc[cut:]

    def rates(d):
        d = d.copy()
        d["minute_of_day"] = d["open_time"].dt.hour * 60 + d["open_time"].dt.minute
        g = d.groupby("minute_of_day")["label"]
        return pd.DataFrame({
            "n": g.count(),
            "up_rate": g.apply(lambda x: (x == 1).mean()),
            "down_rate": g.apply(lambda x: (x == -1).mean()),
        })

    return rates(train), rates(test)


def year_stability(candles, direction):
    c = candles.copy()
    c["minute_of_day"] = c["open_time"].dt.hour * 60 + c["open_time"].dt.minute
    c["year"] = c["open_time"].dt.year
    target = 1 if direction == "up" else -1
    piv = (c.assign(hit=(c["label"] == target).astype(int))
             .pivot_table(index="minute_of_day", columns="year", values="hit", aggfunc="mean"))
    return piv


def fmt_minute(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def report_direction(res, train_r, test_r, candles, direction, out_dir):
    rate_col = "up_rate" if direction == "up" else "down_rate"
    winners = res[(res[rate_col] >= SUCCESS_RATE) & (res["n"] >= MIN_SAMPLES)].copy()
    winners = winners.sort_values(rate_col, ascending=False)

    # ضمّ نتيجة الاختبار خارج العينة
    winners["oos_rate"] = winners["minute_of_day"].map(test_r[rate_col])
    winners["oos_n"] = winners["minute_of_day"].map(test_r["n"])
    winners["time_ny"] = winners["minute_of_day"].map(fmt_minute)

    cols = ["time_ny", "minute_of_day"] + (["weekday"] if SPLIT_BY_WEEKDAY else []) + \
           ["n", rate_col, "oos_rate", "oos_n"]
    winners = winners[cols]

    path = os.path.join(out_dir, f"winners_{direction}.csv")
    winners.to_csv(path, index=False)
    log(f"[{direction}] دقائق فائزة: {len(winners)} → {path}")
    if len(winners):
        print(winners.head(20).to_string(index=False))
    return winners


def make_heatmaps(res, out_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        log(f"تخطّي الخرائط الحرارية (matplotlib غير متوفر): {e}")
        return
    if SPLIT_BY_WEEKDAY:
        return  # الخريطة لليوم المجمّع فقط
    for direction, col in (("up", "up_rate"), ("down", "down_rate")):
        grid = np.full((24, 60), np.nan)
        for _, r in res.iterrows():
            m = int(r["minute_of_day"])
            grid[m // 60, m % 60] = r[col]
        plt.figure(figsize=(16, 6))
        plt.imshow(grid, aspect="auto", cmap="hot", vmin=0, vmax=1)
        plt.colorbar(label=f"{direction} rate")
        plt.xlabel("Minute"); plt.ylabel("Hour (NY)")
        plt.title(f"Gold time-of-day {direction} consistency (NY time)")
        p = os.path.join(out_dir, f"heatmap_{direction}.png")
        plt.tight_layout(); plt.savefig(p, dpi=120); plt.close()
        log(f"خريطة حرارية → {p}")


def main():
    if len(sys.argv) < 2:
        print("الاستخدام: python analyze_gold_time.py <ملف_البيانات.csv>")
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)
    df, mode = load_data(sys.argv[1])

    for tf in TIMEFRAMES:
        log(f"================ إطار {tf} دقيقة ================")
        candles = (build_candles_from_ticks(df, tf) if mode == "tick"
                   else build_candles_from_ohlc(df, tf))
        log(f"عدد الشموع: {len(candles):,}")
        _, res = aggregate(candles)
        train_r, test_r = oos_validation(candles)

        tf_dir = os.path.join(OUT_DIR, f"tf{tf}")
        os.makedirs(tf_dir, exist_ok=True)
        report_direction(res, train_r, test_r, candles, "up", tf_dir)
        report_direction(res, train_r, test_r, candles, "down", tf_dir)
        make_heatmaps(res, tf_dir)
        year_stability(candles, "up").to_csv(os.path.join(tf_dir, "year_stability_up.csv"))
        year_stability(candles, "down").to_csv(os.path.join(tf_dir, "year_stability_down.csv"))

    log("انتهى. راجع مجلد out/ — وركّز على الدقائق التي تبقى ≥ 90% في عمود oos_rate.")


if __name__ == "__main__":
    main()
