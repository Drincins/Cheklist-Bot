# bot/export.py
import os
import tempfile
import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage


# === Модель данных (единый формат, независимый от БД) ===
@dataclass
class AnswerRow:
    number: int
    question: str
    qtype: str              # 'yesno' | 'scale' | 'text' | ...
    answer: str
    comment: Optional[str] = None
    score: Optional[float] = None
    photo_path: Optional[str] = None

@dataclass
class AttemptData:
    attempt_id: int
    checklist_name: str
    user_name: str
    company_name: Optional[str]
    submitted_at: dt.datetime
    answers: List[AnswerRow]

# === Утилиты ===
def _register_font():
    font_path = os.getenv("PDF_FONT_PATH")
    if font_path:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
                print(f"[PDF] Using font from PDF_FONT_PATH: {font_path}")
                return "DejaVuSans"
            except Exception as e:
                print(f"[PDF] Failed to register font from PDF_FONT_PATH: {e}")
        else:
            print(f"[PDF] PDF_FONT_PATH points to missing file: {font_path}")

    candidates = [
        "assets/fonts/DejaVuSans.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", p))
                print(f"[PDF] Using fallback font: {p}")
                return "DejaVuSans"
            except Exception as e:
                print(f"[PDF] Failed to register fallback font {p}: {e}")

    print("[PDF] No font registered, fallback to Helvetica (may break Cyrillic)")
    return None

def _auto_fit_columns(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value)) if cell.value else 0)
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

