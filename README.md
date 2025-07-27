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

✨ **Paste & Analyze** - Just paste any Google Sheets URL and start asking questions!  
🔄 **Automatic Data Sync** - Sync your Google Sheets data to local SQLite for fast queries  
💬 **Natural Language Queries** - Ask questions in plain English  
🔍 **SQL Interface** - Execute custom SQL queries for advanced analysis  
📊 **Schema Exploration** - Automatically understand your data structure  
⚡ **Fast Performance** - Local SQLite database for instant results  
🔐 **Secure Authentication** - Uses Google's OAuth2 for secure access  
🚀 **Zero Configuration** - No environment variables or complex setup required  

## Prerequisites

- Python 3.8 or higher
- MCP-compatible client (Claude Desktop, Continue, etc.)
- Google account with access to Google Sheets
- Google Cloud Project with Sheets API enabled

## Quick Start Checklist

**For Automated Setup (Recommended):**
- [ ] ✅ **Python 3.8+** installed (`python3 --version`)
- [ ] ✅ **Google Cloud Project** with Sheets API enabled
- [ ] ✅ **OAuth2 credentials** downloaded as `credentials.json`
- [ ] ✅ **Run automated setup:** `python3 setup.py`
- [ ] ✅ **Add generated config to Claude Desktop**
- [ ] ✅ **Restart Claude Desktop** completely

**For Manual Setup:**
- [ ] ✅ **Python 3.8+** installed (`python3 --version`)
- [ ] ✅ **Virtual environment** created and activated
- [ ] ✅ **Dependencies** installed in virtual environment  
- [ ] ✅ **Google Cloud Project** with Sheets API enabled
- [ ] ✅ **OAuth2 credentials** downloaded as `credentials.json`
- [ ] ✅ **OAuth authentication** completed using oauth_setup.py
- [ ] ✅ **Absolute file paths** used in Claude Desktop config
- [ ] ✅ **Virtual environment Python path** used in config
- [ ] ✅ **Claude Desktop** completely restarted after config changes

**Common mistakes that cause errors:**
- ❌ Using `python` instead of `python3`
- ❌ Using system Python instead of virtual environment Python
- ❌ Using relative paths instead of absolute paths  
- ❌ Not restarting Claude Desktop after config changes
- ❌ Missing `credentials.json` file
- ❌ Skipping OAuth authentication step

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

### 2. Clone and Setup Project

**Option A: Automated Setup (Recommended)**
```bash
# Clone the repository
git clone https://github.com/your-username/google-sheet-analytics-mcp.git
cd google-sheet-analytics-mcp

# Add your credentials.json file (see step 1 above)
# Then run the automated setup:
python3 setup.py
```

**Option B: Manual Setup**
```bash
# Clone the repository
git clone https://github.com/your-username/google-sheet-analytics-mcp.git
cd google-sheet-analytics-mcp

# Create virtual environment (RECOMMENDED)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**⚠️ Important:** The automated setup will handle everything including OAuth authentication!

### 3. Complete Setup (Automated)

If you used the automated setup (`python3 setup.py`), everything is already done! Skip to step 5.

If you used manual setup, complete these steps:

**Manual Setup Only:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Test the MCP server
python mcp_server.py
```

You should see: `🚀 Google Sheets Analytics MCP Server starting...` and `💡 Users can now paste Google Sheets URLs directly - no configuration needed!`

### 4. OAuth Authentication (Manual Setup Only)

**If you used automated setup, this is already done!**

