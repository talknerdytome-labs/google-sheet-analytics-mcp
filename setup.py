#!/usr/bin/env python3
"""Unified setup script for Google Sheets Analytics MCP server"""

import os
import sys
import json
import platform
import shutil
import subprocess
from pathlib import Path

def get_claude_config_path():
    """Get the Claude Desktop configuration file path based on OS"""
    system = platform.system()
    home = Path.home()
    
    if system == "Darwin":  # macOS
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    else:  # Linux
        return home / ".config" / "Claude" / "claude_desktop_config.json"

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n📋 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Error: {result.stderr}")
            return False
        print(f"✅ Success")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def setup_claude_desktop(project_dir):
    """Configure Claude Desktop to use the MCP server"""
    config_path = get_claude_config_path()
    
    print("\n🔧 Configuring Claude Desktop...")
    
    # Check if Claude Desktop config directory exists
    if not config_path.parent.exists():
        print(f"⚠️  Claude Desktop config directory not found: {config_path.parent}")
        print("📋 Please ensure Claude Desktop is installed")
        print("   You can configure it manually later by running: python3 setup.py --claude-only")
        return False
    
    # Load existing config or create new one
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            print(f"✅ Found existing Claude Desktop config")
        except Exception as e:
            print(f"⚠️  Error reading config: {e}")
            config = {}
    
    # Ensure mcpServers section exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    
    # Add our server configuration
    venv_python = project_dir / "venv" / "bin" / "python"
    if platform.system() == "Windows":
        venv_python = project_dir / "venv" / "Scripts" / "python.exe"
    
    server_config = {
        "command": str(venv_python),
        "args": [
            str(project_dir / "src" / "mcp_server.py")
        ],
        "env": {
            "PYTHONPATH": str(project_dir)
        }
    }
    
    config["mcpServers"]["google-sheets-analytics"] = server_config
    
    # Back up existing config
    if config_path.exists():
        backup_path = config_path.with_suffix('.json.backup')
        shutil.copy2(config_path, backup_path)
        print(f"📁 Backed up existing config to: {backup_path}")
    
    # Write updated config
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"✅ Updated Claude Desktop config: {config_path}")
        return True
    except Exception as e:
        print(f"❌ Error writing config: {e}")
        return False

def main(claude_only=False):
    """Main setup process"""
    print("🚀 Google Sheets Analytics MCP - Setup")
    print("=" * 50)
    
    project_dir = Path(__file__).parent.absolute()
    os.chdir(project_dir)
    
    if claude_only:
        # Just configure Claude Desktop
        if setup_claude_desktop(project_dir):
            print("\n✅ Claude Desktop configured!")
            print("\n📋 Next steps:")
            print("1. Restart Claude Desktop")
            print("2. The MCP server should appear in Claude")
        return
    
    # Full setup process
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        return False
    
    # 1. Create virtual environment if it doesn't exist
    venv_path = project_dir / "venv"
    if not venv_path.exists():
        if not run_command("python3 -m venv venv", "Creating virtual environment"):
            return False
    else:
        print("✅ Virtual environment already exists")
    
    # 2. Install dependencies
    pip_cmd = "venv/bin/pip" if os.name != 'nt' else "venv\\Scripts\\pip"
    if not run_command(f"{pip_cmd} install -r requirements.txt", "Installing dependencies"):
        return False
    
    # 3. Check for credentials.json
    creds_paths = [
        project_dir / 'config' / 'credentials.json',
        project_dir / 'credentials.json'
    ]
    
    creds_found = any(p.exists() for p in creds_paths)
    if not creds_found:
        print("\n⚠️  No credentials.json found!")
        print("Please download it from Google Cloud Console:")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Create OAuth 2.0 Client ID (Desktop type)")
        print("3. Download and save as credentials.json in:")
        print(f"   - {creds_paths[0]} (recommended)")
        print(f"   - {creds_paths[1]}")
        return False
    
    # 4. Run OAuth setup
    python_cmd = "venv/bin/python" if os.name != 'nt' else "venv\\Scripts\\python"
    oauth_cmd = f"{python_cmd} src/auth/oauth_setup.py --auto"
    
    print("\n🔐 Setting up Google OAuth...")
    print("This will open your browser for authentication.")
    input("Press Enter to continue...")
    
    if not run_command(oauth_cmd, "Running OAuth setup"):
        print("\n⚠️  Automatic OAuth setup failed. Trying manual setup...")
        if not run_command(f"{python_cmd} src/auth/oauth_setup.py --manual", "Running manual OAuth setup"):
            return False
    
    # 5. Configure Claude Desktop
    setup_claude_desktop(project_dir)
    
    print("\n✅ Setup Complete!")
    print("=" * 50)
    print("\n📋 Next steps:")
    print("1. Restart Claude Desktop")
    print("2. The MCP server should appear in Claude")
    print("\n🔧 Useful commands:")
    print(f"   Check auth status: {python_cmd} src/auth/oauth_setup.py --status")
    print(f"   Test connection: {python_cmd} src/auth/oauth_setup.py --test")
    print(f"   Configure Claude Desktop: python3 setup.py --claude-only")
    
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup Google Sheets Analytics MCP server')
    parser.add_argument('--claude-only', action='store_true', 
                        help='Only configure Claude Desktop (skip other setup steps)')
    
    args = parser.parse_args()
    
    success = main(claude_only=args.claude_only)
    sys.exit(0 if success else 1)