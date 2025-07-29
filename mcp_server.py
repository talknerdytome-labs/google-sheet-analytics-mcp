#!/usr/bin/env python3
"""Enhanced practical Google Sheets MCP server with better multi-tab support"""

import asyncio
import json
import sys
import os
import sqlite3
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

# Set up paths
SCRIPT_DIR = Path(__file__).parent.absolute()
os.chdir(SCRIPT_DIR)

# MCP imports
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Google imports
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Constants
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
MAX_ROWS_PER_SYNC = 1000  # Default limit

# Create server
app = Server("enhanced-sheets-server")

class GoogleSheetsService:
    def __init__(self):
        self.db_path = SCRIPT_DIR / 'data' / 'sheets_data.sqlite'
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with metadata table"""
        with sqlite3.connect(self.db_path) as conn:
            # Metadata table to track synced sheets
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _sheet_metadata (
                    spreadsheet_id TEXT,
                    spreadsheet_title TEXT,
                    sheet_name TEXT,
                    table_name TEXT,
                    row_count INTEGER,
                    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (spreadsheet_id, sheet_name)
                )
            """)
    
    def get_credentials(self) -> Optional[Credentials]:
        """Get Google credentials"""
        token_path = SCRIPT_DIR / 'data' / 'token.json'
        if not token_path.exists():
            return None
        
        try:
            return Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except:
            return None
    
    def extract_spreadsheet_id(self, url: str) -> Optional[str]:
        """Extract spreadsheet ID from URL"""
        patterns = [
            r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)',
            r'^([a-zA-Z0-9-_]+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

# Create service instance
service = GoogleSheetsService()

