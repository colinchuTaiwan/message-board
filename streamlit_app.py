"""
app.py
------
單頁留言板（Firebase Realtime Database 版）
"""

import time
import math
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import firebase_admin
from firebase_admin import credentials, db

# ── 常數 ───────────────────────────────────────────────────────────────────────
TW = ZoneInfo("Asia/Taipei")
COLLECTION = "messages"          # Realtime DB 路徑
MAX_NAME    = 50
MAX_CONTENT = 500
PAGE_SIZE   = 20
POST_COOLDOWN = 10               # 秒

# ── 頁面設定 ───────────────────────────────────────────────────────────────────
st.set_page_config(page_title="留言板", page_icon="💬", layout="centered")

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }

.board-header { text-align:center; padding:1.5rem 0 1rem; border-bottom:2px solid #e2e8f0; margin-bottom:1.5rem; }
.board-header h1 { font-size:2rem; font-weight:700; color:#1a202c; margin:0; }
.board-header p { color:#718096; font-size:0.9rem; margin:0.25rem 0 0; }

.msg-card {
    background:#fff; border:1px solid #e2e8f0; border-radius:12px;
    padding:1rem 1.25rem; margin-bottom:1rem;
    box-shadow:0 1px 3px rgba(0,0,0,0.06);
    transition:box-shadow 0.2s;
}
.msg-card:hover { box-shadow:0 4px 12px rgba(0,0,0,0.10); }
.msg-name    { font-weight:700; color:#2d3748; font-size:1rem; }
.msg-content { color:#4a5568; margin:0.4rem 0; font-size:0.95rem; white-space:pre-wrap; word-break:break-word; }
.msg-meta    { font-size:0.75rem; color:#a0aec0; }

.pager-info  { text-align:center; color:#718096; font-size:0.88rem; margin:0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Firebase 初始化 ────────────────────────────────────────────────────────────
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        if "firebase" not in st.secrets:
            st.error("❌ 找不到 [firebase] 設定，請檢查 secrets.toml。")
            st.stop()

        fb = st.secrets["firebase"]
        required = ["type", "project_id", "private_key_id", "private_key", "client_email", "client_id"]
        missing = [k for k in required if k not in fb]
        if missing:
            st.error(f"❌ [firebase] 缺少欄位：{', '.join(missing)}")
            st.stop()

        cert = {
            "type":           fb["type"],
            "project_id":     fb["project_id"],
            "private_key_id": fb["private_key_id"],
            "private_key":    fb["private_key"].replace("\\n", "\n"),
            "client_email":   fb["client_email"],
            "client_id":      fb["client_id"],
        }
        for opt in ("auth_uri", "token_uri", "auth_provider_x509_cert_url", "client_x509_cert_url"):
            if opt in fb:
                cert[opt] = fb[opt]

        db_url = st.secrets.get("firebase_db_url") or f"https://{fb['project_id']}-default-rtdb.firebaseio.com"
        firebase_admin.initialize_app(credentials.Certificate(cert), {"databaseURL": db_url})

    return db.reference("/")

root_ref = init_firebase()

# ── 工具函式 ───────────────────────────────────────────────────────────────────
def now_tw() -> datetime:
    return datetime.now(tz=TW)

def fmt_dt(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso).astimezone(TW)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso

def sanitize(text: str) -> str:
    """移除危險 HTML 字元，防止 XSS。"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def check_admin(pwd: str) -> bool:
    return pwd == st.secrets.get("admin_password", "")

# ── Realtime DB CRUD ───────────────────────────────────────────────────────────
def fetch_messages() -> list[dict]:
    """讀取所有留言，依 created_at 由新到舊排序。"""
    data = root_ref.child(COLLECTION).get()
    if not data:
        return []
    msgs = [{"id": k, **v} for k, v in data.items() if not v.get("is_hidden", False)]
    msgs.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return msgs

def add_message(name: str, content: str) -> bool:
    now = now_tw().isoformat()
    root_ref.child(COLLECTION).push({
        "name":       name.strip(),
        "content":    content.strip(),
        "created_at": now,
        "updated_at": now,
        "is_hidden":  False,
    })
    return True

def update_message(msg_id: str, content: str) -> bool:
    root_ref.child(COLLECTION).child(msg_id).update({
        "content":    content.strip(),
        "updated_at": now_tw().isoformat(),
    })
    return True

def delete_message(msg_id: str) -> bool:
    root_ref.child(COLLECTION).child(msg_id).delete()
    return True

# ── Session State ──────────────────────────────────────────────────────────────
def init_states():
    defaults = {
        "admin_verified":  False,
        "editing_id":      None,
        "edit_content":    "",
        "last_post_time":  None,
        "current_page":    1,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_states()

# ── 標題 ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="board-header">
    <h1>💬 留言板</h1>
    <p>歡迎留下你的想法，大家一起交流！</p>
</div>
""", unsafe_allow_html=True)

# ── 管理員登入 ─────────────────────────────────────────────────────────────────
with st.expander("🔑 管理員登入（編輯 / 刪除留言需要）", expanded=False):
    if st.session_state.admin_verified:
        st.success("✅ 已以管理員身分登入")
        if st.button("登出管理員"):
            st.session_state.admin_verified = False
            st.rerun()
    else:
        pwd_input = st.text_input("管理員密碼", type="password", key="pwd_input")
        if st.button("驗證"):
            if check_admin(pwd_input):
                st.session_state.admin_verified = True
                st.rerun()
            else:
                st.error("密碼錯誤，請再試一次。")

st.divider()

# ── 新增留言 ───────────────────────────────────────────────────────────────────
st.subheader("✏️ 新增留言")

new_name    = st.text_input("暱稱", max_chars=MAX_NAME,    placeholder="你的暱稱（最多 50 字）", key="new_name")
new_content = st.text_area ("留言內容", max_chars=MAX_CONTENT, placeholder="寫下你想說的話…（最多 500 字）", height=120, key="new_content")
st.caption(f"字數：{len(new_content)} / {MAX_CONTENT}")

if st.button("送出留言", type="primary", use_container_width=True):
    name_v    = new_name.strip()
    content_v = new_content.strip()
    errors = []
    if not name_v:               errors.append("暱稱不可為空。")
    elif len(name_v) > MAX_NAME: errors.append(f"暱稱最多 {MAX_NAME} 字。")
    if not content_v:                   errors.append("留言內容不可為空。")
    elif len(content_v) > MAX_CONTENT:  errors.append(f"留言內容最多 {MAX_CONTENT} 字。")

    # 冷卻時間
    last = st.session_state.last_post_time
    if last and (time.time() - last) < POST_COOLDOWN:
        remaining = math.ceil(POST_COOLDOWN - (time.time() - last))
        errors.append(f"請稍後再留言（還需等待 {remaining} 秒）。")

    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            add_message(name_v, content_v)
            st.session_state.last_post_time = time.time()
            st.session_state.current_page = 1
            st.success("留言成功！")
            st.rerun()
        except Exception as ex:
            st.error(f"儲存失敗：{ex}")

st.divider()

# ── 留言列表 ───────────────────────────────────────────────────────────────────
st.subheader("📋 所有留言")

try:
    all_messages = fetch_messages()
except Exception as ex:
    st.error(f"讀取留言失敗：{ex}")
    all_messages = []

total_count = len(all_messages)
total_pages = max(1, math.ceil(total_count / PAGE_SIZE))
if st.session_state.current_page > total_pages:
    st.session_state.current_page = total_pages
current_page = st.session_state.current_page

st.markdown(
    f'<div class="pager-info">共 {total_count} 則 ｜ 第 {current_page} 頁 / 共 {total_pages} 頁</div>',
    unsafe_allow_html=True,
)

# 分頁控制
col_prev, col_input, col_next = st.columns([1, 2, 1])
with col_prev:
    if st.button("上一頁", disabled=(current_page <= 1), use_container_width=True):
        st.session_state.current_page -= 1
        st.rerun()
with col_input:
    jump = st.number_input("頁碼", min_value=1, max_value=total_pages,
                           value=current_page, step=1,
                           label_visibility="collapsed", key="page_input")
    if jump != current_page:
        st.session_state.current_page = jump
        st.rerun()
with col_next:
    if st.button("下一頁", disabled=(current_page >= total_pages), use_container_width=True):
        st.session_state.current_page += 1
        st.rerun()

st.divider()

# 顯示當頁留言
start = (current_page - 1) * PAGE_SIZE
page_msgs = all_messages[start : start + PAGE_SIZE]

if not page_msgs:
    st.info("還沒有留言，成為第一個留言的人吧！")

for msg in page_msgs:
    msg_id    = msg["id"]
    is_editing = st.session_state.editing_id == msg_id

    st.markdown(f"""
<div class="msg-card">
    <div class="msg-name">👤 {sanitize(msg.get('name','訪客'))}</div>
    <div class="msg-content">{sanitize(msg.get('content',''))}</div>
    <div class="msg-meta">
        🕐 建立：{fmt_dt(msg.get('created_at',''))}
        &nbsp;｜&nbsp;
        🔄 更新：{fmt_dt(msg.get('updated_at',''))}
    </div>
</div>
""", unsafe_allow_html=True)

    # 管理員按鈕
    if st.session_state.admin_verified:
        col_edit, col_del, _ = st.columns([1, 1, 4])
        with col_edit:
            if not is_editing:
                if st.button("✏️ 編輯", key=f"edit_{msg_id}"):
                    st.session_state.editing_id   = msg_id
                    st.session_state.edit_content = msg.get("content", "")
                    st.rerun()
            else:
                if st.button("取消", key=f"cancel_{msg_id}"):
                    st.session_state.editing_id = None
                    st.rerun()
        with col_del:
            if st.button("🗑️ 刪除", key=f"del_{msg_id}"):
                try:
                    delete_message(msg_id)
                    st.success("已刪除。")
                    st.rerun()
                except Exception as ex:
                    st.error(f"刪除失敗：{ex}")

    # 編輯表單
    if is_editing:
        with st.form(key=f"edit_form_{msg_id}"):
            edited = st.text_area(
                "修改留言內容",
                value=st.session_state.edit_content,
                max_chars=MAX_CONTENT,
                height=120,
            )
            st.caption(f"字數：{len(edited)} / {MAX_CONTENT}")
            if st.form_submit_button("儲存修改", type="primary"):
                content_v = edited.strip()
                if not content_v:
                    st.error("留言內容不可為空。")
                elif len(content_v) > MAX_CONTENT:
                    st.error(f"留言內容最多 {MAX_CONTENT} 字。")
                else:
                    try:
                        update_message(msg_id, content_v)
                        st.session_state.editing_id = None
                        st.success("已更新！")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"更新失敗：{ex}")

st.divider()
st.caption("Powered by Streamlit × Firebase Realtime Database")