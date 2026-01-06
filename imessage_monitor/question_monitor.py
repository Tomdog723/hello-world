#!/usr/bin/env python3
"""
iMessage Question Monitor Daemon
Monitors incoming iMessages, detects questions using Claude, and sends email notifications.
"""

import datetime
import os
import sqlite3
import re
import time
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import timezone

import anthropic
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# =============================================================================
# CONFIGURATION - Update these paths for your Mac
# =============================================================================

# Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = '/Users/tom/Desktop/EC Automation Scripts/confirm_appointments/credentials.json'
TOKEN_FILE = '/Users/tom/Desktop/EC Automation Scripts/confirm_appointments/token.json'

# iMessage database
MESSAGES_DB = '/Users/tom/Library/Messages/chat.db'

# Logging
LOG_FILE = '/Users/tom/Desktop/EC Automation Scripts/question_monitor/monitor.log'

# Email settings
GMAIL_ADDRESS = 'silviacleaning001@gmail.com'
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')  # Set this environment variable

# Anthropic API
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')  # Set this environment variable

# Polling interval (seconds)
POLL_INTERVAL = 10

# How far back to look on startup (hours)
STARTUP_LOOKBACK_HOURS = 1

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# APPLE DATE CONVERSION
# =============================================================================

APPLE_EPOCH = datetime.datetime(2001, 1, 1, tzinfo=timezone.utc)


def apple_date_to_dt(raw_date):
    """Convert Apple timestamp (nanoseconds since 2001-01-01) to datetime."""
    if raw_date is None:
        return None
    try:
        if abs(raw_date) > 10_000_000_000:
            return APPLE_EPOCH + datetime.timedelta(seconds=raw_date / 1_000_000_000)
        return APPLE_EPOCH + datetime.timedelta(seconds=raw_date)
    except Exception:
        return None


def dt_to_apple_date(dt):
    """Convert datetime to Apple timestamp (nanoseconds since 2001-01-01)."""
    if dt is None:
        return None
    delta = dt - APPLE_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


# =============================================================================
# PHONE NUMBER UTILITIES
# =============================================================================

def normalize_phone_number(phone):
    """Generate multiple format variations of a phone number for matching."""
    if not phone:
        return []
    cleaned = re.sub(r'[^\d+]', '', phone)
    variations = [phone, cleaned]

    ten_digit = None
    if cleaned.startswith('+1') and len(cleaned) == 12:
        ten_digit = cleaned[2:]
        variations.append(ten_digit)
    elif len(cleaned) == 10:
        ten_digit = cleaned
        variations.append('+1' + cleaned)

    if ten_digit:
        variations.extend([
            f"+1 ({ten_digit[:3]}) {ten_digit[3:6]}-{ten_digit[6:]}",
            f"+1-{ten_digit[:3]}-{ten_digit[3:6]}-{ten_digit[6:]}",
            f"({ten_digit[:3]}) {ten_digit[3:6]}-{ten_digit[6:]}",
        ])

    return list(set(variations))


def extract_phone_from_description(description):
    """Extract phone numbers from calendar event description."""
    if not description:
        return []
    matches = re.findall(r'Phone:\s*(\+?\d{1,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4})', description)
    return matches if matches else []


# =============================================================================
# GOOGLE CALENDAR
# =============================================================================

_calendar_service = None


def get_calendar_service():
    """Authenticate and return Google Calendar service (cached)."""
    global _calendar_service
    if _calendar_service is not None:
        return _calendar_service

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    _calendar_service = build('calendar', 'v3', credentials=creds)
    return _calendar_service


