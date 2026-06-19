import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone
import pytz

# ── 頁面設定 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="留言板",
    page_icon="💬",
    layout="centered",
)

# ── 自訂 CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* 全域字體與背景 */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans TC', sans-serif;
}

/* 標題區 */
.board-header {
    text-align: center;
    padding: 1.5rem 0 1rem;
    border-bottom: 2px solid #e2e8f0;
    margin-bottom: 1.5rem;
}
.board-header h1 {
    font-size: 2rem;
    font-weight: 700;
    color: #1a202c;
    margin: 0;
}
.board-header p {
    color: #718096;
    font-size: 0.9rem;
    margin: 0.25rem 0 0;
}

/* 留言卡片 */
.msg-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    transition: box-shadow 0.2s;
}
.msg-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.msg-name {
    font-weight: 700;
    color: #2d3748;
    font-size: 1rem;
}
.msg-content {
    color: #4a5568;
    margin: 0.4rem 0;
    font-size: 0.95rem;
    white-space: pre-wrap;
    word-break: break-word;
}
.msg-meta {
    font-size: 0.75rem;
    color: #a0aec0;
}

/* 表單區 */
.form-section {
    background: #f7fafc;
    border-radius: 12px;
    padding: 1.25rem;
    border: 1px solid #e2e8f0;
    margin-bottom: 1.5rem;
}

/* 管理員區 */
.admin-section {
    background: #fff8f0;
    border: 1px solid #fbd38d;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.5rem;
}

