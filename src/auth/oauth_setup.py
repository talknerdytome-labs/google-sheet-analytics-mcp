#!/usr/bin/env python3
"""Unified OAuth setup for Google Sheets MCP server"""

import os
import json
import sys
import webbrowser
from pathlib import Path
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

# Allow OAuth2 over HTTP for localhost (development only)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Define paths
SCRIPT_DIR = Path(__file__).parent.parent.parent  # Back to project root
DATA_DIR = SCRIPT_DIR / 'data'
TOKEN_PATH = DATA_DIR / 'token.json'

# Try multiple locations for credentials.json
CREDENTIALS_PATHS = [
    SCRIPT_DIR / 'config' / 'credentials.json',
    SCRIPT_DIR / 'credentials.json',
]

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
REDIRECT_URI = 'http://localhost:8080'

def find_credentials() -> Optional[Path]:
    """Find credentials.json in any of the expected locations"""
    for path in CREDENTIALS_PATHS:
        if path.exists():
            return path
    return None

def check_status():
    """Check current OAuth status"""
    print("=== OAuth Status Check ===\n")
    
    creds_path = find_credentials()
    print(f"Credentials search paths: {[str(p) for p in CREDENTIALS_PATHS]}")
    print(f"Credentials found: {'✓' if creds_path else '✗'}")
    if creds_path:
        print(f"Credentials location: {creds_path}")
    
    print(f"\nToken path: {TOKEN_PATH}")
    print(f"Token exists: {'✓' if TOKEN_PATH.exists() else '✗'}")
    
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            print(f"Token valid: {'✓' if creds.valid else '✗'}")
            print(f"Token expired: {'Yes' if creds.expired else 'No'}")
            if creds.expiry:
                print(f"Expiry: {creds.expiry}")
            print(f"Has refresh token: {'✓' if creds.refresh_token else '✗'}")
        except Exception as e:
            print(f"Error reading token: {e}")
    
    return creds_path is not None and TOKEN_PATH.exists()

def reset_oauth():
    """Reset OAuth by removing existing token"""
    if TOKEN_PATH.exists():
        # Create backup
        backup_path = TOKEN_PATH.with_suffix('.json.backup')
        TOKEN_PATH.rename(backup_path)
        print(f"✓ Backed up existing token to {backup_path}")
        print("Token reset complete. Run setup again to create new token.")
    else:
        print("No existing token to reset.")

def setup_oauth_auto():
    """Run automatic OAuth setup with local server"""
    creds_path = find_credentials()
    if not creds_path:
        print("❌ Error: credentials.json not found")
        print("\nPlease download credentials.json from Google Cloud Console:")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Create or select a project")
        print("3. Create OAuth 2.0 Client ID (Desktop type)")
        print("4. Download the credentials.json")
        print(f"5. Place it in one of these locations:")
        for path in CREDENTIALS_PATHS:
            print(f"   - {path}")
        return False
    
    print(f"✓ Found credentials at {creds_path}")
    
    # Create data directory
    DATA_DIR.mkdir(exist_ok=True)
    
    try:
        # Use installed app flow for automatic handling
        flow = InstalledAppFlow.from_client_secrets_file(
            str(creds_path), SCOPES
        )
        
        print("\n🌐 Opening browser for authentication...")
        print("If browser doesn't open automatically, visit the URL shown below.")
        
        # Run local server and automatically open browser
        creds = flow.run_local_server(
            port=8080,
            success_message='Authentication successful! You can close this window.',
            open_browser=True
        )
        
        # Save credentials
        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
            'universe_domain': getattr(creds, 'universe_domain', 'googleapis.com'),
            'account': '',
            'expiry': creds.expiry.isoformat() if creds.expiry else None
        }
        
        with open(TOKEN_PATH, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print(f"\n✅ Success! Token saved to {TOKEN_PATH}")
        print("You can now use the Google Sheets MCP server.")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during authentication: {e}")
        print("\nFalling back to manual setup...")
        return setup_oauth_manual()

def setup_oauth_manual():
    """Run manual OAuth setup (no local server)"""
    creds_path = find_credentials()
    if not creds_path:
        print("❌ Error: credentials.json not found")
        return False
    
    # Create OAuth flow
    flow = Flow.from_client_secrets_file(
        str(creds_path),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Generate authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    print("\n📋 Manual OAuth Setup Instructions:")
    print("1. Open this URL in your browser:")
    print(f"\n{auth_url}\n")
    print("2. Log in with your Google account")
    print("3. Grant access to view Google Sheets")
    print("4. You'll be redirected to a URL starting with 'http://localhost:8080'")
    print("5. Copy the ENTIRE redirect URL from your browser")
    print("\nExample: http://localhost:8080/?code=4/0AQlEd8x...&scope=...")
    
    redirect_url = input("\nPaste the redirect URL here: ").strip()
    
    try:
        # Exchange code for token
        flow.fetch_token(authorization_response=redirect_url)
        
        # Save credentials
        creds = flow.credentials
        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
            'universe_domain': getattr(creds, 'universe_domain', 'googleapis.com'),
            'account': '',
            'expiry': creds.expiry.isoformat() if creds.expiry else None
        }
        
        with open(TOKEN_PATH, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print(f"\n✅ Success! Token saved to {TOKEN_PATH}")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nCommon issues:")
        print("- Make sure you copied the ENTIRE URL including all parameters")
        print("- The URL should start with 'http://localhost:8080/?code='")
        print("- Authorization codes expire quickly - try again if needed")
        return False

def test_auth():
    """Test if authentication is working"""
    if not TOKEN_PATH.exists():
        print("❌ No token found. Run setup first.")
        return False
    
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        
        # Refresh if needed
        if creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
            
            # Save refreshed token
            with open(TOKEN_PATH, 'w') as f:
                f.write(creds.to_json())
        
        # Try to build service
        service = build('sheets', 'v4', credentials=creds)
        
        # Test with Google's example spreadsheet
        test_sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        
        try:
            result = service.spreadsheets().get(spreadsheetId=test_sheet_id).execute()
            print(f"✅ Successfully accessed test spreadsheet: {result['properties']['title']}")
            return True
        except HttpError as e:
            if e.resp.status == 403:
                print("✅ Authentication working (403 is expected for example sheet)")
                return True
            else:
                print(f"❌ API Error: {e}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        return False

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Google Sheets MCP OAuth Setup')
    parser.add_argument('--auto', action='store_true', help='Run automatic setup (default)')
    parser.add_argument('--manual', action='store_true', help='Run manual setup')
    parser.add_argument('--status', action='store_true', help='Check OAuth status')
    parser.add_argument('--reset', action='store_true', help='Reset OAuth token')
    parser.add_argument('--test', action='store_true', help='Test authentication')
    
    args = parser.parse_args()
    
    # Default to auto if no args
    if not any(vars(args).values()):
        args.auto = True
    
    if args.status:
        check_status()
    elif args.reset:
        reset_oauth()
    elif args.test:
        test_auth()
    elif args.manual:
        setup_oauth_manual()
    else:  # auto
        setup_oauth_auto()

if __name__ == "__main__":
    main()