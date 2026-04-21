import os
import datetime
import requests
import gspread
import re  # 🎯 引入正則表達式，用來精準萃取數字
import getpass  # 🎯 引入 getpass，讓本機輸入密碼時不會顯示明碼
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# ==========================================
# 🔐 安全升級：改從 GitHub 雲端保險箱讀取帳號密碼
# ==========================================
TREC_ACCOUNT = os.environ.get("TREC_ACCOUNT")
TREC_PASSWORD = os.environ.get("TREC_PASSWORD")
# ==========================================

def run_auto_bot():
    print(f"🤖 [{datetime.datetime.now().strftime('%H:%M:%S')}] 自動機器人啟動中...")

    # 🎯 --- [新增] 雙軌密碼驗證機制 --- 🎯
    default_pwd = "ASCH300!"
    
    # 判斷是否在 GitHub Actions 環境中執行
    if os.environ.get("GITHUB_ACTIONS"):
        # 模式 A：雲端執行 (透過 GitHub Secrets 的環境變數驗證)
        action_pwd = os.environ.get("BOT_RUN_PASSWORD")
        if action_pwd != default_pwd:
             print("❌ 雲端執行密碼錯誤！請確認 GitHub Secrets 中的 BOT_RUN_PASSWORD 是否正確。")
             return
        print("   ✅ 雲端密碼驗證通過！")
    else:
        # 模式 B：本機執行 (要求使用者手動輸入)
        input_pwd = getpass.getpass(f"   🔐 請輸入啟動密碼 (直接按 Enter 可帶入預設密碼): ")
        if input_pwd == "":
            input_pwd = default_pwd
            
        if input_pwd != default_pwd:
            print("   ❌ 密碼錯誤！機器人終止執行。")
            return
        print("   ✅ 本機密碼驗證通過！")
    # ----------------------------------------

    if not TREC_ACCOUNT or not TREC_PASSWORD:
        print("❌ 錯誤：找不到帳號或密碼！請確認 GitHub Secrets 設定是否正確。")
        return

    # --- 第一階段：登入 T-REC 抓資料 ---
    with sync_playwright() as p:
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
            
            # 🎯 --- [升級] 更強大的綠電憑證抓取雷達 --- 🎯
            trec_count = None
            try:
                page.wait_for_timeout(2000) # 等待數字載入
                body_text = page.locator("body").inner_text()
                
                if '已發證數量' in body_text:
                    # 切割出 '已發證數量' 後面的所有文字
                    text_after = body_text.split('已發證數量')[1]
                    
                    # 🔍 智慧數字萃取：忽略帶小數點的數字 (如 1.607, 62.24)，只抓取千分位或整數 (如 1,671)
                    matches = re.findall(r'(?<![\d\.])(\d{1,3}(?:,\d{3})+|\d+)(?![\d\.])', text_after)
                    
                    if matches:
                        trec_count = matches[0].replace(',', '')
                        print(f"   📜 成功在戰情首頁掃描到綠電憑證數量：{trec_count} 張！")
                    else:
                        print("   ⚠️ 找到標題，但無法辨識憑證數字。")
                else:
                    print("   ⚠️ 網頁中找不到 '已發證數量' 的標題。")
            except Exception as e:
                print(f"   ⚠️ 抓取憑證數量發生錯誤：{e}")
            # ----------------------------------------

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
        print("   ☁️ 準備將資料同步至 Google 試算表...")
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
            client = gspread.authorize(creds)
            spreadsheet = client.open("中創園區_太陽能發電紀錄_雲端版")
            sheet = spreadsheet.sheet1

            # 🎯 --- [新增] 寫入憑證數量到專屬分頁 --- 🎯
            if trec_count:
                try:
                    try:
                        cert_sheet = spreadsheet.worksheet("憑證紀錄")
                    except gspread.exceptions.WorksheetNotFound:
                        cert_sheet = spreadsheet.add_worksheet(title="憑證紀錄", rows="1000", cols="2")
                        cert_sheet.append_row(["更新時間", "已發證數量(張)"])

                    # 檢查最後一筆憑證數量，如果沒有變動就不重複寫入
                    cert_data = cert_sheet.get_all_values()
                    should_write = True
                    if len(cert_data) > 1:
                        last_count = cert_data[-1][1]
                        if str(last_count) == str(trec_count):
                            should_write = False
                    
                    if should_write:
                        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cert_sheet.append_row([current_time_str, trec_count])
                        print(f"   🎉 綠電憑證增加啦！已將 {trec_count} 張最新紀錄寫入「憑證紀錄」分頁！")
                    else:
                        print(f"   👀 綠電憑證數量維持在 {trec_count} 張，無需重複寫入。")
                except Exception as e:
                    print(f"   ❌ 憑證分頁寫入失敗：{e}")
            # ----------------------------------------

            if not new_records_buffer:
                print("   👀 系統目前沒有產出任何新的發電度數。")
                return

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
