"""
app.py — punto de entrada de la aplicación Streamlit.
"""
import streamlit as st

st.set_page_config(
    page_title="Rappi Ops Intelligence",
    page_icon="🟠",
    layout="wide",
)

# --- Session state initialization ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "dataframes" not in st.session_state:
    st.session_state.dataframes = None

# --- Sidebar ---
with st.sidebar:
    st.title("🟠 Rappi Ops Intelligence")
    st.divider()
    mode = st.radio(
        "Modo",
        options=["Chat", "Insights Report"],
        index=0,
    )

# --- Main content ---
if mode == "Chat":
    st.info("Modo Chat — por implementar")

elif mode == "Insights Report":
    st.info("Modo Insights Report — por implementar")