def find_customer_by_phone(phone):
    """
    Search Google Calendar for a customer matching this phone number.
    Returns dict with customer info or None.
    """
    try:
        service = get_calendar_service()
        phone_variations = normalize_phone_number(phone)

        # Search events in the next 30 days
        now = datetime.datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + datetime.timedelta(days=30)).isoformat()

        calendar_list = service.calendarList().list().execute()

        for calendar in calendar_list.get('items', []):
            calendar_id = calendar['id']
            events = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime',
                maxResults=100
            ).execute().get('items', [])

            for event in events:
                description = event.get('description', '')
                event_phones = extract_phone_from_description(description)

                for event_phone in event_phones:
                    event_phone_variations = normalize_phone_number(event_phone)
                    if any(pv in event_phone_variations for pv in phone_variations):
                        # Found a match
                        summary = event.get('summary', 'Unknown Client')
                        client_name = summary.split(';')[0].strip() if ';' in summary else summary

                        start = event['start'].get('dateTime', event['start'].get('date'))

                        return {
                            'name': client_name,
                            'full_summary': summary,
                            'next_appointment': start,
                            'calendar': calendar.get('summary', calendar_id),
                            'event_id': event.get('id'),
                            'phone': event_phone
                        }

        return None

    except Exception as e:
        logger.error(f"Error searching calendar for phone {phone}: {e}")
        return None


# =============================================================================
# LLM - QUESTION DETECTION
# =============================================================================

def is_question_llm(message_text, customer_name=None):
    """
    Use Claude to determine if this message is a question requiring a response.
    Returns (is_question: bool, interpretation: str, suggested_response: str)
    """
    if not message_text or not message_text.strip():
        return False, "", ""

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set, falling back to simple '?' detection")
        is_q = '?' in message_text
        return is_q, "Question mark detected" if is_q else "", ""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        context = f"from a cleaning service customer named {customer_name}" if customer_name else "from a cleaning service customer"

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"""Analyze this text message {context}:

"{message_text}"

Determine:
1. Is this a question or request that needs a response from the cleaning company? (Yes/No)
2. If yes, what is the customer asking about? (brief interpretation)
3. If yes, suggest a brief, friendly response.

Consider these as questions/requests needing response:
- Rescheduling or cancellation requests
- Questions about timing, pricing, services
- Requests for callbacks or information
- Complaints or concerns

Consider these as NOT needing response:
- Simple confirmations like "ok", "sounds good", "see you then", "thank you"
- Thumbs up, emojis, reactions
- Statements that don't require a reply

Respond in this exact format:
NEEDS_RESPONSE: Yes or No
INTERPRETATION: (one line summary, or "N/A" if no response needed)
SUGGESTED_RESPONSE: (brief friendly response, or "N/A" if no response needed)"""
            }]
        )

        result = response.content[0].text

        needs_response = "NEEDS_RESPONSE: Yes" in result or "NEEDS_RESPONSE:Yes" in result

        interpretation = ""
        suggested = ""

        for line in result.split('\n'):
            if line.startswith('INTERPRETATION:'):
                interpretation = line.replace('INTERPRETATION:', '').strip()
            elif line.startswith('SUGGESTED_RESPONSE:'):
                suggested = line.replace('SUGGESTED_RESPONSE:', '').strip()

        if interpretation == "N/A":
            interpretation = ""
        if suggested == "N/A":
            suggested = ""

        return needs_response, interpretation, suggested

    except Exception as e:
        logger.error(f"LLM API error: {e}")
        # Fallback to simple detection
        is_q = '?' in message_text
        return is_q, "Question mark detected (LLM unavailable)" if is_q else "", ""


# =============================================================================
# EMAIL NOTIFICATIONS
# =============================================================================

