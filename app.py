import streamlit as st

from till import db, ui, views

st.set_page_config(page_title="Till", page_icon=":material/sell:", layout="wide", initial_sidebar_state="collapsed")
db.init()
ui.inject()

if "user_id" not in st.session_state:
    views.auth_page()
    st.stop()

if db.get_business(st.session_state["user_id"]) is None:
    views.onboarding()
    st.stop()

pages = {
    "home": st.Page(views.home, title="Home", icon=":material/home:", url_path="home", default=True),
    "coach": st.Page(views.coach, title="Ask Till", icon=":material/forum:", url_path="ask"),
    "plan": st.Page(views.plan, title="Plan", icon=":material/checklist:", url_path="plan"),
    "stuff": st.Page(views.stuff, title="My stuff", icon=":material/inventory_2:", url_path="my-stuff"),
}
st.session_state["pages"] = pages
navigation = st.navigation(list(pages.values()), position="hidden")
if st.session_state.pop("fresh_login", False):
    st.switch_page(pages["home"])
with st.container(horizontal=True, key="topbar"):
    st.markdown(ui.logo(), unsafe_allow_html=True)
    for page in pages.values():
        st.page_link(page, width="content")
navigation.run()
