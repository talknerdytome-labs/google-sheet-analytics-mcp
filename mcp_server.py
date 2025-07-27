#!/usr/bin/env python3

import asyncio
import sqlite3
import json
import os
import hashlib
import time
from typing import Any, Sequence, Optional, Dict, List
from datetime import datetime
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
import mcp.types as types
import mcp.server.stdio
from pydantic import AnyUrl
import logging
import sys

# Google Sheets API imports
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sheets-mcp-server")

# Query result cache
class QueryCache:
    def __init__(self, max_size=100, ttl_seconds=300):  # 5 minute TTL
        self.cache = {}
        self.access_times = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
    
    def _generate_key(self, query: str) -> str:
        """Generate a hash key for the query"""
        return hashlib.md5(query.encode()).hexdigest()
    
    def get(self, query: str):
        """Get cached result for query"""
        key = self._generate_key(query)
        if key in self.cache:
            # Check if cache entry is still valid
            if time.time() - self.access_times[key] < self.ttl_seconds:
                self.access_times[key] = time.time()  # Update access time
                return self.cache[key]
            else:
                # Remove expired entry
                del self.cache[key]
                del self.access_times[key]
        return None
    
    def set(self, query: str, result):
        """Cache query result"""
        key = self._generate_key(query)
        
        # Remove oldest entries if cache is full
        if len(self.cache) >= self.max_size:
            # Find least recently used entry
            oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
        
        self.cache[key] = result
        self.access_times[key] = time.time()
    
    def clear(self):
        """Clear all cached entries"""
        self.cache.clear()
        self.access_times.clear()

# Global query cache instance
query_cache = QueryCache()

# Google Sheets API scopes
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Configuration - No environment variables needed!
# Use absolute paths to ensure files are found regardless of working directory
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(_script_dir, 'credentials.json')
TOKEN_FILE = os.path.join(_script_dir, 'token.json')

# Cache for multiple sheets
sheets_cache = {}
current_sheet_info = None

def extract_spreadsheet_id(url_or_id):
    """Extract spreadsheet ID from Google Sheets URL or return ID if already an ID"""
    import re
    
    # If it's already just an ID (no slashes or dots), return as is
    if '/' not in url_or_id and '.' not in url_or_id:
        return url_or_id
    
    # Extract from various Google Sheets URL formats
    patterns = [
        r'/spreadsheets/d/([a-zA-Z0-9-_]+)',
        r'[?&]id=([a-zA-Z0-9-_]+)',
        r'^([a-zA-Z0-9-_]+)$'  # Just the ID itself
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    
    raise ValueError(f"Could not extract spreadsheet ID from: {url_or_id}")

def get_cached_sheet_data(spreadsheet_id):
    """Get cached sheet data if available"""
    return sheets_cache.get(spreadsheet_id)

def cache_sheet_data(spreadsheet_id, data):
    """Cache sheet data for quick access"""
    sheets_cache[spreadsheet_id] = data

class GoogleSheetsService:
    """Service for interacting with Google Sheets API"""
    
    def __init__(self):
        self.service = None
        self.sheet_info = None
    
    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API"""
        creds = None
        
        # Load existing token
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Token refresh failed: {e}")
                    logger.error("Please run 'python oauth_setup.py' to re-authenticate")
                    return False
            else:
                logger.error("No valid OAuth token found")
                logger.error("Please run 'python oauth_setup.py' to authenticate")
                return False
            
            # Save refreshed credentials
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        try:
            self.service = build('sheets', 'v4', credentials=creds)
            return True
        except Exception as e:
            logger.error(f"Failed to build Google Sheets service: {e}")
            return False
    
    def get_sheet_data(self, spreadsheet_id: str, range_name: str) -> Optional[List[List[Any]]]:
        """Get data from Google Sheets"""
        if not self.service:
            if not self.authenticate():
                return None
        
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            return values
        except HttpError as e:
            logger.error(f"Error fetching data from Google Sheets: {e}")
            return None
    
    def get_sheet_metadata(self, spreadsheet_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata about the spreadsheet"""
        if not self.service:
            if not self.authenticate():
                return None
        
        try:
            result = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            return {
                'title': result.get('properties', {}).get('title', 'Unknown'),
                'sheets': [sheet['properties']['title'] for sheet in result.get('sheets', [])],
                'url': f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            }
        except HttpError as e:
            logger.error(f"Error fetching sheet metadata: {e}")
            return None

# Database connection
def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), "sheets_data.sqlite")
    return sqlite3.connect(db_path)

