"""
utils.py
--------
共用工具函式模組。
無內部依賴，可被 auth.py、firebase_service.py、app.py 安全 import。

提供：
- sanitize_input()      : 清理使用者輸入
- format_datetime_tw()  : Firestore Timestamp → 台灣時間字串
- get_client_ip_hash()  : 取得 IP 的 SHA256 雜湊（含 fallback）
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

logger = logging.getLogger(__name__)

# 台灣時區（UTC+8），使用 Python 3.9+ 內建 zoneinfo，不依賴 pytz
_TW_TZ = ZoneInfo("Asia/Taipei")


def sanitize_input(text: str) -> str:
    """
    清理使用者輸入字串。

    處理順序：
    1. strip() 去除前後空白
    2. 移除 ASCII 控制字元（保留 \\t=9、\\n=10）
    3. 保留正常標點、中文字元、emoji
    4. 不進行 HTML escape（Streamlit 已自動處理）

    Args:
        text: 原始輸入字串

    Returns:
        清理後的字串
    """
    if not isinstance(text, str):
        return ""
    text = text.strip()
    # 移除控制字元，排除 \t (0x09) 與 \n (0x0a)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return text


def format_datetime_tw(timestamp) -> str:
    """
    將 Firestore Timestamp 或 datetime 物件轉換為台灣時間（UTC+8）字串。

    使用 Python 3.9+ 內建 zoneinfo 模組，不依賴第三方 pytz。

    Args:
        timestamp: Firestore Timestamp 物件 或 datetime 物件

    Returns:
        格式化字串，例如「2024-01-15 14:30:00」；
        若轉換失敗則回傳原始 str(timestamp)。

    Examples:
        >>> ts = firestore.SERVER_TIMESTAMP  # Firestore Timestamp
        >>> format_datetime_tw(ts)
        '2024-01-15 14:30:00'
    """
    try:
        if hasattr(timestamp, "toDatetime"):
            # Firestore Timestamp 物件
            dt: datetime = timestamp.toDatetime()
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return str(timestamp)

        # 若無 tzinfo，視為 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        dt_tw = dt.astimezone(_TW_TZ)
        return dt_tw.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        logger.warning("format_datetime_tw 轉換失敗：%s", exc)
        return str(timestamp)


def get_client_ip_hash() -> str:
    """
    取得 client IP 並回傳 SHA256 雜湊值。

    在 Streamlit Community Cloud 環境中，X-Forwarded-For 等 Header
    可能為 Cloudflare proxy IP，無法保證取得真實用戶 IP。

    Fallback 優先順序：
    1. 嘗試從 st.context.headers 取得 X-Forwarded-For / X-Real-IP
    2. 若無法取得，使用 session_state["user_session_id"]（由 init_app_states 初始化的 UUID）

    禁止依賴 Streamlit 內部 API（如 _session_id），避免版本升級後報錯。
    禁止儲存原始 IP，僅儲存 SHA256 雜湊值。

    Returns:
        64 字元 SHA256 十六進位字串
    """
    ip: str = ""

    try:
        headers = st.context.headers  # Streamlit >= 1.31.0
        forwarded = headers.get("X-Forwarded-For", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        if not ip:
            ip = headers.get("X-Real-IP", "").strip()
    except Exception as exc:
        logger.debug("無法取得 request headers：%s", exc)

    if not ip:
        # fallback：使用由 app.py init_app_states() 生成的穩定 UUID
        session_uuid = st.session_state.get("user_session_id", "unknown")
        ip = f"session:{session_uuid}"

    return hashlib.sha256(ip.encode("utf-8")).hexdigest()
