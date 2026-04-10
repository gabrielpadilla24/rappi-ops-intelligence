"""
Export — maneja la exportación de datos a CSV y reportes a PDF.

Responsabilidades:
- Serializar un DataFrame pandas a bytes en formato CSV
- Convertir texto Markdown a un documento PDF descargable via fpdf2

Funciones principales:
    export_to_csv(df)                            -> bytes
    export_to_pdf(markdown_text, title)          -> bytes
"""

import re
from datetime import date

import pandas as pd
from fpdf import FPDF

_ORANGE = (255, 107, 0)
_DARK_GRAY = (51, 51, 51)
_MID_GRAY = (120, 120, 120)
_BLACK = (0, 0, 0)


class _RappiPDF(FPDF):
    def header(self):
        # Orange banner
        self.set_fill_color(*_ORANGE)
        self.rect(0, 0, 210, 15, style="F")
        # Title in white
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        self.set_y(3)
        self.cell(0, 6, "Rappi Ops Intelligence", align="C", ln=True)
        # Date in light gray below banner
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_MID_GRAY)
        self.cell(0, 4, str(date.today()), align="C", ln=True)
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_MID_GRAY)
        self.cell(0, 6, f"Página {self.page_no()}", align="C")


def _strip_markdown(text: str) -> str:
    """Elimina marcado inline de negrita/cursiva."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text


def _to_latin1(text: str) -> str:
    """Remueve emojis y caracteres fuera de Latin-1, preserva tildes y ñ."""
    # Primero reemplazar emojis comunes por texto equivalente
    emoji_map = {
        "📊": "",
        "🔴": "",
        "📉": "",
        "🔗": "",
        "🟢": "",
        "📧": "",
        "🚀": "",
        "⬇️": "",
        "📋": "",
        "🤔": "",
        "👋": "",
        "✅": "",
        "❌": "",
        "⚠️": "",
        "🔍": "",
    }
    for emoji, replacement in emoji_map.items():
        text = text.replace(emoji, replacement)
    # Remover cualquier otro caracter fuera de Latin-1 silenciosamente
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def export_to_csv(df: pd.DataFrame) -> bytes:
    """Convierte un DataFrame a bytes CSV en UTF-8."""
    return df.to_csv(index=False).encode("utf-8")


def export_to_pdf(markdown_text: str, title: str = "Rappi Ops Intelligence Report") -> bytes:
    """
    Convierte texto Markdown a PDF usando fpdf2.

    Soporta: # ## ### para headings, - /* para bullets, líneas vacías como espacio,
    y texto plano. Limpia markdown inline antes de renderizar.
    Retorna los bytes del PDF.
    """
    try:
        pdf = _RappiPDF(orientation="P", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        for raw_line in markdown_text.splitlines():
            line = raw_line.rstrip()

            # Blank line → small vertical gap
            if not line.strip():
                pdf.ln(5)
                continue

            text = _to_latin1(_strip_markdown(line))

            if line.startswith("# "):
                text = text.lstrip("# ").strip()
                pdf.ln(4)
                pdf.set_font("Helvetica", "B", 18)
                pdf.set_text_color(*_ORANGE)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 8, text)

            elif line.startswith("## "):
                text = text.lstrip("# ").strip()
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 14)
                pdf.set_text_color(*_DARK_GRAY)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 7, text)

            elif line.startswith("### "):
                text = text.lstrip("# ").strip()
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_text_color(*_BLACK)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, text)

            elif line.startswith(("- ", "* ")):
                text = "- " + text[2:].strip()
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*_BLACK)
                pdf.set_x(pdf.l_margin + 4)
                pdf.multi_cell(pdf.w - pdf.r_margin - (pdf.l_margin + 4), 6, text)

            else:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*_BLACK)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, text)

        return bytes(pdf.output())

    except Exception as exc:
        print(f"[export] export_to_pdf → error: {exc}, falling back to plain text PDF")
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "", 10)
            for line in markdown_text.splitlines():
                pdf.multi_cell(0, 5, line[:200])
            return bytes(pdf.output())
        except Exception:
            return b""
