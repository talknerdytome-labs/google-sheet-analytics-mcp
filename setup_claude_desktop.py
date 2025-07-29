#!/usr/bin/env python3
"""
Setup script to configure Google Sheets Analytics MCP server for Claude Desktop
"""

import os
import json
import platform
import shutil
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

def setup_claude_desktop():
    """Configure Claude Desktop to use the Google Sheets Analytics MCP server"""
    
    # Get paths
    config_path = get_claude_config_path()
    project_dir = Path(__file__).parent.absolute()
    
    print("🚀 Google Sheets Analytics MCP - Claude Desktop Setup")
    print("=" * 50)
    
    # Check if Claude Desktop config exists
    if not config_path.parent.exists():
        print(f"❌ Claude Desktop config directory not found: {config_path.parent}")
        print("📋 Please ensure Claude Desktop is installed")
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
    if not venv_python.exists():
        print(f"⚠️  Virtual environment not found at {venv_python}")
        print("📋 Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt")
        return False
    
    server_config = {
        "command": str(venv_python),
        "args": [
            str(project_dir / "src" / "mcp_server.py")
        ],
        "env": {
            "PYTHONPATH": str(project_dir / "src")
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
    except Exception as e:
        print(f"❌ Error writing config: {e}")
        return False
    
    # Display instructions
    print("\n📋 Setup Complete!")
    print("=" * 50)
    print("Next steps:")
    print("1. Restart Claude Desktop")
    print("2. In Claude, you'll have access to these tools:")
    print("   - instant_setup: Sync a Google Sheet by URL")
    print("   - ask_data: Query the synced data with natural language")
    print("\n🔧 Example usage:")
    print('   Use instant_setup with URL: "https://docs.google.com/spreadsheets/d/..."')
    print('   Then ask_data: "Show me all rows where sales > 1000"')
    
    return True

if __name__ == "__main__":
    success = setup_claude_desktop()
    exit(0 if success else 1)