/* 成功 / 錯誤訊息 */
.stAlert { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Firebase 初始化 ───────────────────────────────────────────────────────────
@st.cache_resource
def init_firebase():
    """只初始化一次 Firebase，之後從快取取得。"""
    if not firebase_admin._apps:
        fb = st.secrets["firebase"]
        cred = credentials.Certificate({
            "type": fb["type"],
            "project_id": fb["project_id"],
            "private_key_id": fb["private_key_id"],
            "private_key": fb["private_key"].replace("\\n", "\n"),
            "client_email": fb["client_email"],
            "client_id": fb["client_id"],
            "auth_uri": fb["auth_uri"],
            "token_uri": fb["token_uri"],
            "auth_provider_x509_cert_url": fb["auth_provider_x509_cert_url"],
            "client_x509_cert_url": fb["client_x509_cert_url"],
        })
        firebase_admin.initialize_app(cred)
    return firestore.client()


db = init_firebase()
COLLECTION = "messages"
TW = pytz.timezone("Asia/Taipei")

# ── 輔助函式 ──────────────────────────────────────────────────────────────────
def now_tw() -> datetime:
    return datetime.now(tz=TW)


def fmt_dt(ts) -> str:
    """將 Firestore Timestamp 或 datetime 格式化為台灣時間字串。"""
    if ts is None:
        return "—"
    if hasattr(ts, "tzinfo"):
        dt = ts
    else:
        dt = ts.astimezone(TW)
    if dt.tzinfo is None:
        dt = TW.localize(dt)
    else:
        dt = dt.astimezone(TW)
    return dt.strftime("%Y-%m-%d %H:%M")


def fetch_messages():
    """從 Firestore 取得所有留言，依 created_at 由新到舊排序。"""
    docs = (
        db.collection(COLLECTION)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .stream()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]


def add_message(name: str, content: str):
    now = now_tw()
    db.collection(COLLECTION).add({
        "name": name.strip(),
        "content": content.strip(),
        "created_at": now,
        "updated_at": now,
    })


def update_message(doc_id: str, content: str):
    db.collection(COLLECTION).document(doc_id).update({
        "content": content.strip(),
        "updated_at": now_tw(),
    })


def delete_message(doc_id: str):
    db.collection(COLLECTION).document(doc_id).delete()


def check_admin(password: str) -> bool:
    return password == st.secrets.get("admin_password", "")


# ── Session State 初始化 ──────────────────────────────────────────────────────
if "admin_verified" not in st.session_state:
    st.session_state.admin_verified = False
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "edit_content" not in st.session_state:
    st.session_state.edit_content = ""

# ── 頁面標題 ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="board-header">
    <h1>💬 留言板</h1>
    <p>歡迎留下你的想法，大家一起交流！</p>
</div>
""", unsafe_allow_html=True)

# ── 管理員驗證區 ──────────────────────────────────────────────────────────────
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
                st.success("登入成功！")
                st.rerun()
            else:
                st.error("密碼錯誤，請再試一次。")

st.divider()

# ── 新增留言表單 ───────────────────────────────────────────────────────────────
st.subheader("✏️ 新增留言")
with st.container():
    new_name = st.text_input(
        "暱稱",
        max_chars=50,
        placeholder="你的暱稱（最多 50 字）",
        key="new_name",
    )
    new_content = st.text_area(
        "留言內容",
        max_chars=500,
        placeholder="寫下你想說的話…（最多 500 字）",
        height=120,
        key="new_content",
    )
    char_count = len(new_content)
    st.caption(f"字數：{char_count} / 500")

    if st.button("送出留言", type="primary", use_container_width=True):
        name_val = new_name.strip()
        content_val = new_content.strip()
        errors = []
        if not name_val:
            errors.append("暱稱不可為空。")
        elif len(name_val) > 50:
            errors.append("暱稱最多 50 字。")
        if not content_val:
            errors.append("留言內容不可為空。")
        elif len(content_val) > 500:
            errors.append("留言內容最多 500 字。")

        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                add_message(name_val, content_val)
                st.success("留言成功！")
                st.rerun()
            except Exception as ex:
                st.error(f"儲存失敗：{ex}")

st.divider()

# ── 留言列表 ──────────────────────────────────────────────────────────────────
st.subheader("📋 所有留言")

try:
    messages = fetch_messages()
except Exception as ex:
    st.error(f"讀取留言失敗：{ex}")
    messages = []

if not messages:
    st.info("目前還沒有留言，成為第一個留言的人吧！")
else:
    for msg in messages:
        doc_id = msg["id"]
        is_editing = st.session_state.editing_id == doc_id

        with st.container():
            st.markdown(f"""
<div class="msg-card">
    <div class="msg-name">👤 {msg.get('name', '匿名')}</div>
    <div class="msg-content">{msg.get('content', '')}</div>
    <div class="msg-meta">
        🕐 建立：{fmt_dt(msg.get('created_at'))}
        &nbsp;｜&nbsp;
        🔄 更新：{fmt_dt(msg.get('updated_at'))}
    </div>
</div>
""", unsafe_allow_html=True)

            # 管理員操作按鈕
            if st.session_state.admin_verified:
                col_edit, col_del, _ = st.columns([1, 1, 4])
                with col_edit:
                    if not is_editing:
                        if st.button("✏️ 編輯", key=f"edit_{doc_id}"):
                            st.session_state.editing_id = doc_id
                            st.session_state.edit_content = msg.get("content", "")
                            st.rerun()
                    else:
                        if st.button("取消", key=f"cancel_{doc_id}"):
                            st.session_state.editing_id = None
                            st.rerun()
                with col_del:
                    if st.button("🗑️ 刪除", key=f"del_{doc_id}"):
                        try:
                            delete_message(doc_id)
                            st.success("留言已刪除。")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"刪除失敗：{ex}")

            # 編輯表單（展開於該留言下方）
            if is_editing:
                with st.form(key=f"edit_form_{doc_id}"):
                    edited = st.text_area(
                        "修改留言內容",
                        value=st.session_state.edit_content,
                        max_chars=500,
                        height=120,
                        key=f"edit_ta_{doc_id}",
                    )
                    st.caption(f"字數：{len(edited)} / 500")
                    submitted = st.form_submit_button("儲存修改", type="primary")
                    if submitted:
                        content_val = edited.strip()
                        if not content_val:
                            st.error("留言內容不可為空。")
                        elif len(content_val) > 500:
                            st.error("留言內容最多 500 字。")
                        else:
                            try:
                                update_message(doc_id, content_val)
                                st.session_state.editing_id = None
                                st.success("留言已更新！")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"更新失敗：{ex}")

# ── 頁尾 ──────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Powered by Streamlit × Firebase Firestore")