def sync_sheets_to_sqlite(url_or_id: str, sheet_name: str = None, data_range: str = 'A:Z') -> Dict[str, Any]:
    """Sync data from Google Sheets to SQLite database"""
    try:
        # Extract spreadsheet ID from URL
        spreadsheet_id = extract_spreadsheet_id(url_or_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    # Check cache first
    cached_data = get_cached_sheet_data(spreadsheet_id)
    if cached_data:
        logger.info(f"Using cached data for spreadsheet {spreadsheet_id}")
        return {"success": True, "cached": True, **cached_data}
    
    sheets_service = GoogleSheetsService()
    
    if not sheets_service.authenticate():
        return {"success": False, "error": "Failed to authenticate with Google Sheets"}
    
    # If no sheet name provided, get metadata and use first sheet
    if not sheet_name:
        metadata = sheets_service.get_sheet_metadata(spreadsheet_id)
        if metadata and metadata.get('sheets'):
            sheet_name = metadata['sheets'][0]
            logger.info(f"No sheet name provided, using first sheet: {sheet_name}")
        else:
            sheet_name = 'Sheet1'  # Fallback to default
    
    # Get sheet data
    full_range = f"{sheet_name}!{data_range}"
    data = sheets_service.get_sheet_data(spreadsheet_id, full_range)
    
    if not data:
        return {"success": False, "error": "No data found in the sheet"}
    
    if len(data) == 0:
        return {"success": False, "error": "Sheet is empty"}
    
    # Get sheet metadata
    metadata = sheets_service.get_sheet_metadata(spreadsheet_id)
    
    # Prepare data for SQLite
    headers = data[0] if data else []
    rows = data[1:] if len(data) > 1 else []
    
    # Clean headers (remove special characters, make valid SQL column names)
    clean_headers = []
    for header in headers:
        clean_header = str(header).strip().replace(' ', '_').replace('-', '_')
        clean_header = ''.join(c for c in clean_header if c.isalnum() or c == '_')
        if not clean_header or clean_header[0].isdigit():
            clean_header = f"col_{len(clean_headers) + 1}"
        clean_headers.append(clean_header)
    
    # Create SQLite table
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Drop existing table if it exists
        cursor.execute(f"DROP TABLE IF EXISTS sheet_data")
        
        # Create new table with dynamic columns
        columns_sql = ', '.join([f"{header} TEXT" for header in clean_headers])
        create_table_sql = f"CREATE TABLE sheet_data ({columns_sql})"
        cursor.execute(create_table_sql)
        
        # Insert data
        placeholders = ', '.join(['?' for _ in clean_headers])
        insert_sql = f"INSERT INTO sheet_data ({', '.join(clean_headers)}) VALUES ({placeholders})"
        
        for row in rows:
            # Pad row with None values if it's shorter than headers
            padded_row = row + [None] * (len(clean_headers) - len(row))
            # Truncate row if it's longer than headers
            padded_row = padded_row[:len(clean_headers)]
            cursor.execute(insert_sql, padded_row)
        
        conn.commit()
        
        # Store metadata
        cursor.execute("DROP TABLE IF EXISTS sheet_metadata")
        cursor.execute("""
            CREATE TABLE sheet_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        metadata_items = {
            'spreadsheet_id': spreadsheet_id,
            'sheet_name': sheet_name,
            'data_range': data_range,
            'last_sync': datetime.now().isoformat(),
            'title': metadata.get('title', 'Unknown') if metadata else 'Unknown',
            'url': metadata.get('url', '') if metadata else '',
            'total_rows': len(rows),
            'total_columns': len(clean_headers)
        }
        
        for key, value in metadata_items.items():
            cursor.execute("INSERT INTO sheet_metadata (key, value) VALUES (?, ?)", (key, str(value)))
        
        conn.commit()
        conn.close()
        
        result = {
            "success": True, 
            "rows_synced": len(rows),
            "columns": clean_headers,
            "title": metadata.get('title', 'Unknown') if metadata else 'Unknown',
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "url": metadata.get('url', '') if metadata else ''
        }
        
        # Clear query cache since we have new data
        query_cache.clear()
        logger.info("Cleared query cache due to new data sync")
        
        # Cache the result
        cache_sheet_data(spreadsheet_id, result)
        
        # Set as current sheet
        global current_sheet_info
        current_sheet_info = result
        
        return result
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "error": f"Database error: {str(e)}"}

def get_sheet_metadata_from_db() -> Optional[Dict[str, str]]:
    """Get sheet metadata from SQLite database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM sheet_metadata")
        rows = cursor.fetchall()
        conn.close()
        
        return {row[0]: row[1] for row in rows}
    except Exception:
        return None

server = Server("sheets-mcp-server")

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available data resources"""
    metadata = get_sheet_metadata_from_db()
    
    if not metadata:
        return [
            Resource(
                uri=AnyUrl("sheets://sync/required"),
                name="Google Sheets Sync Required",
                description="No data found. Please sync your Google Sheets data first using the sync_sheets tool.",
                mimeType="application/json",
            )
        ]
    
    title = metadata.get('title', 'Google Sheets Data')
    total_rows = metadata.get('total_rows', '0')
    
    return [
        Resource(
            uri=AnyUrl("sheets://data/current"),
            name=f"{title} (Google Sheets)",
            description=f"Your Google Sheets data - {total_rows} records from {metadata.get('sheet_name', 'Unknown Sheet')}",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """Read resource data"""
    uri_str = str(uri)
    
    if uri_str == "sheets://sync/required":
        return json.dumps({
            "message": "No synced data available",
            "instructions": "Use the sync_sheets tool with any Google Sheets URL to get started!",
            "example": "Just say: 'Sync this Google Sheet: [paste your URL here]'",
            "setup_required": [
                "1. Run OAuth authentication: python oauth_setup.py",
                "2. Paste any Google Sheets URL into Claude",
                "3. Start asking questions about your data!"
            ]
        }, indent=2)
    
    elif uri_str == "sheets://data/current":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sheet_data'")
            if not cursor.fetchone():
                conn.close()
                return json.dumps({"error": "No data found. Please sync your Google Sheets data first."}, indent=2)
            
            # Get sample data
            cursor.execute("SELECT * FROM sheet_data LIMIT 5")
            rows = cursor.fetchall()
            
            # Get column names
            cursor.execute("PRAGMA table_info(sheet_data)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Get row count
            cursor.execute("SELECT COUNT(*) FROM sheet_data")
            count = cursor.fetchone()[0]
            
            # Get metadata
            metadata = get_sheet_metadata_from_db() or {}
            
            conn.close()
            
            data = {
                "total_rows": count,
                "columns": columns,
                "sample_data": [dict(zip(columns, row)) for row in rows],
                "metadata": metadata
            }
            
            return json.dumps(data, indent=2)
            
        except Exception as e:
            return json.dumps({"error": f"Failed to read data: {str(e)}"}, indent=2)
    
    raise ValueError(f"Unknown resource: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="sync_sheets",
            description="Sync data from Google Sheets to local SQLite database. Just paste any Google Sheets URL!",
            inputSchema={
                "type": "object",
                "properties": {
                    "url_or_id": {
                        "type": "string",
                        "description": "Google Sheets URL (e.g., https://docs.google.com/spreadsheets/d/ABC123/edit) or just the spreadsheet ID"
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Name of the sheet tab to sync (optional, auto-detects first sheet if not provided)"
                    },
                    "data_range": {
                        "type": "string",
                        "description": "Data range to sync (optional, defaults to 'A:Z' for all data)"
                    }
                },
                "required": ["url_or_id"]
            },
        ),
        Tool(
            name="query_database",
            description="Execute SQL queries on the synced Google Sheets data",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL query to execute on the 'sheet_data' table"
                    }
                },
                "required": ["query"]
            },
        ),
        Tool(
            name="batch_query",
            description="Execute multiple SQL queries in a single batch for improved performance",
            inputSchema={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "description": "Array of SQL queries to execute",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Unique identifier for this query (optional)"
                                },
                                "query": {
                                    "type": "string",
                                    "description": "SQL query to execute on the 'sheet_data' table"
                                }
                            },
                            "required": ["query"]
                        }
                    }
                },
                "required": ["queries"]
            },
        ),
        Tool(
            name="analyze_schema",
            description="Get comprehensive schema analysis including statistics, data types, and sample values",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_samples": {
                        "type": "boolean",
                        "description": "Include sample values for each column (default: true)"
                    },
                    "include_stats": {
                        "type": "boolean", 
                        "description": "Include statistical analysis for numeric columns (default: true)"
                    }
                }
            },
        ),
        Tool(
            name="describe_table",
            description="Get schema information about the synced data table",
            inputSchema={
                "type": "object",
                "properties": {}
            },
        ),
        Tool(
            name="quick_analysis", 
            description="One-stop analysis: sync Google Sheets data and get comprehensive overview including schema, stats, and sample data",
            inputSchema={
                "type": "object",
                "properties": {
                    "url_or_id": {
                        "type": "string",
                        "description": "Google Sheets URL (e.g., https://docs.google.com/spreadsheets/d/ABC123/edit) or spreadsheet ID"
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Name of the sheet tab to sync (optional, auto-detects first sheet if not provided)"
                    },
                    "sample_size": {
                        "type": "number",
                        "description": "Number of sample rows to include (default: 5)"
                    }
                },
                "required": ["url_or_id"]
            },
        ),
        Tool(
            name="get_sheet_info",
            description="Get information about the connected Google Sheet",
            inputSchema={
                "type": "object",
                "properties": {}
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls"""
    
    if name == "sync_sheets":
        # Get parameters from arguments
        url_or_id = arguments.get("url_or_id") if arguments else None
        sheet_name = arguments.get("sheet_name") if arguments else None
        data_range = arguments.get("data_range", "A:Z") if arguments else "A:Z"
        
        if not url_or_id:
            return [TextContent(type="text", text="❌ Error: Google Sheets URL or ID is required.\n\nExample usage:\n• \"Sync this sheet: https://docs.google.com/spreadsheets/d/ABC123/edit\"\n• \"Load data from this Google Sheet: [paste URL here]\"")]
        
        result = sync_sheets_to_sqlite(url_or_id, sheet_name, data_range)
        
        if result["success"]:
            cache_indicator = " (cached)" if result.get("cached") else ""
            result_text = f"✅ Sync completed successfully!{cache_indicator}\n\n"
            result_text += f"📊 Spreadsheet: {result.get('title', 'Unknown')}\n"
            result_text += f"🔗 URL: {result.get('url', 'Unknown')}\n"
            result_text += f"📄 Sheet: {result.get('sheet_name', sheet_name or 'Auto-detected')}\n"
            result_text += f"📈 Rows synced: {result['rows_synced']:,}\n"
            result_text += f"📋 Columns: {', '.join(result['columns'])}\n\n"
            if result.get("cached"):
                result_text += "💡 This data was cached from a previous sync. Query away!\n\n"
            result_text += "🔍 You can now ask questions about your data!\n"
            result_text += "   • \"What are the column names?\"\n"
            result_text += "   • \"Show me the first 10 rows\"\n"
            result_text += "   • \"What's the total number of records?\""
        else:
            result_text = f"❌ Sync failed: {result['error']}\n\n"
            if "Could not extract spreadsheet ID" in result['error']:
                result_text += "💡 Make sure you're using a valid Google Sheets URL like:\n"
                result_text += "   https://docs.google.com/spreadsheets/d/SHEET_ID/edit\n\n"
            else:
                result_text += "Please check:\n"
                result_text += "- You have run OAuth authentication (python oauth_setup.py)\n"
                result_text += "- The Google Sheets URL is accessible to your account\n"
                result_text += "- The sheet name exists (default is 'Sheet1')\n"
                result_text += "- You have read access to the spreadsheet"
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "query_database":
        query = arguments.get("query") if arguments else None
        if not query:
            raise ValueError("Query is required")
        
        # Check cache first
        cached_result = query_cache.get(query)
        if cached_result:
            result_text = f"🚀 Query executed successfully (cached). Found {cached_result['row_count']} rows.\n\n"
            result_text += json.dumps(cached_result['data'], indent=2, default=str)
            return [TextContent(type="text", text=result_text)]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if table exists first
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sheet_data'")
            if not cursor.fetchone():
                return [TextContent(type="text", text="No data found. Please sync your Google Sheets data first using the sync_sheets tool.")]
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            # Get column names
            column_names = [description[0] for description in cursor.description] if cursor.description else []
            
            # Format results
            if results:
                formatted_results = []
                for row in results:
                    formatted_results.append(dict(zip(column_names, row)))
                
                # Cache the result
                cache_data = {
                    'data': formatted_results,
                    'row_count': len(results),
                    'columns': column_names
                }
                query_cache.set(query, cache_data)
                
                result_text = f"Query executed successfully. Found {len(results)} rows.\n\n"
                result_text += json.dumps(formatted_results, indent=2, default=str)
            else:
                # Cache empty result
                cache_data = {
                    'data': [],
                    'row_count': 0,
                    'columns': column_names
                }
                query_cache.set(query, cache_data)
                
                result_text = "Query executed successfully. No rows returned."
                
        except Exception as e:
            result_text = f"Error executing query: {str(e)}\n\n"
            result_text += "Note: The table name for your synced data is 'sheet_data'"
        finally:
            conn.close()
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "batch_query":
        queries = arguments.get("queries") if arguments else None
        if not queries:
            raise ValueError("Queries array is required")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if table exists first
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sheet_data'")
            if not cursor.fetchone():
                return [TextContent(type="text", text="No data found. Please sync your Google Sheets data first using the sync_sheets tool.")]
            
            results = []
            total_execution_time = 0
            
            for i, query_obj in enumerate(queries):
                query_id = query_obj.get("id", f"query_{i+1}")
                query = query_obj.get("query")
                
                if not query:
                    results.append({
                        "id": query_id,
                        "success": False,
                        "error": "Query is required"
                    })
                    continue
                
                try:
                    import time
                    start_time = time.time()
                    
                    cursor.execute(query)
                    query_results = cursor.fetchall()
                    
                    execution_time = time.time() - start_time
                    total_execution_time += execution_time
                    
                    # Get column names
                    column_names = [description[0] for description in cursor.description] if cursor.description else []
                    
                    # Format results
                    formatted_results = []
                    if query_results:
                        for row in query_results:
                            formatted_results.append(dict(zip(column_names, row)))
                    
                    results.append({
                        "id": query_id,
                        "success": True,
                        "rows": len(query_results),
                        "columns": column_names,
                        "data": formatted_results,
                        "execution_time_ms": round(execution_time * 1000, 2)
                    })
                    
                except Exception as e:
                    results.append({
                        "id": query_id,
                        "success": False,
                        "error": str(e)
                    })
            
            # Create summary
            successful_queries = sum(1 for r in results if r["success"])
            total_rows = sum(r.get("rows", 0) for r in results if r["success"])
            
            summary = {
                "total_queries": len(queries),
                "successful_queries": successful_queries,
                "failed_queries": len(queries) - successful_queries,
                "total_rows_returned": total_rows,
                "total_execution_time_ms": round(total_execution_time * 1000, 2)
            }
            
            result_data = {
                "summary": summary,
                "results": results
            }
            
            result_text = f"✅ Batch query completed: {successful_queries}/{len(queries)} queries successful\n"
            result_text += f"📊 Total rows returned: {total_rows:,}\n"
            result_text += f"⏱️ Total execution time: {summary['total_execution_time_ms']}ms\n\n"
            result_text += json.dumps(result_data, indent=2, default=str)
                
        except Exception as e:
            result_text = f"Error executing batch query: {str(e)}\n\n"
            result_text += "Note: The table name for your synced data is 'sheet_data'"
        finally:
            conn.close()
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "analyze_schema":
        include_samples = arguments.get("include_samples", True) if arguments else True
        include_stats = arguments.get("include_stats", True) if arguments else True
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sheet_data'")
            if not cursor.fetchone():
                return [TextContent(type="text", text="No data found. Please sync your Google Sheets data first using the sync_sheets tool.")]
            
            # Get table schema
            cursor.execute("PRAGMA table_info(sheet_data)")
            schema = cursor.fetchall()
            
            # Get row count
            cursor.execute("SELECT COUNT(*) FROM sheet_data")
            total_rows = cursor.fetchone()[0]
            
            # Get metadata
            metadata = get_sheet_metadata_from_db() or {}
            
            column_analysis = []
            
            for col in schema:
                col_name = col[1]
                col_analysis = {
                    "name": col_name,
                    "type": "TEXT"  # SQLite stores everything as TEXT for Google Sheets data
                }
                
                # Get null count
                cursor.execute(f"SELECT COUNT(*) FROM sheet_data WHERE `{col_name}` IS NULL OR `{col_name}` = ''")
                null_count = cursor.fetchone()[0]
                col_analysis["null_count"] = null_count
                col_analysis["null_percentage"] = round((null_count / total_rows) * 100, 2) if total_rows > 0 else 0
                
                # Get unique count
                cursor.execute(f"SELECT COUNT(DISTINCT `{col_name}`) FROM sheet_data WHERE `{col_name}` IS NOT NULL AND `{col_name}` != ''")
                unique_count = cursor.fetchone()[0]
                col_analysis["unique_count"] = unique_count
                col_analysis["unique_percentage"] = round((unique_count / total_rows) * 100, 2) if total_rows > 0 else 0
                
                if include_samples:
                    # Get sample values
                    cursor.execute(f"SELECT `{col_name}`, COUNT(*) as freq FROM sheet_data WHERE `{col_name}` IS NOT NULL AND `{col_name}` != '' GROUP BY `{col_name}` ORDER BY freq DESC LIMIT 5")
                    samples = cursor.fetchall()
                    col_analysis["sample_values"] = [{"value": sample[0], "frequency": sample[1]} for sample in samples]
                
                if include_stats:
                    # Try to detect if column contains numeric data
                    cursor.execute(f"SELECT `{col_name}` FROM sheet_data WHERE `{col_name}` IS NOT NULL AND `{col_name}` != '' LIMIT 100")
                    sample_values = [row[0] for row in cursor.fetchall()]
                    
                    numeric_values = []
                    for val in sample_values:
                        try:
                            numeric_val = float(str(val).replace(',', ''))
                            numeric_values.append(numeric_val)
                        except (ValueError, TypeError):
                            pass
                    
                    if len(numeric_values) > len(sample_values) * 0.7:  # If >70% are numeric
                        col_analysis["data_type"] = "numeric"
                        if numeric_values:
                            col_analysis["min_value"] = min(numeric_values)
                            col_analysis["max_value"] = max(numeric_values)
                            col_analysis["avg_value"] = round(sum(numeric_values) / len(numeric_values), 2)
                    else:
                        col_analysis["data_type"] = "text"
                        # Get average text length
                        text_lengths = [len(str(val)) for val in sample_values if val]
                        if text_lengths:
                            col_analysis["avg_length"] = round(sum(text_lengths) / len(text_lengths), 1)
                            col_analysis["max_length"] = max(text_lengths)
                
                column_analysis.append(col_analysis)
            
            # Create comprehensive analysis
            analysis = {
                "table_info": {
                    "name": "sheet_data",
                    "total_rows": total_rows,
                    "total_columns": len(schema),
                    "last_sync": metadata.get('last_sync', 'Unknown'),
                    "spreadsheet_title": metadata.get('title', 'Unknown'),
                    "sheet_name": metadata.get('sheet_name', 'Unknown')
                },
                "columns": column_analysis,
                "data_quality": {
                    "columns_with_nulls": sum(1 for col in column_analysis if col["null_count"] > 0),
                    "avg_null_percentage": round(sum(col["null_percentage"] for col in column_analysis) / len(column_analysis), 2) if column_analysis else 0,
                    "numeric_columns": sum(1 for col in column_analysis if col.get("data_type") == "numeric"),
                    "text_columns": sum(1 for col in column_analysis if col.get("data_type") == "text")
                }
            }
            
            result_text = f"📊 COMPREHENSIVE SCHEMA ANALYSIS\n"
            result_text += f"{'='*50}\n\n"
            result_text += f"📋 Table: {analysis['table_info']['name']}\n"
            result_text += f"📄 Source: {analysis['table_info']['spreadsheet_title']} / {analysis['table_info']['sheet_name']}\n"
            result_text += f"📈 Rows: {analysis['table_info']['total_rows']:,}\n"
            result_text += f"📊 Columns: {analysis['table_info']['total_columns']}\n"
            result_text += f"🕒 Last Sync: {analysis['table_info']['last_sync']}\n\n"
            
            result_text += f"🔍 DATA QUALITY SUMMARY:\n"
            result_text += f"• Numeric columns: {analysis['data_quality']['numeric_columns']}\n"
            result_text += f"• Text columns: {analysis['data_quality']['text_columns']}\n"
            result_text += f"• Columns with nulls: {analysis['data_quality']['columns_with_nulls']}\n"
            result_text += f"• Average null %: {analysis['data_quality']['avg_null_percentage']}%\n\n"
            
            result_text += json.dumps(analysis, indent=2, default=str)
            
        except Exception as e:
            result_text = f"Error analyzing schema: {str(e)}"
        finally:
            conn.close()
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "describe_table":
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sheet_data'")
            if not cursor.fetchone():
                return [TextContent(type="text", text="No data found. Please sync your Google Sheets data first using the sync_sheets tool.")]
            
            # Get table schema
            cursor.execute("PRAGMA table_info(sheet_data)")
            schema = cursor.fetchall()
            
            # Get row count
            cursor.execute("SELECT COUNT(*) FROM sheet_data")
            count = cursor.fetchone()[0]
            
            # Get sample data
            cursor.execute("SELECT * FROM sheet_data LIMIT 3")
            sample_data = cursor.fetchall()
            
            # Get metadata
            metadata = get_sheet_metadata_from_db() or {}
            
            result_text = f"Table: sheet_data\n"
            result_text += f"Total rows: {count:,}\n"
            result_text += f"Last sync: {metadata.get('last_sync', 'Unknown')}\n\n"
            
            result_text += "Schema:\n"
            for col in schema:
                result_text += f"  - {col[1]} (TEXT)\n"
            
            if sample_data:
                result_text += "\nSample data:\n"
                column_names = [col[1] for col in schema]
                for i, row in enumerate(sample_data, 1):
                    result_text += f"  Row {i}: {dict(zip(column_names, row))}\n"
            
        except Exception as e:
            result_text = f"Error describing table: {str(e)}"
        finally:
            conn.close()
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "get_sheet_info":
        global current_sheet_info
        
        # Try to get current sheet info, fallback to database metadata
        if current_sheet_info:
            info = current_sheet_info
        else:
            metadata = get_sheet_metadata_from_db()
            if not metadata:
                return [TextContent(type="text", text="📋 No sheet synced yet!\n\n💡 To get started, just say:\n   \"Sync this Google Sheet: [paste your URL here]\"\n\nOr provide any Google Sheets URL and I'll analyze it for you!")]
            info = metadata
        
        result_text = "📊 Current Google Sheet Information\n"
        result_text += "=" * 40 + "\n\n"
        result_text += f"📋 Title: {info.get('title', 'Unknown')}\n"
        result_text += f"🔗 URL: {info.get('url', 'Unknown')}\n"
        result_text += f"📄 Sheet: {info.get('sheet_name', 'Unknown')}\n"
        result_text += f"📈 Rows: {info.get('rows_synced', info.get('total_rows', 0)):,}\n"
        result_text += f"📋 Columns: {len(info.get('columns', []))}\n"
        if info.get('columns'):
            result_text += f"   ├─ {', '.join(info['columns'][:5])}\n"
            if len(info['columns']) > 5:
                result_text += f"   └─ ... and {len(info['columns']) - 5} more\n"
        result_text += "\n💡 Ready to answer questions about your data!"
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "quick_analysis":
        url_or_id = arguments.get("url_or_id") if arguments else None
        sheet_name = arguments.get("sheet_name") if arguments else None
        sample_size = arguments.get("sample_size", 5) if arguments else 5
        
        if not url_or_id:
            return [TextContent(type="text", text="❌ Error: Google Sheets URL or ID is required.")]
        
        try:
            # Step 1: Sync the sheet
            sync_result = sync_sheets_to_sqlite(url_or_id, sheet_name)
            
            if not sync_result["success"]:
                return [TextContent(type="text", text=f"❌ Sync failed: {sync_result['error']}")]
            
            # Step 2: Get comprehensive schema analysis
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get table schema
            cursor.execute("PRAGMA table_info(sheet_data)")
            schema = cursor.fetchall()
            
            # Get basic stats
            cursor.execute("SELECT COUNT(*) FROM sheet_data")
            total_rows = cursor.fetchone()[0]
            
            # Get sample data
            cursor.execute(f"SELECT * FROM sheet_data LIMIT {sample_size}")
            sample_data = cursor.fetchall()
            column_names = [col[1] for col in schema]
            
            # Get data type analysis for each column
            column_stats = {}
            for col in schema:
                col_name = col[1]
                # Check if numeric
                cursor.execute(f"SELECT `{col_name}` FROM sheet_data WHERE `{col_name}` IS NOT NULL AND `{col_name}` != '' LIMIT 50")
                sample_values = [row[0] for row in cursor.fetchall()]
                
                numeric_count = 0
                for val in sample_values:
                    try:
                        float(str(val).replace(',', ''))
                        numeric_count += 1
                    except (ValueError, TypeError):
                        pass
                
                is_numeric = numeric_count > len(sample_values) * 0.7 if sample_values else False
                
                # Get unique count
                cursor.execute(f"SELECT COUNT(DISTINCT `{col_name}`) FROM sheet_data WHERE `{col_name}` IS NOT NULL AND `{col_name}` != ''")
                unique_count = cursor.fetchone()[0]
                
                column_stats[col_name] = {
                    "is_numeric": is_numeric,
                    "unique_values": unique_count,
                    "sample_values": sample_values[:3]
                }
            
            conn.close()
            
            # Format comprehensive result
            result_text = f"🚀 QUICK ANALYSIS COMPLETE\n"
            result_text += f"{'='*50}\n\n"
            
            # Sync summary
            cache_indicator = " (cached)" if sync_result.get("cached") else ""
            result_text += f"✅ Data sync successful{cache_indicator}\n"
            result_text += f"📊 Spreadsheet: {sync_result.get('title', 'Unknown')}\n"
            result_text += f"📄 Sheet: {sync_result.get('sheet_name', 'Unknown')}\n"
            result_text += f"📈 Total rows: {sync_result['rows_synced']:,}\n"
            result_text += f"📋 Total columns: {len(sync_result['columns'])}\n\n"
            
            # Column overview
            result_text += f"📊 COLUMN OVERVIEW:\n"
            for i, col_name in enumerate(sync_result['columns'], 1):
                col_stat = column_stats.get(col_name, {})
                data_type = "📈 Numeric" if col_stat.get("is_numeric") else "📝 Text"
                unique_count = col_stat.get("unique_values", 0)
                result_text += f"  {i}. {col_name} - {data_type} ({unique_count:,} unique)\n"
            
            # Sample data
            result_text += f"\n📋 SAMPLE DATA ({sample_size} rows):\n"
            for i, row in enumerate(sample_data, 1):
                row_dict = dict(zip(column_names, row))
                result_text += f"  Row {i}: {json.dumps(row_dict, default=str)}\n"
            
            # Quick insights
            numeric_cols = sum(1 for col in column_stats.values() if col.get("is_numeric"))
            text_cols = len(column_stats) - numeric_cols
            
            result_text += f"\n💡 QUICK INSIGHTS:\n"
            result_text += f"• {numeric_cols} numeric columns for calculations\n"
            result_text += f"• {text_cols} text columns for grouping/filtering\n"
            result_text += f"• Ready for analysis - ask questions about your data!\n\n"
            
            result_text += f"🔍 EXAMPLE QUERIES:\n"
            result_text += f"• \"What are the column names and types?\"\n"
            result_text += f"• \"Show me summary statistics\"\n"
            result_text += f"• \"What are the most common values in [column]?\"\n"
            
        except Exception as e:
            result_text = f"❌ Quick analysis failed: {str(e)}"
        
        return [TextContent(type="text", text=result_text)]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="sheets-mcp-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    # Check for OAuth setup on startup
    if not os.path.exists(CREDENTIALS_FILE):
        logger.warning(f"Google credentials file not found: {CREDENTIALS_FILE}. Please set up Google API credentials.")
    
    if not os.path.exists(TOKEN_FILE):
        logger.warning(f"Google OAuth token not found: {TOKEN_FILE}. Run 'python oauth_setup.py' to authenticate.")
    
    logger.info("🚀 Google Sheets Analytics MCP Server starting...")
    logger.info("💡 Users can now paste Google Sheets URLs directly - no configuration needed!")
    
    asyncio.run(main())