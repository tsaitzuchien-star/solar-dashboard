import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import streamlit.components.v1 as components
import warnings
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 🤫 幫 Plotly 戴上耳塞
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ⚠️ 關鍵：set_page_config 必須是第一個 Streamlit 指令，不能移動
st.set_page_config(page_title="中創園區太陽能戰情室", layout="wide", page_icon="☀️")

# ==========================================
# 🔐 [新增] 網頁前端密碼攔截區塊
# ==========================================
def check_password():
    # 在側邊欄建立密碼輸入框
    user_pwd = st.sidebar.text_input("🔑 請輸入戰情室密碼", type="password")
    
    if user_pwd == "ASCH300!":
        return True
    elif user_pwd != "":
        st.sidebar.error("密碼錯誤！請重新輸入。")
    return False

# 密碼驗證防線：如果不通過，程式會在此強制停止，保護下方數據
if not check_password():
    st.warning("🔒 戰情室已鎖定。請在左側側邊欄輸入密碼以查看太陽能數據。")
    st.stop()
# ==========================================

# --- 驗證通過後，才會執行以下的戰情室畫面與資料抓取 ---

st.title("☀️ 中創園區太陽能監控戰情室")
st.markdown("這套 11 年太陽能系統的活化數據，正由中創行政服務部實時守護中。(數據來源：國家再生能源憑證中心T-REC)")
st.markdown("---")

# ⏱️ 隱形計時器：每 15 分鐘自動重整
components.html(
    """
    <script>
    setTimeout(function(){
        window.parent.location.reload();
    }, 900000);
    </script>
    """,
    height=0
)

# ==========================================
# ☁️ 雲端資料庫連線區
# ==========================================
@st.cache_data(ttl=60)
def load_data_from_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open("中創園區_太陽能發電紀錄_雲端版").sheet1
        data = sheet.get_all_values()
        if len(data) > 1:
            return pd.DataFrame(data[1:], columns=data[0])
        return pd.DataFrame()
    except Exception as e:
        st.error(f"連線雲端資料庫發生錯誤：{e}")
        return None

with st.spinner('⏳ 正在下載最新發電數據...'):
    df = load_data_from_gsheets()

