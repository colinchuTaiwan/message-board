"""
app.py
------
多留言板系統主程式（Firebase Realtime Database 版）
支援七個留言板，各有獨立主題色，側邊欄切換。
依賴：utils、auth、firebase_service
"""

import logging
import math
import time
import uuid

import streamlit as st

from auth import is_admin_logged_in, render_sidebar_login
from firebase_service import (
    BOARDS,
    BOARD_MAP,
    clamp_page,
    compute_total_pages,
    create_announcement,
    create_message,
    delete_announcement,
    delete_message,
    get_admin_messages,
    get_announcements,
    get_all_announcements,
    get_messages,
    get_total_message_count,
    hide_message,
    is_duplicate_message,
    toggle_announcement,
    track_visitor,
    unhide_message,
    update_announcement,
)
from utils import format_datetime_tw, sanitize_input

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_PAGE_SIZE_FRONT: int = 50
_PAGE_SIZE_ADMIN: int = 20
_POST_COOLDOWN_SECONDS: int = 10
_MAX_CONTENT_LENGTH: int = 300


# ─── 主題色定義 ────────────────────────────────────────────────────────────────

THEMES: dict[str, dict] = {
    # 🏠 可愛的家 — 暖棕米色
    "warm": {
        "bg":           "#FAF6F1",
        "title":        "#5C3D2E",
        "subtitle":     "#A07855",
        "visitor":      "#B08060",
        "card_bg":      "#FFFDF9",
        "card_border":  "#EDD9C0",
        "card_shadow":  "140,90,50",
        "name_color":   "#7B4F2E",
        "time_color":   "#C4A882",
        "ann_bg1":      "#FFF8ED",
        "ann_bg2":      "#FDEFD8",
        "ann_border":   "#C8864A",
        "ann_title":    "#7B4F2E",
        "ann_meta":     "#B08050",
        "section":      "#6B4226",
        "pager":        "#A07855",
        "empty":        "#C4A882",
        "input_border": "#D9BFA0",
        "input_focus":  "#C8864A",
        "input_focus_shadow": "200,134,74",
        "btn_grad1":    "#C8864A",
        "btn_grad2":    "#A0622E",
        "btn_hover1":   "#D9935A",
        "btn_hover2":   "#B0723E",
        "sidebar_bg":   "#F5EDE0",
        "placeholder":  "有什麼想跟大家分享的嗎？🍵",
        "post_btn":     "留下足跡 🏠",
        "name_hint":    "叫我什麼都好～",
        "empty_msg":    "還沒有人留言，來當第一個吧 🏠",
        "empty_ann":    "目前沒有公告 🏡",
        "ann_expander": "📋 家裡公告",
        "msg_section":  "🏡 大家說的話",
        "post_section": "✏️ 留下你的話",
        "name_label":   "你的名字 🏷️",
        "name_emoji":   "🏷️",
        "visitor_icon": "🚪",
    },
    # 👩 媽媽的大小事 — 玫瑰粉
    "rose": {
        "bg":           "#FFF5F7",
        "title":        "#C2185B",
        "subtitle":     "#E91E63",
        "visitor":      "#F06292",
        "card_bg":      "#FFFFFF",
        "card_border":  "#FFCDD2",
        "card_shadow":  "194,24,91",
        "name_color":   "#AD1457",
        "time_color":   "#F48FB1",
        "ann_bg1":      "#FFF0F3",
        "ann_bg2":      "#FCE4EC",
        "ann_border":   "#E91E63",
        "ann_title":    "#880E4F",
        "ann_meta":     "#C2185B",
        "section":      "#880E4F",
        "pager":        "#E91E63",
        "empty":        "#F48FB1",
        "input_border": "#F8BBD9",
        "input_focus":  "#E91E63",
        "input_focus_shadow": "233,30,99",
        "btn_grad1":    "#E91E63",
        "btn_grad2":    "#C2185B",
        "btn_hover1":   "#F06292",
        "btn_hover2":   "#D81B60",
        "sidebar_bg":   "#FCE4EC",
        "placeholder":  "媽媽們，說說今天的大小事吧 🌸",
        "post_btn":     "分享心情 💕",
        "name_hint":    "請輸入暱稱",
        "empty_msg":    "還沒有留言，來聊聊吧 🌸",
        "empty_ann":    "目前沒有公告 🌸",
        "ann_expander": "📢 公告欄",
        "msg_section":  "💕 媽媽們說",
        "post_section": "💬 說說你的心情",
        "name_label":   "暱稱 🌸",
        "name_emoji":   "🌸",
        "visitor_icon": "👀",
    },
    # ✈️ 旅遊討論區 — 天空藍
    "sky": {
        "bg":           "#F0F8FF",
        "title":        "#01579B",
        "subtitle":     "#0288D1",
        "visitor":      "#29B6F6",
        "card_bg":      "#FFFFFF",
        "card_border":  "#B3E5FC",
        "card_shadow":  "2,136,209",
        "name_color":   "#0277BD",
        "time_color":   "#81D4FA",
        "ann_bg1":      "#E1F5FE",
        "ann_bg2":      "#B3E5FC",
        "ann_border":   "#0288D1",
        "ann_title":    "#01579B",
        "ann_meta":     "#0288D1",
        "section":      "#01579B",
        "pager":        "#0288D1",
        "empty":        "#81D4FA",
        "input_border": "#81D4FA",
        "input_focus":  "#0288D1",
        "input_focus_shadow": "2,136,209",
        "btn_grad1":    "#0288D1",
        "btn_grad2":    "#01579B",
        "btn_hover1":   "#29B6F6",
        "btn_hover2":   "#0277BD",
        "sidebar_bg":   "#E1F5FE",
        "placeholder":  "分享你的旅遊經驗、行程規劃 ✈️",
        "post_btn":     "出發囉 ✈️",
        "name_hint":    "旅人暱稱",
        "empty_msg":    "還沒有旅遊分享，來開啟第一篇吧 ✈️",
        "empty_ann":    "目前沒有公告 ✈️",
        "ann_expander": "📢 旅遊公告",
        "msg_section":  "🗺️ 旅遊分享",
        "post_section": "✈️ 分享你的旅程",
        "name_label":   "旅人名稱 🧳",
        "name_emoji":   "🧳",
        "visitor_icon": "🌍",
    },
    # 🎮 寶可夢討論區 — 寶可夢黃
    "poke": {
        "bg":           "#FFFDE7",
        "title":        "#E65100",
        "subtitle":     "#F57C00",
        "visitor":      "#FFA000",
        "card_bg":      "#FFFFFF",
        "card_border":  "#FFE082",
        "card_shadow":  "230,81,0",
        "name_color":   "#E65100",
        "time_color":   "#FFCA28",
        "ann_bg1":      "#FFF8E1",
        "ann_bg2":      "#FFECB3",
        "ann_border":   "#FFA000",
        "ann_title":    "#E65100",
        "ann_meta":     "#F57C00",
        "section":      "#BF360C",
        "pager":        "#F57C00",
        "empty":        "#FFCA28",
        "input_border": "#FFE082",
        "input_focus":  "#FFA000",
        "input_focus_shadow": "255,160,0",
        "btn_grad1":    "#FFA000",
        "btn_grad2":    "#E65100",
        "btn_hover1":   "#FFB300",
        "btn_hover2":   "#F57C00",
        "sidebar_bg":   "#FFF8E1",
        "placeholder":  "討論你最愛的寶可夢吧！⚡",
        "post_btn":     "投出精靈球 ⚡",
        "name_hint":    "訓練師名稱",
        "empty_msg":    "還沒有訓練師來討論，第一個出發吧 ⚡",
        "empty_ann":    "目前沒有公告 ⚡",
        "ann_expander": "📢 道館公告",
        "msg_section":  "⚡ 訓練師的話",
        "post_section": "🎮 加入討論",
        "name_label":   "訓練師名稱 ⚡",
        "name_emoji":   "⚡",
        "visitor_icon": "🎮",
    },
    # 💬 閒聊區 — 薄荷綠
    "mint": {
        "bg":           "#F1FBF7",
        "title":        "#1B5E20",
        "subtitle":     "#388E3C",
        "visitor":      "#66BB6A",
        "card_bg":      "#FFFFFF",
        "card_border":  "#C8E6C9",
        "card_shadow":  "56,142,60",
        "name_color":   "#2E7D32",
        "time_color":   "#A5D6A7",
        "ann_bg1":      "#E8F5E9",
        "ann_bg2":      "#C8E6C9",
        "ann_border":   "#388E3C",
        "ann_title":    "#1B5E20",
        "ann_meta":     "#388E3C",
        "section":      "#1B5E20",
        "pager":        "#388E3C",
        "empty":        "#A5D6A7",
        "input_border": "#A5D6A7",
        "input_focus":  "#388E3C",
        "input_focus_shadow": "56,142,60",
        "btn_grad1":    "#43A047",
        "btn_grad2":    "#2E7D32",
        "btn_hover1":   "#66BB6A",
        "btn_hover2":   "#388E3C",
        "sidebar_bg":   "#E8F5E9",
        "placeholder":  "想聊什麼都可以，輕鬆聊～ 💬",
        "post_btn":     "聊起來 💬",
        "name_hint":    "你的暱稱",
        "empty_msg":    "還沒人聊天，來開話題吧 💬",
        "empty_ann":    "目前沒有公告 💬",
        "ann_expander": "📢 公告",
        "msg_section":  "💬 大家說",
        "post_section": "💬 來閒聊",
        "name_label":   "暱稱 😊",
        "name_emoji":   "😊",
        "visitor_icon": "👋",
    },
    # 📚 學習專區 — 深藍紫
    "indigo": {
        "bg":           "#F3F0FF",
        "title":        "#1A237E",
        "subtitle":     "#3949AB",
        "visitor":      "#5C6BC0",
        "card_bg":      "#FFFFFF",
        "card_border":  "#C5CAE9",
        "card_shadow":  "57,73,171",
        "name_color":   "#283593",
        "time_color":   "#9FA8DA",
        "ann_bg1":      "#E8EAF6",
        "ann_bg2":      "#C5CAE9",
        "ann_border":   "#3949AB",
        "ann_title":    "#1A237E",
        "ann_meta":     "#3949AB",
        "section":      "#1A237E",
        "pager":        "#3949AB",
        "empty":        "#9FA8DA",
        "input_border": "#9FA8DA",
        "input_focus":  "#3949AB",
        "input_focus_shadow": "57,73,171",
        "btn_grad1":    "#3949AB",
        "btn_grad2":    "#1A237E",
        "btn_hover1":   "#5C6BC0",
        "btn_hover2":   "#283593",
        "sidebar_bg":   "#E8EAF6",
        "placeholder":  "分享學習心得、問題討論 📚",
        "post_btn":     "發表見解 📚",
        "name_hint":    "學習者暱稱",
        "empty_msg":    "還沒有學習分享，來開啟第一篇吧 📚",
        "empty_ann":    "目前沒有公告 📚",
        "ann_expander": "📢 學習公告",
        "msg_section":  "📚 學習分享",
        "post_section": "✏️ 分享你的學習",
        "name_label":   "暱稱 📖",
        "name_emoji":   "📖",
        "visitor_icon": "📚",
    },
    # 🤖 AI學習區 — 科技灰藍
    "tech": {
        "bg":           "#F0F4F8",
        "title":        "#0D1B2A",
        "subtitle":     "#1B4F72",
        "visitor":      "#2E86C1",
        "card_bg":      "#FFFFFF",
        "card_border":  "#AED6F1",
        "card_shadow":  "46,134,193",
        "name_color":   "#1A5276",
        "time_color":   "#85C1E9",
        "ann_bg1":      "#EAF2FF",
        "ann_bg2":      "#D6EAF8",
        "ann_border":   "#2E86C1",
        "ann_title":    "#1A5276",
        "ann_meta":     "#2E86C1",
        "section":      "#0D1B2A",
        "pager":        "#2E86C1",
        "empty":        "#85C1E9",
        "input_border": "#85C1E9",
        "input_focus":  "#2E86C1",
        "input_focus_shadow": "46,134,193",
        "btn_grad1":    "#1B4F72",
        "btn_grad2":    "#0D1B2A",
        "btn_hover1":   "#2E86C1",
        "btn_hover2":   "#1A5276",
        "sidebar_bg":   "#D6EAF8",
        "placeholder":  "分享 AI 學習心得、工具使用經驗 🤖",
        "post_btn":     "送出討論 🤖",
        "name_hint":    "暱稱 / ID",
        "empty_msg":    "還沒有 AI 討論，來開啟第一篇吧 🤖",
        "empty_ann":    "目前沒有公告 🤖",
        "ann_expander": "📢 AI 公告",
        "msg_section":  "🤖 AI 討論區",
        "post_section": "💡 分享你的 AI 見解",
        "name_label":   "暱稱 🤖",
        "name_emoji":   "🤖",
        "visitor_icon": "🤖",
    },
}


