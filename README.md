# Google Sheets Analytics MCP

A Model Context Protocol (MCP) server that connects your Google Sheets to AI assistants, enabling natural language analytics and insights.

## Use Case

Transform any Google Sheets spreadsheet into a conversational database! This MCP server enables you to:

- **Connect any Google Sheet** to Claude Desktop or other MCP-compatible AI assistants
- **Ask questions in plain English** instead of writing complex formulas
- **Get instant insights** from your data using natural language queries
- **Sync data automatically** from Google Sheets to a local SQLite database for fast querying

**Example queries:**
- "What are my top 10 customers by revenue?"
- "Show me sales trends by month"
- "What's the average order value?"
- "Find all transactions from last quarter"
- "Which products are performing best?"

## Features

✨ **Easy Google Sheets Integration** - Connect any spreadsheet with just the sheet ID  
🔄 **Automatic Data Sync** - Sync your Google Sheets data to local SQLite for fast queries  
💬 **Natural Language Queries** - Ask questions in plain English  
🔍 **SQL Interface** - Execute custom SQL queries for advanced analysis  
📊 **Schema Exploration** - Automatically understand your data structure  
⚡ **Fast Performance** - Local SQLite database for instant results  
🔐 **Secure Authentication** - Uses Google's OAuth2 for secure access  

## Prerequisites

- Python 3.8 or higher
- MCP-compatible client (Claude Desktop, Continue, etc.)
- Google account with access to Google Sheets
- Google Cloud Project with Sheets API enabled

## Step-by-Step Setup

### 1. Set Up Google Cloud Project

1. **Create a Google Cloud Project:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one

2. **Enable Google Sheets API:**
   - Go to "APIs & Services" > "Library"
   - Search for "Google Sheets API" and enable it

3. **Create OAuth2 Credentials:**
   - Go to "APIs & Services" > "Credentials"
   - Click "+ CREATE CREDENTIALS" > "OAuth client ID"
   - Choose "Desktop application"
   - Download the JSON file and save it as `credentials.json` in this project directory

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Your Google Sheet

1. **Get your Google Sheets ID:**
   - Open your Google Sheet
   - Copy the ID from the URL: `https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit`

2. **Set environment variables:**
   ```bash
   export GOOGLE_SPREADSHEET_ID="your_sheet_id_here"
   export GOOGLE_SHEET_NAME="Sheet1"  # Optional, defaults to Sheet1
   export GOOGLE_DATA_RANGE="A:Z"     # Optional, defaults to A:Z
   ```

   Or create a `.env` file (copy from `.env.example`):
   ```
   GOOGLE_SPREADSHEET_ID=your_sheet_id_here
   GOOGLE_SHEET_NAME=Sheet1
   GOOGLE_DATA_RANGE=A:Z
   ```

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
      "cwd": "/path/to/your/project",
      "env": {
        "GOOGLE_SPREADSHEET_ID": "your_sheet_id_here",
        "GOOGLE_SHEET_NAME": "Sheet1"
      }
    }
  }
}
```

3. Replace `/path/to/your/` with the actual path to your project directory
4. Replace `your_sheet_id_here` with your actual Google Sheets ID
5. Restart Claude Desktop

#### For Other MCP Clients:

Refer to your client's documentation for adding MCP servers. Use:
- **Command**: `python`
- **Args**: `["/path/to/mcp_server.py"]`
- **Working Directory**: Your project directory
- **Environment Variables**: Set `GOOGLE_SPREADSHEET_ID` and optionally `GOOGLE_SHEET_NAME`

### 5. Sync and Analyze Your Data

1. **First, sync your Google Sheets data:**
   ```
   "Sync my Google Sheets data"
   ```
   This will authenticate with Google (opens browser) and import your data.

2. **Start analyzing:**
   ```
   "Describe my data structure"
   "What are the column names and data types?"
   "Show me the first 10 rows"
   "What's the total number of records?"
   ```

3. **Ask business questions:**
   ```
   "What are my top customers by revenue?"
   "Show me sales trends over time"
   "Which products have the highest profit margins?"
   ```

## Available Tools

The server provides these tools for working with your Google Sheets data:

1. **sync_sheets**: Sync data from Google Sheets to local SQLite database
2. **query_database**: Execute SQL queries on your synced data
3. **describe_table**: Get schema information and sample data
4. **get_sheet_info**: View information about your connected Google Sheet

## How It Works

1. **Authentication**: Uses Google OAuth2 to securely access your sheets
2. **Data Sync**: Downloads your Google Sheets data and stores it in a local SQLite database (`sheets_data.sqlite`)
3. **Query Interface**: Provides SQL access to your data through the `sheet_data` table
4. **Natural Language**: AI assistant translates your questions into SQL queries automatically

## Example Workflow

```
# 1. Sync your data
User: "Sync my Google Sheets data"
MCP: ✅ Synced 1,234 rows from 'Sales Data' sheet

# 2. Explore your data
User: "What columns do I have?"
MCP: Your data has columns: date, customer, product, amount, region

# 3. Ask business questions
User: "What are my top 5 customers by total sales?"
MCP: [Executes SQL and returns results]

# 4. Get insights
User: "Show me monthly sales trends"
MCP: [Groups data by month and shows trends]
```

## File Structure

After setup, your project should contain:
```
.
├── mcp_server.py              # Main MCP server
├── requirements.txt           # Python dependencies
├── credentials.json           # Google API credentials (you create this)
├── credentials.json.example   # Example credentials file
├── .env.example              # Environment variables example
├── token.json                # OAuth token (auto-generated)
├── sheets_data.sqlite        # Your synced data (auto-generated)
└── README.md                 # This file
```

## Troubleshooting

**Authentication Issues:**
- Ensure `credentials.json` exists and is valid
- Check that Google Sheets API is enabled in your Google Cloud project
- Make sure your Google account has access to the spreadsheet
- If authentication fails, delete `token.json` and try again

**Sync Issues:**
- Verify the spreadsheet ID is correct
- Check that the sheet name exists in your spreadsheet
- Ensure the data range covers your actual data
- Make sure the spreadsheet is not empty

**MCP Client Issues:**
- Verify file paths in your MCP client configuration
- Check that environment variables are set correctly
- Restart your MCP client after configuration changes
- Check the client logs for error messages

**No Data Issues:**
- Run the sync tool first: "Sync my Google Sheets data"
- Check if `sheets_data.sqlite` file exists
- Verify data was imported: "Describe my data structure"

## Security Notes

- Your Google Sheets data is stored locally in SQLite
- Credentials are stored locally and never shared
- The server only requests read-only access to your sheets
- Authentication tokens are cached locally for convenience

## Limitations

- Read-only access to Google Sheets (cannot modify your sheets)
- Supports text data (numbers, dates, strings)
- Maximum recommended sheet size: ~100,000 rows
- Requires internet connection for initial sync and re-authentication

## Support

For issues with:
- **Google Sheets API**: Check [Google's documentation](https://developers.google.com/sheets/api)
- **MCP Protocol**: Check the [official MCP documentation](https://modelcontextprotocol.io/)
- **Claude Desktop**: Visit [Anthropic's support resources](https://support.anthropic.com/)
- **This Server**: Create an issue on the GitHub repository

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.