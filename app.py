"""
app.py
------
可愛留言板系統主程式。
依賴：utils、auth、firebase_service

功能：
- 可愛風格 UI（柔和色系、圓角卡片）
- 公告區（卡片式顯示）
- 留言輸入（防洗版 + 重複留言檢查）
- 留言列表（分頁、越界校正）
- 管理員側邊欄（登入 / 登出）
- 管理員後台（留言管理 + 公告管理）
"""

import logging
import math
import time
import uuid

import streamlit as st

from auth import is_admin_logged_in, render_sidebar_login
from firebase_service import (
    clamp_page,
    compute_total_pages,
    create_announcement,
    create_message,
    delete_announcement,
    delete_message,
    get_active_announcements,
    get_admin_messages_page,
    get_all_announcements,
    get_db,
    get_messages_page,
    get_total_message_count,
    hide_message,
    is_duplicate_message,
    toggle_announcement,
    unhide_message,
    update_announcement,
)
from utils import format_datetime_tw, sanitize_input

# ─── 設定 ──────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 分頁設定
_PAGE_SIZE_FRONT: int = 50
_PAGE_SIZE_ADMIN: int = 20

# 防洗版冷卻秒數
_POST_COOLDOWN_SECONDS: int = 10

# 留言最大字數
_MAX_CONTENT_LENGTH: int = 300


# ─── Session 初始化 ────────────────────────────────────────────────────────────