if df is not None and not df.empty:
    try:
        # 資料轉換
        df["紀錄時間"] = pd.to_datetime(df["紀錄時間"])
        df["累計度數(kWh)"] = pd.to_numeric(df["累計度數(kWh)"], errors='coerce')
        df["當前功率(W)"] = pd.to_numeric(df["當前功率(W)"], errors='coerce')
        df['年份'] = df["紀錄時間"].dt.year
        df['月份'] = df["紀錄時間"].dt.month
        df['日期'] = df['紀錄時間'].dt.date

        # 計算每段發電量 (15分鐘增量)
        df = df.sort_values(by=["系統名稱", "紀錄時間"])
        df['每段發電量(kWh)'] = df.groupby('系統名稱')['累計度數(kWh)'].diff().clip(lower=0)
        
        # BIPV-1 功率修正邏輯
        df['time_diff_hours'] = df.groupby('系統名稱')['紀錄時間'].diff().dt.total_seconds() / 3600.0
        estimated_watts = (df['每段發電量(kWh)'] / df['time_diff_hours']) * 1000
        bipv1_mask = df['系統名稱'].str.contains('BIPV-1', na=False)
        df.loc[bipv1_mask & estimated_watts.notnull(), '當前功率(W)'] = estimated_watts[bipv1_mask & estimated_watts.notnull()].round(0)

        # ==========================================
        # 🎯 年度 KPI 與 YoY 比較區
        # ==========================================
        st.subheader(f"📈 {datetime.datetime.now().year} 年度：發電成效與綠電憑證追蹤")
        
        monthly_sys = df.groupby(['年份', '月份', '系統名稱'])['累計度數(kWh)'].agg(['max', 'min']).reset_index()
        monthly_sys['當月發電量(kWh)'] = monthly_sys['max'] - monthly_sys['min']
        monthly_total = monthly_sys.groupby(['年份', '月份'])['當月發電量(kWh)'].sum().reset_index()

        current_year = datetime.datetime.now().year
        last_year = current_year - 1
        df_current_year = monthly_total[monthly_total['年份'] == current_year]
        months_this_year = df_current_year['月份'].unique()
        
        # 🎯 憑證精準推算邏輯
        anchor_time = pd.to_datetime('2026-03-31 12:30:00')
        anchor_certs = 56 
        anchor_leftover_kwh = 286.691
        
        new_kwh_since_anchor = df[df['紀錄時間'] > anchor_time]['每段發電量(kWh)'].sum()
        total_leftover_kwh = anchor_leftover_kwh + new_kwh_since_anchor
        new_certs_earned = int(total_leftover_kwh // 1000)
        current_leftover_kwh = total_leftover_kwh % 1000
        
        current_certs = anchor_certs + new_certs_earned
        target_certs = 210
        
        col_cert1, col_cert2 = st.columns([1, 2.5])
        with col_cert1:
            st.metric("📜 今年累積綠電憑證(目標：210張)", f"{current_certs} 張", f"邁向第 {current_certs + 1} 張：{current_leftover_kwh:,.1f} / 1000 kWh", delta_color="off")
        with col_cert2:
            st.markdown(f"<div style='margin-top: 10px; font-size: 18px;'><b>🎯 年度目標達成率：{(current_certs/target_certs)*100:.1f}%</b></div>", unsafe_allow_html=True)
            st.progress(min(current_certs / target_certs, 1.0))
            
        st.markdown("<br>", unsafe_allow_html=True)

        if len(months_this_year) > 0:
            cols = st.columns(len(months_this_year))
            for i, m in enumerate(sorted(months_this_year)):
                this_year_kwh = monthly_total[(monthly_total['年份'] == current_year) & (monthly_total['月份'] == m)]['當月發電量(kWh)'].sum()
                last_year_kwh = monthly_total[(monthly_total['年份'] == last_year) & (monthly_total['月份'] == m)]['當月發電量(kWh)'].sum()

                if last_year_kwh > 0:
                    diff = this_year_kwh - last_year_kwh
                    diff_pct = (diff / last_year_kwh) * 100
                    delta_str = f"{diff:,.2f} kWh ({diff_pct:+.1f}% YoY)"
                else:
                    delta_str = "⚠️ 尚無去年同期資料"

                with cols[i]:
                    st.metric(f"🎯 {m} 月份發電量", f"{this_year_kwh:,.2f} kWh", delta=delta_str)
        else:
            st.info(f"💡 目前資料庫尚未包含 {current_year} 年的數據。")

        st.markdown("---")

        # ==========================================
        # ⚡ 今日即時監控區
        # ==========================================
        st.subheader("⚡ 今日 15 分鐘區間發電監控")
        latest_time = df["紀錄時間"].max()
        
        full_today_df = df[df['日期'] == latest_time.date()].copy()
        
        chart_df = full_today_df[
            (full_today_df['紀錄時間'].dt.hour >= 6) & 
            (full_today_df['紀錄時間'].dt.hour < 18)
        ].copy()
        
        st.caption(f"🕒 最後更新點：**{latest_time.strftime('%H:%M')}** (圖表顯示範圍：06:00 - 18:00)")

        if not full_today_df.empty:
            df_latest = full_today_df[full_today_df['紀錄時間'] == latest_time]
            current_total_kw = df_latest['當前功率(W)'].sum() / 1000.0
            today_total_kwh = full_today_df['每段發電量(kWh)'].sum()
            latest_kwh_diff = df_latest['每段發電量(kWh)'].sum()

            c1, c2, c3 = st.columns(3)
            c1.metric("🌞 今日累積發電", f"{today_total_kwh:,.2f} kWh")
            c2.metric("⚡ 目前即時總功率", f"{current_total_kw:,.2f} kW")
            c3.metric("📊 最新發電增量", f"{latest_kwh_diff:.2f} kWh")

            if not chart_df.empty:
                chart_df['時間'] = chart_df['紀錄時間'].dt.strftime('%H:%M')
                chart_df['當前功率(kW)'] = chart_df['當前功率(W)'] / 1000.0
                
                fig_bar_kw = px.bar(
                    chart_df.sort_values('紀錄時間'), 
                    x="時間", 
                    y="當前功率(kW)", 
                    color="系統名稱",
                    title=f"{latest_time.date()} 發電功率時序圖 - 觀察出力強度 (kW)",
                    template="plotly_white",
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    text_auto='.1f'
                )
                fig_bar_kw.update_layout(hovermode="x unified", xaxis_title="紀錄點", yaxis_title="即時功率 (kW)", barmode='stack')
                st.plotly_chart(fig_bar_kw, use_container_width=True)

                fig_bar_kwh = px.bar(
                    chart_df.sort_values('紀錄時間'), 
                    x="時間", 
                    y="每段發電量(kWh)", 
                    color="系統名稱",
                    title=f"{latest_time.date()} 發電量時序圖 - 觀察實質收穫 (kWh)",
                    template="plotly_white",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    text_auto='.2f'
                )
                fig_bar_kwh.update_layout(hovermode="x unified", xaxis_title="紀錄點", yaxis_title="發電量增量 (kWh)", barmode='stack')
                st.plotly_chart(fig_bar_kwh, use_container_width=True)

            else:
                st.info("💡 目前時間不在 06:00 - 18:00 的圖表顯示範圍內。")

            with st.expander("各子系統今日數據統計"):
                sys_summary = full_today_df.groupby('系統名稱').agg({
                    '每段發電量(kWh)': 'sum',
                    '當前功率(W)': 'last' 
                }).reset_index()
                sys_summary.columns = ['系統名稱', '今日累積(kWh)', '最新功率(W)']
                st.dataframe(sys_summary, use_container_width=True)

        with st.expander("查看雲端原始數據庫"):
            st.dataframe(df.sort_values('紀錄時間', ascending=False), use_container_width=True)
            
    except Exception as e:
        st.error(f"資料處理時發生錯誤：{e}")
else:
    st.info("💡 雲端試算表中目前尚未偵測到資料！")