# ─── Session 初始化 ────────────────────────────────────────────────────────────

def init_app_states() -> None:
    """集中初始化所有 Session State。"""
    defaults: dict = {
        "user_session_id":    uuid.uuid4().hex,
        "active_board_id":    BOARDS[0]["id"],
        "admin_logged_in":    False,
        "admin_login_failures": 0,
        "admin_locked_until": None,
        "last_post_time":     None,
    }
    # 每個留言板的前台 / 後台頁碼獨立初始化
    for board in BOARDS:
        bid = board["id"]
        defaults[f"page_{bid}"] = 1
        defaults[f"admin_page_{bid}"] = 1
        defaults[f"counted_{bid}"] = False

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ─── CSS 注入 ──────────────────────────────────────────────────────────────────

def inject_css(theme: dict) -> None:
    """依照目前留言板的主題色注入 CSS。"""
    t = theme
    st.markdown(f"""
    <style>
    .stApp {{ background-color: {t["bg"]}; }}

    .main-title {{
        text-align: center; font-size: 2.2rem; font-weight: 800;
        color: {t["title"]}; margin-bottom: 0.2rem;
    }}
    .main-subtitle {{
        text-align: center; color: {t["subtitle"]};
        font-size: 0.95rem; margin-bottom: 0.4rem;
    }}
    .visitor-badge {{
        text-align: center; color: {t["visitor"]};
        font-size: 0.85rem; margin-bottom: 1rem;
    }}

    .announcement-card {{
        background: linear-gradient(135deg, {t["ann_bg1"]}, {t["ann_bg2"]});
        border-left: 5px solid {t["ann_border"]}; border-radius: 12px;
        padding: 1rem 1.25rem; margin-bottom: 0.75rem;
        box-shadow: 0 2px 8px rgba({t["card_shadow"]},0.10);
    }}
    .announcement-title {{ font-size:1.05rem; font-weight:700; color:{t["ann_title"]}; margin-bottom:0.3rem; }}
    .announcement-content {{ color:#555; font-size:0.92rem; line-height:1.65; white-space:pre-wrap; }}
    .announcement-meta {{ font-size:0.78rem; color:{t["ann_meta"]}; margin-top:0.4rem; opacity:0.8; }}

    .message-card {{
        background: {t["card_bg"]}; border-radius: 14px;
        padding: 1rem 1.25rem; margin-bottom: 0.85rem;
        box-shadow: 0 2px 8px rgba({t["card_shadow"]},0.08);
        border: 1px solid {t["card_border"]};
        transition: box-shadow 0.2s, transform 0.15s;
    }}
    .message-card:hover {{
        box-shadow: 0 4px 14px rgba({t["card_shadow"]},0.14);
        transform: translateY(-1px);
    }}
    .message-name {{ font-weight:700; color:{t["name_color"]}; font-size:0.95rem; }}
    .message-content {{ color:#3D3D3D; font-size:0.92rem; margin:0.35rem 0; line-height:1.7; white-space:pre-wrap; word-break:break-word; }}
    .message-time {{ font-size:0.75rem; color:{t["time_color"]}; }}

    .pager-info {{ text-align:center; color:{t["pager"]}; font-size:0.88rem; margin:0.5rem 0; }}
    .section-header {{ font-size:1.1rem; font-weight:700; color:{t["section"]}; margin:1rem 0 0.5rem; }}
    .empty-hint {{ text-align:center; color:{t["empty"]}; font-size:0.95rem; padding:1.5rem; }}

    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea {{
        border-radius: 10px; border: 1.5px solid {t["input_border"]};
        background: #FAFAFA; color: #2D2D2D;
    }}
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus {{
        border-color: {t["input_focus"]};
        box-shadow: 0 0 0 2px rgba({t["input_focus_shadow"]},0.18);
    }}
    div[data-testid="stButton"] > button {{ border-radius: 10px; font-weight: 600; }}
    div[data-testid="stButton"] > button[kind="primary"] {{
        background: linear-gradient(135deg, {t["btn_grad1"]}, {t["btn_grad2"]});
        border: none; color: white;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
        background: linear-gradient(135deg, {t["btn_hover1"]}, {t["btn_hover2"]});
    }}
    section[data-testid="stSidebar"] {{ background: {t["sidebar_bg"]}; }}
    </style>
    """, unsafe_allow_html=True)


