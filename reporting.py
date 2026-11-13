from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#14213D")
TEAL = colors.HexColor("#007F7B")
ORANGE = colors.HexColor("#F59E0B")
RED = colors.HexColor("#D1495B")
BLUE = colors.HexColor("#3B82F6")
GREEN = colors.HexColor("#16A36A")
PURPLE = colors.HexColor("#7C5CFC")
LIGHT = colors.HexColor("#F2F5F8")
PAGE_BG = colors.HexColor("#F6F8FB")
SOFT_TEAL = colors.HexColor("#E7F5F3")
SOFT_BLUE = colors.HexColor("#EAF2FF")
SOFT_ORANGE = colors.HexColor("#FFF3DB")
SOFT_RED = colors.HexColor("#FDECEF")
SOFT_GREEN = colors.HexColor("#E8F7F0")
MUTED = colors.HexColor("#5D6876")
GRID = colors.HexColor("#D8E0E7")
WHITE = colors.white

EVENT_TYPE_LABELS = {
    "data_gap": "Veri kesintisi",
    "high_current": "Yüksek akım",
    "high_temperature": "Yüksek sıcaklık",
    "voltage_fluctuation": "Gerilim dalgalanması",
    "connection_loss": "Bağlantı kaybı",
    "maintenance": "Bakım",
}

SEVERITY_LABELS = {
    "info": "Bilgi",
    "warning": "Uyarı",
    "critical": "Kritik",
}


