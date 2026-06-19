import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime
import json

# ==========================================
# 1. 初始化 Firebase Firestore
# ==========================================
@st.cache_resource
def init_firestore():
    """使用 st.secrets 的 credentials 初始化 Firestore 實例"""
    try:
        # 將 secrets 中的 firebase 字典轉為與 Google 認證相符的格式
        # 處理 private_key 中的換行符號
        creds_dict = dict(st.secrets["firebase"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(credentials=credentials, project=creds_dict["project_id"])
        return db
    except Exception as e:
        st.error(f"Firebase 初始化失敗，請檢查 secrets.toml 設定。錯誤訊息: {e}")
        return None

db = init_firestore()
COLLECTION_NAME = "messages"

# ==========================================
# 2. 頁面基本設定與狀態初始化
# ==========================================
st.set_page_config(page_title="Streamlit 留言板", page_icon="💬", layout="centered")
st.title("💬 雙向防詐防注水留言板")

# 用於儲存當前正在編輯或刪除的 Message ID 狀態
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "deleting_id" not in st.session_state:
    st.session_state.deleting_id = None

# ==========================================
# 3. 功能函式庫 (CRUD 操作)
# ==========================================
def get_all_messages():
    """取得所有留言，依 created_at 由新到舊排序"""
    if db is None:
        return []
    try:
        docs = db.collection(COLLECTION_NAME).order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except Exception as e:
        st.error(f"讀取留言失敗: {e}")
        return []

def create_message(name, content):
    """新增留言"""
    if db is None: return
    now = datetime.utcnow() # 建議使用 UTC 時間儲存，顯示時再處理或交由前端
    try:
        db.collection(COLLECTION_NAME).add({
            "name": name,
            "content": content,
            "created_at": now,
            "updated_at": now
        })
        st.success("留言成功！")
        st.rerun()
    except Exception as e:
        st.error(f"新增留言失敗: {e}")

def update_message(msg_id, new_content):
    """更新留言內容"""
    if db is None: return
    try:
        db.collection(COLLECTION_NAME).document(msg_id).update({
            "content": new_content,
            "updated_at": datetime.utcnow()
        })
        st.success("留言更新成功！")
        st.session_state.editing_id = None # 清空編輯狀態
        st.rerun()
    except Exception as e:
        st.error(f"更新留言失敗: {e}")

def delete_message(msg_id):
    """刪除指定留言"""
    if db is None: return
    try:
        db.collection(COLLECTION_NAME).document(msg_id).delete()
        st.success("留言已刪除！")
        st.session_state.deleting_id = None # 清空刪除狀態
        st.rerun()
    except Exception as e:
        st.error(f"刪除留言失敗: {e}")

# ==========================================
# 4. 管理者密碼驗證
# ==========================================
def verify_admin(password_input):
    """驗證密碼是否與 secrets.toml 一致"""
    return password_input == st.secrets.get("admin_password", "")

# Sidebar 放管理員登入，方便全頁權限控管
st.sidebar.header("🔐 管理員權限驗證")
admin_password = st.sidebar.text_input("輸入管理者密碼", type="password", help="編輯與刪除留言需在此輸入正確密碼")

# ==========================================
# 5. UI 區塊：新增留言表單
# ==========================================
st.subheader("✍️ 發表新留言")
with st.form("new_message_form", clear_on_submit=True):
    input_name = st.text_input("暱稱 (最多 50 字)", max_chars=50).strip()
    input_content = st.text_area("留言內容 (最多 500 字)", max_chars=500).strip()
    submit_btn = st.form_submit_button("送出留言")
    
    if submit_btn:
        # 後端邊界條件驗證
        if not input_name:
            st.error("❌ 暱稱不可為空！")
        elif not input_content:
            st.error("❌ 留言內容不可為空！")
        else:
            create_message(input_name, input_content)

# ==========================================
# 6. UI 區塊：動態彈出視窗 (編輯 / 刪除 互動區)
# ==========================================
# 處理編輯狀態 (當點擊某則留言的編輯，且密碼正確時觸發)
if st.session_state.editing_id:
    st.info("✏️ 正在編輯留言...")
    # 取得舊資料回填
    try:
        target_doc = db.collection(COLLECTION_NAME).document(st.session_state.editing_id).get().to_dict()
        if target_doc:
            with st.container(border=True):
                st.write(f"**原作者:** {target_doc.get('name')}")
                edit_content = st.text_area("修改留言內容", value=target_doc.get("content"), max_chars=500)
                col_eb1, col_eb2 = st.columns(2)
                with col_eb1:
                    if st.button("確認修改", type="primary"):
                        if not edit_content.strip():
                            st.error("❌ 修改後內容不可為空！")
                        else:
                            update_message(st.session_state.editing_id, edit_content.strip())
                with col_eb2:
                    if st.button("取消編輯"):
                        st.session_state.editing_id = None
                        st.rerun()
    except Exception as e:
        st.error(f"讀取待編輯資料失敗: {e}")

# 處理刪除確認狀態
if st.session_state.deleting_id:
    st.warning("⚠️ 確定要刪除這條留言嗎？此操作無法復原。")
    with st.container(border=True):
        col_db1, col_db2 = st.columns(2)
        with col_db1:
            if st.button("💥 確定刪除", type="primary"):
                delete_message(st.session_state.deleting_id)
        with col_db2:
            if st.button("保留留言"):
                st.session_state.deleting_id = None
                st.rerun()

st.divider()

# ==========================================
# 7. UI 區塊：顯示留言列表
# ==========================================
st.subheader("📥 歷史留言列表")
messages = get_all_messages()

if not messages:
    st.info("目前尚無任何留言，快來搶沙發！")
else:
    for msg in messages:
        # 使用 st.container 包裹每則留言，不使用不安全 HTML，改用原生 markdown 防範 XSS
        with st.container(border=True):
            col_meta, col_actions = st.columns([3, 1])
            
            with col_meta:
                st.markdown(f"### 👤 {msg['name']}")
                # 轉為本地時間格式易讀
                c_time = msg['created_at'].strftime('%Y-%m-%d %H:%M:%S') if msg.get('created_at') else "未知"
                u_time = msg['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if msg.get('updated_at') else "未知"
                
                if c_time == u_time:
                    st.caption(f"🕒 發表於: {c_time}")
                else:
                    st.caption(f"🕒 發表於: {c_time} | ✏️ 修改於: {u_time}")
            
            with col_actions:
                # 權限按鈕：點擊時先驗證側邊欄密碼
                btn_edit = st.button("編輯", key=f"edit_{msg['id']}")
                btn_delete = st.button("刪除", key=f"del_{msg['id']}")
                
                if btn_edit:
                    if verify_admin(admin_password):
                        st.session_state.editing_id = msg['id']
                        st.session_state.deleting_id = None # 互斥
                        st.rerun()
                    else:
                        st.error("🔒 密碼錯誤或未輸入，無編輯權限")
                        
                if btn_delete:
                    if verify_admin(admin_password):
                        st.session_state.deleting_id = msg['id']
                        st.session_state.editing_id = None # 互斥
                        st.rerun()
                    else:
                        st.error("🔒 密碼錯誤或未輸入，無刪除權限")
            
            # 留言內文顯示
            st.write(msg['content'])