import os
import datetime
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# ==========================================
# 🔐 安全升級：改從 GitHub 雲端保險箱讀取帳號密碼
# (這裡不需要再手動輸入帳密了，它會自己去抓)
# ==========================================
TREC_ACCOUNT = os.environ.get("TREC_ACCOUNT")
TREC_PASSWORD = os.environ.get("TREC_PASSWORD")
# ==========================================

def run_auto_bot():
    print(f"🤖 [{datetime.datetime.now().strftime('%H:%M:%S')}] 自動機器人啟動中 (GitHub Actions 雲端模式)...")

    # 檢查保險箱密碼是否有成功讀取
    if not TREC_ACCOUNT or not TREC_PASSWORD:
        print("❌ 錯誤：找不到帳號或密碼！請確認 GitHub Secrets 設定是否正確。")
        return

    # --- 第一階段：登入 T-REC 抓資料 ---
    with sync_playwright() as p:
        # 雲端環境直接啟動隱形瀏覽器即可
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto("https://www.trec.org.tw/site_power/14")
            page.wait_for_timeout(2000)
            
            if "login" in page.url:
                print("   👉 偵測到需要登入，機器人自動輸入帳密中...")
                try:
                    account_filled = False
                    for selector in [
                        'input[name="email"]', 'input[name="account"]', 'input[name="username"]', 
                        'input[id="email"]', 'input[id="account"]', 'input[id="username"]', 
                        'input[type="text"]', 'input[type="email"]'
                    ]:
                        if page.locator(selector).count() > 0:
                            first_input = page.locator(selector).first
                            if first_input.is_visible():
                                first_input.fill(TREC_ACCOUNT)
                                account_filled = True
                                break 
                    
                    page.locator('input[type="password"]').first.fill(TREC_PASSWORD)
                    page.wait_for_timeout(500) 
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"   ❌ 自動登入輸入失敗：{e}")

            if "login" in page.url:
                print("   ❌ 登入失敗！請檢查 GitHub Secrets 裡的帳密。")
                browser.close()
                return

            print("   ✅ 成功進入 T-REC，開始抓取最新發電數據...")
            csrf_token = page.evaluate('() => document.querySelector("meta[name=\'csrf-token\']").content')
            cookies = "; ".join([f"{c['name']}={c['value']}" for c in context.cookies()])
        
        except Exception as e:
            print(f"   ❌ 網頁連線發生錯誤：{e}")
            browser.close()
            return
            
        browser.close()

        # --- 第二階段：API 抓取與整理 ---
        METERS = {
            "BIPV-1 (67360973)": "205", 
            "BIPV-2 (72760070)": "4159", 
            "斜坡PV (67360271)": "220",
            "鋼構PV (72760059)": "4160"
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "x-csrf-token": csrf_token,
            "Cookie": cookies
        }

        date_str = datetime.date.today().strftime("%Y-%m-%d")
        new_records_buffer = []

        for name, eq_id in METERS.items():
            API_URL = f"https://www.trec.org.tw/site_power/14/equipments/{eq_id}/data"
            payload = (
                "draw=1&columns%5B0%5D%5Bdata%5D=created_at&columns%5B0%5D%5Bname%5D=created_at"
                "&order%5B0%5D%5Bcolumn%5D=0&order%5B0%5D%5Bdir%5D=asc"
                f"&start=0&length=100&date={date_str}"
            )
            
            try:
                res = requests.post(API_URL, data=payload, headers=headers)
                if res.status_code == 200:
                    rows = res.json().get("data", [])
                    for r in rows:
                        if r['eac']:
                            new_records_buffer.append([name, r['created_at'], r['vac'], r['iac'], r['pac'], r['eac']])
            except Exception:
                pass

        # --- 第三階段：連線 Google 試算表並寫入 ---
        if not new_records_buffer:
            print("   👀 系統目前沒有產出任何發電度數。")
            return

        print("   ☁️ 準備將資料同步至 Google 試算表...")
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        
        try:
            # 這裡會讀取 GitHub Actions 動態產生的金鑰檔案
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            client = gspread.authorize(creds)
            sheet = client.open("中創園區_太陽能發電紀錄_雲端版").sheet1

            # 🛡️ 雲端防重複機制
            existing_data = sheet.get_all_values()
            existing_records = set()
            for row in existing_data:
                if len(row) >= 2:
                    existing_records.add(f"{row[0]}_{row[1]}") 

            final_new_records = []
            for record in new_records_buffer:
                unique_id = f"{record[0]}_{record[1]}"
                if unique_id not in existing_records:
                    final_new_records.append(record)

            if final_new_records:
                sheet.append_rows(final_new_records)
                print(f"   🎉 成功將 {len(final_new_records)} 筆最新數據寫入雲端試算表！")
            else:
                print("   👀 雲端資料庫已是最新狀態，目前沒有新的發電度數需要更新。")

        except Exception as e:
            print(f"   ❌ 雲端同步失敗：{e}")

if __name__ == '__main__':
    run_auto_bot()