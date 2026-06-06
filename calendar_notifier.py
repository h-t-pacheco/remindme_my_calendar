# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "google-api-python-client",
#   "google-auth",
#   "requests",
# ]
# ///

import os
import json
import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SCOPES_READONLY = ["https://www.googleapis.com/auth/calendar.readonly"]
SCOPES_WRITE = ["https://www.googleapis.com/auth/calendar.events"]

DAYS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def get_calendar_service(write=False):
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw)
    scopes = SCOPES_WRITE if write else SCOPES_READONLY
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build("calendar", "v3", credentials=creds)


def get_events_in_range(service, calendar_id: str, start: datetime, end: datetime) -> list[dict]:
    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])


def is_last_business_day_of_month(today: datetime) -> bool:
    last_day = calendar.monthrange(today.year, today.month)[1]
    candidate = today.replace(day=last_day)
    # retroceder hasta encontrar un día hábil (lunes=0 ... viernes=4)
    while candidate.weekday() > 4:
        candidate -= timedelta(days=1)
    return today.date() == candidate.date()


def format_date_es(dt: datetime) -> str:
    day_name = DAYS_ES[dt.weekday()]
    return f"{day_name} {dt.day} de {MONTHS_ES[dt.month - 1]} de {dt.year}"


def format_event(event: dict) -> str:
    title = event.get("summary", "(Sin título)")
    start = event["start"]

    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"]).astimezone(TZ)
        time_str = dt.strftime("%H:%M")
        end_dt = datetime.fromisoformat(event["end"]["dateTime"]).astimezone(TZ)
        end_str = end_dt.strftime("%H:%M")
        return f"🕐 {time_str}–{end_str}  {title}"
    else:
        return f"🕐 Todo el día  {title}"


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()


def check_next_month_first_week(service, calendar_id: str, today: datetime) -> str | None:
    # primer día del mes siguiente
    if today.month == 12:
        first_of_next = today.replace(year=today.year + 1, month=1, day=1)
    else:
        first_of_next = today.replace(month=today.month + 1, day=1)

    first_of_next = first_of_next.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_first_week = first_of_next + timedelta(days=7)

    next_month_name = MONTHS_ES[first_of_next.month - 1].capitalize()
    events = get_events_in_range(service, calendar_id, first_of_next, end_of_first_week)

    if not events:
        return (
            f"⚠️ <b>Recordatorio de pagos</b>\n\n"
            f"No hay eventos registrados en la primera semana de {next_month_name}.\n"
            f"Validar el registro de pago de servicios para el 1° de {next_month_name}."
        )
    return None


def parse_event_datetime(date_str: str, time_str: str) -> datetime:
    parts = date_str.strip().split("/")
    day = int(parts[0])
    month = int(parts[1])
    if len(parts) == 3:
        year = int(parts[2])
        if year < 100:
            year += 2000
    else:
        year = datetime.now(TZ).year
    hour, minute = map(int, time_str.strip().split(":"))
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


def create_calendar_event(service, calendar_id: str, title: str, date_str: str, time_str: str) -> dict:
    start = parse_event_datetime(date_str, time_str)
    end = start + timedelta(hours=1)
    body = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": "America/Argentina/Buenos_Aires"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/Argentina/Buenos_Aires"},
    }
    return service.events().insert(calendarId=calendar_id, body=body).execute()


def main():
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
    telegram_chat_id = os.environ["TELEGRAM_CHAT_ID"]
    mode = os.environ.get("MODE", "notify")

    if mode == "create_event":
        title = os.environ["EVENT_TITLE"]
        date_str = os.environ["EVENT_DATE"]
        time_str = os.environ["EVENT_TIME"]
        service = get_calendar_service(write=True)
        event = create_calendar_event(service, calendar_id, title, date_str, time_str)
        start = parse_event_datetime(date_str, time_str)
        msg = (
            f"✅ <b>Evento creado</b>\n\n"
            f"📌 {title}\n"
            f"📅 {format_date_es(start)} a las {time_str}"
        )
        send_telegram(telegram_token, telegram_chat_id, msg)
        print(f"Evento creado: {event.get('htmlLink')}")
        return

    service = get_calendar_service()
    today = datetime.now(TZ)

    # Agenda del día
    start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
    events = get_events_in_range(service, calendar_id, start_of_day, start_of_day + timedelta(days=1))

    today_str = format_date_es(today)

    if not events:
        message = f"<b>Agenda del {today_str}</b>\n\nNo tienes eventos hoy."
    else:
        lines = [f"<b>Agenda del {today_str}</b>\n"]
        for event in events:
            lines.append(format_event(event))
        message = "\n".join(lines)

    send_telegram(telegram_token, telegram_chat_id, message)

    # Alerta de pagos si es el último día hábil del mes
    force = os.environ.get("FORCE_PAYMENT_CHECK", "false").lower() == "true"
    if force or is_last_business_day_of_month(today):
        warning = check_next_month_first_week(service, calendar_id, today)
        if warning:
            send_telegram(telegram_token, telegram_chat_id, warning)

    print("Notificacion enviada.")
    print(message)


if __name__ == "__main__":
    main()
