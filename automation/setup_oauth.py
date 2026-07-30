"""
One-time Gmail OAuth setup.
Run this once: python3 setup_oauth.py
"""

import os
import pickle

from config import GMAIL_CREDS_PATH, GMAIL_SCOPES, GMAIL_TOKEN_PATH


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        print("\n► Installing Google libraries...")
        os.system("pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib --break-system-packages -q")
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request

    if not os.path.exists(GMAIL_CREDS_PATH):
        print("""
╔══════════════════════════════════════════════════════════╗
║  gmail_credentials.json NOT FOUND                        ║
╠══════════════════════════════════════════════════════════╣
║  Download it from Google Cloud Console:                  ║
║  APIs & Services → Credentials → your OAuth client      ║
║  → Download JSON → rename to gmail_credentials.json     ║
║  → place in automation/ folder                           ║
╚══════════════════════════════════════════════════════════╝
""")
        return

    # Delete old token if it exists (fresh auth with full scopes)
    if os.path.exists(GMAIL_TOKEN_PATH):
        os.remove(GMAIL_TOKEN_PATH)
        print("► Removed old token, starting fresh auth...")

    flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDS_PATH, GMAIL_SCOPES)
    creds = flow.run_local_server(port=0)

    with open(GMAIL_TOKEN_PATH, "wb") as f:
        pickle.dump(creds, f)

    print(f"""
╔══════════════════════════════════════════════════════╗
║  ✅ Gmail OAuth authorised successfully!             ║
╠══════════════════════════════════════════════════════╣
║  Token saved to: gmail_token.pickle                  ║
║  Scopes: send + read inbox + mark read               ║
║                                                      ║
║  Next steps:                                         ║
║    python3 run_daily.py --dry-run   (preview)        ║
║    python3 run_daily.py             (live run)       ║
║    bash setup_cron.sh               (set up 9AM IST) ║
╚══════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
