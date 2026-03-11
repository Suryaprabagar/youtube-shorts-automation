"""
get_refresh_token.py
════════════════════
One-time local script to generate your YouTube OAuth 2.0 refresh token.

Run this on your LOCAL machine (not in GitHub Actions).
It will open a browser, ask you to sign in with your YouTube channel
Google account, and print the refresh token you need to add to GitHub Secrets.

Usage:
    python get_refresh_token.py

Requirements (already in requirements.txt):
    pip install google-auth-oauthlib google-auth-httplib2

You need:
  - Your OAuth Client ID and Client Secret from Google Cloud Console
    (APIs & Services → Credentials → your Desktop OAuth client)
"""

import os
import sys
import json

# ── Try loading from .env if present ──────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional here


def get_credentials_interactively() -> tuple[str, str]:
    """Prompt the user for Client ID and Secret if not in env."""
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()

    if not client_id:
        print("\nEnter your Google OAuth Client ID")
        print("(Google Cloud Console → APIs & Services → Credentials → your Desktop client)")
        client_id = input("Client ID: ").strip()

    if not client_secret:
        print("\nEnter your Google OAuth Client Secret")
        client_secret = input("Client Secret: ").strip()

    if not client_id or not client_secret:
        print("\n❌ Client ID and Client Secret are both required.")
        sys.exit(1)

    return client_id, client_secret


def main():
    print("=" * 60)
    print("  YouTube OAuth 2.0 Refresh Token Generator")
    print("=" * 60)
    print()
    print("This will open your browser to authenticate with Google.")
    print("Sign in with the Google account that OWNS your YouTube channel.")
    print()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("❌ Missing dependency. Run:")
        print("   pip install google-auth-oauthlib")
        sys.exit(1)

    client_id, client_secret = get_credentials_interactively()

    # Build the client config dict (same format as downloaded JSON)
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    print("\n🌐 Opening browser for Google sign-in...")
    print("   (If the browser doesn't open automatically, copy the URL printed below)\n")

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    # Try local server first, fall back to console flow
    try:
        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
        )
    except Exception:
        print("⚠️  Local server failed. Using console-based flow instead.")
        credentials = flow.run_console()

    print("\n" + "=" * 60)
    print("✅  Authentication successful!")
    print("=" * 60)
    print()
    print("Add the following as GitHub Repository Secrets:")
    print("  Settings → Secrets and variables → Actions → New repository secret")
    print()
    print(f"  YOUTUBE_CLIENT_ID     = {credentials.client_id}")
    print(f"  YOUTUBE_CLIENT_SECRET = {credentials.client_secret}")
    print(f"  YOUTUBE_REFRESH_TOKEN = {credentials.refresh_token}")
    print()
    print("─" * 60)
    print("REFRESH TOKEN (copy this to GitHub Secrets):")
    print()
    print(credentials.refresh_token)
    print()
    print("─" * 60)

    # Also save to a local file for convenience (gitignored)
    output = {
        "YOUTUBE_CLIENT_ID": credentials.client_id,
        "YOUTUBE_CLIENT_SECRET": credentials.client_secret,
        "YOUTUBE_REFRESH_TOKEN": credentials.refresh_token,
    }
    token_file = "youtube_tokens.json"
    with open(token_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n💾 Tokens also saved to: {token_file}")
    print("   ⚠️  This file is gitignored — never commit it!")
    print("\n🎉 Done! Add YOUTUBE_REFRESH_TOKEN to GitHub Secrets and you're ready.")


if __name__ == "__main__":
    main()
