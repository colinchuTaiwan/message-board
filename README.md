# 💬 多留言板系統

使用 Streamlit + Firebase Realtime Database 打造的多主題留言板，
支援七個獨立留言板，部署於 Streamlit Community Cloud。

---

## ✨ 功能特色

- 七個獨立留言板，各有不同主題色
- 側邊欄切換留言板
- 📢 各板獨立公告系統
- 💬 防洗版、重複留言檢查
- 🔐 管理員後台（可管理全部七個板）
- 👀 各板獨立訪客人次計數
- 🛡️ IP Hash 保護（不儲存原始 IP）

---

## 📋 留言板清單

| 名稱 | DB 路徑 | 主題色 |
|------|---------|--------|
| 🏠 可愛的家 | `homeboard` | 暖棕米色 |
| 👩 媽媽的大小事 | `momboard` | 玫瑰粉 |
| ✈️ 旅遊討論區 | `travelboard` | 天空藍 |
| 🎮 寶可夢討論區 | `pokeboard` | 寶可夢黃 |
| 💬 閒聊區 | `chatboard` | 薄荷綠 |
| 📚 學習專區 | `studyboard` | 深藍紫 |
| 🤖 AI學習區 | `aiboard` | 科技灰藍 |

---

## 📁 專案結構

```
message-board/
├── app.py                # 主程式
├── firebase_service.py   # Realtime Database CRUD
├── auth.py               # 管理員認證
├── utils.py              # 工具函式
├── requirements.txt      # 依賴套件
└── README.md
```

---

## 🚀 安裝依賴

```bash
pip install -r requirements.txt
```

---

## 🔥 Firebase 設定

### 建立 Firebase 專案

1. 前往 [Firebase Console](https://console.firebase.google.com/)
2. 建立新專案（或使用現有專案）
3. 前往「Realtime Database」→ 建立資料庫
4. 選擇地區，選「測試模式」開始開發

### 取得 Database URL

建立完成後頁面上方會顯示：
```
https://your-project-default-rtdb.firebaseio.com/
```

### 建立 Service Account

1. Firebase Console → 專案設定 ⚙️ → 服務帳戶
2. 點擊「產生新的私密金鑰」→ 下載 JSON 檔案

---

## 🔑 Streamlit Secrets 設定

建立 `.streamlit/secrets.toml`：

```toml
[admin]
username = "admin"
password = "admin"

[firebase]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
private_key = '''-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...
（從 JSON 金鑰檔複製完整私鑰，保留真實換行）
-----END PRIVATE KEY-----'''
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
database_url = "https://your-project-default-rtdb.firebaseio.com"
```

> ⚠️ **`private_key` 必須使用三單引號 `'''` 包覆，保留真實換行。**
> 不可使用雙引號加 `\n`，否則 Streamlit Cloud 的 TOML 解析器可能失敗。

---

## 🔒 預設管理員帳號

| 項目 | 預設值 |
|------|--------|
| 帳號 | `admin` |
| 密碼 | `admin` |

> 🚨 **正式上線前務必修改預設帳號與密碼！**

管理員登入連續失敗 **5 次**後鎖定 **60 秒**。

---

## 📄 分頁機制說明

Realtime Database 不支援 offset 查詢，採用 Python 端分頁：
讀取全部留言後在記憶體排序切片。

適合中小型留言板（數百至數千筆）。
若資料量大幅成長，建議改用 **Firestore + offset 分頁**。

---

## 🌐 IP 取得限制說明

Streamlit Community Cloud 環境中無法保證取得真實用戶 IP（Cloudflare proxy）。
無法取得時自動改用 Session UUID 作為 hash 來源，不影響基本防護功能。
所有情況下均只儲存 SHA256 雜湊值，**絕不儲存原始 IP**。

---

## 📝 Realtime Database 安全規則（正式上線）

```json
{
  "rules": {
    ".read": false,
    ".write": false
  }
}
```

Service Account 不受安全規則限制，設為 `false` 可防止前端直接存取。

---

## 💻 本機執行

```bash
git clone https://github.com/your-username/message-board.git
cd message-board
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
mkdir -p .streamlit
# 建立 .streamlit/secrets.toml
streamlit run app.py
```

---

## ☁️ Streamlit Community Cloud 部署

1. 推送至 GitHub（`.gitignore` 排除 `.streamlit/secrets.toml` 和 `*.json`）
2. 前往 [share.streamlit.io](https://share.streamlit.io)
3. New app → 選 repo → Main file path 設為 `app.py`
4. Advanced settings → Secrets 貼上設定內容
5. Deploy

---

## 🛠️ 技術棧

| 項目 | 技術 |
|------|------|
| 前端框架 | Streamlit >= 1.31.0 |
| 資料庫 | Firebase Realtime Database |
| SDK | firebase-admin >= 6.3.0 |
| 時區處理 | Python 內建 zoneinfo（3.9+） |
| 部署 | Streamlit Community Cloud |
