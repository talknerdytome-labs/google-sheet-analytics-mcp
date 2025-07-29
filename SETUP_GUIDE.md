# Google Sheets Analytics MCP - Setup Guide

## Quick Start

1. **Install dependencies** (if not already done):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set up Google OAuth** (if not already done):
   ```bash
   # Copy your credentials.json from Google Cloud Console to this directory
   cp /path/to/your/credentials.json .
   
   # Run OAuth setup
   python3 src/auth/oauth_setup.py --auto
   ```

3. **Configure Claude Desktop**:
   ```bash
   python3 setup_claude_desktop.py
   ```

4. **Restart Claude Desktop**

## Using the MCP Server

Once configured, you'll have access to two tools in Claude:

### 1. instant_setup
Syncs a Google Sheet to local database.

Example:
```
Use instant_setup to sync this sheet: https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit
```

Parameters:
- `spreadsheet_url`: Google Sheets URL (required)
- `sync_mode`: "full", "smart", or "incremental" (optional, default: "smart")
- `performance_tier`: "basic", "optimized", or "enterprise" (optional, default: "optimized")

### 2. ask_data
Query the synced data using natural language.

Example:
```
Use ask_data to show me all sales data from January
```

Parameters:
- `query`: Your natural language question (required)
- `format`: "compact", "full", "summary", or "auto" (optional, default: "auto")

## Troubleshooting

### OAuth Issues
- Ensure credentials.json is valid
- Check token expiration: `python3 src/auth/oauth_setup.py --status`
- Reset OAuth if needed: `python3 src/auth/oauth_setup.py --reset`

### MCP Server Not Appearing in Claude
1. Check Claude Desktop is fully closed
2. Verify config was written: `cat ~/Library/Application\ Support/Claude/claude_desktop_config.json`
3. Restart Claude Desktop
4. Check logs in Claude Desktop developer console

### Database Issues
- Database is created automatically on first sync
- Located at: `sheets_data.sqlite`
- To reset: Simply delete the file

## Manual Configuration

If automatic setup doesn't work, add this to your Claude Desktop config:

```json
{
  "mcpServers": {
    "google-sheets-analytics": {
      "command": "python3",
      "args": [
        "/full/path/to/google-sheet-analytics-mcp/src/mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "/full/path/to/google-sheet-analytics-mcp/src"
      }
    }
  }
}
```

Config file locations:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`