def _register_fonts() -> tuple[str, str]:
    candidates = [
        (
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/seguisb.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ]
    for regular_path, bold_path in candidates:
        if regular_path.is_file() and bold_path.is_file():
            pdfmetrics.registerFont(TTFont("DeviceReport", str(regular_path)))
            pdfmetrics.registerFont(TTFont("DeviceReportBold", str(bold_path)))
            return "DeviceReport", "DeviceReportBold"
    return "Helvetica", "Helvetica-Bold"


def _number(value: int | float | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{value:,}".replace(",", ".")


def _timestamp(value: str | datetime | None) -> str:
    if value is None:
        return "Açık"
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%d.%m.%Y %H:%M UTC")


class HorizontalBars(Flowable):
    def __init__(
        self,
        items: list[tuple[str, int]],
        regular_font: str,
        bold_font: str,
        bar_color: colors.Color = TEAL,
    ) -> None:
        super().__init__()
        self.items = items
        self.regular_font = regular_font
        self.bold_font = bold_font
        self.bar_color = bar_color
        self.width = 0
        self.height = max(24 * len(items) + 6, 40)

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        return available_width, self.height

    def draw(self) -> None:
        canvas = self.canv
        if not self.items:
            canvas.setFillColor(MUTED)
            canvas.setFont(self.regular_font, 9)
            canvas.drawString(0, 12, "Bu dönem için olay bulunmadı.")
            return

        max_value = max(value for _, value in self.items) or 1
        label_width = min(58 * mm, self.width * 0.38)
        bar_width = self.width - label_width - 18 * mm

        for index, (label, value) in enumerate(self.items):
            y = self.height - 20 - index * 24
            canvas.setFillColor(NAVY)
            canvas.setFont(self.regular_font, 8.5)
            canvas.drawString(0, y + 3, label[:30])
            canvas.setFillColor(LIGHT)
            canvas.roundRect(label_width, y, bar_width, 11, 3, fill=1, stroke=0)
            canvas.setFillColor(self.bar_color)
            canvas.roundRect(
                label_width,
                y,
                max(bar_width * value / max_value, 2),
                11,
                3,
                fill=1,
                stroke=0,
            )
            canvas.setFillColor(NAVY)
            canvas.setFont(self.bold_font, 8.5)
            canvas.drawRightString(self.width, y + 3, _number(value))


class DonutChart(Flowable):
    def __init__(
        self,
        values: list[tuple[str, int, colors.Color]],
        regular_font: str,
        bold_font: str,
    ) -> None:
        super().__init__()
        self.values = values
        self.regular_font = regular_font
        self.bold_font = bold_font
        self.width = 0
        self.height = 58 * mm

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        return available_width, self.height

    def draw(self) -> None:
        canvas = self.canv
        total = sum(value for _, value, _ in self.values)
        center_x = min(self.width * 0.31, 25 * mm)
        center_y = self.height / 2
        radius = 21 * mm
        start_angle = 90.0
        positive_values = [item for item in self.values if item[1] > 0]

        if len(positive_values) == 1:
            canvas.setFillColor(positive_values[0][2])
            canvas.circle(center_x, center_y, radius, fill=1, stroke=0)
        elif total:
            for _, value, color in positive_values:
                extent = 360.0 * value / total
                canvas.setFillColor(color)
                canvas.setStrokeColor(WHITE)
                canvas.setLineWidth(1.2)
                canvas.wedge(
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius,
                    start_angle,
                    extent,
                    fill=1,
                    stroke=1,
                )
                start_angle += extent
        else:
            canvas.setFillColor(LIGHT)
            canvas.circle(center_x, center_y, radius, fill=1, stroke=0)

        canvas.setFillColor(WHITE)
        canvas.circle(center_x, center_y, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(NAVY)
        canvas.setFont(self.bold_font, 18)
        canvas.drawCentredString(center_x, center_y + 1.5 * mm, _number(total))
        canvas.setFillColor(MUTED)
        canvas.setFont(self.regular_font, 7.5)
        canvas.drawCentredString(center_x, center_y - 4 * mm, "toplam olay")

        legend_x = max(55 * mm, self.width * 0.58)
        legend_y = self.height - 16 * mm
        for index, (label, value, color) in enumerate(self.values):
            y = legend_y - index * 13 * mm
            canvas.setFillColor(color)
            canvas.roundRect(legend_x, y, 4 * mm, 4 * mm, 1.5, fill=1, stroke=0)
            canvas.setFillColor(NAVY)
            canvas.setFont(self.regular_font, 8)
            canvas.drawString(legend_x + 6 * mm, y + 1.2 * mm, label)
            canvas.setFont(self.bold_font, 9)
            canvas.drawRightString(self.width, y + 1.2 * mm, _number(value))


class HourlyHeatmap(Flowable):
    def __init__(
        self,
        hourly_values: dict[int, int],
        regular_font: str,
        bold_font: str,
    ) -> None:
        super().__init__()
        self.hourly_values = hourly_values
        self.regular_font = regular_font
        self.bold_font = bold_font
        self.width = 0
        self.height = 37 * mm

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        return available_width, self.height

    def draw(self) -> None:
        canvas = self.canv
        gap = 1.5 * mm
        cell_width = (self.width - 11 * gap) / 12
        cell_height = 13 * mm
        maximum = max(self.hourly_values.values(), default=1)

        for hour in range(24):
            row = hour // 12
            column = hour % 12
            x = column * (cell_width + gap)
            y = self.height - (row + 1) * cell_height - row * 3 * mm
            value = self.hourly_values.get(hour, 0)
            strength = 0.12 + (0.88 * value / maximum if maximum else 0)
            fill = colors.Color(
                1 - (1 - TEAL.red) * strength,
                1 - (1 - TEAL.green) * strength,
                1 - (1 - TEAL.blue) * strength,
            )
            canvas.setFillColor(fill)
            canvas.roundRect(x, y, cell_width, cell_height, 2.5, fill=1, stroke=0)
            canvas.setFillColor(NAVY if strength < 0.55 else WHITE)
            canvas.setFont(self.bold_font, 8)
            canvas.drawCentredString(x + cell_width / 2, y + 7 * mm, _number(value))
            canvas.setFont(self.regular_font, 6.5)
            canvas.drawCentredString(x + cell_width / 2, y + 2.8 * mm, f"{hour:02d}:00")


def _page_chrome(
    canvas: Any,
    document: Any,
    regular_font: str,
    bold_font: str,
) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)

    if document.page > 1:
        canvas.setFillColor(TEAL)
        canvas.roundRect(18 * mm, height - 16 * mm, 4 * mm, 4 * mm, 1.2, fill=1, stroke=0)
        canvas.setFillColor(NAVY)
        canvas.setFont(bold_font, 8)
        canvas.drawString(25 * mm, height - 13.3 * mm, "DEVICE DATA")
        canvas.setFillColor(MUTED)
        canvas.setFont(regular_font, 8)
        canvas.drawRightString(width - 18 * mm, height - 13.3 * mm, "OLAY ANALİTİĞİ")

    canvas.setStrokeColor(GRID)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont(regular_font, 8)
    canvas.drawString(18 * mm, 9 * mm, "device-data MCP - sentetik demo raporu")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Sayfa {document.page}")
    canvas.restoreState()


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value)), style)


