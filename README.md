# TNTM Google Sheets Analytics MCP Server

![TNTM Logo](assets/tntm-logo.png)

A clean, practical MCP (Model Context Protocol) server for analyzing Google Sheets data with multi-tab support. Built for Claude Desktop and other MCP-compatible AI assistants by TNTM.

## 🚀 Features

- **Smart Sync** - Sync Google Sheets with configurable row limits to prevent timeouts
- **Multi-tab Support** - Query across multiple sheets with SQL JOINs
- **SQL Queries** - Direct SQL access to synced data
- **Sheet Analysis** - Get suggestions for cross-sheet queries
- **Quick Preview** - Preview sheets without full sync
- **Performance Optimized** - Row limits and result pagination for large datasets

## 📋 Prerequisites

- Python 3.8+
- Claude Desktop or another MCP-compatible client
- Google Cloud Project with Sheets API enabled
- OAuth2 credentials from Google Cloud Console

## 🛠️ Setup

### 1. Clone and Install
```bash
git clone https://github.com/yourusername/google-sheet-analytics-mcp.git
cd google-sheet-analytics-mcp
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Google Cloud Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google Sheets API
4. Create OAuth2 credentials (Desktop Application)
5. Download the credentials and save as `credentials.json` in the project root

### 3. Run Automated Setup
```bash
python3 setup.py
```

This will:
- Set up OAuth authentication
- Configure Claude Desktop automatically
- Test the connection

Or configure MCP client manually:
```json
{
  "mcpServers": {
    "google-sheets-analytics": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["/path/to/google-sheet-analytics-mcp/src/mcp_server.py"]
    }
  }
}
```

### 4. First Run
Restart your MCP client (e.g., Claude Desktop) and the OAuth flow will start automatically on first tool use.

## 🔧 Tools

### `smart_sync`
Sync Google Sheet data with intelligent chunking for large datasets.
```
Use smart_sync with url "https://docs.google.com/spreadsheets/d/your_sheet_id" and max_rows 100000
```
- `url` (required): Google Sheets URL
- `max_rows` (optional): Max rows per sheet (default: 1000, supports up to 1M+)
- `sheets` (optional): Array of specific sheet names to sync

**Auto-scaling behavior:**
- Sheets <10K rows: Single fetch
- Sheets 10K-100K rows: 10K row chunks  
- Sheets >100K rows: 50K row chunks with sampling

### `query_sheets`  
Run SQL queries on synced data, including JOINs across tabs.
```
Use query_sheets with query "SELECT * FROM sheet1 JOIN sheet2 ON sheet1.id = sheet2.id LIMIT 10"
```
- `query` (required): SQL query to execute

### `list_synced_sheets`
View all synced sheets and their table names.
```
Use list_synced_sheets
```

### `analyze_sheets`
Get suggestions for queries across multiple sheets.
```
Use analyze_sheets with question "How can I combine sales data with customer data?"
```
- `question` (required): What you want to analyze

### `get_sheet_preview`
Quick preview without syncing.
```
Use get_sheet_preview with url "https://docs.google.com/spreadsheets/d/your_sheet_id" and rows 20
```
- `url` (required): Google Sheets URL
- `sheet_name` (optional): Specific sheet to preview
- `rows` (optional): Number of rows to preview (default: 10)

## 📊 How It Works

1. **Authentication** - Uses OAuth2 to securely access Google Sheets API
2. **Sync** - Downloads sheet data to local SQLite database with configurable limits
3. **Query** - Enables SQL queries across all synced sheets
4. **Multi-tab** - Each sheet becomes a separate table, joinable via SQL

## 🏗️ Project Structure

```
google-sheet-analytics-mcp/
├── src/
│   ├── mcp_server.py          # Main MCP server implementation
│   └── auth/
│       └── oauth_setup.py     # Unified OAuth authentication module
├── setup.py                   # Unified setup script (handles everything)
├── requirements.txt           # Python dependencies
├── credentials.json.example   # Example OAuth credentials format
├── README.md                  # This file
├── LICENSE                    # MIT License
├── CLAUDE.md                  # Claude-specific instructions
├── data/                      # Runtime data (created automatically)
│   ├── token.json            # OAuth token (created during setup)
│   └── sheets_data.sqlite    # Local database (created on first sync)
└── venv/                      # Virtual environment (created during setup)
```

## ⚡ Performance

### Scale & Capacity
- **1 Million Row Support**: Handles sheets with up to 1M rows efficiently
- **Chunked Processing**: Automatically chunks large sheets (>10K rows) for optimal performance
- **Bulk Operations**: 50-100x faster inserts using batch processing
- **Configurable Limits**: Default 1000 rows, expandable to 1M+ rows per sheet

### Optimizations
- **Smart Caching**: Skip unchanged sheets, 5-minute cache TTL
- **Streaming Queries**: Results streamed in batches to prevent memory overflow
- **Progressive Hashing**: Samples large datasets for efficient change detection
- **Dynamic Indexing**: Auto-creates indexes on large tables for faster queries
- **Memory Management**: Automatic cleanup after processing large datasets

### Performance Metrics
- **Sync Speed**: 50,000-100,000 rows/second (vs 1,000 rows/second previously)
- **Query Response**: <1 second for most queries on 1M rows
- **Memory Usage**: Constant ~200-500MB regardless of dataset size
- **1M Row Sync Time**: ~10-20 seconds

## 🔍 Example Use Cases

### Multi-tab Analysis
```sql
-- Combine sales data with customer information
SELECT 
  s.product_name, 
  s.sales_amount, 
  c.customer_name, 
  c.customer_segment