For manual setup, run OAuth authentication:

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run OAuth setup
python oauth_setup.py
```

The tool will:
1. Check your `credentials.json` file
2. Open Google OAuth in your browser
3. Let you select your Google account
4. Complete authentication automatically
5. Save your token for future use

### 5. Configure Claude Desktop

#### Automated Setup Users:
**If you used `python3 setup.py`, the exact configuration was already displayed at the end of setup!** Just copy and paste it.

#### Manual Setup Users:

1. Open Claude Desktop settings
2. Add a new MCP server configuration:

```json
{
  "mcpServers": {
    "google-sheets-analytics": {
      "command": "/FULL/PATH/TO/YOUR/PROJECT/venv/bin/python",
      "args": ["/FULL/PATH/TO/YOUR/PROJECT/mcp_server.py"],
      "cwd": "/FULL/PATH/TO/YOUR/PROJECT"
    }
  }
}
```

3. **Replace the paths:**
   - Replace `/FULL/PATH/TO/YOUR/PROJECT` with your actual project directory path
   - **Important:** Use the virtual environment Python path (`venv/bin/python`)

4. **Get your exact paths:**
   ```bash
   pwd  # Copy this output for your project path
   ```

5. **Save the configuration and completely restart Claude Desktop** (Cmd+Q, then reopen)

#### For Other MCP Clients:

Refer to your client's documentation for adding MCP servers. Use:
- **Command**: `/full/path/to/your/project/venv/bin/python`
- **Args**: `["/full/path/to/your/project/mcp_server.py"]`
- **Working Directory**: Your project directory
- **Environment Variables**: None needed!

### 6. Start Using Google Sheets Analytics!

#### ✅ **You're Ready!**

1. **Restart Claude Desktop completely** (Cmd+Q, then reopen)
2. **Verify the connection** - you should see Google Sheets Analytics tools available
3. **Start analyzing any Google Sheet immediately:**

#### 🚀 **Just Paste Any Google Sheets URL:**
```
"Analyze this Google Sheet: https://docs.google.com/spreadsheets/d/ABC123/edit"
"Load data from: [paste any Google Sheets URL]" 
"Sync this sheet: https://docs.google.com/spreadsheets/d/XYZ789/edit"
```
The server automatically extracts the sheet ID and syncs your data!

#### 📊 **Start Analyzing Immediately:**
```
"Describe my data structure"
"What are the column names and data types?"
"Show me the first 10 rows"
"What's the total number of records?"
```

#### 💼 **Ask Business Questions:**
```
"What are my top customers by revenue?"
"Show me sales trends over time"  
"Which products have the highest profit margins?"
"Find all transactions from last quarter"
```

#### 🔄 **Switch Between Sheets Anytime:**
```
"Now analyze this other sheet: https://docs.google.com/spreadsheets/d/XYZ789/edit"
```

**That's it!** No configuration, no environment variables - just paste URLs and start asking questions! 🎯

## Available Tools

The server provides these tools for working with your Google Sheets data:

### Core Tools
1. **sync_sheets**: Sync data from any Google Sheets URL to local SQLite database
2. **query_database**: Execute SQL queries on your synced data (with automatic caching)
3. **describe_table**: Get schema information and sample data
4. **get_sheet_info**: View information about your connected Google Sheet

### Optimization Tools (New!)
5. **batch_query**: Execute multiple SQL queries in a single batch for improved performance
6. **analyze_schema**: Get comprehensive data analysis including statistics, data types, and sample values
7. **quick_analysis**: One-stop analysis that combines sync + schema analysis + sample data in a single call

### Performance Features
- **Query Caching**: Automatic caching of query results with 5-minute TTL
- **Batch Processing**: Execute multiple queries in single database connection
- **Smart Analysis**: Comprehensive data overview reduces tool calls by 60-80%

## How It Works

1. **Authentication**: Uses Google OAuth2 to securely access your sheets
2. **Data Sync**: Downloads your Google Sheets data and stores it in a local SQLite database (`sheets_data.sqlite`)
3. **Query Interface**: Provides SQL access to your data through the `sheet_data` table
4. **Natural Language**: AI assistant translates your questions into SQL queries automatically

## Example Workflow

```
# 1. Paste any Google Sheets URL
User: "Analyze this spreadsheet: https://docs.google.com/spreadsheets/d/ABC123/edit"
MCP: ✅ Synced 1,234 rows from 'Sales Data' sheet

# 2. Explore your data
User: "What columns do I have?"
MCP: Your data has columns: date, customer, product, amount, region

# 3. Ask business questions
User: "What are my top 5 customers by total sales?"
MCP: [Executes SQL and returns results]

# 4. Switch to another sheet anytime
User: "Now analyze this other sheet: https://docs.google.com/spreadsheets/d/XYZ789/edit"
MCP: ✅ Synced 856 rows from 'Marketing Data' sheet