def _panel(
    title: str,
    content: Flowable,
    styles: Any,
    width: float,
) -> Table:
    panel = Table(
        [
            [Paragraph(title, styles["PanelTitle"])],
            [content],
        ],
        colWidths=[width],
    )
    panel.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.6, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("TOPPADDING", (0, 0), (-1, 0), 4 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 1 * mm),
                ("TOPPADDING", (0, 1), (-1, 1), 1 * mm),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 4 * mm),
            ]
        )
    )
    return panel


def create_device_event_report(output_path: Path, payload: dict[str, Any]) -> None:
    regular_font, bold_font = _register_fonts()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            fontName=bold_font,
            fontSize=29,
            leading=34,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSubtitle",
            fontName=regular_font,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#DCE8F2"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            fontName=bold_font,
            fontSize=17,
            leading=22,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Subsection",
            fontName=bold_font,
            fontSize=11,
            leading=14,
            textColor=NAVY,
            spaceBefore=5,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Overline",
            fontName=bold_font,
            fontSize=8,
            leading=10,
            tracking=1.4,
            textColor=colors.HexColor("#9FD8D4"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="PanelTitle",
            fontName=bold_font,
            fontSize=10.5,
            leading=13,
            textColor=NAVY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="InsightLabel",
            fontName=bold_font,
            fontSize=7.5,
            leading=9,
            textColor=MUTED,
        )
    )
    styles.add(
        ParagraphStyle(
            name="InsightValue",
            fontName=bold_font,
            fontSize=13,
            leading=16,
            textColor=NAVY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="InsightDetail",
            fontName=regular_font,
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyTR",
            fontName=regular_font,
            fontSize=9.5,
            leading=14,
            textColor=NAVY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallTR",
            fontName=regular_font,
            fontSize=7.5,
            leading=10,
            textColor=NAVY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHeader",
            fontName=bold_font,
            fontSize=7.5,
            leading=10,
            textColor=WHITE,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CriticalCell",
            parent=styles["SmallTR"],
            fontName=bold_font,
            textColor=RED,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="WarningCell",
            parent=styles["SmallTR"],
            fontName=bold_font,
            textColor=colors.HexColor("#9A6500"),
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="InfoCell",
            parent=styles["SmallTR"],
            fontName=bold_font,
            textColor=BLUE,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="OpenCell",
            parent=styles["SmallTR"],
            fontName=bold_font,
            textColor=colors.HexColor("#9A6500"),
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ResolvedCell",
            parent=styles["SmallTR"],
            fontName=bold_font,
            textColor=GREEN,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KpiValue",
            fontName=bold_font,
            fontSize=19,
            leading=22,
            textColor=NAVY,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KpiLabel",
            fontName=regular_font,
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=23 * mm,
        bottomMargin=20 * mm,
        title="Cihaz Olay Raporu",
        author="device-data MCP",
        subject="Cihaz olayları ve ölçüm özeti",
    )

    scope = payload["scope"]
    summary = payload["summary"]
    device = scope.get("device")
    scope_name = device["device_name"] if device else "Tüm cihazlar"
    period_label = f"{_timestamp(scope['start_time'])} - {_timestamp(scope['end_time'])}"
    busiest_device = payload["by_device"][0] if payload["by_device"] else None
    busiest_location = payload["by_location"][0] if payload["by_location"] else None
    busiest_hour = max(payload["by_hour"], key=lambda row: row["event_count"], default=None)

    story: list[Any] = []
    cover = Table(
        [
            [""],
            [
                Paragraph("DEVICE DATA / OPERASYON RAPORU", styles["Overline"]),
            ],
            [Paragraph("Cihaz Olay Raporu", styles["ReportTitle"])],
            [Paragraph(escape(scope_name), styles["ReportSubtitle"])],
            [Paragraph(escape(period_label), styles["ReportSubtitle"])],
            [Paragraph("SENTETİK DEMO VERİSİ", styles["Overline"])],
        ],
        colWidths=[174 * mm],
        rowHeights=[3 * mm, 12 * mm, 30 * mm, 10 * mm, 12 * mm, 11 * mm],
    )
    cover.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), TEAL),
                ("BACKGROUND", (0, 1), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 1), (-1, -1), 12 * mm),
                ("RIGHTPADDING", (0, 1), (-1, -1), 12 * mm),
                ("TOPPADDING", (0, 1), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3 * mm),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.extend([cover, Spacer(1, 9 * mm)])

    kpis = [
        (summary["event_count"], "Toplam olay"),
        (summary["critical_event_count"], "Kritik olay"),
        (summary["open_event_count"], "Açık olay"),
        (summary["affected_device_count"], "Etkilenen cihaz"),
    ]
    kpi_cells = [
        Table(
            [
                [Paragraph(_number(value), styles["KpiValue"])],
                [Paragraph(label, styles["KpiLabel"])],
            ],
            colWidths=[39 * mm],
            rowHeights=[11 * mm, 8 * mm],
        )
        for value, label in kpis
    ]
    kpi_table = Table([kpi_cells], colWidths=[43.5 * mm] * 4, rowHeights=[23 * mm])
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
                ("LINEABOVE", (0, 0), (0, 0), 3, TEAL),
                ("LINEABOVE", (1, 0), (1, 0), 3, RED),
                ("LINEABOVE", (2, 0), (2, 0), 3, ORANGE),
                ("LINEABOVE", (3, 0), (3, 0), 3, BLUE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )
    story.extend(
        [
            kpi_table,
            Spacer(1, 7 * mm),
            Table(
                [
                    [
                        "",
                        Paragraph(
                            (
                                f"En yoğun kaynak <b>{escape(busiest_device['device_name'])}</b> "
                                f"({_number(busiest_device['event_count'])} olay). "
                                f"En yoğun lokasyon <b>{escape(busiest_location['location'])}</b>; "
                                f"zirve saat <b>{busiest_hour['hour_utc']:02d}:00 UTC</b>."
                                if busiest_device and busiest_location and busiest_hour
                                else "Seçilen dönemde olay kaydı bulunmadı."
                            ),
                            styles["BodyTR"],
                        ),
                    ]
                ],
                colWidths=[4 * mm, 170 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, 0), TEAL),
                        ("BACKGROUND", (1, 0), (1, 0), SOFT_TEAL),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C5E7E4")),
                        ("LEFTPADDING", (0, 0), (0, 0), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                        ("LEFTPADDING", (1, 0), (1, 0), 5 * mm),
                        ("RIGHTPADDING", (1, 0), (1, 0), 5 * mm),
                        ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
                    ]
                ),
            ),
            Spacer(1, 6 * mm),
            Paragraph(
                "Seçilen UTC dönemindeki olay ve ölçüm verileri birlikte analiz edilmiştir. "
                f"Rapor üretim zamanı: {_timestamp(payload['generated_at'])}",
                styles["SmallTR"],
            ),
            PageBreak(),
        ]
    )

    by_device = [
        (row["device_name"], row["event_count"])
        for row in payload["by_device"]
    ]
    by_location = [
        (row["location"], row["event_count"])
        for row in payload["by_location"]
    ]
    by_type = [
        (EVENT_TYPE_LABELS.get(row["event_type"], row["event_type"]), row["event_count"])
        for row in payload["by_type"]
    ]

    def insight_card(label: str, value: str, detail: str, accent: colors.Color) -> Table:
        card = Table(
            [
                ["", Paragraph(label, styles["InsightLabel"])],
                ["", Paragraph(value, styles["InsightValue"])],
                ["", Paragraph(detail, styles["InsightDetail"])],
            ],
            colWidths=[3 * mm, 52 * mm],
            rowHeights=[7 * mm, 9 * mm, 8 * mm],
        )
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), accent),
                    ("BACKGROUND", (1, 0), (1, -1), WHITE),
                    ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                    ("LEFTPADDING", (1, 0), (1, -1), 4 * mm),
                    ("RIGHTPADDING", (1, 0), (1, -1), 2 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        return card

    device_insight = insight_card(
        "EN YOĞUN CİHAZ",
        busiest_device["device_name"] if busiest_device else "Kayıt yok",
        f"{_number(busiest_device['event_count'])} olay" if busiest_device else "0 olay",
        TEAL,
    )
    location_insight = insight_card(
        "EN YOĞUN LOKASYON",
        busiest_location["location"] if busiest_location else "Kayıt yok",
        f"{_number(busiest_location['event_count'])} olay" if busiest_location else "0 olay",
        ORANGE,
    )
    hour_insight = insight_card(
        "ZİRVE SAAT",
        f"{busiest_hour['hour_utc']:02d}:00 UTC" if busiest_hour else "Kayıt yok",
        f"{_number(busiest_hour['event_count'])} olay" if busiest_hour else "0 olay",
        PURPLE,
    )

    severity_chart = DonutChart(
        [
            ("Kritik", summary["critical_event_count"], RED),
            ("Uyarı", summary["warning_event_count"], ORANGE),
            ("Bilgi", summary["info_event_count"], BLUE),
        ],
        regular_font,
        bold_font,
    )

    severity_panel = _panel("Önem dağılımı", severity_chart, styles, 83 * mm)
    type_panel = _panel(
        "Olay türleri",
        HorizontalBars(by_type, regular_font, bold_font, RED),
        styles,
        87 * mm,
    )
    device_panel = _panel(
        "Cihaz yoğunluğu",
        HorizontalBars(by_device, regular_font, bold_font, TEAL),
        styles,
        102 * mm,
    )
    location_panel = _panel(
        "Lokasyon yoğunluğu",
        HorizontalBars(by_location, regular_font, bold_font, ORANGE),
        styles,
        68 * mm,
    )

    story.extend(
        [
            Paragraph("Operasyon görünümü", styles["Section"]),
            Table(
                [[device_insight, location_insight, hour_insight]],
                colWidths=[56 * mm, 56 * mm, 56 * mm],
                style=TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                ),
            ),
            Spacer(1, 6 * mm),
            Table(
                [[severity_panel, "", type_panel]],
                colWidths=[83 * mm, 4 * mm, 87 * mm],
                style=TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                ),
            ),
            Spacer(1, 6 * mm),
            Table(
                [[device_panel, "", location_panel]],
                colWidths=[102 * mm, 4 * mm, 68 * mm],
                style=TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                ),
            ),
            PageBreak(),
        ]
    )

    hourly_values = {row["hour_utc"]: row["event_count"] for row in payload["by_hour"]}
    story.extend(
        [
            Paragraph("Zaman ve cihaz performansı", styles["Section"]),
            _panel(
                "24 saatlik olay ısı haritası",
                HourlyHeatmap(hourly_values, regular_font, bold_font),
                styles,
                174 * mm,
            ),
            Spacer(1, 6 * mm),
        ]
    )

    device_rows: list[list[Any]] = [
        [
            _paragraph("Cihaz", styles["TableHeader"]),
            _paragraph("Lokasyon", styles["TableHeader"]),
            _paragraph("Olay", styles["TableHeader"]),
            _paragraph("Kritik", styles["TableHeader"]),
            _paragraph("Açık", styles["TableHeader"]),
            _paragraph("Ölçüm", styles["TableHeader"]),
            _paragraph("Ort. sıcaklık", styles["TableHeader"]),
        ]
    ]
    measurement_by_device = {
        row["device_id"]: row for row in payload["measurement_summaries"]
    }
    for row in payload["by_device"]:
        measurement = measurement_by_device.get(row["device_id"], {})
        device_rows.append(
            [
                _paragraph(row["device_name"], styles["SmallTR"]),
                _paragraph(row["location"], styles["SmallTR"]),
                _paragraph(_number(row["event_count"]), styles["SmallTR"]),
                _paragraph(_number(row["critical_event_count"]), styles["SmallTR"]),
                _paragraph(_number(row["open_event_count"]), styles["SmallTR"]),
                _paragraph(_number(measurement.get("measurement_count", 0)), styles["SmallTR"]),
                _paragraph(
                    f"{_number(measurement.get('average_temperature'))} °C",
                    styles["SmallTR"],
                ),
            ]
        )

    device_table = Table(
        device_rows,
        colWidths=[24 * mm, 25 * mm, 17 * mm, 17 * mm, 17 * mm, 24 * mm, 30 * mm],
        repeatRows=1,
    )
    device_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT_BLUE]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID),
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1.35 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.35 * mm),
            ]
        )
    )
    total_measurements = sum(
        row["measurement_count"] for row in payload["measurement_summaries"]
    )
    resolution_rate = (
        100 * summary["resolved_event_count"] / summary["event_count"]
        if summary["event_count"]
        else 0
    )
    story.extend(
        [
            _panel("Cihaz karşılaştırması", device_table, styles, 174 * mm),
            Spacer(1, 6 * mm),
            Table(
                [
                    [
                        insight_card(
                            "ÖLÇÜM KAPSAMI",
                            _number(total_measurements),
                            "seçilen dönemdeki ölçüm",
                            BLUE,
                        ),
                        insight_card(
                            "ÇÖZÜM ORANI",
                            f"%{resolution_rate:.1f}".replace(".", ","),
                            f"{_number(summary['resolved_event_count'])} çözülmüş olay",
                            GREEN,
                        ),
                        insight_card(
                            "AÇIK OLAY",
                            _number(summary["open_event_count"]),
                            "takip gerektiren kayıt",
                            ORANGE,
                        ),
                    ]
                ],
                colWidths=[56 * mm, 56 * mm, 56 * mm],
                style=TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                ),
            ),
            PageBreak(),
        ]
    )

    story.append(Paragraph("Olay kayıtları", styles["Section"]))
    story.append(
        Paragraph(
            f"Seçilen dönemdeki {_number(summary['event_count'])} olayın zaman, cihaz, "
            "lokasyon, önem ve çözüm durumu.",
            styles["BodyTR"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    event_rows: list[list[Any]] = [
        [
            _paragraph("Zaman", styles["TableHeader"]),
            _paragraph("Cihaz", styles["TableHeader"]),
            _paragraph("Lokasyon", styles["TableHeader"]),
            _paragraph("Tür", styles["TableHeader"]),
            _paragraph("Önem", styles["TableHeader"]),
            _paragraph("Durum", styles["TableHeader"]),
        ]
    ]
    event_cell_styles: list[tuple[Any, ...]] = []
    for row_index, row in enumerate(payload["events"], start=1):
        severity_style = {
            "critical": styles["CriticalCell"],
            "warning": styles["WarningCell"],
            "info": styles["InfoCell"],
        }[row["severity"]]
        is_open = row["resolved_at"] is None
        event_rows.append(
            [
                _paragraph(_timestamp(row["event_time"]), styles["SmallTR"]),
                _paragraph(row["device_name"], styles["SmallTR"]),
                _paragraph(row["location"], styles["SmallTR"]),
                _paragraph(EVENT_TYPE_LABELS.get(row["event_type"], row["event_type"]), styles["SmallTR"]),
                _paragraph(SEVERITY_LABELS.get(row["severity"], row["severity"]), severity_style),
                _paragraph(
                    "Açık" if is_open else "Çözüldü",
                    styles["OpenCell"] if is_open else styles["ResolvedCell"],
                ),
            ]
        )
        severity_background = {
            "critical": SOFT_RED,
            "warning": SOFT_ORANGE,
            "info": SOFT_BLUE,
        }[row["severity"]]
        event_cell_styles.extend(
            [
                ("BACKGROUND", (4, row_index), (4, row_index), severity_background),
                (
                    "BACKGROUND",
                    (5, row_index),
                    (5, row_index),
                    SOFT_ORANGE if is_open else SOFT_GREEN,
                ),
            ]
        )

    event_table = Table(
        event_rows,
        colWidths=[36 * mm, 24 * mm, 26 * mm, 34 * mm, 20 * mm, 20 * mm],
        repeatRows=1,
    )
    event_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("ROWBACKGROUNDS", (0, 1), (3, -1), [WHITE, LIGHT]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, GRID),
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1.1 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1 * mm),
                *event_cell_styles,
            ]
        )
    )
    story.append(event_table)

    document.build(
        story,
        onFirstPage=lambda canvas, doc: _page_chrome(canvas, doc, regular_font, bold_font),
        onLaterPages=lambda canvas, doc: _page_chrome(canvas, doc, regular_font, bold_font),
    )
