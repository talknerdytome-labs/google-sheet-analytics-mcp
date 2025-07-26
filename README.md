# Google Sheets Analytics MCP

A Model Context Protocol (MCP) server that provides analytics capabilities for Google Sheets data through natural language queries.

## Use Case

This MCP server enables you to analyze Google Sheets data using natural language through any MCP-compatible AI assistant (like Claude Desktop). Instead of manually writing SQL queries or complex formulas, you can ask questions like:

- "What are the top 10 customers by revenue?"
- "Show me booking trends by month"
- "What's the average transaction value?"
- "Find all bookings from last quarter"

The server provides direct access to your Google Sheets data through a local SQLite database, allowing for fast analytics and insights.

## Features

- **Natural Language Analytics**: Query your data using plain English
- **SQL Query Interface**: Execute custom SQL queries on your sheets data
- **Schema Exploration**: Understand your data structure and columns
- **Sample Data Access**: Preview your data before running complex queries
- **Fast Performance**: Local SQLite database for quick query execution

## Prerequisites

- Python 3.8 or higher
- MCP-compatible client (Claude Desktop, Continue, etc.)
- Google Sheets data (already imported as SQLite database)

## Step-by-Step Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Verify Files

Ensure you have these files in your project directory:
- `mcp_server.py` - The MCP server implementation
- `app_db.sqlite` - Your Google Sheets data in SQLite format
- `requirements.txt` - Python dependencies

### 3. Test the Server

Run the server directly to verify it works:

```bash
python mcp_server.py
```

If successful, you should see the server start without errors.

### 4. Configure Your MCP Client

#### For Claude Desktop:

1. Open Claude Desktop settings
2. Add a new MCP server configuration:

```json
{
  "mcpServers": {
    "google-sheets-analytics": {
      "command": "python",
      "args": ["/path/to/your/mcp_server.py"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

3. Replace `/path/to/your/` with the actual path to your project directory
4. Restart Claude Desktop

#### For Other MCP Clients:

Refer to your client's documentation for adding MCP servers. Use:
- **Command**: `python`
- **Args**: `["/path/to/mcp_server.py"]`
- **Working Directory**: Your project directory

### 5. Start Analyzing

Once configured, you can start asking questions about your data:

**Example Queries:**
- "Describe the data structure"
- "Show me the first 10 records"
- "What's the total revenue?"
- "Find bookings from 2024"

## Available Tools

The server provides these tools for data analysis:

1. **query_database**: Execute SQL queries on your Google Sheets data
2. **describe_table**: Get schema information and sample data
3. **get_connected_sheet_info**: View information about your source Google Sheet

## Data Information

- **Source**: Google Sheets "Bookings Data"
- **Records**: 50,300+ transaction records
- **Date Range**: 2023-01-01 to 2025-07-05
- **Columns**: 9 data columns including customer info, financial data, and timestamps

## Troubleshooting

**Server won't start:**
- Verify Python version (3.8+)
- Check that `app_db.sqlite` exists and is readable
- Ensure all dependencies are installed

**Client can't connect:**
- Verify the file paths in your MCP client configuration
- Check that the working directory is correct
- Restart your MCP client after configuration changes

**No data returned:**
- Verify the SQLite database contains data: `SELECT COUNT(*) FROM sheet1`
- Check table schema: Use the `describe_table` tool

## Support

For issues with:
- **MCP Protocol**: Check the official MCP documentation
- **Claude Desktop**: Visit Anthropic's support resources
- **This Server**: Review the `mcp_server.py` file for implementation details