# 5. Get insights from any sheet
User: "Show me monthly trends"
MCP: [Groups data by month and shows trends]
```

## Performance & Optimization

### New Workflow Examples

**Traditional approach (multiple tool calls):**
```
User: "Analyze this sheet: [URL]"
1. sync_sheets → ✅ Synced 1000 rows
2. describe_table → Schema info
3. query_database → Sample data
4. query_database → Column statistics
5. query_database → Data validation
Total: 5 tool calls
```

**Optimized approach (single tool call):**
```
User: "Quick analysis of this sheet: [URL]"
1. quick_analysis → ✅ Complete analysis with sync + schema + samples + insights
Total: 1 tool call (80% reduction!)
```

**Batch queries for complex analysis:**
```
User: "I need sales summary, top customers, and monthly trends"
1. batch_query → Execute 3 SQL queries simultaneously with timing metrics
Total: 1 tool call instead of 3
```

### Performance Benefits
- **Faster Analysis**: 60-80% reduction in tool calls for typical workflows
- **Smart Caching**: Repeated queries return instantly from cache
- **Batch Processing**: Multiple queries executed in single database connection
- **Comprehensive Overview**: Get complete data understanding in one call

## File Structure

After setup, your project should contain:
```
.
├── mcp_server.py              # Main MCP server
├── setup.py                   # Automated setup script  
├── oauth_setup.py            # Interactive OAuth setup tool
├── post-clone.sh             # Alternative setup script
├── requirements.txt           # Python dependencies
├── credentials.json.example   # Example credentials file
├── credentials.json           # Google API credentials (you create this)
├── token.json                # OAuth token (auto-generated after setup)
├── sheets_data.sqlite        # Your synced data (auto-generated)
├── venv/                     # Virtual environment (auto-created)
└── README.md                 # This file
```

**Note:** `credentials.json`, `token.json`, `sheets_data.sqlite`, and `venv/` are not included in the repository for security reasons.

## Troubleshooting

**Authentication Issues:**
- Ensure `credentials.json` exists and is valid
- Check that Google Sheets API is enabled in your Google Cloud project
- Make sure your Google account has access to the spreadsheet
- If authentication fails, delete `token.json` and try again

**Sync Issues:**
- Make sure you're pasting a valid Google Sheets URL
- Check that the sheet name exists in your spreadsheet (defaults to 'Sheet1')
- Ensure the data range covers your actual data (defaults to 'A:Z')
- Make sure the spreadsheet is not empty
- Verify your Google account has access to the spreadsheet

**MCP Client Issues:**
- **"spawn ENOENT" errors**: The Python path is wrong or virtual environment doesn't exist
  - Check that `/path/to/project/venv/bin/python` exists
  - Verify you created the virtual environment: `python3 -m venv venv`
- **"ModuleNotFoundError: No module named 'mcp'"**: Dependencies not installed in virtual environment
  - Run: `source venv/bin/activate && pip install -r requirements.txt`
- **Wrong file paths**: Use absolute paths, not relative paths
- **Configuration not updating**: Completely restart Claude Desktop (Cmd+Q)
- **Check logs**: Look at `/Users/yourname/Library/Logs/Claude/mcp-server-google-sheets-analytics.log`

**No Data Issues:**
- Paste a Google Sheets URL first: "Analyze this sheet: [URL]"
- **"Failed to authenticate"**: Run `python oauth_setup.py` and complete OAuth
- **"Could not extract spreadsheet ID"**: Make sure you're using a valid Google Sheets URL
- **"No data found"**: Make sure the sheet name exists (try 'Sheet1')
- Check if `sheets_data.sqlite` file exists after sync
- Verify data was imported: "Describe my data structure"

**Quick Diagnosis:**
1. Check MCP server logs: `/Users/yourname/Library/Logs/Claude/mcp-server-google-sheets-analytics.log`
2. Test server directly: `source venv/bin/activate && python mcp_server.py`
3. Verify virtual environment: `ls venv/bin/python` should exist
4. Check dependencies: `source venv/bin/activate && pip list | grep mcp`

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