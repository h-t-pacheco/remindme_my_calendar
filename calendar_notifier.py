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
from datetime import datetime, timezone, timedelta

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_service():
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)


def get_todays_events(service, calendar_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

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


def format_event(event: dict) -> str:
    title = event.get("summary", "(Sin título)")
    start = event["start"]

    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        time_str = dt.strftime("%H:%M")
        end_dt = datetime.fromisoformat(event["end"]["dateTime"])
        end_str = end_dt.strftime("%H:%M")
        return f"  {time_str}–{end_str}  {title}"
    else:
        return f"  Todo el día  {title}"


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()


def main():
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
    telegram_chat_id = os.environ["TELEGRAM_CHAT_ID"]

    service = get_calendar_service()
    events = get_todays_events(service, calendar_id)

    today_str = datetime.now().strftime("%A %d de %B de %Y")

    if not events:
        message = f"<b>Agenda del {today_str}</b>\n\nNo tienes eventos hoy."
    else:
        lines = [f"<b>Agenda del {today_str}</b>\n"]
        for event in events:
            lines.append(format_event(event))
        message = "\n".join(lines)

    send_telegram(telegram_token, telegram_chat_id, message)
    print("Notificacion enviada.")
    print(message)


if __name__ == "__main__":
    main()
