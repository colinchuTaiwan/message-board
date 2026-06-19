import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timezone
import uuid

MAX_NAME_LENGTH = 50
MAX_CONTENT_LENGTH = 500
DB_PATH = "messages"

st.set_page_config(page_title="留言板", page_icon="💬")


def init_firebase():
    if not firebase_admin._apps:
        firebase_config = dict(st.secrets["firebase"])

        firebase_config["private_key"] = firebase_config["private_key"].replace("\\n", "\n")

        cred = credentials.Certificate(firebase_config)

        firebase_admin.initialize_app(cred, {
            "databaseURL": st.secrets["database_url"]
        })


def now_text():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def is_admin(password):
    return password == st.secrets.get("admin_password", "")


def validate_message(name, content):
    name = name.strip()
    content = content.strip()

    if not name:
        return False, "暱稱不可為空"

    if not content:
        return False, "留言內容不可為空"

    if len(name) > MAX_NAME_LENGTH:
        return False, f"暱稱不可超過 {MAX_NAME_LENGTH} 字"

    if len(content) > MAX_CONTENT_LENGTH:
        return False, f"留言內容不可超過 {MAX_CONTENT_LENGTH} 字"

    return True, ""


def add_message(name, content):
    message_id = str(uuid.uuid4())
    current_time = now_text()

    ref = db.reference(f"{DB_PATH}/{message_id}")
    ref.set({
        "id": message_id,
        "name": name.strip(),
        "content": content.strip(),
        "created_at": current_time,
        "updated_at": current_time,
    })


def get_messages():
    ref = db.reference(DB_PATH)
    data = ref.get()

    if not data:
        return []

    messages = list(data.values())
    messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return messages


def update_message(message_id, content):
    ref = db.reference(f"{DB_PATH}/{message_id}")
    ref.update({
        "content": content.strip(),
        "updated_at": now_text(),
    })


def delete_message(message_id):
    ref = db.reference(f"{DB_PATH}/{message_id}")
    ref.delete()


init_firebase()

st.title("💬 留言板")

st.subheader("新增留言")

with st.form("add_message_form", clear_on_submit=True):
    name = st.text_input("暱稱", max_chars=MAX_NAME_LENGTH)
    content = st.text_area("留言內容", max_chars=MAX_CONTENT_LENGTH)
    submitted = st.form_submit_button("送出留言")

    if submitted:
        valid, error_message = validate_message(name, content)

        if not valid:
            st.error(error_message)
        else:
            add_message(name, content)
            st.success("留言新增成功")
            st.rerun()

st.divider()

st.subheader("管理者功能")

admin_password = st.text_input("管理者密碼", type="password")
admin_mode = is_admin(admin_password)

if admin_password and not admin_mode:
    st.error("管理者密碼錯誤")

if admin_mode:
    st.success("已啟用管理者模式")

st.divider()

st.subheader("留言列表")

messages = get_messages()

if not messages:
    st.info("目前尚無留言")
else:
    for message in messages:
        message_id = message["id"]

        with st.container(border=True):
            st.markdown(f"### {message.get('name', '')}")
            st.write(message.get("content", ""))

            st.caption(f"建立時間：{message.get('created_at', '-')}")
            st.caption(f"更新時間：{message.get('updated_at', '-')}")

            if admin_mode:
                with st.expander("編輯留言"):
                    new_content = st.text_area(
                        "修改內容",
                        value=message.get("content", ""),
                        max_chars=MAX_CONTENT_LENGTH,
                        key=f"edit_{message_id}"
                    )

                    if st.button("儲存修改", key=f"save_{message_id}"):
                        if not new_content.strip():
                            st.error("修改後內容不可為空")
                        else:
                            update_message(message_id, new_content)
                            st.success("留言已更新")
                            st.rerun()

                if st.button("刪除留言", key=f"delete_{message_id}"):
                    delete_message(message_id)
                    st.success("留言已刪除")
                    st.rerun()