def send_email_notification(customer_info, message_text, interpretation, suggested_response):
    """Send email notification about a customer question."""
    if not GMAIL_APP_PASSWORD:
        logger.error("GMAIL_APP_PASSWORD not set, cannot send email")
        return False

    try:
        customer_name = customer_info.get('name', 'Unknown Customer') if customer_info else 'Unknown Customer'
        phone = customer_info.get('phone', 'Unknown') if customer_info else 'Unknown'
        next_appt = customer_info.get('next_appointment', 'No upcoming appointment') if customer_info else 'Unknown'

        subject = f"Question from {customer_name}"

        body = f"""Customer Question Alert

CUSTOMER: {customer_name}
PHONE: {phone}
NEXT APPOINTMENT: {next_appt}

MESSAGE:
{message_text}

INTERPRETATION:
{interpretation}

SUGGESTED RESPONSE:
{suggested_response}

---
Sent by iMessage Monitor
"""

        msg = MIMEMultipart()
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = GMAIL_ADDRESS
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email notification sent for {customer_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


# =============================================================================
# MESSAGE MONITORING
# =============================================================================

def get_new_incoming_messages(since_timestamp):
    """
    Fetch incoming messages (is_from_me = 0) newer than since_timestamp.
    Returns list of dicts with message info.
    """
    messages = []

    try:
        conn = sqlite3.connect(MESSAGES_DB)
        cursor = conn.cursor()

        # Get messages where is_from_me = 0 (incoming) and date > since_timestamp
        cursor.execute("""
            SELECT
                m.ROWID,
                m.text,
                m.date,
                m.is_from_me,
                m.associated_message_type,
                h.id as handle_id
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_from_me = 0
              AND m.date > ?
              AND m.text IS NOT NULL
              AND m.text != ''
            ORDER BY m.date ASC
        """, (since_timestamp,))

        rows = cursor.fetchall()

        for row in rows:
            rowid, text, date, is_from_me, assoc_type, handle_id = row

            # Skip reactions/tapbacks
            if assoc_type and assoc_type != 0:
                continue

            messages.append({
                'rowid': rowid,
                'text': text,
                'date': date,
                'datetime': apple_date_to_dt(date),
                'handle_id': handle_id  # This is the phone number/email
            })

        conn.close()

    except sqlite3.Error as e:
        logger.error(f"Database error fetching messages: {e}")

    return messages


def get_latest_message_timestamp():
    """Get the timestamp of the most recent message in the database."""
    try:
        conn = sqlite3.connect(MESSAGES_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(date) FROM message")
        result = cursor.fetchone()
        conn.close()
        return result[0] if result[0] else 0
    except sqlite3.Error as e:
        logger.error(f"Database error getting latest timestamp: {e}")
        return 0


# =============================================================================
# MAIN DAEMON LOOP
# =============================================================================

def run_daemon():
    """Main monitoring loop."""
    logger.info("Starting iMessage Question Monitor daemon...")

    # Validate configuration
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set - will use simple '?' detection")
    if not GMAIL_APP_PASSWORD:
        logger.warning("GMAIL_APP_PASSWORD not set - email notifications disabled")
    if not os.path.exists(MESSAGES_DB):
        logger.error(f"Messages database not found at {MESSAGES_DB}")
        return

    # Start from messages in the last STARTUP_LOOKBACK_HOURS
    lookback_dt = datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=STARTUP_LOOKBACK_HOURS)
    last_processed_timestamp = dt_to_apple_date(lookback_dt)

    logger.info(f"Monitoring for new messages (looking back {STARTUP_LOOKBACK_HOURS} hour(s) on startup)...")

    while True:
        try:
            new_messages = get_new_incoming_messages(last_processed_timestamp)

            for msg in new_messages:
                handle = msg['handle_id'] or 'Unknown'
                text = msg['text']
                msg_time = msg['datetime']

                logger.info(f"New message from {handle}: {text[:50]}...")

                # Look up customer in calendar
                customer_info = find_customer_by_phone(handle) if handle != 'Unknown' else None
                customer_name = customer_info['name'] if customer_info else None

                # Check if it's a question using LLM
                is_question, interpretation, suggested = is_question_llm(text, customer_name)

                if is_question:
                    logger.info(f"Question detected from {customer_name or handle}: {interpretation}")
                    send_email_notification(customer_info, text, interpretation, suggested)
                else:
                    logger.debug(f"Not a question, skipping: {text[:30]}...")

                # Update last processed timestamp
                if msg['date'] > last_processed_timestamp:
                    last_processed_timestamp = msg['date']

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    run_daemon()
