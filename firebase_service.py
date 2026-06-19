"""
firebase_service.py
-------------------
Firebase Realtime Database 資料存取模組。
支援多個留言板，每個板有獨立的 DB 路徑。
依賴：utils
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import firebase_admin
import streamlit as st
from firebase_admin import credentials
from firebase_admin import db as firebase_db

from utils import get_client_ip_hash, sanitize_input

logger = logging.getLogger(__name__)

# ─── 留言板設定 ────────────────────────────────────────────────────────────────

BOARDS: list[dict] = [
    {
        "id":       "homeboard",
        "name":     "🏠 可愛的家",
        "db_path":  "homeboard",
        "theme":    "warm",
    },
    {
        "id":       "momboard",
        "name":     "👩 媽媽的大小事",
        "db_path":  "momboard",
        "theme":    "rose",
    },
    {
        "id":       "travelboard",
        "name":     "✈️ 旅遊討論區",
        "db_path":  "travelboard",
        "theme":    "sky",
    },
    {
        "id":       "pokeboard",
        "name":     "🎮 寶可夢討論區",
        "db_path":  "pokeboard",
        "theme":    "poke",
    },
    {
        "id":       "chatboard",
        "name":     "💬 閒聊區",
        "db_path":  "chatboard",
        "theme":    "mint",
    },
    {
        "id":       "studyboard",
        "name":     "📚 學習專區",
        "db_path":  "studyboard",
        "theme":    "indigo",
    },
    {
        "id":       "aiboard",
        "name":     "🤖 AI學習區",
        "db_path":  "aiboard",
        "theme":    "tech",
    },
]

# id → board dict 查找表
BOARD_MAP: dict[str, dict] = {b["id"]: b for b in BOARDS}


def get_paths(board_id: str) -> tuple[str, str, str]:
    """
    回傳指定留言板的 (messages路徑, announcements路徑, visitors路徑)。

    Args:
        board_id: 留言板 ID

    Returns:
        (messages_path, announcements_path, visitors_path)
    """
    db_path = BOARD_MAP[board_id]["db_path"]
    return (
        f"{db_path}/messages",
        f"{db_path}/announcements",
        f"{db_path}/visitor_counts",
    )


# ─── Firebase 初始化 ───────────────────────────────────────────────────────────

@st.cache_resource
def init_firebase():
    """
    初始化 Firebase Admin SDK（Realtime Database）。
    cache_resource 確保全生命週期只初始化一次。
    """
    if firebase_admin._apps:
        return firebase_admin.get_app()

    s = st.secrets["firebase"]
    cert_dict = {
        "type":                        s["type"],
        "project_id":                  s["project_id"],
        "private_key_id":              s["private_key_id"],
        "private_key":                 s["private_key"].replace("\\n", "\n"),
        "client_email":                s["client_email"],
        "client_id":                   s["client_id"],
        "auth_uri":                    s["auth_uri"],
        "token_uri":                   s["token_uri"],
        "client_x509_cert_url":        s.get("client_x509_cert_url", ""),
        "auth_provider_x509_cert_url": s.get("auth_provider_x509_cert_url", ""),
    }
    cred = credentials.Certificate(cert_dict)
    return firebase_admin.initialize_app(
        cred, {"databaseURL": s["database_url"]}
    )


def _get_db() -> Any:
    """確保 Firebase 已初始化並回傳 db 模組。"""
    init_firebase()
    return firebase_db


# ─── 訪客計數 ──────────────────────────────────────────────────────────────────

def track_visitor(board_id: str) -> int:
    """
    原子累加指定留言板的訪客人數。
    同一 Session 每個板只計數一次。

    Args:
        board_id: 留言板 ID

    Returns:
        目前累計訪客數；失敗時回傳 0。
    """
    counted_key = f"counted_{board_id}"
    _, _, visitors_path = get_paths(board_id)
    try:
        db = _get_db()
        ref = db.reference(f"{visitors_path}/main")

        def increment(current):
            return (current or 0) + 1

        if not st.session_state.get(counted_key):
            count = ref.transaction(increment)
            st.session_state[counted_key] = True
            return count or 0
        else:
            v = ref.get()
            return v if v is not None else 0
    except Exception as exc:
        logger.warning("track_visitor[%s] 失敗：%s", board_id, exc)
        return 0


# ─── 留言 CRUD ─────────────────────────────────────────────────────────────────

def get_total_message_count(board_id: str) -> int:
    """取得指定留言板可見留言總數（is_hidden == False）。"""
    try:
        messages_path, _, _ = get_paths(board_id)
        data = _get_db().reference(messages_path).get(shallow=False)
        if not data:
            return 0
        return sum(
            1 for v in data.values()
            if isinstance(v, dict) and not v.get("is_hidden", False)
        )
    except Exception as exc:
        logger.warning("get_total_message_count[%s] 失敗：%s", board_id, exc)
        return 0


def get_messages(
    board_id: str,
    page_number: int,
    page_size: int = 50,
) -> list[dict]:
    """
    取得指定留言板前台留言列表（is_hidden == False），依 created_at 降序。

    Args:
        board_id: 留言板 ID
        page_number: 頁碼（從 1 開始）
        page_size: 每頁筆數

    Returns:
        dict 列表。
    """
    try:
        messages_path, _, _ = get_paths(board_id)
        data = _get_db().reference(messages_path).get()
        if not data:
            return []

        messages = [
            {"id": k, **v}
            for k, v in data.items()
            if isinstance(v, dict) and not v.get("is_hidden", False)
        ]
        messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        start = (page_number - 1) * page_size
        return messages[start: start + page_size]
    except Exception as exc:
        logger.exception("get_messages[%s] 失敗：%s", board_id, exc)
        st.error("讀取留言失敗，請稍後再試")
        return []


def get_admin_messages(
    board_id: str,
    page_number: int,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """取得管理員後台指定留言板留言列表（含隱藏），依 created_at 降序。"""
    try:
        messages_path, _, _ = get_paths(board_id)
        data = _get_db().reference(messages_path).get()
        if not data:
            return [], 0

        messages = [
            {"id": k, **v}
            for k, v in data.items()
            if isinstance(v, dict)
        ]
        messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(messages)
        start = (page_number - 1) * page_size
        return messages[start: start + page_size], total
    except Exception as exc:
        logger.exception("get_admin_messages[%s] 失敗：%s", board_id, exc)
        st.error("讀取留言失敗，請稍後再試")
        return [], 0


def is_duplicate_message(
    board_id: str,
    name: str,
    content: str,
    seconds: int = 60,
) -> bool:
    """檢查指定留言板 60 秒內是否有相同暱稱 + 相同內容的留言。"""
    try:
        messages_path, _, _ = get_paths(board_id)
        data = _get_db().reference(messages_path).get()
        if not data:
            return False

        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)
        ).isoformat()

        for v in data.values():
            if not isinstance(v, dict):
                continue
            if (
                v.get("name") == name
                and v.get("content") == content
                and v.get("created_at", "") >= cutoff
            ):
                return True
        return False
    except Exception as exc:
        logger.warning("is_duplicate_message[%s] 失敗（保守放行）：%s", board_id, exc)
        return False


def create_message(board_id: str, name: str, content: str) -> bool:
    """
    新增留言至指定留言板。

    Args:
        board_id: 留言板 ID
        name: 暱稱
        content: 留言內容

    Returns:
        True 表示成功。
    """
    try:
        messages_path, _, _ = get_paths(board_id)
        ip_hash = get_client_ip_hash()
        now = datetime.now(tz=timezone.utc).isoformat()

        _get_db().reference(messages_path).push({
            "name":       sanitize_input(name),
            "content":    sanitize_input(content),
            "created_at": now,
            "updated_at": now,
            "is_hidden":  False,
            "ip_hash":    ip_hash,
        })
        return True
    except Exception as exc:
        logger.exception("create_message[%s] 失敗：%s", board_id, exc)
        st.error("留言送出失敗，請稍後再試")
        return False


def hide_message(board_id: str, message_id: str) -> bool:
    """隱藏指定留言板的指定留言。"""
    return _update_message(board_id, message_id, {"is_hidden": True})


def unhide_message(board_id: str, message_id: str) -> bool:
    """取消隱藏指定留言板的指定留言。"""
    return _update_message(board_id, message_id, {"is_hidden": False})


def delete_message(board_id: str, message_id: str) -> bool:
    """永久刪除指定留言板的指定留言。"""
    try:
        messages_path, _, _ = get_paths(board_id)
        _get_db().reference(f"{messages_path}/{message_id}").delete()
        return True
    except Exception as exc:
        logger.exception("delete_message[%s] 失敗：%s", board_id, exc)
        st.error("刪除失敗，請稍後再試")
        return False


def _update_message(board_id: str, message_id: str, fields: dict) -> bool:
    """更新留言欄位（內部輔助）。"""
    try:
        messages_path, _, _ = get_paths(board_id)
        fields["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        _get_db().reference(f"{messages_path}/{message_id}").update(fields)
        return True
    except Exception as exc:
        logger.exception("_update_message[%s] 失敗：%s", board_id, exc)
        st.error("操作失敗，請稍後再試")
        return False


# ─── 公告 CRUD ─────────────────────────────────────────────────────────────────

def get_announcements(board_id: str) -> list[dict]:
    """取得指定留言板前台公告（is_active == True），依 sort_order 升序。"""
    try:
        _, announcements_path, _ = get_paths(board_id)
        data = _get_db().reference(announcements_path).get()
        if not data:
            return []
        anns = [
            {"id": k, **v}
            for k, v in data.items()
            if isinstance(v, dict) and v.get("is_active", False)
        ]
        anns.sort(key=lambda x: x.get("sort_order", 0))
        return anns
    except Exception as exc:
        logger.exception("get_announcements[%s] 失敗：%s", board_id, exc)
        st.error("讀取公告失敗，請稍後再試")
        return []


def get_all_announcements(board_id: str) -> list[dict]:
    """取得指定留言板所有公告（含停用），供管理員使用。"""
    try:
        _, announcements_path, _ = get_paths(board_id)
        data = _get_db().reference(announcements_path).get()
        if not data:
            return []
        anns = [{"id": k, **v} for k, v in data.items() if isinstance(v, dict)]
        anns.sort(key=lambda x: x.get("sort_order", 0))
        return anns
    except Exception as exc:
        logger.exception("get_all_announcements[%s] 失敗：%s", board_id, exc)
        st.error("讀取公告列表失敗，請稍後再試")
        return []


def create_announcement(
    board_id: str, title: str, content: str, sort_order: int = 0
) -> bool:
    """新增公告至指定留言板。"""
    try:
        _, announcements_path, _ = get_paths(board_id)
        now = datetime.now(tz=timezone.utc).isoformat()
        _get_db().reference(announcements_path).push({
            "title":      sanitize_input(title),
            "content":    sanitize_input(content),
            "is_active":  True,
            "sort_order": sort_order,
            "created_at": now,
            "updated_at": now,
        })
        return True
    except Exception as exc:
        logger.exception("create_announcement[%s] 失敗：%s", board_id, exc)
        st.error("新增公告失敗，請稍後再試")
        return False


def update_announcement(
    board_id: str, ann_id: str, title: str, content: str, sort_order: int
) -> bool:
    """修改指定留言板的公告內容與排序。"""
    try:
        _, announcements_path, _ = get_paths(board_id)
        _get_db().reference(f"{announcements_path}/{ann_id}").update({
            "title":      sanitize_input(title),
            "content":    sanitize_input(content),
            "sort_order": sort_order,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        })
        return True
    except Exception as exc:
        logger.exception("update_announcement[%s] 失敗：%s", board_id, exc)
        st.error("更新公告失敗，請稍後再試")
        return False


def delete_announcement(board_id: str, ann_id: str) -> bool:
    """永久刪除指定留言板的公告。"""
    try:
        _, announcements_path, _ = get_paths(board_id)
        _get_db().reference(f"{announcements_path}/{ann_id}").delete()
        return True
    except Exception as exc:
        logger.exception("delete_announcement[%s] 失敗：%s", board_id, exc)
        st.error("刪除公告失敗，請稍後再試")
        return False


def toggle_announcement(board_id: str, ann_id: str, is_active: bool) -> bool:
    """切換指定留言板的公告啟用狀態。"""
    try:
        _, announcements_path, _ = get_paths(board_id)
        _get_db().reference(f"{announcements_path}/{ann_id}").update({
            "is_active":  is_active,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        })
        return True
    except Exception as exc:
        logger.exception("toggle_announcement[%s] 失敗：%s", board_id, exc)
        st.error("切換公告狀態失敗，請稍後再試")
        return False


# ─── 分頁輔助 ──────────────────────────────────────────────────────────────────

def compute_total_pages(total_count: int, page_size: int) -> int:
    """計算總頁數，最少為 1。"""
    if page_size <= 0:
        return 1
    return max(math.ceil(total_count / page_size), 1)


def clamp_page(session_key: str, total_pages: int) -> None:
    """
    若當前頁碼超出總頁數，強制修正並觸發 rerun。
    防止刪除最後一筆後出現空頁面。
    """
    safe_total = max(total_pages, 1)
    if st.session_state.get(session_key, 1) > safe_total:
        st.session_state[session_key] = safe_total
        st.rerun()
