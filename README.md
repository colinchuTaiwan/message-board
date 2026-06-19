# 🌸 可愛留言板

一個使用 Streamlit + Firebase Firestore 打造的可愛風格留言板系統，
支援一鍵部署至 Streamlit Community Cloud。

---

## ✨ 功能特色

- 🌸 柔和粉色系可愛 UI，支援手機與桌面
- 📢 公告系統（卡片式顯示，管理員可管理）
- 💬 留言板（分頁顯示、防洗版、重複留言檢查）
- 🔐 管理員後台（含登入失敗鎖定機制）
- 🛡️ IP Hash 保護（不儲存原始 IP）
- 📄 Firestore 分頁查詢（offset + limit）

---

## 📁 專案結構

```
message-board/
├── app.py                # 主程式
├── firebase_service.py   # Firestore CRUD
├── auth.py               # 管理員認證
├── utils.py              # 工具函式
├── requirements.txt      # 依賴套件
└── README.md
```

---

## 🚀 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定 Streamlit Secrets

在本機建立 `.streamlit/secrets.toml`（部署至 Cloud 時改在 UI 設定，詳見後文）。

---

## 🔥 Firebase 設定

### 建立 Firebase 專案

1. 前往 [Firebase Console](https://console.firebase.google.com/)
2. 建立新專案（或使用現有專案）
3. 前往「Firestore Database」→ 建立資料庫
4. 選擇「正式模式」或「測試模式」（測試模式方便開發，上線前請設定安全規則）

### 建立 Service Account

1. Firebase Console → 專案設定 ⚙️ → 服務帳戶
2. 點擊「產生新的私密金鑰」
3. 下載 JSON 檔案（妥善保管，勿上傳至 Git）

---

## 🔑 Streamlit Secrets 設定

### 本機設定

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
（從 JSON 金鑰檔複製你的完整私鑰，保留真實換行）
-----END PRIVATE KEY-----'''
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
```

> ⚠️ **Private Key 格式說明**：
> `private_key` 必須使用 TOML 三單引號（`'''`）多行字面字串。
> 直接從 JSON 金鑰檔複製貼上，保留真實換行，**不需要**手動轉換 `\n`。
>
> 若使用雙引號 `"..."` 加 `\n` 的格式，Streamlit Community Cloud 的 TOML
> 解析器偶爾會發生換行符號解析失敗，導致 Firebase 憑證驗證錯誤
> （`ValueError: Could not format private key`）。

---

## 🔒 預設管理員帳號

| 項目 | 預設值 |
|------|--------|
| 帳號 | `admin` |
| 密碼 | `admin` |

> 🚨 **正式上線前務必修改預設帳號與密碼！**
>
> 在 Streamlit Secrets 中修改 `[admin]` 區塊的 `username` 與 `password`。
> 預設的 `admin/admin` 僅供開發測試使用。

### 管理員登入失敗鎖定

連續輸入錯誤密碼 **5 次**後，帳號將鎖定 **60 秒**，防止暴力破解。
鎖定期間畫面會顯示剩餘秒數。

---

## 📊 Firestore Composite Index 設定

本專案使用複合查詢，**必須手動建立以下兩個 Composite Index**，
否則會出現 `FailedPrecondition: The query requires an index.` 錯誤。

### 建立步驟

```
Firebase Console
  → Firestore Database
  → Indexes（索引）
  → Composite（複合）
  → Create Index（建立索引）
```

### Index 1：留言列表查詢

| 設定項目 | 值 |
|---------|-----|
| Collection ID | `messages` |
| 欄位 1 | `is_hidden`（Ascending ↑） |
| 欄位 2 | `created_at`（Descending ↓） |
| Query scope | Collection |

### Index 2：重複留言檢查查詢

| 設定項目 | 值 |
|---------|-----|
| Collection ID | `messages` |
| 欄位 1 | `name`（Ascending ↑） |
| 欄位 2 | `content`（Ascending ↑） |
| 欄位 3 | `created_at`（Ascending ↑） |
| Query scope | Collection |

> 💡 索引建立後通常需要等待數分鐘才能生效。
> 建立中狀態為「Building」，完成後變為「Enabled」。

---

## 📦 Firestore Count API 說明

本專案使用 Firestore Count API 取得留言總數：

```python
result = db.collection("messages").where("is_hidden", "==", False).count().get()
total = result[0][0].value
```

**需要 `firebase-admin >= 6.3.0`**（已在 `requirements.txt` 指定）。

此 API 僅計費一次讀取（固定費用），遠比 `len(list(query.stream()))` 讀取全部文件便宜。

---

## 📄 offset() 分頁機制說明

本專案使用 `offset()` + `limit()` 進行頁碼式分頁：

```python
query = (
    db.collection("messages")
    .where("is_hidden", "==", False)
    .order_by("created_at", direction=firestore.Query.DESCENDING)
    .offset((page_number - 1) * page_size)
    .limit(page_size)
)
```

> ⚠️ **計費警告**：
> Firestore 的 `offset()` 雖然不回傳跳過的文件，
> 但**被跳過的文件仍然計入 Firestore 讀取費用**。
>
> 例如：讀取第 3 頁（offset=100, limit=50）→ 實際計費 **150 次**讀取。
>
> 此限制適合中小型應用（數千 ～ 數萬筆留言）。
> 若未來資料量大幅成長，建議改用 **Cursor Pagination（游標分頁）+ Infinite Scroll**，
> 以大幅降低 Firestore 讀取成本。

---

## 🌐 IP 取得限制說明

在 Streamlit Community Cloud 環境中，由於 Cloudflare proxy 的緣故，
`X-Forwarded-For` 等 Header 無法保證取得真實用戶 IP。

本專案的處理方式：

1. 優先嘗試從 `st.context.headers` 取得 `X-Forwarded-For` / `X-Real-IP`
2. 若無法取得，自動改用 Session 初始化時生成的 UUID（`user_session_id`）作為 hash 來源
3. UUID 在單次 Session 生命週期內固定不變，提供基本的防重複送出保護

> 此 UUID 由 `uuid.uuid4().hex` 生成，不依賴任何 Streamlit 內部 API，
> 版本升級後依然穩定可用。
> 所有情況下均只儲存 SHA256 雜湊值，**絕不儲存原始 IP**。

---

## 💻 本機執行

```bash
# 1. 複製專案
git clone https://github.com/your-username/message-board.git
cd message-board

# 2. 建立虛擬環境（建議）
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. 安裝依賴
pip install -r requirements.txt

# 4. 設定 Secrets（見上方說明）
mkdir -p .streamlit
# 建立 .streamlit/secrets.toml 並填入設定

# 5. 執行
streamlit run app.py
```

瀏覽器會自動開啟 `http://localhost:8501`。

---

## ☁️ Streamlit Community Cloud 部署

1. 將專案推送至 GitHub（確認 `.gitignore` 已排除 `.streamlit/secrets.toml`）

```gitignore
.streamlit/secrets.toml
*.json
```

2. 前往 [share.streamlit.io](https://share.streamlit.io) 並登入

3. 點擊「New app」→ 選擇你的 GitHub 倉庫 → 主檔案設為 `app.py`

4. 在「Advanced settings」→「Secrets」貼上 `secrets.toml` 的完整內容

5. 點擊「Deploy」

> 部署完成後，記得在 Firebase Console 建立上方說明的兩個 Composite Index。

---

## 📝 Firestore 安全規則建議（正式上線）

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 留言：後端（Service Account）可完整存取，前端禁止直接存取
    match /messages/{doc} {
      allow read, write: if false;
    }
    match /announcements/{doc} {
      allow read, write: if false;
    }
  }
}
```

本專案透過 `firebase-admin` SDK（Service Account）存取 Firestore，
安全規則設為 `false` 可防止前端直接繞過後端存取資料庫。

---

## 🛠️ 技術棧

| 項目 | 技術 |
|------|------|
| 前端框架 | Streamlit >= 1.31.0 |
| 資料庫 | Firebase Cloud Firestore |
| SDK | firebase-admin >= 6.3.0 |
| 時區處理 | Python 內建 zoneinfo（Python 3.9+） |
| 部署 | Streamlit Community Cloud |
