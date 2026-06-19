"""
auth.py
-------
管理員認證模組。
依賴：utils（間接）

提供：
- render_sidebar_login()  : 側邊欄登入 / 登出介面
- check_admin_login()     : 帳密驗證含失敗鎖定
- is_admin_logged_in()    : 檢查登入狀態
"""

import logging
import time

import streamlit as st

logger = logging.getLogger(__name__)

# 最大連續失敗次數
_MAX_FAILURES: int = 5
# 鎖定秒數
_LOCK_SECONDS: int = 60


def is_admin_logged_in() -> bool:
    """
    回傳目前管理員登入狀態。

    Returns:
        True 表示已登入，False 表示未登入。
    """
    return bool(st.session_state.get("admin_logged_in", False))


def _get_remaining_lock_seconds() -> float:
    """
    計算帳號目前的鎖定剩餘秒數。

    Returns:
        剩餘鎖定秒數；若未鎖定則回傳 0。
    """
    locked_until: float | None = st.session_state.get("admin_locked_until")
    if locked_until is None:
        return 0.0
    remaining = locked_until - time.time()
    return max(remaining, 0.0)


def check_admin_login(username: str, password: str) -> bool:
    """
    驗證管理員帳號與密碼，含失敗鎖定機制。

    規則：
    - 連續失敗 5 次後鎖定 60 秒
    - 鎖定期間顯示剩餘秒數
    - 登入成功後重置失敗計數

    帳密來源：st.secrets["admin"]["username"] / ["password"]

    Args:
        username: 使用者輸入的帳號
        password: 使用者輸入的密碼

    Returns:
        True 表示驗證成功，False 表示失敗或鎖定中。
    """
    remaining = _get_remaining_lock_seconds()
    if remaining > 0:
        st.error(f"登入失敗次數過多，請稍後再試 🔒（剩餘 {int(remaining)} 秒）")
        return False

    try:
        correct_user: str = st.secrets["admin"]["username"]
        correct_pass: str = st.secrets["admin"]["password"]
    except KeyError:
        st.error("⚠️ 尚未設定管理員帳密，請在 Streamlit Secrets 中設定 [admin] 區塊。")
        logger.error("st.secrets 缺少 [admin] 設定")
        return False

    if username == correct_user and password == correct_pass:
        # 登入成功，重置計數
        st.session_state["admin_login_failures"] = 0
        st.session_state["admin_locked_until"] = None
        st.session_state["admin_logged_in"] = True
        logger.info("管理員登入成功")
        return True

    # 登入失敗
    st.session_state["admin_login_failures"] = (
        st.session_state.get("admin_login_failures", 0) + 1
    )
    failures: int = st.session_state["admin_login_failures"]
    logger.warning("管理員登入失敗，累計 %d 次", failures)

    if failures >= _MAX_FAILURES:
        st.session_state["admin_locked_until"] = time.time() + _LOCK_SECONDS
        st.session_state["admin_login_failures"] = 0
        st.error(f"連續失敗 {_MAX_FAILURES} 次，帳號已鎖定 {_LOCK_SECONDS} 秒 🔒")
    else:
        remaining_attempts = _MAX_FAILURES - failures
        st.error(f"帳號或密碼錯誤 🐰（還剩 {remaining_attempts} 次機會）")

    return False


def render_sidebar_login() -> None:
    """
    在 st.sidebar 渲染管理員登入 / 登出介面。

    已登入時顯示登出按鈕；
    未登入時顯示帳密輸入欄位與登入按鈕。
    """
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🔐 管理員區域")

        if is_admin_logged_in():
            st.success("✅ 已登入管理員")
            if st.button("登出 👋", key="btn_logout", use_container_width=True):
                st.session_state["admin_logged_in"] = False
                st.session_state["admin_login_failures"] = 0
                st.session_state["admin_locked_until"] = None
                logger.info("管理員已登出")
                st.rerun()
        else:
            # 顯示鎖定倒數（若正在鎖定）
            remaining = _get_remaining_lock_seconds()
            if remaining > 0:
                st.warning(f"🔒 帳號鎖定中，請等待 {int(remaining)} 秒")
                return

            with st.form(key="admin_login_form"):
                username = st.text_input(
                    "帳號",
                    placeholder="請輸入管理員帳號",
                    autocomplete="username",
                )
                password = st.text_input(
                    "密碼",
                    type="password",
                    placeholder="請輸入密碼",
                    autocomplete="current-password",
                )
                submitted = st.form_submit_button(
                    "管理員登入 🔐",
                    use_container_width=True,
                )

            if submitted:
                if not username or not password:
                    st.error("請填寫帳號與密碼 🐰")
                elif check_admin_login(username, password):
                    st.success("登入成功 ✨")
                    st.rerun()