# ─── 側邊欄選單 ────────────────────────────────────────────────────────────────

def render_sidebar(theme: dict) -> None:
    """
    渲染側邊欄：留言板選單 + 管理員登入。
    選單使用 radio，選取後切換 active_board_id。
    """
    with st.sidebar:
        st.markdown(
            f"<div style='font-size:1.1rem;font-weight:800;"
            f"color:{theme['title']};margin-bottom:0.8rem;'>📋 選擇留言板</div>",
            unsafe_allow_html=True,
        )
        board_names = [b["name"] for b in BOARDS]
        current_idx = next(
            (i for i, b in enumerate(BOARDS)
             if b["id"] == st.session_state["active_board_id"]),
            0,
        )
        selected = st.radio(
            "留言板",
            board_names,
            index=current_idx,
            key="board_radio",
            label_visibility="collapsed",
        )
        new_id = next(b["id"] for b in BOARDS if b["name"] == selected)
        if new_id != st.session_state["active_board_id"]:
            st.session_state["active_board_id"] = new_id
            st.rerun()

    render_sidebar_login()


# ─── 公告區 ────────────────────────────────────────────────────────────────────

def render_announcements(board_id: str, theme: dict) -> None:
    """渲染前台公告區。"""
    with st.expander(theme["ann_expander"], expanded=True):
        anns = get_announcements(board_id)
        if not anns:
            st.markdown(
                f'<div class="empty-hint">{theme["empty_ann"]}</div>',
                unsafe_allow_html=True,
            )
            return
        for ann in anns:
            st.markdown(f"""
            <div class="announcement-card">
                <div class="announcement-title">📌 {ann.get("title", "")}</div>
                <div class="announcement-content">{ann.get("content", "")}</div>
                <div class="announcement-meta">🕐 更新時間：{format_datetime_tw(ann.get("updated_at", ""))}</div>
            </div>
            """, unsafe_allow_html=True)


