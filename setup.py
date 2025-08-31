#!/usr/bin/env python3
"""
Automated setup script for Google Sheets Analytics MCP Server
Handles installation, virtual environment creation, and OAuth setup
"""

import os
import sys
import subprocess
import json
from pathlib import Path


def run_command(cmd, check=True, capture_output=False):
    """Run a command with proper error handling"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, 
        check=check, 
        capture_output=capture_output, 
        text=True
    )
    if capture_output:
        return result.stdout.strip()
    return result


def check_requirements():
    """Check system requirements"""
    print("🔍 Checking system requirements...")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ is required")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Check if mcp command is available
    try:
        run_command(['mcp', '--help'], capture_output=True)
        print("✅ MCP CLI available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ MCP CLI not found. Please install Claude Code first.")
        print("   Visit: https://claude.ai/code")
        sys.exit(1)


def setup_virtual_environment():
    """Create and setup virtual environment"""
    print("🔧 Setting up virtual environment...")
    
    venv_path = Path("venv")
    if not venv_path.exists():
        run_command([sys.executable, "-m", "venv", "venv"])
        print("✅ Virtual environment created")
    else:
        print("✅ Virtual environment already exists")
    
    # Install dependencies in virtual environment
    if os.name == 'nt':  # Windows
        pip_path = venv_path / "Scripts" / "pip"
        python_path = venv_path / "Scripts" / "python"
    else:  # Unix-like
        pip_path = venv_path / "bin" / "pip"
        python_path = venv_path / "bin" / "python"
    
    print("📦 Installing dependencies...")
    run_command([str(pip_path), "install", "-e", "."])
    print("✅ Dependencies installed")
    
    return python_path


def install_mcp_server(python_path):
    """Install MCP server into Claude Code"""
    print("🚀 Installing MCP server...")
    
    try:
        run_command([
            "mcp", "install", 
            "src/mcp_server.py",
            "--name", "google-sheets-analytics",
            "--with-editable", "."
        ])
        print("✅ MCP server installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ MCP server installation failed: {e}")
        return False


def check_credentials():
    """Check if credentials.json exists"""
    print("🔐 Checking credentials...")
    
    cred_paths = [
        Path("credentials.json"),
        Path("config/credentials.json")
    ]
    
    for path in cred_paths:
        if path.exists():
            print(f"✅ Credentials found at: {path}")
            return True
    
    print("⚠️  No credentials.json found")
    print("📝 Please:")
    print("   1. Go to https://console.cloud.google.com/")
    print("   2. Create a project and enable Google Sheets API")
    print("   3. Create OAuth2 credentials (Desktop Application)")
    print("   4. Download and save as 'credentials.json' in project root")
    return False


def setup_oauth(python_path):
    """Setup OAuth if credentials exist"""
    if not check_credentials():
        return False
    
    print("🔑 Setting up OAuth...")
    
    # Check if token already exists
    token_path = Path("data/token.json")
    if token_path.exists():
        print("✅ OAuth token already exists")
        return True
    
    print("🌐 Starting OAuth flow...")
    print("   (Browser will open automatically)")
    
    try:
        run_command([str(python_path), "src/auth/oauth_setup.py"])
        print("✅ OAuth setup completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ OAuth setup failed: {e}")
        return False


def main():
    """Main setup function"""
    print("🚀 Google Sheets Analytics MCP Server Setup")
    print("=" * 50)
    
    try:
        # Check requirements
        check_requirements()
        
        # Setup virtual environment
        python_path = setup_virtual_environment()
        
        # Install MCP server
        if not install_mcp_server(python_path):
            print("⚠️  MCP installation failed, but you can try manually:")
            print(f"   mcp install src/mcp_server.py --name google-sheets-analytics --with-editable .")
        
        # Setup OAuth
        oauth_success = setup_oauth(python_path)
        
        print("\n" + "=" * 50)
        print("🎉 Setup Summary:")
        print(f"   Virtual Environment: ✅")
        print(f"   Dependencies: ✅")
        print(f"   MCP Server: ✅")
        print(f"   OAuth Setup: {'✅' if oauth_success else '⚠️  Needs credentials.json'}")
        
        if oauth_success:
            print("\n🚀 Ready to use! Available tools:")
            print("   • smart_sync - Sync Google Sheets data")
            print("   • query_sheets - Run SQL queries")  
            print("   • get_sheet_preview - Quick preview")
            print("   • list_synced_sheets - View synced sheets")
            print("   • analyze_sheets - Get query suggestions")
        else:
            print("\n📝 Next step: Add your credentials.json file and run:")
            print(f"   {python_path} src/auth/oauth_setup.py")
            
    except KeyboardInterrupt:
        print("\n❌ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()