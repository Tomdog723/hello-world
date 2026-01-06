"""
Example configuration file for iMessage Question Monitor
Copy this to config.py and update with your actual paths and settings
"""

import os

# =============================================================================
# GOOGLE CALENDAR CONFIGURATION
# =============================================================================
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = '/Users/YOUR_USERNAME/path/to/credentials.json'
TOKEN_FILE = '/Users/YOUR_USERNAME/path/to/token.json'

# =============================================================================
# iMESSAGE DATABASE
# =============================================================================
# Default location - usually doesn't need to change
MESSAGES_DB = '/Users/YOUR_USERNAME/Library/Messages/chat.db'

# =============================================================================
# LOGGING
# =============================================================================
LOG_FILE = '/Users/YOUR_USERNAME/path/to/monitor.log'

# =============================================================================
# EMAIL SETTINGS
# =============================================================================
GMAIL_ADDRESS = 'your-email@gmail.com'
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')

# =============================================================================
# API KEYS
# =============================================================================
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# =============================================================================
# DAEMON SETTINGS
# =============================================================================
POLL_INTERVAL = 10  # seconds between checks
STARTUP_LOOKBACK_HOURS = 1  # how far back to check on startup
