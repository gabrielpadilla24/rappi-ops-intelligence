"""
Data Pipeline — carga, limpia y enriquece los datos del Excel.

Responsabilidades:
- Leer el archivo Excel con múltiples hojas (métricas, órdenes, etc.)
- Limpiar y normalizar columnas (tipos, fechas, nulos)
- Calcular métricas derivadas (tasas, promedios, variaciones)
- Generar un string de esquema para el agente LLM

Funciones principales:
    load_all_data()             -> dict[str, pd.DataFrame]
    _load_raw_data()
    _process_metrics()
    _process_orders()
    _compute_derived_features()
    _generate_schema_string()   -> str
"""


def load_all_data() -> dict:
    pass


def _load_raw_data():
    pass


def _process_metrics():
    pass


def _process_orders():
    pass


def _compute_derived_features():
    pass


def _generate_schema_string() -> str:
    pass