# ─── 留言輸入 ──────────────────────────────────────────────────────────────────

def render_post_form(board_id: str, theme: dict) -> None:
    """渲染留言輸入表單，含防洗版與重複留言檢查。"""
    st.markdown(
        f'<div class="section-header">{theme["post_section"]}</div>',
        unsafe_allow_html=True,
    )
    with st.form(key=f"post_form_{board_id}", clear_on_submit=True):
        name = st.text_input(
            theme["name_label"],
            placeholder=theme["name_hint"],
            max_chars=30,
        )
        content = st.text_area(
            f"內容（最多 {_MAX_CONTENT_LENGTH} 字）",
            placeholder=theme["placeholder"],
            max_chars=_MAX_CONTENT_LENGTH,
            height=120,
        )
        submitted = st.form_submit_button(
            theme["post_btn"],
            use_container_width=True,
            type="primary",
        )

    if submitted:
        _handle_post(board_id, theme, name, content)


def _handle_post(board_id: str, theme: dict, name: str, content: str) -> None:
    """處理留言送出的驗證與寫入。"""
    name = sanitize_input(name)
    content = sanitize_input(content)
    emoji = theme["name_emoji"]

    if not name:
        st.warning(f"名稱不可空白喔 {emoji}")
        return
    if not content:
        st.warning("內容不可空白喔")
        return
    if len(content) > _MAX_CONTENT_LENGTH:
        st.warning(f"內容不可超過 {_MAX_CONTENT_LENGTH} 字")
        return

    # 10 秒冷卻（跨留言板共用，避免快速輪流灌版）
    last_post = st.session_state.get("last_post_time")
    if last_post is not None:
        elapsed = time.time() - last_post
        if elapsed < _POST_COOLDOWN_SECONDS:
            remaining = math.ceil(_POST_COOLDOWN_SECONDS - elapsed)
            st.warning(f"請稍後再留言（還需等待 {remaining} 秒）")
            return

    # 60 秒重複留言檢查
    if is_duplicate_message(board_id, name, content, seconds=60):
        st.warning("你剛才已經留過相同的訊息了，請稍後再試")
        return

    if create_message(board_id, name, content):
        st.session_state["last_post_time"] = time.time()
        st.session_state[f"page_{board_id}"] = 1
        st.success("已送出！")
        st.rerun()