def init_app_states() -> None:
    """
    集中初始化所有 Session State 預設值。

    必須在 app.py 最頂部呼叫，確保所有 key 存在。
    使用 dict 批次初始化，避免重複的 if-not-in 判斷。

    特別說明：
    - user_session_id：自行生成的 UUID，作為無法取得真實 IP 時的 fallback。
      禁止依賴 Streamlit 內部 _session_id（未公開 API，可能隨版本移除）。
      使用 if-not-in 確保同一 Session 生命週期內固定不變（不隨 rerun 重新生成）。
    """
    defaults: dict = {
        # 自生成 UUID，IP fallback hash 來源（穩定、不依賴 Streamlit 內部 API）
        "user_session_id": uuid.uuid4().hex,
        # 前台分頁
        "current_page": 1,
        # 後台分頁（與前台完全獨立）
        "admin_current_page": 1,
        # 管理員登入狀態
        "admin_logged_in": False,
        "admin_login_failures": 0,
        "admin_locked_until": None,
        # 防洗版：最後送出時間
        "last_post_time": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ─── CSS 樣式 ──────────────────────────────────────────────────────────────────

def inject_css() -> None:
    """
    注入可愛風格的自訂 CSS。

    色系：柔和粉色系（#FFF0F5 背景、#FF85A1 主色、#FFB6C1 輔色）
    字型：使用系統預設，確保中文正常顯示
    卡片：圓角、陰影、溫暖感
    """
    st.markdown(
        """
        <style>
        /* ── 整體背景 ── */
        .stApp {
            background-color: #FFF8FB;
        }

        /* ── 主標題 ── */
        .main-title {
            text-align: center;
            font-size: 2.4rem;
            font-weight: 800;
            color: #D63384;
            margin-bottom: 0.2rem;
            letter-spacing: 0.05em;
        }
        .main-subtitle {
            text-align: center;
            color: #F48FB1;
            font-size: 0.95rem;
            margin-bottom: 1.5rem;
        }

        /* ── 公告卡片 ── */
        .announcement-card {
            background: linear-gradient(135deg, #FFF0F5, #FCE4EC);
            border-left: 5px solid #F06292;
            border-radius: 16px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 2px 8px rgba(240, 98, 146, 0.12);
        }
        .announcement-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: #C2185B;
            margin-bottom: 0.3rem;
        }
        .announcement-content {
            color: #555;
            font-size: 0.92rem;
            line-height: 1.6;
            white-space: pre-wrap;
        }
        .announcement-meta {
            font-size: 0.78rem;
            color: #E91E63;
            margin-top: 0.4rem;
            opacity: 0.7;
        }

        /* ── 留言卡片 ── */
        .message-card {
            background: #FFFFFF;
            border-radius: 18px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.85rem;
            box-shadow: 0 2px 10px rgba(211, 47, 47, 0.07);
            border: 1px solid #FCE4EC;
            transition: box-shadow 0.2s;
        }
        .message-card:hover {
            box-shadow: 0 4px 16px rgba(240, 98, 146, 0.15);
        }
        .message-name {
            font-weight: 700;
            color: #D81B60;
            font-size: 0.95rem;
        }
        .message-content {
            color: #333;
            font-size: 0.92rem;
            margin: 0.35rem 0;
            line-height: 1.65;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .message-time {
            font-size: 0.75rem;
            color: #BDBDBD;
        }

        /* ── 分頁資訊 ── */
        .pager-info {
            text-align: center;
            color: #F06292;
            font-size: 0.88rem;
            margin: 0.5rem 0;
        }

        /* ── 區塊標題 ── */
        .section-header {
            font-size: 1.1rem;
            font-weight: 700;
            color: #AD1457;
            margin: 1rem 0 0.5rem;
        }

        /* ── 空白提示 ── */
        .empty-hint {
            text-align: center;
            color: #F48FB1;
            font-size: 0.95rem;
            padding: 1.5rem;
        }

        /* ── 輸入框美化 ── */
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea {
            border-radius: 12px;
            border: 1.5px solid #F8BBD9;
            background: #FFF9FB;
        }
        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stTextArea"] textarea:focus {
            border-color: #F06292;
            box-shadow: 0 0 0 2px rgba(240, 98, 146, 0.2);
        }

        /* ── 按鈕美化 ── */
        div[data-testid="stButton"] > button {
            border-radius: 20px;
            font-weight: 600;
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #F06292, #E91E63);
            border: none;
            color: white;
        }

        /* ── Sidebar ── */
        section[data-testid="stSidebar"] {
            background: #FFF0F5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ─── 公告區 ────────────────────────────────────────────────────────────────────

def render_announcements(db) -> None:
    """
    渲染前台公告區（僅顯示 is_active == True 的公告）。

    使用 st.expander 包覆，預設展開。
    若無公告則顯示空白提示。

    Args:
        db: Firestore Client
    """
    with st.expander("📢 最新公告", expanded=True):
        announcements = get_active_announcements(db)
        if not announcements:
            st.markdown(
                '<div class="empty-hint">目前沒有公告 🌸</div>',
                unsafe_allow_html=True,
            )
            return

        for ann in announcements:
            title = ann.get("title", "（無標題）")
            content = ann.get("content", "")
            updated_at = format_datetime_tw(ann.get("updated_at", ""))
            st.markdown(
                f"""
                <div class="announcement-card">
                    <div class="announcement-title">📌 {title}</div>
                    <div class="announcement-content">{content}</div>
                    <div class="announcement-meta">🕐 更新時間：{updated_at}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ─── 留言輸入區 ────────────────────────────────────────────────────────────────

def render_post_form(db) -> None:
    """
    渲染留言輸入表單，含防洗版（10 秒冷卻）與重複留言檢查（60 秒）。

    驗證：
    - 暱稱與內容不可空白
    - 留言最大 300 字
    - 10 秒內不可再次送出
    - 60 秒內不可送出相同暱稱 + 相同內容的留言

    Args:
        db: Firestore Client
    """
    st.markdown('<div class="section-header">💬 留言板</div>', unsafe_allow_html=True)

    with st.container():
        with st.form(key="post_form", clear_on_submit=True):
            name = st.text_input(
                "暱稱 🐰",
                placeholder="請輸入你的暱稱",
                max_chars=30,
            )
            content = st.text_area(
                f"留言內容（最多 {_MAX_CONTENT_LENGTH} 字）✨",
                placeholder="在這裡輸入你的留言吧 🌸",
                max_chars=_MAX_CONTENT_LENGTH,
                height=120,
            )
            submitted = st.form_submit_button(
                "送出留言 ✨",
                use_container_width=True,
                type="primary",
            )

        if submitted:
            _handle_post_submission(db, name, content)


def _handle_post_submission(db, name: str, content: str) -> None:
    """
    處理留言送出的驗證與寫入邏輯。

    Args:
        db: Firestore Client
        name: 表單輸入的暱稱
        content: 表單輸入的留言內容
    """
    # 清理輸入
    name = sanitize_input(name)
    content = sanitize_input(content)

    # 基本驗證
    if not name:
        st.warning("暱稱不可空白喔 🐰")
        return
    if not content:
        st.warning("留言內容不可空白喔 ✨")
        return
    if len(content) > _MAX_CONTENT_LENGTH:
        st.warning(f"留言不可超過 {_MAX_CONTENT_LENGTH} 字 🐰")
        return

    # 防洗版：10 秒冷卻
    last_post = st.session_state.get("last_post_time")
    if last_post is not None:
        elapsed = time.time() - last_post
        if elapsed < _POST_COOLDOWN_SECONDS:
            remaining = math.ceil(_POST_COOLDOWN_SECONDS - elapsed)
            st.warning(f"請稍後再留言 🐰（還需等待 {remaining} 秒）")
            return

    # 重複留言檢查（60 秒）
    if is_duplicate_message(db, name, content, seconds=60):
        st.warning("你剛才已經留過相同的留言了，請稍後再試 🐰")
        return

    # 寫入 Firestore
    success = create_message(db, name, content)
    if success:
        st.session_state["last_post_time"] = time.time()
        # 留言後跳回第一頁，看到最新留言
        st.session_state["current_page"] = 1
        st.success("留言成功 ✨")
        st.rerun()


# ─── 留言列表區 ────────────────────────────────────────────────────────────────

def render_messages(db) -> None:
    """
    渲染前台留言列表，含分頁控制與越界校正。

    使用 offset + limit 分頁，每頁 50 筆。
    僅顯示 is_hidden == False 的留言。

    Args:
        db: Firestore Client
    """
    st.markdown('<div class="section-header">🌸 留言列表</div>', unsafe_allow_html=True)

    # 取得總數並計算總頁數
    total_count = get_total_message_count(db)
    total_pages = compute_total_pages(total_count, _PAGE_SIZE_FRONT)

    # 越界校正：避免刪除/隱藏留言後出現空頁
    clamp_page("current_page", total_pages)
    current_page = st.session_state["current_page"]

    # 分頁資訊
    st.markdown(
        f'<div class="pager-info">'
        f"總留言數：{total_count} ｜ 第 {current_page} 頁 / 共 {total_pages} 頁 ｜ 每頁 {_PAGE_SIZE_FRONT} 筆"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 分頁控制元件
    _render_pager(
        session_key="current_page",
        current_page=current_page,
        total_pages=total_pages,
        input_key="front_page_input",
    )

    st.divider()

    # 取得留言資料
    messages = get_messages_page(db, current_page, _PAGE_SIZE_FRONT)

    if not messages:
        st.markdown(
            '<div class="empty-hint">還沒有留言，來當第一個留言的人吧 🌸</div>',
            unsafe_allow_html=True,
        )
        return

    for msg in messages:
        _render_message_card(msg)


def _render_message_card(msg: dict) -> None:
    """
    渲染單筆留言的卡片 UI。

    Args:
        msg: 留言資料字典（含 name、content、created_at）
    """
    name = msg.get("name", "匿名")
    content = msg.get("content", "")
    created_at = format_datetime_tw(msg.get("created_at", ""))

    st.markdown(
        f"""
        <div class="message-card">
            <div class="message-name">🐰 {name}</div>
            <div class="message-content">{content}</div>
            <div class="message-time">🕐 {created_at}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── 分頁控制元件 ──────────────────────────────────────────────────────────────

def _render_pager(
    session_key: str,
    current_page: int,
    total_pages: int,
    input_key: str,
) -> None:
    """
    渲染分頁控制元件（上一頁 / 跳頁輸入框 / 下一頁）。

    協調策略：
    - number_input 使用獨立 key（input_key）
    - 每次 rerun 後比對 input_key 與 session_key，若不同則同步並 rerun
    - 按鈕只修改 session_key，不直接操作 input_key

    Args:
        session_key: session_state 中儲存當前頁碼的 key
        current_page: 目前頁碼
        total_pages: 總頁數
        input_key: number_input widget 的 key（前台與後台必須不同）
    """
    col_prev, col_input, col_next = st.columns([1, 2, 1])

    with col_prev:
        if st.button(
            "上一頁 🐾",
            key=f"btn_prev_{session_key}",
            disabled=(current_page <= 1),
            use_container_width=True,
        ):
            st.session_state[session_key] = current_page - 1
            st.rerun()

    with col_input:
        # number_input 用於跳頁，value 讀取 session_state 確保同步
        st.number_input(
            "頁碼",
            min_value=1,
            max_value=total_pages,
            value=current_page,
            step=1,
            key=input_key,
            label_visibility="collapsed",
        )

    with col_next:
        if st.button(
            "下一頁 🐾",
            key=f"btn_next_{session_key}",
            disabled=(current_page >= total_pages),
            use_container_width=True,
        ):
            st.session_state[session_key] = current_page + 1
            st.rerun()

    # 同步 number_input 跳頁：若使用者直接輸入頁碼，觸發 rerun 更新 session_key
    input_val = st.session_state.get(input_key, 1)
    if input_val != st.session_state[session_key]:
        st.session_state[session_key] = input_val
        st.rerun()


# ─── 管理員後台 ────────────────────────────────────────────────────────────────

def render_admin_panel(db) -> None:
    """
    渲染管理員後台介面（留言管理 + 公告管理）。

    只有 is_admin_logged_in() == True 時才顯示。

    Args:
        db: Firestore Client
    """
    st.divider()
    st.markdown("## 🛠️ 管理員後台")

    tab_messages, tab_announcements = st.tabs(["💬 留言管理", "📢 公告管理"])

    with tab_messages:
        _render_admin_messages(db)

    with tab_announcements:
        _render_admin_announcements(db)


def _render_admin_messages(db) -> None:
    """
    管理員留言管理頁面（含隱藏、取消隱藏、刪除）。

    每頁 20 筆，使用獨立的 admin_current_page session key。

    Args:
        db: Firestore Client
    """
    st.markdown("### 💬 留言管理")

    messages, total_count = get_admin_messages_page(
        db, st.session_state["admin_current_page"], _PAGE_SIZE_ADMIN
    )
    total_pages = compute_total_pages(total_count, _PAGE_SIZE_ADMIN)

    # 越界校正
    clamp_page("admin_current_page", total_pages)
    current_page = st.session_state["admin_current_page"]

    st.markdown(
        f'<div class="pager-info">'
        f"總留言數：{total_count} ｜ 第 {current_page} 頁 / 共 {total_pages} 頁 ｜ 每頁 {_PAGE_SIZE_ADMIN} 筆"
        f"</div>",
        unsafe_allow_html=True,
    )

    _render_pager(
        session_key="admin_current_page",
        current_page=current_page,
        total_pages=total_pages,
        input_key="admin_page_input",
    )

    st.divider()

    if not messages:
        st.markdown(
            '<div class="empty-hint">目前沒有留言 🌸</div>',
            unsafe_allow_html=True,
        )
        return

    for msg in messages:
        _render_admin_message_row(db, msg)


def _render_admin_message_row(db, msg: dict) -> None:
    """
    渲染管理員後台的單筆留言列（含操作按鈕）。

    Args:
        db: Firestore Client
        msg: 留言資料字典
    """
    msg_id = msg["id"]
    name = msg.get("name", "匿名")
    content = msg.get("content", "")
    created_at = format_datetime_tw(msg.get("created_at", ""))
    is_hidden = msg.get("is_hidden", False)

    status_emoji = "🙈 隱藏中" if is_hidden else "✅ 顯示中"
    card_style = "opacity:0.5;" if is_hidden else ""

    with st.container():
        st.markdown(
            f"""
            <div class="message-card" style="{card_style}">
                <div class="message-name">🐰 {name}
                    <span style="font-size:0.75rem;color:#888;margin-left:0.5rem;">{status_emoji}</span>
                </div>
                <div class="message-content">{content}</div>
                <div class="message-time">🕐 {created_at} ｜ ID: {msg_id[:8]}...</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_hide, col_delete = st.columns([1, 1])

        with col_hide:
            if is_hidden:
                if st.button(
                    "取消隱藏 👁️",
                    key=f"unhide_{msg_id}",
                    use_container_width=True,
                ):
                    if unhide_message(db, msg_id):
                        st.success("已取消隱藏 ✨")
                        st.rerun()
            else:
                if st.button(
                    "隱藏留言 🙈",
                    key=f"hide_{msg_id}",
                    use_container_width=True,
                ):
                    if hide_message(db, msg_id):
                        st.success("已隱藏留言 ✨")
                        st.rerun()

        with col_delete:
            confirm_key = f"confirm_delete_{msg_id}"
            confirmed = st.checkbox("確認刪除", key=confirm_key)
            if confirmed:
                if st.button(
                    "永久刪除 🗑️",
                    key=f"delete_{msg_id}",
                    use_container_width=True,
                ):
                    if delete_message(db, msg_id):
                        st.success("已刪除留言 ✨")
                        st.rerun()


def _render_admin_announcements(db) -> None:
    """
    管理員公告管理頁面（新增 / 修改 / 刪除 / 啟停用 / 排序）。

    Args:
        db: Firestore Client
    """
    st.markdown("### 📢 公告管理")

    # ── 新增公告 ──────────────────────────────────
    with st.expander("➕ 新增公告", expanded=False):
        with st.form(key="form_add_announcement"):
            new_title = st.text_input("標題", max_chars=100)
            new_content = st.text_area("內容", height=100)
            new_sort = st.number_input("排序值（越小越前面）", value=0, step=1)
            if st.form_submit_button("新增公告 ✨", use_container_width=True):
                if not new_title.strip():
                    st.warning("標題不可空白 🐰")
                elif not new_content.strip():
                    st.warning("內容不可空白 🐰")
                elif create_announcement(db, new_title, new_content, int(new_sort)):
                    st.success("公告新增成功 ✨")
                    st.rerun()

    st.divider()

    # ── 現有公告列表 ──────────────────────────────
    announcements = get_all_announcements(db)

    if not announcements:
        st.markdown(
            '<div class="empty-hint">目前沒有公告 🌸</div>',
            unsafe_allow_html=True,
        )
        return

    for ann in announcements:
        _render_admin_announcement_row(db, ann)


def _render_admin_announcement_row(db, ann: dict) -> None:
    """
    渲染管理員後台的單筆公告列（含修改 / 刪除 / 啟停用）。

    Args:
        db: Firestore Client
        ann: 公告資料字典
    """
    ann_id = ann["id"]
    is_active = ann.get("is_active", False)
    updated_at = format_datetime_tw(ann.get("updated_at", ""))
    status_label = "✅ 啟用中" if is_active else "⏸️ 停用中"

    with st.expander(
        f"{'📌' if is_active else '📋'} {ann.get('title', '（無標題）')} ｜ {status_label}",
        expanded=False,
    ):
        with st.form(key=f"form_edit_ann_{ann_id}"):
            edit_title = st.text_input("標題", value=ann.get("title", ""), max_chars=100)
            edit_content = st.text_area(
                "內容", value=ann.get("content", ""), height=100
            )
            edit_sort = st.number_input(
                "排序值", value=int(ann.get("sort_order", 0)), step=1
            )

            col_save, col_toggle, col_del = st.columns(3)

            with col_save:
                if st.form_submit_button("儲存修改 💾", use_container_width=True):
                    if not edit_title.strip():
                        st.warning("標題不可空白 🐰")
                    elif update_announcement(
                        db, ann_id, edit_title, edit_content, int(edit_sort)
                    ):
                        st.success("公告已更新 ✨")
                        st.rerun()

            with col_toggle:
                toggle_label = "停用公告 ⏸️" if is_active else "啟用公告 ▶️"
                if st.form_submit_button(toggle_label, use_container_width=True):
                    if toggle_announcement(db, ann_id, not is_active):
                        action = "停用" if is_active else "啟用"
                        st.success(f"公告已{action} ✨")
                        st.rerun()

            with col_del:
                if st.form_submit_button("刪除公告 🗑️", use_container_width=True):
                    if delete_announcement(db, ann_id):
                        st.success("公告已刪除 ✨")
                        st.rerun()

        st.caption(f"🕐 最後更新：{updated_at}")


# ─── 主程式 ────────────────────────────────────────────────────────────────────

def main() -> None:
    """
    應用程式主入口。

    執行順序：
    1. 頁面設定
    2. Session 初始化
    3. CSS 注入
    4. Firebase 連線
    5. 側邊欄（管理員登入）
    6. 主標題
    7. 公告區
    8. 留言輸入區
    9. 留言列表區
    10. 管理員後台（若已登入）
    """
    st.set_page_config(
        page_title="🌸 可愛留言板",
        page_icon="🌸",
        layout="centered",
        initial_sidebar_state="auto",
    )

    # 初始化 session（必須最先執行）
    init_app_states()

    # 注入 CSS
    inject_css()

    # 取得 Firestore 連線
    db = get_db()
    if db is None:
        st.error("⚠️ 無法連線至資料庫，請確認 Firebase 設定後重新整理。")
        st.stop()

    # 側邊欄：管理員登入 / 登出
    render_sidebar_login()

    # ── 主標題 ──────────────────────────────────────
    st.markdown(
        '<div class="main-title">🌸 可愛留言板</div>'
        '<div class="main-subtitle">溫暖的小角落，歡迎你來留言 🐰✨</div>',
        unsafe_allow_html=True,
    )

    # ── 公告區 ──────────────────────────────────────
    render_announcements(db)

    st.divider()

    # ── 留言輸入區 ──────────────────────────────────
    render_post_form(db)

    st.divider()

    # ── 留言列表區 ──────────────────────────────────
    render_messages(db)

    # ── 管理員後台 ──────────────────────────────────
    if is_admin_logged_in():
        render_admin_panel(db)


if __name__ == "__main__":
    main()
