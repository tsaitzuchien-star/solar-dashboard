import datetime
import html
import inspect
import math
import warnings
from zoneinfo import ZoneInfo

import gspread
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from oauth2client.service_account import ServiceAccountCredentials

# 幫 Plotly 戴上耳塞
warnings.filterwarnings("ignore", category=DeprecationWarning)

# 關鍵：set_page_config 必須是第一個 Streamlit 指令，不能移動
st.set_page_config(page_title="中創園區太陽能戰情室", layout="wide", page_icon="☀️")

# ==========================================
# 設定區
# ==========================================
APP_PASSWORD = "ASCH300!"
SHEET_NAME = "中創園區_太陽能發電紀錄_雲端版"
TW = ZoneInfo("Asia/Taipei")
REFRESH_SECONDS = 900  # 每 15 分鐘自動更新資料（不會登出）

# 憑證精準推算的基準點（與舊版相同）
CERT_ANCHOR_TIME = pd.Timestamp("2026-03-31 12:30:00")
CERT_ANCHOR_COUNT = 56
CERT_ANCHOR_LEFTOVER_KWH = 286.691
CERT_TARGET = 210

# 各子系統固定配色（深淺不同，避免只靠色相辨識）
SYSTEM_COLOR_RULES = [
    ("BIPV-1", "#E8A317"),
    ("BIPV-2", "#B5541F"),
    ("斜坡", "#1F7A6D"),
    ("鋼構", "#2F4858"),
]
FALLBACK_COLORS = ["#7A6FA8", "#8C9A3C", "#C2607A", "#4E8FB5"]

POWER_MODE = "功率 kW"
ENERGY_MODE = "發電量 kWh"