# ─── 留言列表 ──────────────────────────────────────────────────────────────────

def render_messages(board_id: str, theme: dict) -> None:
    """渲染前台留言列表，含分頁與越界校正。"""
    st.markdown(
        f'<div class="section-header">{theme["msg_section"]}</div>',
        unsafe_allow_html=True,
    )

    page_key = f"page_{board_id}"
    total_count = get_total_message_count(board_id)
    total_pages = compute_total_pages(total_count, _PAGE_SIZE_FRONT)
    clamp_page(page_key, total_pages)
    current_page = st.session_state[page_key]

    st.markdown(
        f'<div class="pager-info">'
        f"共 {total_count} 則 ｜ 第 {current_page} 頁 / 共 {total_pages} 頁"
        f"</div>",
        unsafe_allow_html=True,
    )
    _render_pager(page_key, current_page, total_pages, f"input_{board_id}")
    st.divider()

    messages = get_messages(board_id, current_page, _PAGE_SIZE_FRONT)
    if not messages:
        st.markdown(
            f'<div class="empty-hint">{theme["empty_msg"]}</div>',
            unsafe_allow_html=True,
        )
        return

    for msg in messages:
        st.markdown(f"""
        <div class="message-card">
            <div class="message-name">{theme["name_emoji"]} {msg.get("name", "訪客")}</div>
            <div class="message-content">{msg.get("content", "")}</div>
            <div class="message-time">🕐 {format_datetime_tw(msg.get("created_at", ""))}</div>
        </div>
        """, unsafe_allow_html=True)


