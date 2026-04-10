"""
Charts — genera gráficos Plotly a partir de configuraciones estructuradas.

Responsabilidades:
- Recibir un diccionario de configuración de gráfico generado por el agente
- Construir y retornar una figura Plotly lista para renderizar en Streamlit
- Soportar tipos: line, bar, scatter, pie, heatmap

Funciones principales:
    create_chart(chart_config, df)  -> plotly.graph_objects.Figure | None
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_LAYOUT = dict(
    template="plotly_white",
    height=450,
    title_x=0.5,
    margin=dict(l=40, r=40, t=60, b=40),
)


def create_chart(chart_config: dict, df: pd.DataFrame) -> go.Figure | None:
    """
    Crea un gráfico Plotly basado en la configuración del agente.

    chart_config keys:
        type   : "line" | "bar" | "scatter" | "heatmap" | "pie"
        title  : str
        x      : str  — nombre de columna para el eje X (o names en pie)
        y      : str  — nombre de columna para el eje Y (o values en pie)
        color  : str | None — columna para agrupar/colorear
        labels : dict — (opcional) renombrar ejes
    """
    try:
        chart_type = chart_config.get("type", "none")
        if chart_type == "none" or not isinstance(df, pd.DataFrame) or df.empty:
            return None

        title = chart_config.get("title", "")
        x = chart_config.get("x")
        y = chart_config.get("y")
        color = chart_config.get("color")
        labels = chart_config.get("labels") or {}

        # Validar que color exista en el df
        cols = set(df.columns)
        if color and color not in cols:
            color = None

        # Para bar charts con muchas filas, limitar a 30 para legibilidad
        plot_df = df.head(30) if chart_type == "bar" and len(df) > 50 else df

        common = dict(title=title, labels=labels)

        if chart_type == "line":
            fig = px.line(plot_df, x=x, y=y, color=color, **common)

        elif chart_type == "bar":
            fig = px.bar(plot_df, x=x, y=y, color=color, **common)

        elif chart_type == "scatter":
            fig = px.scatter(plot_df, x=x, y=y, color=color, **common)

        elif chart_type == "pie":
            fig = px.pie(plot_df, names=x, values=y, title=title)

        elif chart_type == "heatmap":
            fig = px.density_heatmap(plot_df, x=x, y=y, **common)

        else:
            return None

        fig.update_layout(**_LAYOUT)
        return fig

    except Exception as exc:
        print(f"[charts] create_chart → error: {exc}")
        return None