SUN_SVG = (
    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#1E2A2E" '
    'stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle>'
    '<path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>'
)

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=Noto+Sans+TC:wght@400;500;700&display=swap');
.block-container { padding-top: 2rem; max-width: 1400px; }
.stTabs [data-baseweb="tab"] { height: 44px; font-size: 15px; }
.sd-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-family: 'Noto Sans TC', sans-serif; }
.sd-brand { display: flex; align-items: center; gap: 16px; }
.sd-logo { width: 52px; height: 52px; border-radius: 14px; background: #E8A317; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.sd-title { font-size: 28px; font-weight: 700; line-height: 1.2; color: #1E2A2E; }
.sd-sub { font-size: 14px; color: #5F6B6E; margin-top: 4px; }
.sd-pill { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 999px; font-size: 14px; font-weight: 500; font-family: 'Noto Sans TC', sans-serif; }
.sd-pill-ok { background: #E4F1EA; color: #17694F; }
.sd-pill-warn { background: #FCEFD2; color: #8A5A00; }
.sd-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; display: inline-block; }
.sd-grid { display: grid; gap: 16px; margin: 8px 0 16px 0; }
.sd-grid-kpi { grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }
.sd-grid-sys { grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }
.sd-card { background: #FFFFFF; border: 1px solid #E6E0D0; border-radius: 16px; padding: 20px 24px; font-family: 'Noto Sans TC', sans-serif; color: #1E2A2E; }
.sd-label { font-size: 14px; color: #5F6B6E; }
.sd-value { font-family: 'Manrope', sans-serif; font-size: 38px; font-weight: 800; line-height: 1.15; margin-top: 6px; }
.sd-unit { font-size: 16px; font-weight: 600; color: #5F6B6E; margin-left: 6px; }
.sd-note { font-size: 13px; margin-top: 6px; }
.sd-pos { color: #17694F; font-weight: 500; }
.sd-neg { color: #B3261E; font-weight: 500; }
.sd-muted { color: #5F6B6E; }
.sd-h { font-family: 'Noto Sans TC', sans-serif; font-size: 18px; font-weight: 700; color: #1E2A2E; }
.sd-hs { font-family: 'Noto Sans TC', sans-serif; font-size: 13px; color: #5F6B6E; margin-top: 2px; }
.sd-cert { display: flex; flex-direction: column; align-items: center; gap: 16px; height: 100%; box-sizing: border-box; }
.sd-ring { width: 200px; height: 200px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.sd-ring-in { width: 156px; height: 156px; border-radius: 50%; background: #FFFFFF; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.sd-ring-num { font-family: 'Manrope', sans-serif; font-size: 52px; font-weight: 800; line-height: 1; }
.sd-bar { height: 8px; border-radius: 999px; background: #EDE8DA; width: 100%; }
.sd-bar > div { height: 8px; border-radius: 999px; background: #E8A317; }
.sd-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; width: 100%; }
.sd-status { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; }
.sd-tip { width: 100%; box-sizing: border-box; padding: 12px 14px; border-radius: 12px; background: #F6F3EA; font-size: 13px; line-height: 1.6; }
.sd-sys-name { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 700; }
.sd-swatch { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.sd-sys-val { font-family: 'Manrope', sans-serif; font-size: 32px; font-weight: 800; line-height: 1.1; margin: 10px 0; }
.sd-footer { font-family: 'Noto Sans TC', sans-serif; font-size: 12px; color: #5F6B6E; margin-top: 8px; }
</style>
"""


# ==========================================
# 小工具
# ==========================================
def show_chart(fig):
    """相容新舊版 Streamlit 的圖表顯示。"""
    config = {"displayModeBar": False}
    if "width" in inspect.signature(st.plotly_chart).parameters:
        st.plotly_chart(fig, width="stretch", config=config)
    else:
        st.plotly_chart(fig, use_container_width=True, config=config)


def show_table(data, **kwargs):
    """相容新舊版 Streamlit 的表格顯示。"""
    try:
        st.dataframe(data, width="stretch", **kwargs)
    except Exception:
        st.dataframe(data, use_container_width=True, **kwargs)


def split_name(full_name):
    """'BIPV-1 (67360973)' -> ('BIPV-1', '67360973')"""
    text = str(full_name)
    if " (" in text and text.endswith(")"):
        short, meter = text[:-1].split(" (", 1)
        return short, meter
    return text, ""


def color_for(name, index):
    for key, color in SYSTEM_COLOR_RULES:
        if key in name:
            return color
    return FALLBACK_COLORS[index % len(FALLBACK_COLORS)]


def signed_pct(value):
    return f"{value:+.1f}%"


def section_head(title, subtitle=""):
    sub = f'<div class="sd-hs">{html.escape(subtitle)}</div>' if subtitle else ""
    return f'<div class="sd-h">{html.escape(title)}</div>{sub}'


# ==========================================
# 登入畫面（置中）
# ==========================================
def login_view():
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown(
            '<div class="sd-header" style="justify-content:center;margin-top:48px">'
            f'<div class="sd-brand"><div class="sd-logo">{SUN_SVG}</div>'
            '<div><div class="sd-title" style="font-size:24px">中創園區太陽能戰情室</div>'
            '<div class="sd-sub">請輸入密碼以進入</div></div></div></div>',
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            pwd = st.text_input("戰情室密碼", type="password")
            submitted = st.form_submit_button("確認登入")
        if submitted:
            if pwd == APP_PASSWORD:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("密碼錯誤，請重新輸入")


st.markdown(STYLE, unsafe_allow_html=True)

if not st.session_state.get("authed"):
    login_view()
    st.stop()


# ==========================================
# 雲端資料庫連線與資料整理
# ==========================================
@st.cache_data(ttl=60)
def load_data_from_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except Exception:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_values()
        if len(data) > 1:
            return pd.DataFrame(data[1:], columns=data[0]), None
        return pd.DataFrame(), None
    except Exception as e:
        return None, str(e)


def prepare_data(raw):
    df = raw.copy()
    df["紀錄時間"] = pd.to_datetime(df["紀錄時間"], errors="coerce")
    df = df.dropna(subset=["紀錄時間"])
    df["累計度數(kWh)"] = pd.to_numeric(df["累計度數(kWh)"], errors="coerce")
    df["當前功率(W)"] = pd.to_numeric(df["當前功率(W)"], errors="coerce")
    df["年份"] = df["紀錄時間"].dt.year
    df["月份"] = df["紀錄時間"].dt.month
    df["日期"] = df["紀錄時間"].dt.date

    # 每段發電量 (15 分鐘增量)
    df = df.sort_values(by=["系統名稱", "紀錄時間"])
    df["每段發電量(kWh)"] = df.groupby("系統名稱")["累計度數(kWh)"].diff().clip(lower=0)

    # BIPV-1 功率修正邏輯
    hours = df.groupby("系統名稱")["紀錄時間"].diff().dt.total_seconds() / 3600.0
    estimated_watts = (df["每段發電量(kWh)"] / hours * 1000).replace([np.inf, -np.inf], np.nan)
    bipv1_mask = df["系統名稱"].str.contains("BIPV-1", na=False) & estimated_watts.notna()
    df.loc[bipv1_mask, "當前功率(W)"] = estimated_watts[bipv1_mask].round(0)
    return df


@st.cache_data(ttl=60)
def load_prepared():
    raw, err = load_data_from_gsheets()
    if err:
        return None, err
    if raw is None or raw.empty:
        return pd.DataFrame(), None
    try:
        return prepare_data(raw), None
    except Exception as e:
        return None, f"資料處理時發生錯誤：{e}"


# ==========================================
# 數字計算
# ==========================================
def month_map(monthly_total, year):
    sub = monthly_total[monthly_total["年份"] == year]
    return dict(zip(sub["月份"], sub["當月發電量(kWh)"]))


def summarize(df, tw_now):
    s = {}
    latest = df["紀錄時間"].max()
    today = latest.date()
    day = df[df["日期"] == today].copy()
    s["latest"] = latest
    s["day"] = day

    # 今日發電量與即時功率
    s["today_kwh"] = day["每段發電量(kWh)"].sum()
    s["now_kw"] = day[day["紀錄時間"] == latest]["當前功率(W)"].sum() / 1000.0
    total_kw = (day.groupby("紀錄時間")["當前功率(W)"].sum() / 1000.0).fillna(0)
    if len(total_kw) and total_kw.max() > 0:
        s["peak_kw"] = float(total_kw.max())
        s["peak_time"] = total_kw.idxmax()
    else:
        s["peak_kw"], s["peak_time"] = 0.0, None

    # 與前一天同時段比較
    prev = df[df["日期"] == today - datetime.timedelta(days=1)]
    s["vs_yesterday"] = None
    if not prev.empty:
        if latest.hour < 18:
            prev = prev[prev["紀錄時間"].dt.time <= latest.time()]
        prev_kwh = prev["每段發電量(kWh)"].sum()
        if prev_kwh > 0:
            s["vs_yesterday"] = (s["today_kwh"] - prev_kwh) / prev_kwh * 100

    # 月度與年度
    monthly_sys = df.groupby(["年份", "月份", "系統名稱"])["累計度數(kWh)"].agg(["max", "min"]).reset_index()
    monthly_sys["當月發電量(kWh)"] = monthly_sys["max"] - monthly_sys["min"]
    monthly_total = monthly_sys.groupby(["年份", "月份"])["當月發電量(kWh)"].sum().reset_index()
    cur_year = latest.year
    s["cur_year"] = cur_year
    s["monthly_sys"] = monthly_sys
    s["this_map"] = month_map(monthly_total, cur_year)
    s["last_map"] = month_map(monthly_total, cur_year - 1)

    cur_month = latest.month
    s["cur_month"] = cur_month
    s["month_kwh"] = s["this_map"].get(cur_month, 0.0)
    last_same_month = s["last_map"].get(cur_month)
    s["month_yoy"] = (
        (s["month_kwh"] - last_same_month) / last_same_month * 100 if last_same_month else None
    )
    last_day_of_month = (
        pd.Timestamp(year=cur_year, month=cur_month, day=1) + pd.offsets.MonthEnd(0)
    ).day
    s["month_in_progress"] = latest.day < last_day_of_month

    ytd = sum(v for m, v in s["this_map"].items() if m <= cur_month)
    last_ytd = sum(v for m, v in s["last_map"].items() if m <= cur_month)
    s["ytd_kwh"] = ytd
    s["ytd_yoy"] = (ytd - last_ytd) / last_ytd * 100 if last_ytd else None

    # 綠電憑證精準推算
    new_kwh = df[df["紀錄時間"] > CERT_ANCHOR_TIME]["每段發電量(kWh)"].sum()
    total_leftover = CERT_ANCHOR_LEFTOVER_KWH + new_kwh
    s["new_certs"] = int(total_leftover // 1000)
    s["cert_leftover"] = total_leftover % 1000
    s["certs"] = CERT_ANCHOR_COUNT + s["new_certs"]

    remaining_kwh = (CERT_TARGET - s["certs"]) * 1000 - s["cert_leftover"]
    last30 = df[df["紀錄時間"] > latest - pd.Timedelta(days=30)]["每段發電量(kWh)"].sum()
    daily_avg = last30 / 30.0
    if remaining_kwh <= 0:
        s["cert_eta"] = f"已達成年度目標 {CERT_TARGET} 張。"
    elif daily_avg > 0:
        eta = today + datetime.timedelta(days=math.ceil(remaining_kwh / daily_avg))
        eta_text = f"{eta.month} 月 {eta.day} 日" if eta.year == cur_year else f"{eta.year} 年 {eta.month} 月 {eta.day} 日"
        s["cert_eta"] = f"依近 30 日平均（{daily_avg:,.0f} kWh／日）推估，預計 {eta_text}前後達成 {CERT_TARGET} 張。"
    else:
        s["cert_eta"] = "近 30 日沒有發電資料，暫時無法推估達成日期。"

    # 資料新鮮度
    lag_min = max((tw_now - latest.to_pydatetime()).total_seconds() / 60.0, 0)
    s["lag_min"] = lag_min
    s["stale"] = 6 <= tw_now.hour < 18 and lag_min > 45
    return s


def system_table(s, tw_now):
    """今日各子系統彙總（含狀態）。"""
    day = s["day"]
    if day.empty:
        return []
    grouped = day.groupby("系統名稱").agg(
        kwh=("每段發電量(kWh)", "sum"),
        power=("當前功率(W)", "last"),
        last_time=("紀錄時間", "max"),
    )
    total = grouped["kwh"].sum()
    rows = []
    for idx, (full_name, r) in enumerate(grouped.iterrows()):
        short, meter = split_name(full_name)
        lag = (tw_now - r["last_time"].to_pydatetime()).total_seconds() / 60.0
        if 6 <= tw_now.hour < 18 and lag > 45:
            status, tone = "資料延遲", "warn"
        elif 9 <= tw_now.hour < 16 and (pd.isna(r["power"]) or r["power"] <= 0):
            status, tone = "無輸出", "warn"
        else:
            status, tone = "正常", "ok"
        rows.append(
            {
                "full": full_name,
                "name": short,
                "meter": meter,
                "kwh": float(r["kwh"]),
                "power_w": 0.0 if pd.isna(r["power"]) else float(r["power"]),
                "share": float(r["kwh"] / total * 100) if total > 0 else 0.0,
                "status": status,
                "tone": tone,
                "color": color_for(short, idx),
            }
        )
    return rows


# ==========================================
# 畫面元件（HTML）
# ==========================================
def header_html(s):
    if s["stale"]:
        pill_class = "sd-pill-warn"
        text = f"資料延遲 {int(s['lag_min'])} 分鐘 · 最後更新 {s['latest'].strftime('%H:%M')}"
    else:
        pill_class = "sd-pill-ok"
        text = f"資料更新於 {s['latest'].strftime('%H:%M')} · 運作正常"
    return (
        '<div class="sd-header"><div class="sd-brand">'
        f'<div class="sd-logo">{SUN_SVG}</div>'
        '<div><div class="sd-title">中創園區太陽能監控戰情室</div>'
        '<div class="sd-sub">11 年系統活化數據 · 由行政服務部實時守護 · 數據來源 T-REC</div></div></div>'
        f'<div class="sd-pill {pill_class}"><span class="sd-dot"></span>{html.escape(text)}</div></div>'
    )


def kpi_card(label, value, unit, note="", tone="muted"):
    return (
        '<div class="sd-card">'
        f'<div class="sd-label">{html.escape(label)}</div>'
        f'<div class="sd-value"><span>{html.escape(value)}</span><span class="sd-unit">{html.escape(unit)}</span></div>'
        f'<div class="sd-note sd-{tone}">{html.escape(note)}</div></div>'
    )


def pct_note(value, suffix, in_progress=False):
    if value is None:
        return "尚無去年同期資料", "muted"
    text = f"{signed_pct(value)} {suffix}"
    if in_progress:
        text += " · 本月進行中"
    return text, ("pos" if value >= 0 else "neg")


def kpi_grid_html(s):
    daytime_done = s["latest"].hour >= 18 or s["now_kw"] <= 0
    if s["vs_yesterday"] is None:
        today_note, today_tone = "無前一日資料可比較", "muted"
    else:
        today_note = f"{signed_pct(s['vs_yesterday'])} 比昨日同時段"
        today_tone = "pos" if s["vs_yesterday"] >= 0 else "neg"

    if s["peak_time"] is not None:
        peak = f"今日最高 {s['peak_kw']:,.1f} kW（{s['peak_time'].strftime('%H:%M')}）"
    else:
        peak = "今日尚無發電"
    power_note = ("日落後無發電 · " if daytime_done and s["now_kw"] <= 0 else "") + peak

    m_note, m_tone = pct_note(s["month_yoy"], "對比去年同月", s["month_in_progress"])
    y_note, y_tone = pct_note(s["ytd_yoy"], "對比去年同期")

    cards = [
        kpi_card("今日發電量", f"{s['today_kwh']:,.2f}", "kWh", today_note, today_tone),
        kpi_card("目前即時功率", f"{s['now_kw']:,.2f}", "kW", power_note, "muted"),
        kpi_card(f"{s['cur_month']} 月累計發電量", f"{s['month_kwh']:,.0f}", "kWh", m_note, m_tone),
        kpi_card(f"{s['cur_year']} 年累計發電量", f"{s['ytd_kwh']:,.0f}", "kWh", y_note, y_tone),
    ]
    return '<div class="sd-grid sd-grid-kpi">' + "".join(cards) + "</div>"


def cert_card_html(s):
    certs = s["certs"]
    ratio = min(certs / CERT_TARGET, 1.0)
    degrees = round(ratio * 360)
    ring = f"background: conic-gradient(#E8A317 0deg {degrees}deg, #EDE8DA {degrees}deg 360deg);"
    next_pct = min(s["cert_leftover"] / 1000 * 100, 100)
    return (
        '<div class="sd-card sd-cert">'
        f'<div class="sd-h" style="align-self:flex-start">綠電憑證進度</div>'
        f'<div class="sd-ring" style="{ring}"><div class="sd-ring-in">'
        f'<div class="sd-ring-num">{certs}</div>'
        f'<div class="sd-label" style="margin-top:4px">目標 {CERT_TARGET} 張</div></div></div>'
        f'<div style="font-size:16px;font-weight:700">年度目標達成率 {ratio * 100:.1f}%</div>'
        '<div style="width:100%">'
        f'<div class="sd-row sd-label"><span>邁向第 {certs + 1} 張</span>'
        f'<span style="font-family:Manrope,sans-serif;font-weight:600;color:#1E2A2E">{s["cert_leftover"]:,.1f} / 1,000 kWh</span></div>'
        f'<div class="sd-bar" style="margin-top:8px"><div style="width:{next_pct:.1f}%"></div></div></div>'
        f'<div class="sd-tip">{html.escape(s["cert_eta"])}</div></div>'
    )


def systems_grid_html(rows):
    cards = []
    for r in rows:
        tone_color = "#17694F" if r["tone"] == "ok" else "#8A5A00"
        meter = f" · 電表 {html.escape(r['meter'])}" if r["meter"] else ""
        cards.append(
            '<div class="sd-card">'
            '<div class="sd-row">'
            f'<div class="sd-sys-name"><span class="sd-swatch" style="background:{r["color"]}"></span>{html.escape(r["name"])}</div>'
            f'<div class="sd-status" style="color:{tone_color}"><span class="sd-dot"></span>{html.escape(r["status"])}</div></div>'
            f'<div class="sd-sys-val"><span>{r["kwh"]:,.2f}</span><span class="sd-unit">kWh</span></div>'
            f'<div class="sd-bar"><div style="width:{r["share"]:.1f}%;background:{r["color"]}"></div></div>'
            f'<div class="sd-note sd-muted">今日佔全園區 {r["share"]:.1f}%{meter} · 目前 {r["power_w"] / 1000:,.2f} kW</div></div>'
        )
    return '<div class="sd-grid sd-grid-sys">' + "".join(cards) + "</div>"


# ==========================================
# 圖表
# ==========================================
PLOT_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Noto Sans TC, sans-serif", color="#1E2A2E"),
    margin=dict(l=8, r=8, t=8, b=8),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def monthly_fig(s, detail=False, height=340):
    months = list(range(1, 13))
    this_vals = [s["this_map"].get(m) for m in months]
    last_vals = [s["last_map"].get(m) for m in months]
    ticks = []
    for m, t, l in zip(months, this_vals, last_vals):
        if detail and t is not None and l:
            ticks.append(f"{m}月<br>{t:,.0f}<br>{(t - l) / l * 100:+.1f}%")
        else:
            ticks.append(f"{m}月")
    fig = go.Figure()
    fig.add_bar(x=months, y=last_vals, name=str(s["cur_year"] - 1), marker_color="#CFC8B5",
                hovertemplate="%{y:,.0f} kWh")
    fig.add_bar(x=months, y=this_vals, name=str(s["cur_year"]), marker_color="#E8A317",
                hovertemplate="%{y:,.0f} kWh")
    fig.update_layout(**PLOT_LAYOUT, barmode="group", bargap=0.25, height=height)
    fig.update_xaxes(tickmode="array", tickvals=months, ticktext=ticks)
    fig.update_yaxes(title_text="kWh", tickformat=",.0f", gridcolor="#EEE8D8")
    return fig


def today_fig(s, mode, colors):
    day = s["day"]
    chart_df = day[(day["紀錄時間"].dt.hour >= 6) & (day["紀錄時間"].dt.hour < 18)].copy()
    if chart_df.empty:
        return None
    chart_df["時間"] = chart_df["紀錄時間"].dt.strftime("%H:%M")
    chart_df["系統"] = chart_df["系統名稱"].map(lambda n: split_name(n)[0])
    chart_df["功率(kW)"] = chart_df["當前功率(W)"] / 1000.0
    y_col, unit = ("功率(kW)", "kW") if mode == POWER_MODE else ("每段發電量(kWh)", "kWh")
    times = sorted(chart_df["時間"].unique())
    fig = go.Figure()
    for name, sub in chart_df.sort_values("紀錄時間").groupby("系統", sort=False):
        fig.add_bar(x=sub["時間"], y=sub[y_col], name=name, marker_color=colors.get(name),
                    hovertemplate=f"%{{y:,.2f}} {unit}")
    fig.update_layout(**PLOT_LAYOUT, barmode="stack", bargap=0.15, height=360)
    tick_vals = [t for t in times if t.endswith(":00") and int(t[:2]) % 2 == 0]
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=times,
                     tickmode="array", tickvals=tick_vals)
    fig.update_yaxes(title_text=unit, gridcolor="#EEE8D8")
    return fig


def monthly_by_system_fig(s, colors):
    sub = s["monthly_sys"]
    sub = sub[sub["年份"] == s["cur_year"]]
    fig = go.Figure()
    for idx, (full_name, g) in enumerate(sub.groupby("系統名稱")):
        short, _ = split_name(full_name)
        g = g.sort_values("月份")
        fig.add_bar(x=g["月份"], y=g["當月發電量(kWh)"], name=short,
                    marker_color=colors.get(short, color_for(short, idx)),
                    hovertemplate="%{y:,.0f} kWh")
    fig.update_layout(**PLOT_LAYOUT, barmode="stack", bargap=0.25, height=340)
    months = list(range(1, 13))
    fig.update_xaxes(tickmode="array", tickvals=months, ticktext=[f"{m}月" for m in months])
    fig.update_yaxes(title_text="kWh", tickformat=",.0f", gridcolor="#EEE8D8")
    return fig


# ==========================================
# 主畫面
# ==========================================
def render_dashboard():
    with st.spinner("正在下載最新發電數據..."):
        df, err = load_prepared()

    if err:
        st.error(f"連線雲端資料庫發生錯誤：{err}")
        return
    if df is None or df.empty:
        st.info("雲端試算表中目前尚未偵測到資料！")
        return

    try:
        tw_now = datetime.datetime.now(TW).replace(tzinfo=None)
        s = summarize(df, tw_now)
        rows = system_table(s, tw_now)
        colors = {r["name"]: r["color"] for r in rows}

        st.markdown(header_html(s), unsafe_allow_html=True)
        tab_overview, tab_month, tab_system, tab_raw = st.tabs(["總覽", "月度與年度", "各子系統", "原始資料"])

        # ---------- 總覽 ----------
        with tab_overview:
            st.markdown(kpi_grid_html(s), unsafe_allow_html=True)

            col_chart, col_cert = st.columns([2.2, 1])
            with col_chart:
                with st.container(border=True):
                    st.markdown(section_head("月度發電量：今年與去年同期", "單位 kWh，滑鼠移上去可看各月數字"),
                                unsafe_allow_html=True)
                    show_chart(monthly_fig(s))
            with col_cert:
                st.markdown(cert_card_html(s), unsafe_allow_html=True)

            with st.container(border=True):
                date_text = f"{s['latest'].month} 月 {s['latest'].day} 日"
                if s["latest"].date() != tw_now.date():
                    date_text += "（最後有資料的一天）"
                st.markdown(section_head("今日 15 分鐘發電監控", f"{date_text} · 顯示 06:00 至 18:00"),
                            unsafe_allow_html=True)
                mode = st.radio("顯示內容", [POWER_MODE, ENERGY_MODE], horizontal=True,
                                label_visibility="collapsed", key="today_mode")
                fig = today_fig(s, mode, colors)
                if fig is None:
                    st.info("這一天在 06:00 至 18:00 之間沒有資料。")
                else:
                    show_chart(fig)

            if rows:
                st.markdown(systems_grid_html(rows), unsafe_allow_html=True)

        # ---------- 月度與年度 ----------
        with tab_month:
            with st.container(border=True):
                st.markdown(section_head("月度發電量明細", "每個月份下方依序為：當月發電量 kWh、年增率"),
                            unsafe_allow_html=True)
                show_chart(monthly_fig(s, detail=True, height=420))
            table_rows = []
            for m in range(1, 13):
                t, l = s["this_map"].get(m), s["last_map"].get(m)
                if t is None and l is None:
                    continue
                diff = None if t is None or l is None else t - l
                pct = None if t is None or not l else (t - l) / l * 100
                table_rows.append({
                    "月份": f"{m} 月",
                    f"{s['cur_year']} 年 (kWh)": None if t is None else round(t, 2),
                    f"{s['cur_year'] - 1} 年 (kWh)": None if l is None else round(l, 2),
                    "差異 (kWh)": None if diff is None else round(diff, 2),
                    "年增率": "—" if pct is None else signed_pct(pct),
                })
            show_table(pd.DataFrame(table_rows), hide_index=True)

        # ---------- 各子系統 ----------
        with tab_system:
            with st.container(border=True):
                st.markdown(section_head(f"{s['cur_year']} 年各子系統月度發電量"), unsafe_allow_html=True)
                show_chart(monthly_by_system_fig(s, colors))
            if rows:
                summary = pd.DataFrame([{
                    "子系統": r["name"],
                    "電表": r["meter"],
                    "今日累積 (kWh)": round(r["kwh"], 2),
                    "最新功率 (kW)": round(r["power_w"] / 1000, 2),
                    "今日佔比": f"{r['share']:.1f}%",
                    "狀態": r["status"],
                } for r in rows])
                st.markdown(section_head("各子系統今日數據統計"), unsafe_allow_html=True)
                show_table(summary, hide_index=True)

        # ---------- 原始資料 ----------
        with tab_raw:
            st.caption("顯示最新 3,000 筆紀錄。")
            show_table(df.sort_values("紀錄時間", ascending=False).head(3000))

        st.markdown(
            '<div class="sd-footer">資料來源：國家再生能源憑證中心 T-REC · 每 15 分鐘自動更新，不需重新登入。</div>',
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.error(f"資料處理時發生錯誤：{e}")


if hasattr(st, "fragment"):
    # 只重新整理資料區塊，不會讓使用者被登出
    st.fragment(run_every=REFRESH_SECONDS)(render_dashboard)()
else:
    render_dashboard()
    components.html(
        f"<script>setTimeout(function(){{window.parent.location.reload();}}, {REFRESH_SECONDS * 1000});</script>",
        height=0,
    )
