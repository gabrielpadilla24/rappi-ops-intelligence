"""
app.py — punto de entrada de la aplicación Streamlit.
"""

import pandas as pd
import streamlit as st

from src.agent import ask
from src.data_pipeline import load_all_data
from utils.charts import create_chart

st.set_page_config(
    page_title="Rappi Ops Intelligence",
    page_icon="🟠",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

if "dataframes" not in st.session_state:
    with st.spinner("Cargando datos..."):
        st.session_state.dataframes = load_all_data()

dataframes = st.session_state.dataframes

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🟠 Rappi Ops Intelligence")
    st.caption("Sistema de Análisis Inteligente")
    st.divider()

    mode = st.radio(
        "Modo",
        options=["💬 Chat", "📊 Insights Report"],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("**Acerca de**")
    st.caption(
        "Powered by Gemini 2.0 Flash + Pandas. "
        "Datos: 9 países, 964 zonas, 13 métricas operacionales."
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_result(result):
    """Devuelve result si es DataFrame o tipo básico; de lo contrario lo convierte a str."""
    if isinstance(result, (pd.DataFrame, pd.Series, int, float, bool, str, list, dict, type(None))):
        return result
    return str(result)


def _build_chat_history() -> list:
    """Construye el historial en formato [{"role": ..., "content": ...}] para el agente."""
    return [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state.messages
    ]


def _render_assistant_message(msg: dict, msg_idx: int):
    """Renderiza un mensaje del asistente con gráfico, datos y sugerencias."""
    st.markdown(msg["content"])

    # Gráfico
    chart_config = msg.get("chart_config")
    result = msg.get("result")
    if chart_config and isinstance(result, pd.DataFrame):
        fig = create_chart(chart_config, result)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

    # Expander con datos crudos + descarga CSV
    if isinstance(result, pd.DataFrame) and not result.empty:
        with st.expander("📋 Ver datos"):
            st.dataframe(result.head(20), use_container_width=True)
            csv_bytes = result.to_csv(index=False).encode()
            st.download_button(
                label="⬇️ Descargar CSV",
                data=csv_bytes,
                file_name="resultado.csv",
                mime="text/csv",
                key=f"dl_{msg_idx}",
            )

    # Sugerencias como botones
    suggestions = msg.get("suggestions") or []
    if suggestions:
        cols = st.columns(len(suggestions))
        for i, suggestion in enumerate(suggestions):
            if cols[i].button(suggestion, key=f"sug_{msg_idx}_{i}"):
                st.session_state.pending_question = suggestion
                st.rerun()


# ---------------------------------------------------------------------------
# Mode: Chat
# ---------------------------------------------------------------------------

if mode == "💬 Chat":

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None

    # --- Bienvenida ---
    if not st.session_state.messages:
        with st.chat_message("assistant"):
            st.markdown(
                "👋 **¡Hola!** Soy tu asistente de análisis operacional de Rappi. "
                "Puedo ayudarte con preguntas como:\n\n"
                "- ¿Cuáles son las 5 zonas con mayor Lead Penetration?\n"
                "- Compara Perfect Orders entre zonas Wealthy y Non Wealthy en México\n"
                "- ¿Qué zonas tienen tendencias preocupantes?\n\n"
                "¿En qué puedo ayudarte?"
            )

    # --- Historial de mensajes ---
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                _render_assistant_message(msg, idx)

    # --- Captura de input (chat_input o pending_question desde sugerencia) ---
    user_input = st.chat_input("Pregunta sobre las operaciones de Rappi...")

    question = None
    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None
    elif user_input:
        question = user_input

    # --- Procesamiento de la pregunta ---
    if question:
        # Agregar mensaje de usuario
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Llamar al agente con spinner
        with st.chat_message("assistant"):
            with st.spinner("🤔 Analizando..."):
                chat_history = _build_chat_history()[:-1]  # excluir el mensaje que acabamos de agregar
                response = ask(question, chat_history, dataframes)

            answer = response.get("answer", "")
            chart_config = response.get("chart_config")
            suggestions = response.get("suggestions", [])
            result = _safe_result(response.get("result"))
            code = response.get("code", "")

            # Guardar en historial
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "chart_config": chart_config,
                "suggestions": suggestions,
                "result": result,
                "code": code,
            })

            # Renderizar respuesta inmediatamente
            _render_assistant_message(st.session_state.messages[-1], len(st.session_state.messages) - 1)

# ---------------------------------------------------------------------------
# Mode: Insights Report
# ---------------------------------------------------------------------------

elif mode == "📊 Insights Report":
    st.title("📊 Reporte de Insights Operacionales")

    if "insights_report" not in st.session_state:
        st.session_state.insights_report = None

    col1, col2 = st.columns([1, 4])
    with col1:
        generate_btn = st.button("🚀 Generar Reporte", type="primary")

    if generate_btn:
        with st.spinner("🔍 Analizando datos y generando insights... (esto puede tomar 30-60 segundos)"):
            from src.insights_engine import generate_insights_report
            report = generate_insights_report(dataframes)
            st.session_state.insights_report = report

    if st.session_state.insights_report:
        report = st.session_state.insights_report

        # Renderizar reporte markdown
        st.markdown(report["report_markdown"])

        st.divider()

        # Expanders con datos raw de cada detector
        with st.expander("🔴 Anomalías - Datos Detallados"):
            st.dataframe(report["anomalies"], use_container_width=True)

        with st.expander("📉 Tendencias - Datos Detallados"):
            st.dataframe(report["trends"], use_container_width=True)

        with st.expander("📊 Benchmarking - Datos Detallados"):
            st.dataframe(report["benchmarks"], use_container_width=True)

        with st.expander("🔗 Correlaciones - Datos Detallados"):
            st.dataframe(report["correlations"], use_container_width=True)

        with st.expander("🟢 Oportunidades - Datos Detallados"):
            st.dataframe(report["opportunities"], use_container_width=True)

        st.divider()

        # Botones de descarga
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "⬇️ Descargar Reporte (Markdown)",
                data=report["report_markdown"].encode(),
                file_name="rappi_insights_report.md",
                mime="text/markdown",
            )
        with col2:
            all_insights = pd.concat([
                report["anomalies"].assign(tipo="anomaly"),
                report["trends"].assign(tipo="trend"),
                report["benchmarks"].assign(tipo="benchmark"),
                report["opportunities"].assign(tipo="opportunity"),
            ], ignore_index=True)
            st.download_button(
                "⬇️ Descargar Datos (CSV)",
                data=all_insights.to_csv(index=False).encode(),
                file_name="rappi_insights_data.csv",
                mime="text/csv",
            )
