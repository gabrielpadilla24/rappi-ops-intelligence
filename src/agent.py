"""
Agent — agente LLM que interpreta preguntas en lenguaje natural y genera/ejecuta código pandas.

Responsabilidades:
- Recibir una pregunta del usuario junto con el historial de chat
- Generar código pandas via LLM para responder la pregunta
- Ejecutar el código generado de forma segura sobre los dataframes
- Sintetizar una respuesta en lenguaje natural con los resultados
- Generar configuración de gráficos Plotly cuando sea relevante

Funciones principales:
    ask(question, chat_history, dataframes)  -> dict
    _generate_code()
    _execute_code()
    _synthesize_response()
    _generate_chart_config()
"""


def ask(question: str, chat_history: list, dataframes: dict) -> dict:
    pass


def _generate_code():
    pass


def _execute_code():
    pass


def _synthesize_response():
    pass


def _generate_chart_config():
    pass