@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="smart_sync",
            description="Sync Google Sheet data intelligently with row limits",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Google Sheets URL"
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Maximum rows to sync per sheet (default: 1000)",
                        "default": 1000
                    },
                    "sheets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific sheets to sync (optional, syncs all if not provided)"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="query_sheets",
            description="Query synced sheet data using SQL (supports JOINs across tabs)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL query to run"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_synced_sheets",
            description="List all synced sheets and their tables",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="analyze_sheets",
            description="Analyze relationships between sheets and suggest queries",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "What you want to analyze across sheets"
                    }
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="get_sheet_preview",
            description="Preview any sheet without syncing",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Google Sheets URL"
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Specific sheet to preview (optional)"
                    },
                    "rows": {
                        "type": "integer",
                        "description": "Number of rows to preview (default: 10)",
                        "default": 10
                    }
                },
                "required": ["url"]
            }
        )
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "smart_sync":
        url = arguments.get("url", "")
        max_rows = arguments.get("max_rows", MAX_ROWS_PER_SYNC)
        target_sheets = arguments.get("sheets", [])
        
        spreadsheet_id = service.extract_spreadsheet_id(url)
        if not spreadsheet_id:
            return [TextContent(type="text", text=json.dumps({"error": "Invalid URL"}))]
        
        creds = service.get_credentials()
        if not creds:
            return [TextContent(type="text", text=json.dumps({"error": "No credentials found"}))]
        
        try:
            sheets_service = build('sheets', 'v4', credentials=creds)
            
            # Get spreadsheet metadata
            spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            title = spreadsheet['properties']['title']
            sheets = spreadsheet['sheets']
            
            # Connect to database
            conn = sqlite3.connect(service.db_path)
            cursor = conn.cursor()
            
            synced_sheets = []
            total_rows = 0
            
            for sheet in sheets:
                sheet_title = sheet['properties']['title']
                
                # Skip if specific sheets requested and this isn't one
                if target_sheets and sheet_title not in target_sheets:
                    continue
                
                # Create safe table name
                safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', sheet_title.lower())
                safe_name = f"sheet_{safe_name}" if safe_name[0].isdigit() else safe_name
                
                # Get data with row limit
                range_name = f"'{sheet_title}'!A1:Z{max_rows}"
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute()
                
                values = result.get('values', [])
                if not values:
                    continue
                
                # Create table
                headers = values[0] if values else []
                safe_headers = [re.sub(r'[^a-zA-Z0-9_]', '_', h.lower()) for h in headers]
                
                # Drop existing table
                cursor.execute(f"DROP TABLE IF EXISTS {safe_name}")
                
                # Create new table with row ID
                columns = 'row_id INTEGER PRIMARY KEY, ' + ', '.join([f"{h} TEXT" for h in safe_headers])
                cursor.execute(f"CREATE TABLE {safe_name} ({columns})")
                
                # Insert data
                for idx, row in enumerate(values[1:], 1):
                    # Pad row to match headers
                    padded_row = row + [''] * (len(headers) - len(row))
                    placeholders = ', '.join(['?' for _ in range(len(headers) + 1)])
                    cursor.execute(f"INSERT INTO {safe_name} VALUES ({placeholders})", [idx] + padded_row)
                
                row_count = len(values) - 1
                total_rows += row_count
                
                # Update metadata
                cursor.execute("""
                    INSERT OR REPLACE INTO _sheet_metadata 
                    (spreadsheet_id, spreadsheet_title, sheet_name, table_name, row_count)
                    VALUES (?, ?, ?, ?, ?)
                """, (spreadsheet_id, title, sheet_title, safe_name, row_count))
                
                synced_sheets.append({
                    "sheet_name": sheet_title,
                    "table_name": safe_name,
                    "rows": row_count,
                    "columns": safe_headers
                })
            
            conn.commit()
            conn.close()
            
            result = {
                "status": "success",
                "spreadsheet": title,
                "sheets_synced": len(synced_sheets),
                "total_rows": total_rows,
                "sheets": synced_sheets,
                "note": f"Limited to {max_rows} rows per sheet"
            }
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "query_sheets":
        query = arguments.get("query", "")
        
        try:
            conn = sqlite3.connect(service.db_path)
            cursor = conn.cursor()
            
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            result = {
                "columns": columns,
                "rows": rows[:100],  # Limit results
                "total_rows": len(rows),
                "limited": len(rows) > 100
            }
            
            conn.close()
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "list_synced_sheets":
        try:
            conn = sqlite3.connect(service.db_path)
            cursor = conn.cursor()
            
            # Get synced sheets info
            cursor.execute("""
                SELECT spreadsheet_title, sheet_name, table_name, row_count, sync_time
                FROM _sheet_metadata
                ORDER BY spreadsheet_title, sheet_name
            """)
            
            sheets = cursor.fetchall()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_%'")
            tables = [t[0] for t in cursor.fetchall()]
            
            result = {
                "synced_sheets": [
                    {
                        "spreadsheet": s[0],
                        "sheet": s[1],
                        "table": s[2],
                        "rows": s[3],
                        "synced_at": s[4]
                    } for s in sheets
                ],
                "tables": tables
            }
            
            conn.close()
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_sheets":
        question = arguments.get("question", "")
        
        try:
            conn = sqlite3.connect(service.db_path)
            cursor = conn.cursor()
            
            # Get all tables and their columns
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_%'")
            tables = cursor.fetchall()
            
            table_info = {}
            common_columns = {}
            
            for table in tables:
                table_name = table[0]
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [(col[1], col[2]) for col in cursor.fetchall()]
                table_info[table_name] = columns
                
                # Track common columns for JOIN suggestions
                for col_name, col_type in columns:
                    if col_name not in ['row_id']:
                        if col_name not in common_columns:
                            common_columns[col_name] = []
                        common_columns[col_name].append(table_name)
            
            # Find potential JOIN columns
            join_candidates = {col: tables for col, tables in common_columns.items() if len(tables) > 1}
            
            # Generate suggestions based on question
            suggestions = []
            
            if any(word in question.lower() for word in ['combine', 'join', 'merge', 'together']):
                for col, tables in join_candidates.items():
                    if len(tables) == 2:
                        suggestions.append(f"SELECT * FROM {tables[0]} JOIN {tables[1]} ON {tables[0]}.{col} = {tables[1]}.{col}")
            
            if 'all' in question.lower():
                suggestions.append("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_%'")
                
            if any(word in question.lower() for word in ['count', 'how many']):
                for table in table_info:
                    suggestions.append(f"SELECT COUNT(*) as total_rows FROM {table}")
            
            result = {
                "tables": list(table_info.keys()),
                "table_schemas": {name: [{"column": col[0], "type": col[1]} for col in cols] 
                                 for name, cols in table_info.items()},
                "common_columns": join_candidates,
                "suggested_queries": suggestions,
                "tip": "Use query_sheets to run any SQL query across your synced data"
            }
            
            conn.close()
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_sheet_preview":
        url = arguments.get("url", "")
        sheet_name = arguments.get("sheet_name")
        rows = arguments.get("rows", 10)
        
        spreadsheet_id = service.extract_spreadsheet_id(url)
        if not spreadsheet_id:
            return [TextContent(type="text", text=json.dumps({"error": "Invalid URL"}))]
        
        creds = service.get_credentials()
        if not creds:
            return [TextContent(type="text", text=json.dumps({"error": "No credentials found"}))]
        
        try:
            sheets_service = build('sheets', 'v4', credentials=creds)
            
            # Get spreadsheet info
            spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            title = spreadsheet['properties']['title']
            sheet_names = [s['properties']['title'] for s in spreadsheet['sheets']]
            
            # Get preview of specified or first sheet
            target_sheet = sheet_name if sheet_name and sheet_name in sheet_names else sheet_names[0]
            range_name = f"'{target_sheet}'!A1:Z{rows}"
            
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            preview = {
                "status": "success",
                "title": title,
                "available_sheets": sheet_names,
                "previewing_sheet": target_sheet,
                "preview_rows": len(values),
                "headers": values[0] if values else [],
                "data": values[1:] if len(values) > 1 else []
            }
            
        except Exception as e:
            preview = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(preview, indent=2))]
    
    else:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

async def main():
    """Main entry point"""
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="enhanced-sheets-server",
                    server_version="1.0.0",
                    capabilities=app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    asyncio.run(main())