"""
Data Pipeline — carga, limpia y enriquece los datos del Excel.

Responsabilidades:
- Leer el archivo Excel con múltiples hojas (métricas, órdenes, etc.)
- Limpiar y normalizar columnas (tipos, fechas, nulos)
- Calcular métricas derivadas (wow_change, trend_direction)
- Generar un string de esquema para el agente LLM

Funciones principales:
    load_all_data(filepath)         -> dict[str, pd.DataFrame | str]
    _load_raw_data(filepath)        -> dict[str, pd.DataFrame]
    _process_metrics(df_raw)        -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
    _process_orders(df_raw)         -> tuple[pd.DataFrame, pd.DataFrame]
    _generate_schema_string(df_metrics_wide, df_orders_wide) -> str
"""

import re

import pandas as pd
import streamlit as st

# Semanas en orden cronológico (de más antigua a más reciente)
METRIC_WEEK_COLS = [f"L{i}W_ROLL" for i in range(8, -1, -1)]  # L8W_ROLL ... L0W_ROLL
ORDER_WEEK_COLS = [f"L{i}W" for i in range(8, -1, -1)]         # L8W ... L0W

# Mapeo nombre de columna → entero de semana relativa
METRIC_WEEK_MAP = {col: -(int(re.search(r"\d+", col).group())) for col in METRIC_WEEK_COLS}
ORDER_WEEK_MAP = {col: -(int(re.search(r"\d+", col).group())) for col in ORDER_WEEK_COLS}


def _load_raw_data(filepath: str) -> dict:
    """Lee las 3 sheets del Excel y retorna dict con DataFrames crudos."""
    raw = pd.read_excel(
        filepath,
        sheet_name=["RAW_INPUT_METRICS", "RAW_ORDERS", "RAW_SUMMARY"],
        engine="openpyxl",
    )
    # Limpiar nombres de columnas (strip whitespace)
    for key in raw:
        raw[key].columns = raw[key].columns.str.strip()
    return raw


def _process_metrics(df_raw: pd.DataFrame) -> tuple:
    """
    Procesa RAW_INPUT_METRICS.

    Returns:
        metrics_wide  — DataFrame original enriquecido con trend_direction
        metrics_long  — versión melted con columnas WEEK (int) y VALUE
        trends        — filas donde trend_direction != 'stable'
    """
    df = df_raw.copy()

    # --- Trend direction (calculado sobre el wide antes del melt) ---
    def _trend(row):
        v0 = row.get("L0W_ROLL")
        v1 = row.get("L1W_ROLL")
        v2 = row.get("L2W_ROLL")
        if pd.isna(v0) or pd.isna(v1) or pd.isna(v2):
            return "stable"
        if v0 > v1 > v2:
            return "improving"
        if v0 < v1 < v2:
            return "deteriorating"
        return "stable"

    df["trend_direction"] = df.apply(_trend, axis=1)
    metrics_wide = df.copy()

    # --- Melt a formato long ---
    id_cols = ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", "METRIC"]
    week_cols_present = [c for c in METRIC_WEEK_COLS if c in df.columns]

    metrics_long = df[id_cols + week_cols_present].melt(
        id_vars=id_cols,
        value_vars=week_cols_present,
        var_name="WEEK_COL",
        value_name="VALUE",
    )
    metrics_long["WEEK"] = metrics_long["WEEK_COL"].map(METRIC_WEEK_MAP)
    metrics_long.drop(columns=["WEEK_COL"], inplace=True)
    metrics_long.sort_values(id_cols + ["WEEK"], inplace=True)
    metrics_long.reset_index(drop=True, inplace=True)

    # --- WoW change ---
    metrics_long["wow_change"] = (
        metrics_long
        .groupby(["ZONE", "METRIC"])["VALUE"]
        .pct_change(fill_method=None)
    )

    # --- Trends DataFrame (solo non-stable) ---
    trends = (
        metrics_wide[id_cols + ["trend_direction"]]
        .query("trend_direction != 'stable'")
        .reset_index(drop=True)
    )

    return metrics_wide, metrics_long, trends


