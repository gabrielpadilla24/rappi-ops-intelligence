"""
Insights Engine — motor de detección automática de insights operacionales.

Responsabilidades:
- Analizar los dataframes en busca de anomalías estadísticas (WoW > ±10%)
- Detectar tendencias positivas y negativas de 3+ semanas consecutivas
- Comparar métricas contra benchmarks del grupo (país + tipo de zona)
- Identificar correlaciones relevantes entre métricas
- Detectar oportunidades en zonas High Priority con mejora sostenida
- Sintetizar todos los hallazgos en un reporte ejecutivo via LLM (Groq)

Funciones principales:
    generate_insights_report(dataframes)             -> dict
    _detect_anomalies(metrics_wide)                  -> pd.DataFrame
    _detect_trends(metrics_wide)                     -> pd.DataFrame
    _detect_benchmarks(metrics_wide)                 -> pd.DataFrame
    _detect_correlations(metrics_wide)               -> pd.DataFrame
    _detect_opportunities(metrics_wide)              -> pd.DataFrame
    _format_insights_for_llm(...)                    -> str
    _synthesize_report(insights_text)                -> str
"""

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from groq import Groq

from prompts.insights_prompt import INSIGHTS_PROMPT_TEMPLATE

load_dotenv()

_client = Groq()
_MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_anomalies(metrics_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta zonas con cambio WoW (L1W→L0W) > ±10% en cualquier métrica.
    Severity: abs > 30% = high, abs > 20% = medium, else low.
    Retorna top 30 por abs(change_pct) descendente.
    """
    df = metrics_wide[["COUNTRY", "CITY", "ZONE", "METRIC", "L1W_ROLL", "L0W_ROLL"]].dropna(
        subset=["L1W_ROLL", "L0W_ROLL"]
    ).copy()

    # Evitar división por cero
    df["change_pct"] = np.where(
        df["L1W_ROLL"] == 0,
        np.nan,
        (df["L0W_ROLL"] - df["L1W_ROLL"]) / df["L1W_ROLL"].abs() * 100,
    )
    df = df.dropna(subset=["change_pct"])
    df = df[df["change_pct"].abs() > 10].copy()

    df["severity"] = pd.cut(
        df["change_pct"].abs(),
        bins=[0, 20, 30, np.inf],
        labels=["low", "medium", "high"],
    )

    return (
        df.sort_values("change_pct", key=abs, ascending=False)
        .head(30)
        .reset_index(drop=True)
    )


def _detect_trends(metrics_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta métricas con 3+ semanas consecutivas de deterioro o mejora.
    Severity deteriorating: 4+ semanas = high, 3 = medium.
    Severity improving: 3+ semanas = opportunity.
    Retorna top 30 (deteriorating primero).
    """
    needed = ["COUNTRY", "CITY", "ZONE", "METRIC",
              "L3W_ROLL", "L2W_ROLL", "L1W_ROLL", "L0W_ROLL"]
    df = metrics_wide[needed].dropna(subset=["L2W_ROLL", "L1W_ROLL", "L0W_ROLL"]).copy()

    # 3-week consecutive deterioration
    det3 = (df["L0W_ROLL"] < df["L1W_ROLL"]) & (df["L1W_ROLL"] < df["L2W_ROLL"])
    # 4-week consecutive deterioration (needs L3W_ROLL)
    det4 = det3 & df["L3W_ROLL"].notna() & (df["L2W_ROLL"] < df["L3W_ROLL"])

    # 3-week consecutive improvement
    imp3 = (df["L0W_ROLL"] > df["L1W_ROLL"]) & (df["L1W_ROLL"] > df["L2W_ROLL"])

    deteriorating = df[det3].copy()
    deteriorating["trend_type"] = "deteriorating"
    deteriorating["weeks_declining"] = np.where(det4[det3], 4, 3)
    deteriorating["severity"] = np.where(det4[det3], "high", "medium")

    improving = df[imp3].copy()
    improving["trend_type"] = "improving"
    improving["weeks_improving"] = 3
    improving["severity"] = "opportunity"

    result = pd.concat([deteriorating, improving], ignore_index=True)
    # Deteriorating first, then by magnitude of recent change
    result["_sort"] = (result["trend_type"] == "improving").astype(int)
    result = (
        result.sort_values(["_sort", "severity"], ascending=[True, True])
        .drop(columns=["_sort"])
        .head(30)
        .reset_index(drop=True)
    )
    return result[["COUNTRY", "CITY", "ZONE", "METRIC", "L0W_ROLL",
                   "trend_type", "weeks_declining", "weeks_improving", "severity"]]


def _detect_benchmarks(metrics_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta zonas que están > 1.5 std por debajo de la media de su grupo
    (COUNTRY × ZONE_TYPE × METRIC).
    Severity: z < -2 = high, z < -1.5 = medium.
    Retorna top 30 por z_score más negativo.
    """
    df = metrics_wide[["COUNTRY", "ZONE", "ZONE_TYPE", "METRIC", "L0W_ROLL"]].dropna(
        subset=["L0W_ROLL"]
    ).copy()

    grp = df.groupby(["COUNTRY", "ZONE_TYPE", "METRIC"])["L0W_ROLL"]
    df["group_mean"] = grp.transform("mean")
    df["group_std"] = grp.transform("std")

    # Groups with no variance are not informative
    df = df[df["group_std"] > 0].copy()
    df["z_score"] = (df["L0W_ROLL"] - df["group_mean"]) / df["group_std"]

    underperformers = df[df["z_score"] < -1.5].copy()
    underperformers["severity"] = np.where(underperformers["z_score"] < -2, "high", "medium")

    return (
        underperformers.sort_values("z_score")
        .head(30)
        .reset_index(drop=True)
    )[["COUNTRY", "ZONE", "ZONE_TYPE", "METRIC", "L0W_ROLL", "group_mean", "z_score", "severity"]]


def _detect_correlations(metrics_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula correlaciones entre métricas usando L0W_ROLL por zona.
    Retorna pares con |correlation| > 0.5, sin duplicados.
    """
    pivot = (
        metrics_wide[["ZONE", "METRIC", "L0W_ROLL"]]
        .dropna(subset=["L0W_ROLL"])
        .pivot_table(index="ZONE", columns="METRIC", values="L0W_ROLL", aggfunc="mean")
    )

    corr_matrix = pivot.corr()
    metrics = corr_matrix.columns.tolist()

    rows = []
    seen = set()
    for i, m1 in enumerate(metrics):
        for m2 in metrics[i + 1:]:
            pair = tuple(sorted([m1, m2]))
            if pair in seen:
                continue
            seen.add(pair)
            val = corr_matrix.loc[m1, m2]
            if abs(val) > 0.5:
                if val > 0.7:
                    interp = "Fuerte correlación positiva"
                elif val > 0.5:
                    interp = "Correlación positiva moderada"
                elif val < -0.7:
                    interp = "Fuerte correlación negativa"
                else:
                    interp = "Correlación negativa moderada"
                rows.append({"metric_1": m1, "metric_2": m2,
                             "correlation": round(val, 3), "interpretation": interp})

    return (
        pd.DataFrame(rows)
        .sort_values("correlation", key=abs, ascending=False)
        .reset_index(drop=True)
    )


def _detect_opportunities(metrics_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Zonas High Priority con mejora sostenida (L0W > L1W > L2W).
    Retorna top 20 por improvement_pct.
    """
    needed = ["COUNTRY", "CITY", "ZONE", "METRIC",
              "ZONE_PRIORITIZATION", "L0W_ROLL", "L1W_ROLL", "L2W_ROLL"]
    df = metrics_wide[needed].dropna(subset=["L0W_ROLL", "L1W_ROLL", "L2W_ROLL"]).copy()

    improving_mask = (df["L0W_ROLL"] > df["L1W_ROLL"]) & (df["L1W_ROLL"] > df["L2W_ROLL"])
    high_priority_mask = df["ZONE_PRIORITIZATION"] == "High Priority"

    opps = df[improving_mask & high_priority_mask].copy()

    opps["improvement_pct"] = np.where(
        opps["L2W_ROLL"] == 0,
        np.nan,
        (opps["L0W_ROLL"] - opps["L2W_ROLL"]) / opps["L2W_ROLL"].abs() * 100,
    )
    opps = opps.dropna(subset=["improvement_pct"])

    return (
        opps[["COUNTRY", "CITY", "ZONE", "METRIC", "L0W_ROLL", "L2W_ROLL", "improvement_pct"]]
        .sort_values("improvement_pct", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# LLM synthesis
# ---------------------------------------------------------------------------

def _format_insights_for_llm(
    anomalies: pd.DataFrame,
    trends: pd.DataFrame,
    benchmarks: pd.DataFrame,
    correlations: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> str:
    """Serializa los DataFrames de cada detector a texto legible para el LLM."""

    def _df_to_text(df: pd.DataFrame, top: int = 10) -> str:
        if df.empty:
            return "  (sin hallazgos detectados)"
        return df.head(top).to_string(index=False)

    sections = [
        ("=== ANOMALÍAS WoW (cambios > ±10% semana a semana) ===",
         _df_to_text(anomalies)),
        ("=== TENDENCIAS (3+ semanas consecutivas de deterioro o mejora) ===",
         _df_to_text(trends)),
        ("=== BENCHMARKING (zonas > 1.5σ por debajo de su grupo) ===",
         _df_to_text(benchmarks)),
        ("=== CORRELACIONES ENTRE MÉTRICAS (|r| > 0.5) ===",
         _df_to_text(correlations)),
        ("=== OPORTUNIDADES (High Priority con mejora sostenida) ===",
         _df_to_text(opportunities)),
    ]

    return "\n\n".join(f"{header}\n{body}" for header, body in sections)


def _synthesize_report(insights_text: str) -> str:
    """Llama a Groq con el prompt de insights para generar el reporte ejecutivo."""
    prompt = INSIGHTS_PROMPT_TEMPLATE.format(insights_data=insights_text)

    print(f"[insights_engine] _synthesize_report → llamando Groq ({_MODEL})...")
    response = _client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_insights_report(dataframes: dict) -> dict:
    """
    Función principal. Orquesta los 5 detectores y la síntesis LLM.

    Returns dict con keys:
        "report_markdown"  : str
        "anomalies"        : pd.DataFrame
        "trends"           : pd.DataFrame
        "benchmarks"       : pd.DataFrame
        "correlations"     : pd.DataFrame
        "opportunities"    : pd.DataFrame
        "raw_insights_text": str
    """
    metrics_wide = dataframes["metrics_wide"]

    print("[insights_engine] Corriendo detectores...")
    anomalies = _detect_anomalies(metrics_wide)
    trends = _detect_trends(metrics_wide)
    benchmarks = _detect_benchmarks(metrics_wide)
    correlations = _detect_correlations(metrics_wide)
    opportunities = _detect_opportunities(metrics_wide)

    print(f"[insights_engine] Hallazgos: anomalies={len(anomalies)}, "
          f"trends={len(trends)}, benchmarks={len(benchmarks)}, "
          f"correlations={len(correlations)}, opportunities={len(opportunities)}")

    raw_insights_text = _format_insights_for_llm(
        anomalies, trends, benchmarks, correlations, opportunities
    )

    report_markdown = _synthesize_report(raw_insights_text)

    return {
        "report_markdown": report_markdown,
        "anomalies": anomalies,
        "trends": trends,
        "benchmarks": benchmarks,
        "correlations": correlations,
        "opportunities": opportunities,
        "raw_insights_text": raw_insights_text,
    }
