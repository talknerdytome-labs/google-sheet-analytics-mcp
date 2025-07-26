#!/usr/bin/env python3
"""
Google Sheets Analytics MCP - Setup Script
Automates the complete setup process after git clone.
"""

import os
import sys
import subprocess
import json

def check_python_version():
    """Check if Python version is 3.8+"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ is required")
        print(f"📍 Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True

def create_virtual_environment():
    """Create and activate virtual environment"""
    print("\n🔧 Setting up virtual environment...")
    
    if os.path.exists('venv'):
        print("✅ Virtual environment already exists")
        return True
    
    try:
        subprocess.run([sys.executable, '-m', 'venv', 'venv'], check=True)
        print("✅ Virtual environment created")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        return False

def install_dependencies():
    """Install Python dependencies"""
    print("\n📦 Installing dependencies...")
    
    pip_path = os.path.join('venv', 'bin', 'pip')
    if os.name == 'nt':  # Windows
        pip_path = os.path.join('venv', 'Scripts', 'pip.exe')
    
    try:
        subprocess.run([pip_path, 'install', '-r', 'requirements.txt'], check=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def check_credentials():
    """Check if credentials.json exists"""
    print("\n🔐 Checking Google API credentials...")
    
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json not found")
        print("\n📋 Please follow these steps:")
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/")
        print("2. Create a new project or select existing one")
        print("3. Enable Google Sheets API")
        print("4. Create OAuth2 credentials (Desktop application)")
        print("5. Download the JSON file and save as 'credentials.json' in this directory")
        print("\n🔄 Run this setup script again after adding credentials.json")
        return False
    
    try:
        with open('credentials.json', 'r') as f:
            creds = json.load(f)
        
        if 'installed' not in creds:
            print("❌ Invalid credentials.json format")
            print("📋 Make sure you downloaded 'Desktop application' credentials")
            return False
        
        print("✅ credentials.json looks good")
        return True
    except Exception as e:
        print(f"❌ Error reading credentials.json: {e}")
        return False

def run_oauth_setup():
    """Run OAuth authentication"""
    print("\n🚀 Starting OAuth authentication...")
    
    python_path = os.path.join('venv', 'bin', 'python')
    if os.name == 'nt':  # Windows
        python_path = os.path.join('venv', 'Scripts', 'python.exe')
    
    try:
        # Run OAuth setup automatically
        result = subprocess.run([python_path, 'oauth_setup.py', '--auto'], 
                              capture_output=False, text=True)
        
        if result.returncode == 0:
            print("✅ OAuth authentication completed!")
            return True
        else:
            print("❌ OAuth authentication failed")
            print("🔄 Try running manually: python oauth_setup.py")
            return False
            
    except Exception as e:
        print(f"❌ Error running OAuth setup: {e}")
        return False

def show_claude_config():
    """Show Claude Desktop configuration"""
    print("\n⚙️  CLAUDE DESKTOP CONFIGURATION")
    print("=" * 50)
    
    project_path = os.path.abspath('.')
    python_path = os.path.join(project_path, 'venv', 'bin', 'python')
    server_path = os.path.join(project_path, 'mcp_server.py')
    
    if os.name == 'nt':  # Windows
        python_path = os.path.join(project_path, 'venv', 'Scripts', 'python.exe')
    
    config = {
        "mcpServers": {
            "google-sheets-analytics": {
                "command": python_path,
                "args": [server_path],
                "cwd": project_path
            }
        }
    }
    
    print("📋 Add this to your Claude Desktop settings:")
    print(json.dumps(config, indent=2))
    print("\n📍 Steps:")
    print("1. Open Claude Desktop")
    print("2. Go to Settings > Developer")
    print("3. Add the configuration above")
    print("4. Restart Claude Desktop completely")
    print("5. Test with: 'Analyze this sheet: [paste Google Sheets URL]'")

def main():
    """Main setup process"""
    print("🚀 GOOGLE SHEETS ANALYTICS MCP - SETUP")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Create virtual environment
    if not create_virtual_environment():
        return False
    
    # Install dependencies
    if not install_dependencies():
        return False
    
    # Check credentials
    if not check_credentials():
        return False
    
    # Run OAuth setup
    if not run_oauth_setup():
        return False
    
    # Show Claude Desktop config
    show_claude_config()
    
    print("\n🎉 SETUP COMPLETE!")
    print("✅ Virtual environment created")
    print("✅ Dependencies installed") 
    print("✅ OAuth authentication completed")
    print("✅ Ready to use with Claude Desktop!")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        print("\n❌ Setup failed. Please check the errors above.")
        sys.exit(1)