def _process_orders(df_raw: pd.DataFrame) -> tuple:
    """
    Procesa RAW_ORDERS.

    Returns:
        orders_wide  — DataFrame original
        orders_long  — versión melted con columnas WEEK (int) y VALUE
    """
    df = df_raw.copy()
    id_cols = ["COUNTRY", "CITY", "ZONE", "METRIC"]
    week_cols_present = [c for c in ORDER_WEEK_COLS if c in df.columns]

    orders_wide = df.copy()

    orders_long = df[id_cols + week_cols_present].melt(
        id_vars=id_cols,
        value_vars=week_cols_present,
        var_name="WEEK_COL",
        value_name="VALUE",
    )
    orders_long["WEEK"] = orders_long["WEEK_COL"].map(ORDER_WEEK_MAP)
    orders_long.drop(columns=["WEEK_COL"], inplace=True)
    orders_long.sort_values(id_cols + ["WEEK"], inplace=True)
    orders_long.reset_index(drop=True, inplace=True)

    orders_long["wow_change"] = (
        orders_long
        .groupby(["ZONE"])["VALUE"]
        .pct_change(fill_method=None)
    )

    return orders_wide, orders_long


def _generate_schema_string(df_metrics_wide: pd.DataFrame, df_orders_wide: pd.DataFrame) -> str:
    """
    Genera un string descriptivo del schema para inyectar en el system prompt del LLM.
    Incluye columnas con tipos, valores únicos categóricos, rangos numéricos y ejemplos.
    """
    lines = []

    def _describe_df(name: str, df: pd.DataFrame, num_col_for_range: str | None = None):
        lines.append(f"## DataFrame: `{name}`")
        lines.append(f"Shape: {df.shape[0]:,} rows × {df.shape[1]} columns\n")
        lines.append("### Columns")
        for col in df.columns:
            dtype = df[col].dtype
            if dtype == object or str(dtype) == "category":
                uniq = sorted(df[col].dropna().unique().tolist())
                if len(uniq) <= 20:
                    lines.append(f"- **{col}** (str): {uniq}")
                else:
                    lines.append(f"- **{col}** (str): {len(uniq)} unique values")
            elif "float" in str(dtype) or "int" in str(dtype):
                lines.append(f"- **{col}** (numeric)")
        lines.append("")

        # Rango numérico de la semana actual
        if num_col_for_range and num_col_for_range in df.columns:
            col = num_col_for_range
            mn = df[col].min()
            mx = df[col].max()
            lines.append(f"### Range of `{col}` (current week): min={mn:.4f}, max={mx:.4f}\n")

        # Ejemplo de filas
        lines.append("### Sample rows (2)")
        lines.append(df.head(2).to_string(index=False))
        lines.append("")

    _describe_df("metrics_wide", df_metrics_wide, num_col_for_range="L0W_ROLL")
    _describe_df("orders_wide", df_orders_wide, num_col_for_range="L0W")

    lines.append("## Notes")
    lines.append("- WEEK column in long DataFrames: -8 (oldest) to 0 (current week).")
    lines.append("- wow_change: pct_change vs previous week (NaN for first available week).")
    lines.append("- trend_direction values: 'improving', 'deteriorating', 'stable'.")

    schema = "\n".join(lines)
    # Truncar a ~2000 chars si es necesario
    if len(schema) > 2000:
        schema = schema[:1997] + "..."
    return schema


@st.cache_data
def load_all_data(filepath: str = "data/rappi_data.xlsx") -> dict:
    """
    Función principal. Orquesta la carga y procesamiento de todos los datos.

    Returns dict con keys:
        "metrics_wide"  : pd.DataFrame
        "metrics_long"  : pd.DataFrame  (con columnas WEEK, VALUE, wow_change)
        "orders_wide"   : pd.DataFrame
        "orders_long"   : pd.DataFrame  (con columnas WEEK, VALUE, wow_change)
        "trends"        : pd.DataFrame  (ZONE+METRIC donde trend_direction != 'stable')
        "schema_string" : str
    """
    raw = _load_raw_data(filepath)

    metrics_wide, metrics_long, trends = _process_metrics(raw["RAW_INPUT_METRICS"])
    orders_wide, orders_long = _process_orders(raw["RAW_ORDERS"])
    schema_string = _generate_schema_string(metrics_wide, orders_wide)

    return {
        "metrics_wide": metrics_wide,
        "metrics_long": metrics_long,
        "orders_wide": orders_wide,
        "orders_long": orders_long,
        "trends": trends,
        "schema_string": schema_string,
    }


if __name__ == "__main__":
    data = load_all_data()

    for key, val in data.items():
        if isinstance(val, pd.DataFrame):
            print(f"{key:15s}: {val.shape}")
        else:
            print(f"\n{'=' * 60}")
            print("schema_string:")
            print(val)
