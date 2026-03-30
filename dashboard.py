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

st.set_page_config(page_title="中創園區太陽能戰情室", layout="wide", page_icon="☀️")

st.title("☀️ 中創園區太陽能監控戰情室")
st.markdown("這套 11 年太陽能系統的活化數據，正由中創行政服務部實時守護中。")
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
        # 資料轉換與計算邏輯
        df["紀錄時間"] = pd.to_datetime(df["紀錄時間"])
        df["累計度數(kWh)"] = pd.to_numeric(df["累計度數(kWh)"], errors='coerce')
        df["當前功率(W)"] = pd.to_numeric(df["當前功率(W)"], errors='coerce')
        df['日期'] = df['紀錄時間'].dt.date

        # BIPV-1 功率修復與各時段發電增量計算
        df = df.sort_values(by=["系統名稱", "紀錄時間"])
        df['每段發電量(kWh)'] = df.groupby('系統名稱')['累計度數(kWh)'].diff().clip(lower=0)
        df['time_diff_hours'] = df.groupby('系統名稱')['紀錄時間'].diff().dt.total_seconds() / 3600.0
        
        # 功率修復
        estimated_watts = (df['每段發電量(kWh)'] / df['time_diff_hours']) * 1000
        bipv1_mask = df['系統名稱'].str.contains('BIPV-1', na=False)
        df.loc[bipv1_mask & estimated_watts.notnull(), '當前功率(W)'] = estimated_watts[bipv1_mask & estimated_watts.notnull()].round(0)
        
        # --- 年度 KPI 區 ---
        st.subheader(f"📈 {datetime.datetime.now().year} 年度：發電成效與綠電憑證追蹤")
        this_year_df = df[df['紀錄時間'].dt.year == datetime.datetime.now().year]
        # 計算年度總發電 (各系統 max - min)
        this_year_total_kwh = (this_year_df.groupby('系統名稱')['累計度數(kWh)'].max() - this_year_df.groupby('系統名稱')['累計度數(kWh)'].min()).sum()
        current_certs = int(this_year_total_kwh / 1000)
        target_certs = 210
        
        col_cert1, col_cert2 = st.columns([1, 4])
        with col_cert1:
            st.metric("📜 累積綠電憑證", f"{current_certs} 張", f"目標 {target_certs} 張")
        with col_cert2:
            st.markdown(f"<b>🎯 年度目標達成率：{(current_certs/target_certs)*100:.1f}%</b>", unsafe_allow_html=True)
            st.progress(min(current_certs / target_certs, 1.0))
        
        st.markdown("---")

        # --- 今日即時監控區 ---
        st.subheader("⚡ 今日即時發電趨勢")
        latest_time = df["紀錄時間"].max()
        today_df = df[df['日期'] == latest_time.date()].copy()
        
        st.caption(f"🕒 最新數據：**{latest_time.strftime('%H:%M:%S')}** (每 15 分鐘自動更新)")

        if not today_df.empty:
            # 1. 頂部數據列
            df_latest = today_df[today_df['紀錄時間'] == latest_time]
            current_total_kw = df_latest['當前功率(W)'].sum() / 1000.0
            today_total_kwh = today_df['每段發電量(kWh)'].sum()

            c1, c2, c3 = st.columns(3)
            c1.metric("🌞 今日累積發電", f"{today_total_kwh:,.2f} kWh")
            c2.metric("⚡ 目前即時總功率", f"{current_total_kw:,.2f} kW")
            c3.metric("🕒 最新紀錄點", latest_time.strftime('%H:%M'))

            # 2. 發電趨勢圖 (您要求的樹狀時間分布圖)
            # 將時間格式化為 HH:mm 方便觀看
            today_df['時間點'] = today_df['紀錄時間'].dt.strftime('%H:%M')
            
            fig_trend = px.area(
                today_df.sort_values('紀錄時間'), 
                x="紀錄時間", 
                y="每段發電量(kWh)", 
                color="系統名稱",
                title="今日發電出力曲線 (觀察雲層遮蔽影響)",
                line_group="系統名稱",
                template="plotly_white",
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_trend.update_layout(
                hovermode="x unified",
                xaxis_title="時間 (15分鐘一跳)",
                yaxis_title="發電量增量 (kWh)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_trend, use_container_width=True)
            
            # 3. 系統贡献清單
            with st.expander("各子系統今日數據統計"):
                sys_summary = today_df.groupby('系統名稱').agg({
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
