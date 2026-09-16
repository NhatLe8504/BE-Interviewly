from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing

from ...application.report.ports import InterviewSessionReportData


def _register_fonts() -> str:
    # Look for a Unicode-compatible font
    font_candidates = [
        ("Arial", "C:/Windows/Fonts/arial.ttf"),
        ("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"),
        ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    registered_name = "Helvetica"
    for name, path in font_candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                if name == "Arial":
                    registered_name = "Arial"
            except Exception:
                continue
    return registered_name


class ReportLabPdfGenerator:
    def __init__(self) -> None:
        self.font_name = _register_fonts()

    def generate(self, data: InterviewSessionReportData) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        normal_font = self.font_name

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Normal"],
            fontName=normal_font,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1e293b"),
            alignment=0,
        )

        subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            fontName=normal_font,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#64748b"),
        )

        section_heading = ParagraphStyle(
            "SectionHeading",
            parent=styles["Normal"],
            fontName=normal_font,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=10,
            spaceAfter=6,
        )

        cell_text = ParagraphStyle(
            "CellText",
            parent=styles["Normal"],
            fontName=normal_font,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334155"),
        )

        elements: list[Any] = []

        # Header with Title and QR Code
        qr_widget = qr.QrCodeWidget(f"https://interviewly.ai/verify/session/{data.session_id}")
        qr_widget.barWidth = 55
        qr_widget.barHeight = 55
        qr_drawing = Drawing(55, 55)
        qr_drawing.add(qr_widget)

        header_data = [
            [
                Paragraph("<b>INTERVIEW COACH</b><br/><font size=14>Báo Cáo Đánh Giá Năng Lực Phỏng Vấn AI</font>", title_style),
                qr_drawing,
            ]
        ]
        header_table = Table(header_data, colWidths=[440, 80])
        header_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ])
        )
        elements.append(header_table)
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1")))
        elements.append(Spacer(1, 10))

        # Candidate & Session Info Box
        date_str = data.started_at.strftime("%d/%m/%Y %H:%M") if data.started_at else "N/A"
        info_data = [
            [
                Paragraph(f"<b>Ứng viên:</b> {data.candidate_name}", cell_text),
                Paragraph(f"<b>Vị trí:</b> {data.job_role or 'Chung'}", cell_text),
            ],
            [
                Paragraph(f"<b>Email:</b> {data.candidate_email}", cell_text),
                Paragraph(f"<b>Lĩnh vực:</b> {data.job_domain or 'Chung'}", cell_text),
            ],
            [
                Paragraph(f"<b>Mã phiên:</b> #{data.session_id}", cell_text),
                Paragraph(f"<b>Thời gian:</b> {date_str}", cell_text),
            ],
        ]
        info_table = Table(info_data, colWidths=[260, 260])
        info_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ])
        )
        elements.append(info_table)
        elements.append(Spacer(1, 14))

        # Rubric Scores Section
        elements.append(Paragraph("<b>1. TỔNG QUAN ĐIỂM SỐ RUBRIC</b>", section_heading))

        def _fmt_score(sc: Any) -> str:
            return f"{float(sc):.1f}/10" if sc is not None else "N/A"

        rubric_data = [
            [
                Paragraph("<b>Tiêu chí</b>", cell_text),
                Paragraph("<b>Điểm số</b>", cell_text),
                Paragraph("<b>Đánh giá mức độ</b>", cell_text),
            ],
            [
                Paragraph("Độ rõ ràng & Mạch lạc (Clarity)", cell_text),
                Paragraph(_fmt_score(data.avg_clarity_score), cell_text),
                Paragraph("Trả lời trôi chảy, đúng trọng tâm", cell_text),
            ],
            [
                Paragraph("Tư duy logic & Cấu trúc (STAR)", cell_text),
                Paragraph(_fmt_score(data.avg_logic_score), cell_text),
                Paragraph("Bố cục Situation-Task-Action-Result chặt chẽ", cell_text),
            ],
            [
                Paragraph("Dẫn chứng & Ví dụ thực tế", cell_text),
                Paragraph(_fmt_score(data.avg_example_score), cell_text),
                Paragraph("Minh chứng số liệu thuyết phục", cell_text),
            ],
            [
                Paragraph("<b>Điểm tổng thể toàn phiên</b>", cell_text),
                Paragraph(f"<b>{_fmt_score(data.total_score)}</b>", cell_text),
                Paragraph("<b>Đạt yêu cầu phỏng vấn</b>", cell_text),
            ],
        ]
        rubric_table = Table(rubric_data, colWidths=[200, 100, 220])
        rubric_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        elements.append(rubric_table)
        elements.append(Spacer(1, 14))

        # Turn by Turn Details
        if data.turns:
            elements.append(Paragraph("<b>2. CHI TIẾT TỪNG CÂU HỎI & NHẬN XÉT AI</b>", section_heading))
            for t in data.turns:
                turn_box = [
                    [
                        Paragraph(f"<b>Lượt {t.turn_number}: {t.question}</b>", cell_text),
                    ],
                    [
                        Paragraph(f"<i>Trả lời:</i> {t.answer[:300] + ('...' if len(t.answer) > 300 else '')}", cell_text),
                    ],
                    [
                        Paragraph(
                            f"<b>Điểm:</b> {_fmt_score(t.overall_score)} | "
                            f"<b>Tốc độ (WPM):</b> {float(t.speaking_pace or 0):.0f} | "
                            f"<b>Từ đệm:</b> {t.filler_word_count or 0}<br/>"
                            f"<b>Nhận xét:</b> {t.feedback_text or 'Hoàn thành tốt'}",
                            cell_text,
                        ),
                    ],
                ]
                turn_table = Table(turn_box, colWidths=[520])
                turn_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ])
                )
                elements.append(turn_table)
                elements.append(Spacer(1, 8))

        # Footer note
        elements.append(Spacer(1, 10))
        elements.append(
            Paragraph(
                "<i>Báo cáo được sinh tự động bởi hệ thống AI Interview Coach. Quét mã QR để kiểm tra tính toàn vẹn.</i>",
                subtitle_style,
            )
        )

        doc.build(elements)
        return buf.getvalue()
