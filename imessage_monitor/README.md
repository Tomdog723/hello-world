# iMessage Question Monitor

Intelligent daemon that monitors incoming iMessages, uses Claude AI to detect customer questions, and sends email notifications with suggested responses.

## Overview

This tool automatically:
- Monitors your Mac's iMessage database for new incoming messages
- Looks up sender information in Google Calendar
- Uses Claude AI to intelligently determine if a message requires a response
- Sends email notifications with customer context and AI-generated response suggestions

Perfect for service businesses that receive customer questions via iMessage!

## Features

- **AI-Powered Question Detection**: Uses Claude to intelligently distinguish questions from simple confirmations
- **Customer Lookup**: Automatically matches phone numbers to Google Calendar appointments
- **Smart Notifications**: Emails include customer name, next appointment, question interpretation, and suggested responses
- **Robust Matching**: Handles multiple phone number formats
- **Lightweight**: Polls the iMessage database every 10 seconds
- **Configurable**: Easy to customize polling intervals, lookback periods, and more

## Requirements

### System Requirements
- **macOS only** (requires access to iMessage database at `~/Library/Messages/chat.db`)
- Python 3.8 or higher
- Full Disk Access permission for Terminal/your Python environment

### API Keys & Credentials
1. **Anthropic API Key** - Get from https://console.anthropic.com/
2. **Google Calendar API** - Set up at https://console.cloud.google.com/
3. **Gmail App Password** - Generate at https://myaccount.google.com/apppasswords

## Installation

### 1. Clone this repository
```bash
git clone <your-repo-url>
cd imessage_monitor
```

### 2. Install Python dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Set up Google Calendar API

a. Go to [Google Cloud Console](https://console.cloud.google.com/)
b. Create a new project (or select existing)
c. Enable the Google Calendar API
d. Create OAuth 2.0 credentials (Desktop app)
e. Download the credentials JSON file
f. Save it to your desired location (update `CREDENTIALS_FILE` path in script)

### 4. Configure the script

Edit `question_monitor.py` and update these paths in the CONFIGURATION section:

```python
# Google Calendar
CREDENTIALS_FILE = '/path/to/your/credentials.json'
TOKEN_FILE = '/path/to/your/token.json'

# Logging
LOG_FILE = '/path/to/your/monitor.log'

# Email settings
GMAIL_ADDRESS = 'your-email@gmail.com'
```

### 5. Set environment variables

```bash
# Anthropic API Key
export ANTHROPIC_API_KEY='your-api-key-here'

# Gmail App Password
export GMAIL_APP_PASSWORD='your-app-password-here'
```

For permanent setup, add these to your `~/.zshrc` or `~/.bash_profile`:

```bash
echo 'export ANTHROPIC_API_KEY="your-api-key-here"' >> ~/.zshrc
echo 'export GMAIL_APP_PASSWORD="your-app-password-here"' >> ~/.zshrc
source ~/.zshrc
```

### 6. Grant Full Disk Access

The script needs permission to read the iMessage database:

1. Open System Preferences > Security & Privacy > Privacy
2. Select "Full Disk Access"
3. Click the lock to make changes
4. Add Terminal (or your Python IDE/environment)
5. Restart Terminal

## Usage

### Run the monitor

```bash
python3 question_monitor.py
```

The daemon will:
1. Start monitoring for new messages
2. Look back 1 hour on startup (configurable)
3. Process new incoming messages every 10 seconds
4. Log activity to both console and log file
5. Send email notifications for detected questions

### Run in background

```bash
# Using nohup
nohup python3 question_monitor.py &

# Or use screen
screen -S imessage-monitor
python3 question_monitor.py
# Ctrl+A, then D to detach
```

### Stop the monitor

Press `Ctrl+C` to gracefully shut down, or:

```bash
# Find the process
ps aux | grep question_monitor.py

# Kill it
kill <PID>
```

## Configuration Options

Edit these constants in `question_monitor.py`:

```python
POLL_INTERVAL = 10                  # Seconds between checks
STARTUP_LOOKBACK_HOURS = 1          # How far back to check on startup
GMAIL_ADDRESS = 'your@gmail.com'    # Email to send notifications to
```

## How It Works

### 1. Message Detection
- Reads the iMessage SQLite database at `~/Library/Messages/chat.db`
- Filters for incoming messages (`is_from_me = 0`)
- Skips reactions/tapbacks

### 2. Customer Lookup
- Extracts phone number from message
- Searches Google Calendar for matching events (next 30 days)
- Returns customer name, next appointment, and calendar info

### 3. AI Question Detection
Claude analyzes each message to determine if it requires a response:

**Triggers response:**
- Rescheduling/cancellation requests
- Questions about timing, pricing, services
- Requests for callbacks
- Complaints or concerns

**Does NOT trigger:**
- Simple confirmations ("ok", "sounds good", "thank you")
- Reactions or emojis
- Statements not requiring replies

### 4. Email Notification
Sends a formatted email with:
- Customer name and phone
- Next appointment date/time
- Full message text
- AI interpretation of the question
- Suggested response

## Troubleshooting

### "Database not found" error
- Ensure you're on macOS
- Check the path to `chat.db` is correct
- Verify Full Disk Access permissions

### "ANTHROPIC_API_KEY not set" warning
- Export the environment variable before running
- Script will fall back to simple "?" detection

### "GMAIL_APP_PASSWORD not set" warning
- Set the environment variable
- Generate an app password (don't use your regular Gmail password)

### Google Calendar authentication
- On first run, a browser will open for OAuth consent
- Grant calendar read permissions
- Token is saved for future runs

### Messages not detected
- Check the `POLL_INTERVAL` (default 10 seconds)
- Verify message is incoming (`is_from_me = 0`)
- Check logs for errors

## Security Notes

- **Never commit API keys or passwords to version control**
- Use environment variables for sensitive data
- Google Calendar API uses OAuth 2.0 (secure)
- iMessage database is read-only access
- Email sent over SMTP SSL (port 465)

## Logging

Logs are written to both:
- Console (stdout)
- Log file (specified in `LOG_FILE`)

Log levels:
- `INFO`: Normal operation, message processing
- `WARNING`: Missing configuration
- `ERROR`: API failures, database errors
- `DEBUG`: Skipped messages (non-questions)

## Customization Ideas

- Change the Claude model (currently `claude-sonnet-4-20250514`)
- Adjust the question detection prompt
- Add SMS support (using Twilio API)
- Store processed messages in a separate database
- Add Slack notifications instead of email
- Filter by specific contacts or phone numbers

## License

MIT License - use freely!

## Contributing

Pull requests welcome! Please ensure:
- Code follows existing style
- Update README for new features
- Test on macOS before submitting

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review the logs for error messages
3. Open an issue on GitHub

---

**Note**: This tool is designed for macOS only due to iMessage database access requirements.
