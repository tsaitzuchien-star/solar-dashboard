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

st.title("☀️ 中創園區太陽能監控戰情室 (雲端直連版)")
st.markdown("這套 11 年太陽能系統的活化數據，正由你的自動化機器人實時守護中。")
st.markdown("---")

# ⏱️ 隱形計時器：每 15 分鐘 (900,000 毫秒) 自動重整網頁
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
# ☁️ 雲端資料庫連線區 (支援本地端與雲端雙重模式)
# ==========================================
@st.cache_data(ttl=60) # ⚡ 快取時間設為 60 秒
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
            headers = data[0]
            rows = data[1:]
            df = pd.DataFrame(rows, columns=headers)
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"連線雲端資料庫發生錯誤：{e}")
        return None

# 開始讀取雲端資料
with st.spinner('⏳ 正在從 Google 雲端下載最新發電數據...'):
    df = load_data_from_gsheets()

if df is not None and not df.empty:
    try:
        # 資料格式轉換
        df["紀錄時間"] = pd.to_datetime(df["紀錄時間"])
        df["累計度數(kWh)"] = pd.to_numeric(df["累計度數(kWh)"], errors='coerce')
        df["當前功率(W)"] = pd.to_numeric(df["當前功率(W)"], errors='coerce')

        # 🛠️ --- BIPV-1 功率硬體修復魔法 (虛擬感測器) --- 🛠️
        df = df.sort_values(by=["系統名稱", "紀錄時間"])
        df['kWh_diff'] = df.groupby('系統名稱')['累計度數(kWh)'].diff()
        df['time_diff_hours'] = df.groupby('系統名稱')['紀錄時間'].diff().dt.total_seconds() / 3600.0
        
        estimated_watts = (df['kWh_diff'] / df['time_diff_hours']) * 1000
        estimated_watts = estimated_watts.clip(lower=0)
        
        bipv1_mask = df['系統名稱'].str.contains('BIPV-1', na=False)
        df.loc[bipv1_mask & estimated_watts.notnull(), '當前功率(W)'] = estimated_watts[bipv1_mask & estimated_watts.notnull()].round(0)
        
        df = df.drop(columns=['kWh_diff', 'time_diff_hours'])
        df = df.sort_values(by="紀錄時間", ascending=False)
        # ----------------------------------------------------

        df['年份'] = df["紀錄時間"].dt.year
        df['月份'] = df["紀錄時間"].dt.month
        df['日期'] = df['紀錄時間'].dt.date
        
        # --- 上半部：年度與月份 YoY 邏輯 ---
        monthly_sys = df.groupby(['年份', '月份', '系統名稱'])['累計度數(kWh)'].agg(['max', 'min']).reset_index()
        monthly_sys['當月發電量(kWh)'] = monthly_sys['max'] - monthly_sys['min']
        monthly_total = monthly_sys.groupby(['年份', '月份'])['當月發電量(kWh)'].sum().reset_index()

        current_year = datetime.datetime.now().year
        last_year = current_year - 1
        
        df_current_year = monthly_total[monthly_total['年份'] == current_year]
        months_this_year = df_current_year['月份'].unique()

        st.subheader(f"📈 {current_year} 年度：各月發電成效與 YoY (年增率) 追蹤")
        
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

        # --- 下半部：⭐ 今日即時戰情看板 ⭐ ---
        st.subheader("⚡ 今日即時發電監控")
        
        latest_time = df["紀錄時間"].max()
        today_date = latest_time.date()
        
        st.caption(f"🕒 雲端數據最新更新時間：**{latest_time.strftime('%Y-%m-%d %H:%M:%S')}**")
        st.markdown("*💡 註：系統將每 15 分鐘自動巡邏更新一次最新數據。*")
        
        df_today = df[df['日期'] == today_date]

        if not df_today.empty:
            # 🎯 [新增] 計算「最新一筆紀錄」的全區總發電功率 (換算成 kW)
            df_latest = df_today[df_today['紀錄時間'] == latest_time]
            current_total_kw = df_latest['當前功率(W)'].sum() / 1000.0

            today_max = df_today.groupby('系統名稱')['累計度數(kWh)'].max()
            today_min = df_today.groupby('系統名稱')['累計度數(kWh)'].min()
            today_yield = (today_max - today_min).round(2).reset_index() 
            today_yield.columns = ['系統名稱', '今日發電量(kWh)']
            
            today_total = today_yield['今日發電量(kWh)'].sum().round(2)

            col1, col2 = st.columns([1, 2])

            with col1:
                # 🎯 [新增] 把左邊的區塊再切成兩半，讓這兩個指標並排顯示！
                sub_col1, sub_col2 = st.columns(2)
                with sub_col1:
                    st.metric("🌞 今日全區總發電量", f"{today_total:,.2f} kWh")
                with sub_col2:
                    st.metric("⚡ 目前總發電功率", f"{current_total_kw:,.2f} kW")
                
                st.dataframe(today_yield, use_container_width=True)

            with col2:
                fig_today = px.bar(
                    today_yield, x="系統名稱", y="今日發電量(kWh)", color="系統名稱", 
                    title=f"{today_date} 各系統單日貢獻", template="plotly_white", text="今日發電量(kWh)"
                )
                fig_today.update_layout(hovermode="x unified")
                fig_today.update_traces(textposition='outside')
                st.plotly_chart(fig_today, use_container_width=True)
        else:
            st.warning("⚠️ 目前尚無今日的發電數據。")

        with st.expander("查看雲端原始數據庫"):
            st.dataframe(df, use_container_width=True)
            
    except Exception as e:
        st.error(f"資料處理時發生錯誤：{e}")
else:
    st.info("💡 雲端試算表中目前尚未偵測到資料！")
