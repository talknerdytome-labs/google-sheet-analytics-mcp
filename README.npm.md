# Google Sheets MCP Server

A Node.js/Python MCP server for analyzing Google Sheets data using natural language.

## Quick Start

```bash
npm install -g @tntm/google-sheets-mcp
```

## Prerequisites

- Node.js 16+
- Python 3.8-3.12
- Google Cloud project with Sheets API enabled

## Setup

### 1. Install the package

```bash
npm install -g @tntm/google-sheets-mcp
```

### 2. Set up Google OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable Google Sheets API
4. Create OAuth 2.0 credentials
5. Download credentials as `credentials.json`

### 3. Configure Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "npx",
      "args": ["@tntm/google-sheets-mcp"]
    }
  }
}
```

## Available Tools

- **smart_sync** - Intelligently sync Google Sheets data
- **query_sheets** - Query data using SQL
- **list_synced_sheets** - List all synced sheets
- **analyze_sheets** - Natural language data analysis
- **get_sheet_preview** - Preview sheet data
- **check_sheet_changes** - Check for updates
- **batch_sync_changes** - Sync multiple sheets

## Usage Examples

### With Claude Desktop

Simply paste a Google Sheets URL and ask questions:

> "Analyze the sales data from https://docs.google.com/spreadsheets/d/..."
> "What are the top performing products?"
> "Show me year-over-year growth"

### Programmatic Usage

```javascript
const GoogleSheetsMCP = require('@tntm/google-sheets-mcp');

const server = new GoogleSheetsMCP();
await server.start();

const result = await server.callTool('smart_sync', {
  url: 'https://docs.google.com/spreadsheets/d/...'
});
```

## License

MIT © TNTM
