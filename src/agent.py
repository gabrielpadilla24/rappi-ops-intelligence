"""
Agent — agente LLM que interpreta preguntas en lenguaje natural y genera/ejecuta código pandas.

Responsabilidades:
- Recibir una pregunta del usuario junto con el historial de chat
- Generar código pandas via LLM para responder la pregunta
- Ejecutar el código generado de forma segura sobre los dataframes
- Sintetizar una respuesta en lenguaje natural con los resultados
- Generar configuración de gráficos Plotly cuando sea relevante

Funciones principales:
    ask(question, chat_history, dataframes)              -> dict
    _build_system_prompt(schema_string)                  -> str
    _generate_code(question, chat_history, system_prompt) -> dict
    _execute_code(code, dataframes)                      -> any
    _synthesize_response(question, result, explanation)  -> str
    _generate_chart_config(chart_raw, result)            -> dict | None
"""

import json
import os
import re

import google.generativeai as genai
import numpy as np
import pandas as pd
from dotenv import load_dotenv

from prompts.system_prompt import SYSTEM_PROMPT_TEMPLATE

load_dotenv()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
_MODEL = "gemini-2.0-flash"
_MAX_HISTORY_TURNS = 5  # turnos (user + assistant) a mantener en contexto


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(schema_string: str) -> str:
    """Inyecta el schema en el template del system prompt."""
    return SYSTEM_PROMPT_TEMPLATE.format(schema=schema_string)


def _format_history(chat_history: list) -> list:
    """
    Convierte el historial del formato interno [{"role": "user"|"assistant", "content": "..."}]
    al formato de Gemini: [{"role": "user"|"model", "parts": "..."}].
    """
    formatted = []
    for msg in chat_history:
        role = "model" if msg["role"] == "assistant" else "user"
        formatted.append({"role": role, "parts": msg["content"]})
    return formatted


def _generate_code(question: str, chat_history: list, system_prompt: str) -> dict:
    """
    Llama a Gemini con el system prompt + historial + pregunta.
    Retorna el dict parseado con keys: code, explanation, chart, suggestions.
    """
    recent_history = chat_history[-(2 * _MAX_HISTORY_TURNS):]

    print(f"[agent] _generate_code → llamando Gemini ({_MODEL})...")
    model = genai.GenerativeModel(_MODEL, system_instruction=system_prompt)
    chat = model.start_chat(history=_format_history(recent_history))
    response = chat.send_message(question)
    raw_content = response.text.strip()

    print(f"[agent] _generate_code → respuesta recibida ({len(raw_content)} chars)")
    return _parse_json_response(raw_content)


def _parse_json_response(raw: str) -> dict:
    """
    Intenta parsear el JSON de la respuesta del LLM.
    Si falla, extrae el primer objeto JSON completo mediante regex.
    """
    # Quitar bloques de código markdown si los hay
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Regex fallback: extraer desde primer '{' hasta último '}'
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    print(f"[agent] WARNING: no se pudo parsear JSON. Raw:\n{raw[:500]}")
    return {
        "code": "result = 'Error: el LLM no retornó JSON válido.'",
        "explanation": "Error de parsing",
        "chart": {"type": "none"},
        "suggestions": [],
    }


def _execute_code(code: str, dataframes: dict) -> any:
    """
    Ejecuta el código generado en un namespace controlado.
    Retorna la variable `result` del namespace, o un string de error.
    """
    namespace = {
        "metrics_wide": dataframes.get("metrics_wide"),
        "orders_wide": dataframes.get("orders_wide"),
        "metrics_long": dataframes.get("metrics_long"),
        "orders_long": dataframes.get("orders_long"),
        "trends": dataframes.get("trends"),
        "pd": pd,
        "np": np,
    }

    print(f"[agent] _execute_code → ejecutando código generado...")
    try:
        exec(code, namespace)  # noqa: S102
    except Exception as exc:
        error_msg = f"Error ejecutando código: {type(exc).__name__}: {exc}"
        print(f"[agent] _execute_code → {error_msg}")
        return error_msg

    result = namespace.get("result", "El código no asignó ningún valor a `result`.")
    print(f"[agent] _execute_code → resultado tipo: {type(result).__name__}")
    return result