# ─── 分頁控制 ──────────────────────────────────────────────────────────────────

def _render_pager(
    session_key: str,
    current_page: int,
    total_pages: int,
    input_key: str,
) -> None:
    """渲染上一頁 / 跳頁 / 下一頁，number_input 使用獨立 key。"""
    col_prev, col_input, col_next = st.columns([1, 2, 1])

    with col_prev:
        if st.button("上一頁 🐾", key=f"prev_{session_key}",
                     disabled=(current_page <= 1), use_container_width=True):
            st.session_state[session_key] = current_page - 1
            st.rerun()

    with col_input:
        st.number_input(
            "頁碼", min_value=1, max_value=total_pages,
            value=current_page, step=1,
            key=input_key, label_visibility="collapsed",
        )

    with col_next:
        if st.button("下一頁 🐾", key=f"next_{session_key}",
                     disabled=(current_page >= total_pages), use_container_width=True):
            st.session_state[session_key] = current_page + 1
            st.rerun()

    input_val = st.session_state.get(input_key, 1)
    if input_val != st.session_state[session_key]:
        st.session_state[session_key] = input_val
        st.rerun()


# ─── 管理員後台 ────────────────────────────────────────────────────────────────

def render_admin_panel() -> None:
    """
    管理員後台：用 selectbox 選擇要管理的留言板，
    再切換留言管理 / 公告管理 tab。
    """
    st.divider()
    st.markdown("## 🛠️ 管理員後台")

    board_names = [b["name"] for b in BOARDS]
    selected_name = st.selectbox("選擇要管理的留言板", board_names, key="admin_board_select")
    board_id = next(b["id"] for b in BOARDS if b["name"] == selected_name)

    tab_msg, tab_ann = st.tabs(["💬 留言管理", "📢 公告管理"])
    with tab_msg:
        _render_admin_messages(board_id)
    with tab_ann:
        _render_admin_announcements(board_id)