FROM sales_data s 
JOIN customer_data c ON s.customer_id = c.id
WHERE s.sales_amount > 1000
```

### Cross-sheet Aggregation
```sql
-- Total revenue by region from multiple sheets
SELECT 
  region, 
  SUM(amount) as total_revenue
FROM (
  SELECT region, amount FROM q1_sales
  UNION ALL
  SELECT region, amount FROM q2_sales
)
GROUP BY region
ORDER BY total_revenue DESC
```

## 🔒 Security

- OAuth2 authentication with Google
- Credentials stored locally (never committed to repo)
- Read-only access to Google Sheets
- Local SQLite database (no external data transmission)

## 🐛 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "No credentials found" | Ensure `credentials.json` exists in project root or `config/` directory |
| "Authentication failed" | Check token status with `venv/bin/python src/auth/oauth_setup.py --status` |
| "Token expired" | Run `venv/bin/python src/auth/oauth_setup.py --test` (auto-refreshes) |
| "Sync timeout" | Reduce `max_rows` parameter in smart_sync |
| "Tools not appearing" | Restart Claude Desktop after configuration |
| "Rate limit errors" | Wait a few minutes and try again with smaller batches |

### OAuth Troubleshooting
- **Check status**: `venv/bin/python src/auth/oauth_setup.py --status`
- **Test auth**: `venv/bin/python src/auth/oauth_setup.py --test`
- **Reset OAuth**: `venv/bin/python src/auth/oauth_setup.py --reset`
- **Manual setup**: `venv/bin/python src/auth/oauth_setup.py --manual`

### MCP Server Not Appearing
1. Ensure Claude Desktop is fully closed
2. Verify config: `cat ~/Library/Application\ Support/Claude/claude_desktop_config.json`
3. Check the config includes the google-sheets-analytics server
4. Restart Claude Desktop
5. Check developer console for errors

### Database Issues
- Database location: `data/sheets_data.sqlite`
- Reset database: Delete the file and re-sync
- Check synced sheets: Use the `list_synced_sheets` tool

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built for the [Model Context Protocol](https://modelcontextprotocol.io/)
- Designed for [Claude Desktop](https://claude.ai/download)
- Uses [Google Sheets API](https://developers.google.com/sheets/api)

---

**Need help?** Open an issue on GitHub or check the troubleshooting section above.