def _synthesize_response(question: str, result: any, explanation: str) -> str:
    """
    Hace un segundo llamado a OpenAI para generar la respuesta final
    en lenguaje natural, orientada a un Operations Manager.
    """
    # Serializar result a texto legible
    if isinstance(result, pd.DataFrame):
        result_text = result.head(20).to_string(index=False)
        if len(result) > 20:
            result_text += f"\n... ({len(result)} filas en total)"
    elif isinstance(result, pd.Series):
        result_text = result.head(20).to_string()
    else:
        result_text = str(result)

    synthesis_prompt = (
        "Eres un analista de operaciones de Rappi respondiendo a un Operations Manager. "
        "Tu respuesta debe ser clara, concisa y accionable, en español. "
        "Destaca los hallazgos más importantes. Si hay datos tabulares, resume los puntos clave. "
        "Incluye contexto de negocio cuando sea relevante. No menciones código ni pandas. "
        "Usa formato Markdown (negritas, listas) para facilitar la lectura.\n\n"
        f"**Pregunta del usuario:** {question}\n\n"
        f"**Lógica aplicada:** {explanation}\n\n"
        f"**Resultados:**\n{result_text}"
    )

    print(f"[agent] _synthesize_response → llamando Gemini para síntesis...")
    model = genai.GenerativeModel(_MODEL)
    response = model.generate_content(synthesis_prompt)
    return response.text.strip()


def _generate_chart_config(chart_raw: dict, result: any) -> dict | None:
    """
    Valida y retorna la configuración del gráfico si es aplicable.
    Verifica que las columnas referenciadas existan en result.
    """
    if not isinstance(chart_raw, dict):
        return None
    if chart_raw.get("type", "none") == "none":
        return None
    if not isinstance(result, pd.DataFrame):
        return None

    cols = set(result.columns)
    x = chart_raw.get("x")
    y = chart_raw.get("y")

    if not x or not y:
        return None
    if x not in cols:
        print(f"[agent] _generate_chart_config → columna x='{x}' no existe en result")
        return None
    if y not in cols:
        print(f"[agent] _generate_chart_config → columna y='{y}' no existe en result")
        return None

    color = chart_raw.get("color")
    if color and color not in cols:
        print(f"[agent] _generate_chart_config → columna color='{color}' no existe, ignorando")
        chart_raw = {**chart_raw, "color": None}

    return chart_raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(question: str, chat_history: list, dataframes: dict) -> dict:
    """
    Función principal del agente. Orquesta todo el flujo:
    1. Construye el system prompt con el schema
    2. Genera código via LLM
    3. Ejecuta el código
    4. Si hay error, hace un retry pidiendo corrección
    5. Sintetiza la respuesta en lenguaje natural
    6. Valida la config del gráfico

    Returns dict con keys:
        "answer"       : str   — respuesta en lenguaje natural
        "result"       : any   — DataFrame/valor crudo para la UI
        "chart_config" : dict | None
        "suggestions"  : list[str]
        "code"         : str   — código generado (para debugging)
    """
    schema_string = dataframes.get("schema_string", "")
    system_prompt = _build_system_prompt(schema_string)

    try:
        # --- Paso 1: generar código ---
        llm_response = _generate_code(question, chat_history, system_prompt)
        code = llm_response.get("code", "result = 'No se generó código.'")
        explanation = llm_response.get("explanation", "")
        chart_raw = llm_response.get("chart", {"type": "none"})
        suggestions = llm_response.get("suggestions", [])

        # --- Paso 2: ejecutar código ---
        result = _execute_code(code, dataframes)

        # --- Paso 3: retry si hubo error de ejecución ---
        if isinstance(result, str) and result.startswith("Error ejecutando código:"):
            print("[agent] ask → error en ejecución, intentando retry...")
            retry_question = (
                f"El código que generaste produjo el siguiente error:\n\n"
                f"```\n{result}\n```\n\n"
                f"Por favor, corrige el código. La pregunta original era:\n{question}"
            )
            llm_response = _generate_code(retry_question, chat_history, system_prompt)
            code = llm_response.get("code", "result = 'No se generó código en el retry.'")
            explanation = llm_response.get("explanation", explanation)
            chart_raw = llm_response.get("chart", chart_raw)
            suggestions = llm_response.get("suggestions", suggestions)
            result = _execute_code(code, dataframes)

        # --- Paso 4: sintetizar respuesta ---
        answer = _synthesize_response(question, result, explanation)

        # --- Paso 5: validar chart config ---
        chart_config = _generate_chart_config(chart_raw, result)

    except Exception as exc:
        error_msg = f"Error al procesar la pregunta: {exc}"
        print(f"[agent] ask → excepción no controlada: {exc}")
        return {
            "answer": error_msg,
            "result": None,
            "chart_config": None,
            "suggestions": [],
            "code": "",
        }

    return {
        "answer": answer,
        "result": result,
        "chart_config": chart_config,
        "suggestions": suggestions,
        "code": code,
    }
