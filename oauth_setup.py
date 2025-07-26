#!/usr/bin/env python3
"""
Google Sheets Analytics MCP - OAuth Setup Tool
Consolidates all OAuth flows into one comprehensive tool.
"""

import os
import sys
import time
import json
import threading
import webbrowser
import http.server
import socketserver
import urllib.parse
from google_auth_oauthlib.flow import InstalledAppFlow
from urllib.parse import urlparse, parse_qs

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

class CustomOAuthHandler(http.server.BaseHTTPRequestHandler):
    """Custom handler that displays the auth code prominently"""
    
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_path.query)
        
        if 'code' in params:
            auth_code = params['code'][0]
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Google Sheets Analytics MCP - Authentication Success!</title>
                <style>
                    body {{ 
                        font-family: Arial, sans-serif; 
                        max-width: 800px; 
                        margin: 50px auto; 
                        padding: 20px;
                        background: #f5f5f5;
                    }}
                    .container {{
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        text-align: center;
                    }}
                    .success {{ color: #28a745; font-size: 24px; margin-bottom: 20px; }}
                    .status {{ 
                        margin-top: 20px;
                        padding: 15px;
                        background: #d4edda;
                        border: 1px solid #c3e6cb;
                        border-radius: 5px;
                        color: #155724;
                        font-size: 18px;
                    }}
                    .checkmark {{
                        font-size: 48px;
                        color: #28a745;
                        margin-bottom: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">&#10004;</div>
                    <div class="success">Authentication Successful!</div>
                    
                    <div class="status">
                        <strong>Authentication completed successfully!</strong><br><br>
                        Your Google Sheets access has been authorized.<br>
                        You can close this browser window now.
                    </div>
                </div>
            </body>
            </html>
            """
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html_content.encode())
            
            self.server.auth_code = auth_code
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h1>Error: No authorization code received</h1>")
    
    def log_message(self, format, *args):
        pass

class OAuthSetup:
    """Consolidated OAuth setup tool with multiple methods"""
    
    def __init__(self):
        self.credentials_file = 'credentials.json'
        self.token_file = 'token.json'
    
    def check_prerequisites(self):
        """Check if all prerequisites are met"""
        print("🔍 Checking prerequisites...")
        
        if not os.path.exists(self.credentials_file):
            print(f"❌ {self.credentials_file} not found!")
            print("📋 Please download your OAuth2 credentials from Google Cloud Console")
            return False
        
        try:
            with open(self.credentials_file, 'r') as f:
                creds = json.load(f)
                
            if 'installed' not in creds:
                print("❌ Invalid credentials.json format!")
                print("📋 Make sure you downloaded 'Desktop application' credentials")
                return False
                
            client_id = creds['installed'].get('client_id', '')
            if 'your-client-id' in client_id:
                print("❌ Credentials file contains placeholder values!")
                print("📋 Please download real credentials from Google Cloud Console")
                return False
                
            print("✅ Credentials file looks good")
            return True
            
        except Exception as e:
            print(f"❌ Error reading credentials: {e}")
            return False
    
    def test_basic_oauth(self):
        """Test basic OAuth functionality"""
        print("🧪 Testing basic OAuth setup...")
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
            print("✅ OAuth flow created successfully")
            return True
        except Exception as e:
            print(f"❌ OAuth flow creation failed: {e}")
            return False
    
    def run_automatic_oauth(self):
        """Run OAuth with custom server (recommended)"""
        print("🚀 AUTOMATIC OAUTH WITH CUSTOM SERVER")
        print("=" * 50)
        
        # Check redirect URI
        try:
            with open(self.credentials_file, 'r') as f:
                creds = json.load(f)
                redirect_uris = creds['installed'].get('redirect_uris', [])
                
                if 'http://localhost:8080' not in redirect_uris:
                    print("⚠️  WARNING: http://localhost:8080 not in redirect URIs")
                    print("📋 Please add it to your Google Cloud Console OAuth settings")
                    print("   1. Go to Google Cloud Console > APIs & Services > Credentials")
                    print("   2. Edit your OAuth 2.0 Client ID")
                    print("   3. Add 'http://localhost:8080' to Authorized redirect URIs")
                    print("   4. Save changes")
                    input("Press Enter after updating Google Cloud Console...")
        except:
            pass
        
        # Start local server
        port = 8080
        
        try:
            with socketserver.TCPServer(("", port), CustomOAuthHandler) as httpd:
                httpd.auth_code = None
                
                print(f"🌐 Starting local server on http://localhost:{port}")
                
                # Start server in background
                server_thread = threading.Thread(target=httpd.serve_forever)
                server_thread.daemon = True
                server_thread.start()
                
                # Create OAuth flow
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                flow.redirect_uri = f'http://localhost:{port}'
                
                # Get authorization URL
                auth_url, _ = flow.authorization_url(
                    prompt='select_account',
                    access_type='offline'
                )
                
                print("🔗 Opening Google OAuth...")
                print("👥 You'll be able to select between your Google accounts")
                
                # Open browser
                try:
                    webbrowser.open(auth_url)
                    print("✅ Browser opened automatically")
                except:
                    print("❌ Could not open browser. Please open this URL:")
                    print(auth_url)
                
                print("⏳ Waiting for authentication...")
                
                # Wait for auth code
                timeout = 300  # 5 minutes
                start_time = time.time()
                
                while httpd.auth_code is None:
                    if time.time() - start_time > timeout:
                        print("❌ Timeout waiting for authentication")
                        httpd.shutdown()
                        return False
                    time.sleep(1)
                
                auth_code = httpd.auth_code
                httpd.shutdown()
                
                return self._complete_authentication(flow, auth_code)
                
        except OSError as e:
            if "Address already in use" in str(e):
                print(f"❌ Port {port} is already in use")
                print("🔄 Trying manual OAuth instead...")
                return self.run_manual_oauth()
            else:
                print(f"❌ Server error: {e}")
                return False
    
    def run_manual_oauth(self):
        """Run manual OAuth with URL copy/paste"""
        print("📋 MANUAL OAUTH (Copy/Paste URL)")
        print("=" * 40)
        
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
        flow.redirect_uri = 'http://localhost'
        
        # Get authorization URL
        auth_url, _ = flow.authorization_url(
            prompt='select_account',
            access_type='offline'
        )
        
        print("🔗 OAuth URL (copy this to your browser):")
        print(auth_url)
        print()
        print("📋 Steps:")
        print("1. Copy the URL above")
        print("2. Open it in an incognito/private browser window")
        print("3. Select the correct Google account")
        print("4. Grant permissions")
        print("5. Copy the ENTIRE redirect URL from the error page")
        print()
        
        # Wait for user to paste redirect URL
        redirect_url = input("📥 Paste the full redirect URL here: ").strip()
        
        try:
            # Extract auth code from URL
            parsed_url = urlparse(redirect_url)
            query_params = parse_qs(parsed_url.query)
            
            if 'code' in query_params:
                auth_code = query_params['code'][0]
                return self._complete_authentication(flow, auth_code)
            else:
                print("❌ No authorization code found in URL")
                return False
                
        except Exception as e:
            print(f"❌ Error processing URL: {e}")
            return False
    
    def _complete_authentication(self, flow, auth_code):
        """Complete the authentication process"""
        print(f"✅ Received authorization code: {auth_code[:20]}...")
        
        try:
            print("🔄 Exchanging code for access token...")
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            
            # Save credentials
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
            
            print("🎉 SUCCESS! Authentication complete!")
            print(f"💾 Token saved to {self.token_file}")
            print("🚀 You can now sync your Google Sheets data in Claude Desktop!")
            return True
            
        except Exception as e:
            print(f"❌ Error completing authentication: {e}")
            return False
    
    def reset_authentication(self):
        """Reset authentication by removing token file"""
        if os.path.exists(self.token_file):
            os.remove(self.token_file)
            print(f"🗑️  Removed {self.token_file}")
        else:
            print(f"ℹ️  No {self.token_file} file found")
    
    def show_status(self):
        """Show current authentication status"""
        print("📊 AUTHENTICATION STATUS")
        print("=" * 30)
        
        creds_exists = os.path.exists(self.credentials_file)
        token_exists = os.path.exists(self.token_file)
        
        print(f"📋 Credentials file: {'✅ Found' if creds_exists else '❌ Missing'}")
        print(f"🔑 Token file: {'✅ Found' if token_exists else '❌ Missing'}")
        
        if token_exists:
            try:
                with open(self.token_file, 'r') as f:
                    token_data = json.load(f)
                    print("✅ Authentication appears to be complete")
                    print("🚀 You should be able to sync Google Sheets data")
            except:
                print("⚠️  Token file exists but may be corrupted")
        else:
            print("❌ Not authenticated - run OAuth setup")
    
    def run_interactive_setup(self):
        """Interactive setup menu"""
        while True:
            print("\\n" + "="*60)
            print("🔗 GOOGLE SHEETS ANALYTICS MCP - OAUTH SETUP")
            print("="*60)
            
            self.show_status()
            
            print("\\n📋 OPTIONS:")
            print("1. 🚀 Automatic OAuth (Recommended)")
            print("2. 📋 Manual OAuth (Copy/Paste URL)")
            print("3. 🧪 Test Prerequisites")
            print("4. 🗑️  Reset Authentication")
            print("5. 📊 Show Status")
            print("6. ❌ Exit")
            
            choice = input("\\nSelect option (1-6): ").strip()
            
            if choice == '1':
                if self.check_prerequisites():
                    self.run_automatic_oauth()
                    break
            elif choice == '2':
                if self.check_prerequisites():
                    self.run_manual_oauth()
                    break
            elif choice == '3':
                self.check_prerequisites()
                self.test_basic_oauth()
            elif choice == '4':
                self.reset_authentication()
            elif choice == '5':
                continue  # Status already shown at top
            elif choice == '6':
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please select 1-6.")

def main():
    """Main entry point"""
    oauth_setup = OAuthSetup()
    
    # Check if we should run automatically
    if len(sys.argv) > 1:
        if sys.argv[1] == '--auto':
            oauth_setup.check_prerequisites() and oauth_setup.run_automatic_oauth()
        elif sys.argv[1] == '--manual':
            oauth_setup.check_prerequisites() and oauth_setup.run_manual_oauth()
        elif sys.argv[1] == '--status':
            oauth_setup.show_status()
        elif sys.argv[1] == '--reset':
            oauth_setup.reset_authentication()
        else:
            print("Usage: python oauth_setup.py [--auto|--manual|--status|--reset]")
    else:
        # Run interactive setup
        oauth_setup.run_interactive_setup()

if __name__ == "__main__":
    main()