def _render_admin_messages(board_id: str) -> None:
    """管理員留言管理頁（隱藏 / 取消隱藏 / 刪除）。"""
    page_key = f"admin_page_{board_id}"
    messages, total_count = get_admin_messages(board_id, st.session_state[page_key], _PAGE_SIZE_ADMIN)
    total_pages = compute_total_pages(total_count, _PAGE_SIZE_ADMIN)
    clamp_page(page_key, total_pages)
    current_page = st.session_state[page_key]

    st.markdown(
        f'<div class="pager-info">共 {total_count} 則 ｜ 第 {current_page} 頁 / 共 {total_pages} 頁</div>',
        unsafe_allow_html=True,
    )
    _render_pager(page_key, current_page, total_pages, f"admin_input_{board_id}")
    st.divider()

    if not messages:
        st.info("目前沒有留言")
        return

    for msg in messages:
        msg_id = msg["id"]
        is_hidden = msg.get("is_hidden", False)
        status = "🙈 隱藏中" if is_hidden else "✅ 顯示中"
        fade = "opacity:0.45;" if is_hidden else ""

        st.markdown(f"""
        <div class="message-card" style="{fade}">
            <div class="message-name">👤 {msg.get("name","訪客")}
                <span style="font-size:0.75rem;color:#888;margin-left:0.5rem;">{status}</span>
            </div>
            <div class="message-content">{msg.get("content","")}</div>
            <div class="message-time">🕐 {format_datetime_tw(msg.get("created_at",""))}</div>
        </div>
        """, unsafe_allow_html=True)

        col_hide, col_del = st.columns(2)
        with col_hide:
            if is_hidden:
                if st.button("取消隱藏 👁️", key=f"unhide_{board_id}_{msg_id}", use_container_width=True):
                    if unhide_message(board_id, msg_id):
                        st.success("已取消隱藏")
                        st.rerun()
            else:
                if st.button("隱藏 🙈", key=f"hide_{board_id}_{msg_id}", use_container_width=True):
                    if hide_message(board_id, msg_id):
                        st.success("已隱藏")
                        st.rerun()
        with col_del:
            if st.checkbox("確認刪除", key=f"confirm_{board_id}_{msg_id}"):
                if st.button("永久刪除 🗑️", key=f"delete_{board_id}_{msg_id}", use_container_width=True):
                    if delete_message(board_id, msg_id):
                        st.success("已刪除")
                        st.rerun()


