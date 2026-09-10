"""Schedule export to CSV, XLSX, PDF and ICS (§23)."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from app.models.calendar import MINUTES_PER_DAY
from app.schemas.schedule import ScheduledActivityOut

COLUMNS = [
    "day_ordinal",
    "day",
    "start",
    "end",
    "activity",
    "subject",
    "teachers",
    "room",
    "building",
    "groups",
    "students",
]


def hhmm(minute: int) -> str:
    minute_of_day = minute % MINUTES_PER_DAY
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def as_rows(
    items: list[ScheduledActivityOut], day_names: dict[int, str]
) -> list[dict[str, str]]:
    rows = []
    for item in sorted(items, key=lambda i: (i.day_ordinal, i.start_minute)):
        rows.append(
            {
                "day_ordinal": str(item.day_ordinal),
                "day": day_names.get(item.day_ordinal, str(item.day_ordinal)),
                "start": hhmm(item.start_minute),
                "end": hhmm(item.start_minute + item.duration_minutes),
                "activity": item.activity_name,
                "subject": item.subject_name or "",
                "teachers": ", ".join(item.teacher_names),
                "room": item.room_name or "",
                "building": item.building or "",
                "groups": ", ".join(item.group_names),
                "students": str(item.student_count),
            }
        )
    return rows


def to_csv(items: list[ScheduledActivityOut], day_names: dict[int, str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(as_rows(items, day_names))
    return buffer.getvalue().encode("utf-8-sig")


def to_xlsx(
    items: list[ScheduledActivityOut], day_names: dict[int, str], title: str
) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or "Rozvrh"
    sheet.append(COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in as_rows(items, day_names):
        sheet.append([row[column] for column in COLUMNS])
    widths = [12, 12, 8, 8, 36, 18, 24, 18, 12, 24, 10]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def to_pdf(
    items: list[ScheduledActivityOut], day_names: dict[int, str], title: str
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), title=title, leftMargin=24, rightMargin=24
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 8)]

    header = ["Den", "Od", "Do", "Aktivita", "Předmět", "Učitel", "Učebna"]
    data = [header]
    for row in as_rows(items, day_names):
        data.append(
            [
                row["day"],
                row["start"],
                row["end"],
                row["activity"],
                row["subject"],
                row["teachers"],
                row["room"],
            ]
        )
    if len(data) == 1:
        data.append(["—"] * len(header))
    table = Table(data, repeatRows=1, colWidths=[70, 44, 44, 220, 100, 130, 100])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    document.build(story)
    return buffer.getvalue()


def to_ics(
    items: list[ScheduledActivityOut],
    day_names: dict[int, str],
    title: str,
    *,
    week_start: date | None = None,
) -> bytes:
    """One week of the cycle as an iCalendar file."""
    monday = week_start or (date.today() - timedelta(days=date.today().weekday()))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//School Timetable Optimizer//CS",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{title}",
    ]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for item in sorted(items, key=lambda i: (i.day_ordinal, i.start_minute)):
        day = monday + timedelta(days=item.day_ordinal)
        start_of_day = datetime(day.year, day.month, day.day)
        start = start_of_day + timedelta(minutes=item.start_minute % MINUTES_PER_DAY)
        end = start + timedelta(minutes=item.duration_minutes)
        description = "; ".join(
            part
            for part in [
                ", ".join(item.teacher_names),
                ", ".join(item.group_names),
                f"{item.student_count} studentů",
            ]
            if part
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:activity-{item.id}@timetable",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{item.activity_name}",
            f"LOCATION:{item.room_name or ''}",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")


MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "ics": "text/calendar; charset=utf-8",
}