def _fmt_dt(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M")


# === PDF ===
def export_attempt_to_pdf(filename: str, data: AttemptData):
    font_name = _register_font()
    styles = getSampleStyleSheet()
    if font_name:
        for k in styles.byName:
            styles.byName[k].fontName = font_name
        title_style  = ParagraphStyle(name="TitleCustom",   parent=styles["Title"],   fontName=font_name)
        h2_style     = ParagraphStyle(name="H2Custom",      parent=styles["Heading2"],fontName=font_name)
        normal_style = ParagraphStyle(name="NormalCustom",  parent=styles["Normal"],  fontName=font_name)
    else:
        title_style  = styles["Title"]
        h2_style     = styles["Heading2"]
        normal_style = styles["Normal"]

    doc = SimpleDocTemplate(filename, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    elements = []

    elements.append(Paragraph("Отчёт по чек-листу", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Чек-лист:</b> {data.checklist_name}", normal_style))
    elements.append(Paragraph(f"<b>Сотрудник:</b> {data.user_name}", normal_style))
    if data.company_name:
        elements.append(Paragraph(f"<b>Компания:</b> {data.company_name}", normal_style))
    elements.append(Paragraph(f"<b>Дата прохождения:</b> {_fmt_dt(data.submitted_at)}", normal_style))
    elements.append(Spacer(1, 16))

    # нормализация ответа только для yes/no
    def _norm_answer_for_row(row: AnswerRow) -> str:
        val = row.answer
        if val is None or str(val).strip() == "":
            return "*пусто*"
        qtype = (row.qtype or "").lower().strip()
        if qtype in {"yesno", "boolean", "bool", "yn"}:
            s = str(val).strip().lower()
            if s in {"yes", "да", "true"}:  return "Да"
            if s in {"no", "нет", "false"}: return "Нет"
            if s == "1": return "Да"
            if s == "0": return "Нет"
        return str(val)
    
    def _fmt_score(row) -> str:
        wt = getattr(row, "weight", None)
        sc = getattr(row, "score", None)
        if wt is None:
            return ""
        try:
            wt = float(wt)
        except Exception:
            return ""
        if sc is None:
            sc = 0.0
        else:
            sc = float(sc)

        def f(x: float) -> str:
            return str(int(x)) if abs(x - int(x)) < 1e-9 else f"{x:.2f}".rstrip("0").rstrip(".")
        return f"{f(sc)}/{f(wt)}"


    # помощник фото в ячейке
    def _image_cell(path: str, max_w: int = 45, max_h: int = 45):
        try:
            if path and os.path.exists(path):
                img = RLImage(path)
                ratio = min(max_w / img.drawWidth, max_h / img.drawHeight, 1.0)
                img.drawWidth *= ratio
                img.drawHeight *= ratio
                return img
        except Exception as e:
            print(f"[PDF] inline image failed for {path}: {e}")
        return ""

    def P(text: str):
        return Paragraph((text or "").replace("\n", "<br/>"), normal_style)

    # колонки: № | Вопрос | Ответ | Комментарий | Балл | Фото  (БЕЗ «Тип»)
    table_data = [["№", "Вопрос", "Ответ", "Комментарий", "Балл/Вес", "Фото"]]
    for row in data.answers:
        table_data.append([
            row.number,
            P(row.question),
            P(_norm_answer_for_row(row)),
            P(row.comment or ""),
            _fmt_score(row),                    # ⬅️ тут
            _image_cell(row.photo_path) if row.photo_path else "",
        ])


    # ширины подобраны под A4 (doc.width ≈ 547pt): сумма ≈ 538pt
    col_widths = [28, 230, 110, 95, 30, 45]

    table = Table(
        table_data,
        colWidths=col_widths,
        repeatRows=1,
        hAlign='LEFT'
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#333333")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), font_name or 'Helvetica-Bold'),

        ('FONTNAME', (0,0), (-1,-1), font_name or 'Helvetica'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('FONTSIZE', (0,0), (-1,-1), 9),

        ('LEFTPADDING',  (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING',   (0,0), (-1,-1), 2),
        ('BOTTOMPADDING',(0,0), (-1,-1), 2),

        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.Color(0.98,0.98,0.98)]),

        ('ALIGN', (0,1), (0,-1), 'CENTER'),  # №
        ('ALIGN', (4,1), (4,-1), 'CENTER'),  # Балл
        ('ALIGN', (5,1), (5,-1), 'CENTER'),  # Фото
    ]))
    elements.append(table)
    elements.append(Spacer(1, 14))

    # (опционально) крупные фотоприложения ниже
    images = [r.photo_path for r in data.answers if r.photo_path and os.path.exists(r.photo_path)]
    if images:
        elements.append(Paragraph("Фотоприложения:", h2_style))
        elements.append(Spacer(1, 8))
        max_w, max_h = 380, 240
        for p in images[:8]:
            try:
                img = RLImage(p)
                ratio = min(max_w / img.drawWidth, max_h / img.drawHeight, 1.0)
                img.drawWidth *= ratio
                img.drawHeight *= ratio
                elements.append(img)
                elements.append(Spacer(1, 6))
                elements.append(Paragraph(os.path.basename(p), normal_style))
                elements.append(Spacer(1, 8))
            except Exception as e:
                print(f"[PDF] image add failed for {p}: {e}")
                continue

    doc.build(elements)


# === Excel ===
def export_attempt_to_excel(filename: str, data: AttemptData):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ответы"

    # Шапка (БЕЗ «Тип»)
    ws.append(["№", "Вопрос", "Ответ", "Комментарий", "Балл/Вес", "Фото"])
    header_font = Font(bold=True)
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Базовые ширины колонок
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 40
    ws.column_dimensions["E"].width = 8
    ws.column_dimensions["F"].width = 18  # фото

    # Нормализация ответа только для yes/no
    def _norm_answer_for_row(row: AnswerRow) -> str:
        val = row.answer
        if val is None or str(val).strip() == "":
            return "*пусто*"
        qtype = (row.qtype or "").lower().strip()
        if qtype in {"yesno", "boolean", "bool", "yn"}:
            s = str(val).strip().lower()
            if s in {"yes", "да", "true"}:  return "Да"
            if s in {"no", "нет", "false"}: return "Нет"
            if s == "1": return "Да"
            if s == "0": return "Нет"
        return str(val)

    def _fmt_score(row) -> str:
        if row.weight is None:
            return ""
        sc = 0.0 if row.score is None else float(row.score)
        wt = float(row.weight)
        def f(x):
            return str(int(x)) if abs(x - int(x)) < 1e-9 else f"{x:.2f}".rstrip('0').rstrip('.')
        return f"{f(sc)}/{f(wt)}"


    # Настройки миниатюр
    max_w_px = 160
    max_h_px = 120
    excel_px_to_pts = 0.75  # 1 px ≈ 0.75 pt

    def _make_thumb(src_path: str) -> tuple[Optional[str], int, int]:
        try:
            if not (src_path and os.path.exists(src_path)):
                return None, 0, 0
            im = PILImage.open(src_path)
            im = im.convert("RGB")
            im.thumbnail((max_w_px, max_h_px))
            tmp = os.path.join(tempfile.gettempdir(), f"xlthumb_{os.path.basename(src_path)}")
            im.save(tmp, format="JPEG", quality=85)
            return tmp, im.width, im.height
        except Exception as e:
            print(f"[XLSX] thumb error for {src_path}: {e}")
            return None, 0, 0

    tmp_thumbs: list[str] = []
    try:
        for i, row in enumerate(data.answers, start=2):
            ws.cell(row=i, column=1, value=row.number).alignment = Alignment(horizontal="center", vertical="top")
            ws.cell(row=i, column=2, value=row.question).alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(row=i, column=3, value=_norm_answer_for_row(row)).alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(row=i, column=4, value=row.comment or "").alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(row=i, column=5, value=_fmt_score(row)).alignment = Alignment(horizontal="center", vertical="top")


            # Фото → колонка F
            if row.photo_path and os.path.exists(row.photo_path):
                thumb_path, w_px, h_px = _make_thumb(row.photo_path)
                if thumb_path:
                    tmp_thumbs.append(thumb_path)
                    img = XLImage(thumb_path)
                    ws.add_image(img, f"F{i}")
                    ws.row_dimensions[i].height = max(ws.row_dimensions[i].height or 0, int((h_px + 10) * excel_px_to_pts))
            else:
                ws.cell(row=i, column=6, value="").alignment = Alignment(vertical="top")
    finally:
        _auto_fit_columns(ws)

        # Лист "Сводка"
        ws2 = wb.create_sheet("Сводка")
        ws2.append(["Параметр", "Значение"])
        ws2["A1"].font = header_font
        ws2["B1"].font = header_font

        ws2.append(["Чек-лист", data.checklist_name])
        ws2.append(["Сотрудник", data.user_name])
        if data.company_name:
            ws2.append(["Компания", data.company_name])
        ws2.append(["Дата прохождения", _fmt_dt(data.submitted_at)])
        ws2.append(["Всего вопросов", len(data.answers)])
        total_score = sum([r.score for r in data.answers if isinstance(r.score, (int, float))])
        ws2.append(["Суммарный балл", total_score])
        _auto_fit_columns(ws2)

        wb.save(filename)

        # Чистка временных превью
        for p in tmp_thumbs:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


# === Универсальная обёртка (создаёт оба файла и возвращает пути) ===
def export_attempt_to_files(tmp_dir: Optional[str], data: AttemptData):
    base_dir = tmp_dir or tempfile.gettempdir()
    safe_user = data.user_name.replace(" ", "_")
    safe_check = data.checklist_name.replace(" ", "_")
    stamp = data.submitted_at.strftime("%Y%m%d_%H%M")
    pdf_path = os.path.join(base_dir, f"report_{safe_check}_{safe_user}_{stamp}.pdf")
    xlsx_path = os.path.join(base_dir, f"report_{safe_check}_{safe_user}_{stamp}.xlsx")

    export_attempt_to_pdf(pdf_path, data)
    export_attempt_to_excel(xlsx_path, data)
    return pdf_path, xlsx_path