def _render_admin_announcements(board_id: str) -> None:
    """管理員公告管理頁（新增 / 修改 / 刪除 / 啟停用）。"""
    with st.expander("➕ 新增公告", expanded=False):
        with st.form(f"form_add_ann_{board_id}"):
            t = st.text_input("標題", max_chars=100)
            c = st.text_area("內容", height=80)
            s = st.number_input("排序值（越小越前面）", value=0, step=1)
            if st.form_submit_button("新增 ✨", use_container_width=True):
                if not t.strip():
                    st.warning("標題不可空白")
                elif not c.strip():
                    st.warning("內容不可空白")
                elif create_announcement(board_id, t, c, int(s)):
                    st.success("新增成功")
                    st.rerun()

    st.divider()
    anns = get_all_announcements(board_id)
    if not anns:
        st.info("目前沒有公告")
        return

    for ann in anns:
        ann_id = ann["id"]
        is_active = ann.get("is_active", False)
        label = "✅ 啟用中" if is_active else "⏸️ 停用中"
        icon = "📌" if is_active else "📋"

        with st.expander(f"{icon} {ann.get('title','（無標題）')} ｜ {label}", expanded=False):
            with st.form(f"form_edit_{board_id}_{ann_id}"):
                et = st.text_input("標題", value=ann.get("title", ""), max_chars=100)
                ec = st.text_area("內容", value=ann.get("content", ""), height=80)
                es = st.number_input("排序值", value=int(ann.get("sort_order", 0)), step=1)
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.form_submit_button("儲存 💾", use_container_width=True):
                        if not et.strip():
                            st.warning("標題不可空白")
                        elif update_announcement(board_id, ann_id, et, ec, int(es)):
                            st.success("已更新")
                            st.rerun()
                with c2:
                    tlabel = "停用 ⏸️" if is_active else "啟用 ▶️"
                    if st.form_submit_button(tlabel, use_container_width=True):
                        if toggle_announcement(board_id, ann_id, not is_active):
                            st.success("已切換")
                            st.rerun()
                with c3:
                    if st.form_submit_button("刪除 🗑️", use_container_width=True):
                        if delete_announcement(board_id, ann_id):
                            st.success("已刪除")
                            st.rerun()
            st.caption(f"🕐 最後更新：{format_datetime_tw(ann.get('updated_at',''))}")


# ─── 主程式 ────────────────────────────────────────────────────────────────────

def main() -> None:
    """應用程式主入口。"""
    st.set_page_config(
        page_title="留言板",
        page_icon="💬",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    init_app_states()

    # 取得目前選擇的留言板與主題
    board_id = st.session_state["active_board_id"]
    board = BOARD_MAP[board_id]
    theme = THEMES[board["theme"]]

    inject_css(theme)
    render_sidebar(theme)

    # 訪客計數
    visitor_count = track_visitor(board_id)

    # 主標題
    st.markdown(
        f'<div class="main-title">{board["name"]}</div>'
        f'<div class="main-subtitle">歡迎來到 {board["name"]}，一起聊聊吧！</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="visitor-badge">{theme["visitor_icon"]} 累計到訪：{visitor_count} 人次</div>',
        unsafe_allow_html=True,
    )

    render_announcements(board_id, theme)
    st.divider()
    render_post_form(board_id, theme)
    st.divider()
    render_messages(board_id, theme)

    if is_admin_logged_in():
        render_admin_panel()


if __name__ == "__main__":
    main()
