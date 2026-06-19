"""
firebase_service.py
-------------------
Firebase Firestore 資料存取模組。
依賴：utils

提供 Announcement 與 Message 的完整 CRUD 操作。
所有 Firestore 操作均使用 try-except 包覆，
並捕捉 FailedPrecondition（索引未建立）給出友善提示。
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st
from google.api_core.exceptions import FailedPrecondition, GoogleAPIError
from google.cloud import firestore

from utils import get_client_ip_hash, sanitize_input

logger = logging.getLogger(__name__)

# ─── Firestore 集合名稱 ────────────────────────────────────────────────────────
_COL_MESSAGES: str = "messages"
_COL_ANNOUNCEMENTS: str = "announcements"


# ─── Firebase 初始化 ───────────────────────────────────────────────────────────

@st.cache_resource
def get_db() -> firestore.Client | None:
    """
    初始化並回傳 Firestore Client。

    使用 @st.cache_resource 確保全應用生命週期只初始化一次。
    憑證來源：st.secrets["firebase"]（Service Account JSON 欄位）

    Returns:
        firestore.Client 實例；初始化失敗時回傳 None。
    """
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore as fs

        # 避免重複初始化（Streamlit hot-reload 情境）
        if not firebase_admin._apps:
            secret = dict(st.secrets["firebase"])
            cred = credentials.Certificate(secret)
            firebase_admin.initialize_app(cred)

        return fs.client()
    except Exception as exc:
        logger.exception("Firebase 初始化失敗：%s", exc)
        st.error("⚠️ Firebase 初始化失敗，請確認 Streamlit Secrets 設定是否正確。")
        return None


# ─── 內部輔助函式 ──────────────────────────────────────────────────────────────

def _handle_failed_precondition(exc: Exception, context: str = "") -> None:
    """
    統一處理 FailedPrecondition 例外（Composite Index 未建立）。

    Args:
        exc: 捕捉到的例外
        context: 發生位置說明（用於 log）
    """
    msg = (
        "⚠️ Firestore 複合索引尚未建立，請依 README 建立 Composite Index。\n"
        f"詳細錯誤：{exc}"
    )
    st.error(msg)
    logger.exception("FailedPrecondition [%s]：%s", context, exc)


def _clamp_page(session_key: str, total_pages: int) -> None:
    """
    若目前頁碼超出總頁數，強制修正為最後一頁並觸發 rerun。

    避免刪除最後一筆資料後出現空頁面報錯。
    total_pages 為 0 時強制設為 1（空集合仍顯示第 1 頁）。

    Args:
        session_key: session_state 中儲存當前頁碼的 key
        total_pages: 當前計算出的總頁數
    """
    safe_total = max(total_pages, 1)
    current = st.session_state.get(session_key, 1)
    if current > safe_total:
        st.session_state[session_key] = safe_total
        st.rerun()


# ─── Message CRUD ──────────────────────────────────────────────────────────────

def get_total_message_count(db: firestore.Client) -> int:
    """
    使用 Firestore Count API 取得可見留言總數。

    使用 collection.count().get() 而非 len(list(query.stream()))，
    避免讀取全部文件造成不必要的費用。
    需要 firebase-admin >= 6.3.0。

    Args:
        db: Firestore Client

    Returns:
        is_hidden == False 的留言總數；發生錯誤時回傳 0。
    """
    try:
        col_ref = db.collection(_COL_MESSAGES).where("is_hidden", "==", False)
        result = col_ref.count().get()
        return result[0][0].value
    except FailedPrecondition as exc:
        _handle_failed_precondition(exc, "get_total_message_count")
        return 0
    except GoogleAPIError as exc:
        logger.exception("get_total_message_count GoogleAPIError：%s", exc)
        st.error("讀取留言數失敗，請稍後再試 🐰")
        return 0
    except Exception as exc:
        logger.exception("get_total_message_count 未知錯誤：%s", exc)
        st.error("讀取留言數失敗，請稍後再試 🐰")
        return 0


def get_messages_page(
    db: firestore.Client,
    page_number: int,
    page_size: int = 50,
) -> list[dict[str, Any]]:
    """
    取得前台指定頁面的留言（僅顯示 is_hidden == False）。

    使用 offset() + limit() 分頁。
    ⚠️ 注意：offset() 跳過的文件仍會計入 Firestore 讀取費用。

    需要 Composite Index：
        messages / is_hidden (ASC) / created_at (DESC)

    Args:
        db: Firestore Client
        page_number: 頁碼（從 1 開始）
        page_size: 每頁筆數，預設 50

    Returns:
        dict 列表，每筆包含 id、name、content、created_at、is_hidden。
        發生錯誤時回傳空列表。
    """
    try:
        offset_count = (page_number - 1) * page_size
        query = (
            db.collection(_COL_MESSAGES)
            .where("is_hidden", "==", False)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .offset(offset_count)
            .limit(page_size)
        )
        docs = query.stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except FailedPrecondition as exc:
        _handle_failed_precondition(exc, "get_messages_page")
        return []
    except GoogleAPIError as exc:
        logger.exception("get_messages_page GoogleAPIError：%s", exc)
        st.error("讀取留言失敗，請稍後再試 🐰")
        return []
    except Exception as exc:
        logger.exception("get_messages_page 未知錯誤：%s", exc)
        st.error("讀取留言失敗，請稍後再試 🐰")
        return []


def get_admin_messages_page(
    db: firestore.Client,
    page_number: int,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """
    取得管理員後台指定頁面的留言（含隱藏留言）。

    同時回傳總筆數供計算總頁數用。

    Args:
        db: Firestore Client
        page_number: 頁碼（從 1 開始）
        page_size: 每頁筆數，預設 20

    Returns:
        (留言列表, 總筆數) 的 tuple；發生錯誤時回傳 ([], 0)。
    """
    try:
        # 取得總數（不含 is_hidden 篩選，管理員看全部）
        total_count_result = db.collection(_COL_MESSAGES).count().get()
        total_count: int = total_count_result[0][0].value

        offset_count = (page_number - 1) * page_size
        query = (
            db.collection(_COL_MESSAGES)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .offset(offset_count)
            .limit(page_size)
        )
        docs = query.stream()
        messages = [{"id": doc.id, **doc.to_dict()} for doc in docs]
        return messages, total_count
    except FailedPrecondition as exc:
        _handle_failed_precondition(exc, "get_admin_messages_page")
        return [], 0
    except GoogleAPIError as exc:
        logger.exception("get_admin_messages_page GoogleAPIError：%s", exc)
        st.error("讀取留言失敗，請稍後再試 🐰")
        return [], 0
    except Exception as exc:
        logger.exception("get_admin_messages_page 未知錯誤：%s", exc)
        st.error("讀取留言失敗，請稍後再試 🐰")
        return [], 0


def is_duplicate_message(
    db: firestore.Client,
    name: str,
    content: str,
    seconds: int = 60,
) -> bool:
    """
    檢查是否在指定秒數內有相同暱稱與相同內容的留言（防洗版）。

    需要 Composite Index：
        messages / name (ASC) / content (ASC) / created_at (ASC)

    Args:
        db: Firestore Client
        name: 留言者暱稱
        content: 留言內容
        seconds: 檢查時間窗口（秒），預設 60

    Returns:
        True 表示存在重複留言，False 表示不重複或發生錯誤（保守放行）。
    """
    try:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)
        query = (
            db.collection(_COL_MESSAGES)
            .where("name", "==", name)
            .where("content", "==", content)
            .where("created_at", ">=", cutoff)
            .limit(1)
        )
        docs = list(query.stream())
        return len(docs) > 0
    except FailedPrecondition as exc:
        _handle_failed_precondition(exc, "is_duplicate_message")
        return False
    except Exception as exc:
        logger.exception("is_duplicate_message 錯誤（保守放行）：%s", exc)
        return False


def create_message(
    db: firestore.Client,
    name: str,
    content: str,
) -> bool:
    """
    建立新留言。

    會先呼叫 sanitize_input() 清理輸入，並記錄 IP hash。

    Args:
        db: Firestore Client
        name: 留言者暱稱（已驗證非空）
        content: 留言內容（已驗證非空）

    Returns:
        True 表示建立成功，False 表示失敗。
    """
    try:
        clean_name = sanitize_input(name)
        clean_content = sanitize_input(content)
        ip_hash = get_client_ip_hash()
        now = datetime.now(tz=timezone.utc)

        db.collection(_COL_MESSAGES).add({
            "name": clean_name,
            "content": clean_content,
            "created_at": now,
            "updated_at": now,
            "is_hidden": False,
            "ip_hash": ip_hash,
        })
        logger.info("新增留言成功，暱稱：%s", clean_name)
        return True
    except GoogleAPIError as exc:
        logger.exception("create_message GoogleAPIError：%s", exc)
        st.error("留言送出失敗，請稍後再試 🐰")
        return False
    except Exception as exc:
        logger.exception("create_message 未知錯誤：%s", exc)
        st.error("留言送出失敗，請稍後再試 🐰")
        return False


def hide_message(db: firestore.Client, message_id: str) -> bool:
    """
    將指定留言設為隱藏。

    Args:
        db: Firestore Client
        message_id: 留言文件 ID

    Returns:
        True 表示成功，False 表示失敗。
    """
    return _update_message_field(db, message_id, {"is_hidden": True}, "hide_message")


def unhide_message(db: firestore.Client, message_id: str) -> bool:
    """
    將指定留言取消隱藏。

    Args:
        db: Firestore Client
        message_id: 留言文件 ID

    Returns:
        True 表示成功，False 表示失敗。
    """
    return _update_message_field(db, message_id, {"is_hidden": False}, "unhide_message")


def delete_message(db: firestore.Client, message_id: str) -> bool:
    """
    永久刪除指定留言。

    Args:
        db: Firestore Client
        message_id: 留言文件 ID

    Returns:
        True 表示成功，False 表示失敗。
    """
    try:
        db.collection(_COL_MESSAGES).document(message_id).delete()
        logger.info("刪除留言：%s", message_id)
        return True
    except GoogleAPIError as exc:
        logger.exception("delete_message GoogleAPIError：%s", exc)
        st.error("刪除留言失敗，請稍後再試 🐰")
        return False
    except Exception as exc:
        logger.exception("delete_message 未知錯誤：%s", exc)
        st.error("刪除留言失敗，請稍後再試 🐰")
        return False


def _update_message_field(
    db: firestore.Client,
    message_id: str,
    fields: dict[str, Any],
    context: str,
) -> bool:
    """
    更新留言指定欄位（內部輔助函式）。

    Args:
        db: Firestore Client
        message_id: 留言文件 ID
        fields: 要更新的欄位字典
        context: 呼叫來源說明（用於 log）

    Returns:
        True 表示成功，False 表示失敗。
    """
    try:
        fields["updated_at"] = datetime.now(tz=timezone.utc)
        db.collection(_COL_MESSAGES).document(message_id).update(fields)
        return True
    except GoogleAPIError as exc:
        logger.exception("%s GoogleAPIError：%s", context, exc)
        st.error("操作失敗，請稍後再試 🐰")
        return False
    except Exception as exc:
        logger.exception("%s 未知錯誤：%s", context, exc)
        st.error("操作失敗，請稍後再試 🐰")
        return False


# ─── Announcement CRUD ─────────────────────────────────────────────────────────

def get_active_announcements(db: firestore.Client) -> list[dict[str, Any]]:
    """
    取得所有啟用中的公告，依 sort_order 升序排列。

    Args:
        db: Firestore Client

    Returns:
        dict 列表；發生錯誤時回傳空列表。
    """
    try:
        query = (
            db.collection(_COL_ANNOUNCEMENTS)
            .where("is_active", "==", True)
            .order_by("sort_order")
        )
        docs = query.stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except FailedPrecondition as exc:
        _handle_failed_precondition(exc, "get_active_announcements")
        return []
    except Exception as exc:
        logger.exception("get_active_announcements 錯誤：%s", exc)
        st.error("讀取公告失敗，請稍後再試 🐰")
        return []


def get_all_announcements(db: firestore.Client) -> list[dict[str, Any]]:
    """
    取得所有公告（含停用），供管理員後台使用。

    Args:
        db: Firestore Client

    Returns:
        dict 列表；發生錯誤時回傳空列表。
    """
    try:
        docs = (
            db.collection(_COL_ANNOUNCEMENTS)
            .order_by("sort_order")
            .stream()
        )
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except Exception as exc:
        logger.exception("get_all_announcements 錯誤：%s", exc)
        st.error("讀取公告列表失敗，請稍後再試 🐰")
        return []


def create_announcement(
    db: firestore.Client,
    title: str,
    content: str,
    sort_order: int = 0,
) -> bool:
    """
    新增公告。

    Args:
        db: Firestore Client
        title: 公告標題
        content: 公告內容
        sort_order: 排序值（數字越小越前面），預設 0

    Returns:
        True 表示成功，False 表示失敗。
    """
    try:
        now = datetime.now(tz=timezone.utc)
        db.collection(_COL_ANNOUNCEMENTS).add({
            "title": sanitize_input(title),
            "content": sanitize_input(content),
            "is_active": True,
            "sort_order": sort_order,
            "created_at": now,
            "updated_at": now,
        })
        return True
    except Exception as exc:
        logger.exception("create_announcement 錯誤：%s", exc)
        st.error("新增公告失敗，請稍後再試 🐰")
        return False


def update_announcement(
    db: firestore.Client,
    ann_id: str,
    title: str,
    content: str,
    sort_order: int,
) -> bool:
    """
    更新公告內容與排序。

    Args:
        db: Firestore Client
        ann_id: 公告文件 ID
        title: 新標題
        content: 新內容
        sort_order: 新排序值

    Returns:
        True 表示成功，False 表示失敗。
    """
    try:
        db.collection(_COL_ANNOUNCEMENTS).document(ann_id).update({
            "title": sanitize_input(title),
            "content": sanitize_input(content),
            "sort_order": sort_order,
            "updated_at": datetime.now(tz=timezone.utc),
        })
        return True
    except Exception as exc:
        logger.exception("update_announcement 錯誤：%s", exc)
        st.error("更新公告失敗，請稍後再試 🐰")
        return False


def delete_announcement(db: firestore.Client, ann_id: str) -> bool:
    """
    永久刪除公告。

    Args:
        db: Firestore Client
        ann_id: 公告文件 ID

    Returns:
        True 表示成功，False 表示失敗。
    """
    try:
        db.collection(_COL_ANNOUNCEMENTS).document(ann_id).delete()
        return True
    except Exception as exc:
        logger.exception("delete_announcement 錯誤：%s", exc)
        st.error("刪除公告失敗，請稍後再試 🐰")
        return False


def toggle_announcement(
    db: firestore.Client,
    ann_id: str,
    is_active: bool,
) -> bool:
    """
    切換公告的啟用 / 停用狀態。

    Args:
        db: Firestore Client
        ann_id: 公告文件 ID
        is_active: True 為啟用，False 為停用

    Returns:
        True 表示成功，False 表示失敗。
    """
    try:
        db.collection(_COL_ANNOUNCEMENTS).document(ann_id).update({
            "is_active": is_active,
            "updated_at": datetime.now(tz=timezone.utc),
        })
        return True
    except Exception as exc:
        logger.exception("toggle_announcement 錯誤：%s", exc)
        st.error("切換公告狀態失敗，請稍後再試 🐰")
        return False


# ─── 分頁輔助 ─────────────────────────────────────────────────────────────────

def compute_total_pages(total_count: int, page_size: int) -> int:
    """
    計算總頁數，最少為 1。

    Args:
        total_count: 總筆數
        page_size: 每頁筆數

    Returns:
        總頁數（至少為 1）
    """
    if page_size <= 0:
        return 1
    return max(math.ceil(total_count / page_size), 1)


def clamp_page(session_key: str, total_pages: int) -> None:
    """
    若目前頁碼超出總頁數，強制修正並觸發 rerun（公開介面）。

    Args:
        session_key: session_state 中儲存當前頁碼的 key
        total_pages: 當前計算出的總頁數
    """
    _clamp_page(session_key, total_pages)
