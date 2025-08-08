# @talknerdytome/google-sheets-mcp

A powerful MCP (Model Context Protocol) server for analyzing Google Sheets data with natural language. Built for Claude Desktop and other MCP-compatible AI assistants.

## 🚀 Quick Start

```bash
npm install -g @talknerdytome/google-sheets-mcp
```

## ✨ Features

- **Smart Sync** - Intelligently sync Google Sheets with configurable limits
- **Multi-tab Support** - Query across multiple sheets with SQL JOINs  
- **SQL Queries** - Direct SQL access to synced spreadsheet data
- **Natural Language Analysis** - Ask questions about your data in plain English
- **Performance Optimized** - Handles large datasets with pagination and row limits
- **Zero Configuration** - Just paste Google Sheets URLs and start analyzing

## 📋 Prerequisites

- Node.js 16+
- Python 3.8-3.12 (auto-managed by the package)
- Google Cloud project with Sheets API enabled

## 🛠️ Setup

### 1. Install the Package

```bash
npm install -g @talknerdytome/google-sheets-mcp
```

### 2. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable Google Sheets API
4. Create OAuth 2.0 credentials (Desktop Application)
5. Download credentials as `credentials.json`

### 3. Configure Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "npx",
      "args": ["@talknerdytome/google-sheets-mcp"]
    }
  }
}
```

### 4. First Run Setup

The package will automatically:
- Set up Python virtual environment
- Install Python dependencies  
- Guide you through OAuth authentication
- Configure your credentials

## 🎯 Usage

### With Claude Desktop

Simply paste a Google Sheets URL and start asking questions:

```
"Analyze the sales data from https://docs.google.com/spreadsheets/d/..."
"What are the top performing products this quarter?"
"Show me year-over-year growth trends"
"Compare revenue across different regions"
```

### Available MCP Tools

- **`smart_sync`** - Sync sheets with intelligent row limits
- **`query_sheets`** - Execute SQL queries on synced data
- **`analyze_sheets`** - Get natural language insights
- **`list_synced_sheets`** - View all available data
- **`get_sheet_preview`** - Quick preview without full sync
- **`check_sheet_changes`** - Monitor for updates
- **`batch_sync_changes`** - Sync multiple sheets efficiently

## 💡 Examples

### Basic Data Analysis
```
"Load this spreadsheet and show me a summary of the data"
"What's the average order value in my sales sheet?"
"Find all customers from California"
```

### Cross-Sheet Analysis  
```
"Join the customers sheet with the orders sheet and show top buyers"
"Compare Q1 vs Q2 performance across all sheets"
"Create a pivot table from the combined data"
```

### Advanced Queries
```
"Show me a SQL query to find customers who haven't ordered in 90 days"
"What's the correlation between marketing spend and sales?"
"Identify seasonal trends in the data"
```

## 🔧 Configuration

### Row Limits
Automatically configured based on sheet size:
- Small sheets (< 1000 rows): Full sync
- Medium sheets (1000-5000 rows): 2500 rows
- Large sheets (> 5000 rows): 1000 rows

### Data Caching
- Local SQLite database for fast queries
- Automatic change detection
- Incremental updates for efficiency

## 🚨 Troubleshooting

### Authentication Issues
```bash
# Check status
npx @talknerdytome/google-sheets-mcp --help

# Reset credentials (if package supports it)
rm -rf ~/.google-sheets-mcp/
```

### Permission Errors
- Ensure your Google Cloud project has Sheets API enabled
- Verify OAuth credentials are correctly configured
- Check that the spreadsheet is accessible to your Google account

### Performance Issues
- Large sheets automatically use row limits
- Use preview mode for initial exploration
- Consider breaking very large datasets into smaller sheets

## 🤝 Support

- **Issues**: [GitHub Issues](https://github.com/talknerdytome-labs/google-sheet-analytics-mcp/issues)
- **Documentation**: [GitHub Repository](https://github.com/talknerdytome-labs/google-sheet-analytics-mcp)

## 📄 License

MIT © TNTM

## 🔗 Links

- [GitHub Repository](https://github.com/talknerdytome-labs/google-sheet-analytics-mcp)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/desktop)