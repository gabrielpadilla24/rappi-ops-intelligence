"""
Insights Prompt — contiene el prompt para síntesis de insights automáticos.

Responsabilidades:
- Recibir los hallazgos crudos de cada detector (anomalías, tendencias, benchmarks, etc.)
- Instruir al LLM para sintetizar un reporte ejecutivo estructurado en Markdown
- Definir el formato de salida esperado (secciones, prioridades, recomendaciones)
"""

INSIGHTS_PROMPT_TEMPLATE = """\
Eres un analista senior de operaciones de Rappi. Genera un reporte ejecutivo en español \
basado en los siguientes hallazgos detectados automáticamente.

{insights_data}

Tu reporte debe tener exactamente esta estructura en Markdown:

# 📊 Reporte de Insights Operacionales

## Resumen Ejecutivo
(Top 3-5 hallazgos más críticos en bullets, priorizados por impacto al negocio)

## 🔴 Anomalías Detectadas
(Para cada anomalía: qué zona, qué métrica, qué cambió, qué tan grave es, qué se recomienda hacer)

## 📉 Tendencias Preocupantes
(Métricas en deterioro sostenido de 3+ semanas. Para cada una: zona, métrica, \
magnitud del deterioro, recomendación)

## 📊 Benchmarking entre Zonas
(Zonas similares con performance divergente. Identificar qué zonas están rezagadas \
vs sus pares y por qué podría ser)

## 🔗 Correlaciones Relevantes
(Relaciones entre métricas que vale la pena investigar. \
Ej: zonas con bajo X tienden a tener bajo Y)

## 🟢 Oportunidades Detectadas
(Zonas con métricas mejorando consistentemente que podrían escalarse)

## Recomendaciones Accionables
(Top 5 acciones concretas priorizadas por impacto, con zona/métrica específica)

Sé conciso pero accionable. Cada hallazgo debe tener: **Finding**, **Impacto** y **Recomendación**.
"""
