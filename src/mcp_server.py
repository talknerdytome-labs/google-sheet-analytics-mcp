#!/usr/bin/env python3
"""TNTM Google Sheets Analytics MCP Server - Analyze Google Sheets data with natural language queries"""

import asyncio
import json
import sys
import os
import sqlite3
import re
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# Set up paths
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent  # Go up one level to project root
os.chdir(PROJECT_ROOT)

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

# Create server with TNTM branding
app = Server(
    "tntm-sheets-server",
    version="1.0.0"
)

class GoogleSheetsService:
    def __init__(self):
        self.db_path = PROJECT_ROOT / 'data' / 'sheets_data.sqlite'
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_database()
        
        # Rate limiting and throttling
        self.api_calls = []  # Track API call timestamps
        self.max_calls_per_minute = 50  # Conservative limit
        self.min_delay_between_calls = 0.6  # 600ms between calls
        self.last_api_call = 0
        
        # Change debouncing
        self.pending_changes = {}  # spreadsheet_id -> last_change_time
        self.debounce_seconds = 5  # Wait 5 seconds after last change before syncing
        
        # Cache management
        self.cache_ttl_seconds = 300  # 5 minutes default cache TTL
        self.force_refresh_threshold = 86400  # Force refresh after 24 hours
    
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
                    column_count INTEGER,
                    last_modified TIMESTAMP,
                    content_hash TEXT,
                    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (spreadsheet_id, sheet_name)
                )
            """)
    
    def get_credentials(self) -> Optional[Credentials]:
        """Get Google credentials"""
        token_path = PROJECT_ROOT / 'data' / 'token.json'
        if not token_path.exists():
            return None
        
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            
            # Refresh token if expired
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                
                # Save the refreshed token
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            
            return creds if creds and creds.valid else None
        except Exception as e:
            print(f"Error loading credentials: {e}")
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
    
    def _calculate_content_hash(self, values: List[List[str]]) -> str:
        """Calculate hash of sheet content for change detection"""
        content_str = json.dumps(values, sort_keys=True)
        return hashlib.md5(content_str.encode()).hexdigest()
    
    def _get_sheet_changes(self, spreadsheet_id: str, sheet_name: str, values: List[List[str]]) -> Dict[str, Any]:
        """Check if sheet has changed since last sync"""
        current_hash = self._calculate_content_hash(values)
        current_rows = len(values) - 1 if values else 0
        current_cols = len(values[0]) if values else 0
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT content_hash, row_count, column_count, sync_time 
                FROM _sheet_metadata 
                WHERE spreadsheet_id = ? AND sheet_name = ?
            """, (spreadsheet_id, sheet_name))
            
            result = cursor.fetchone()
            
            if not result:
                return {
                    "is_new": True,
                    "has_changes": True,
                    "changes": ["New sheet - first sync"]
                }
            
            old_hash, old_rows, old_cols, last_sync = result
            changes = []
            
            if current_hash != old_hash:
                changes.append("Content modified")
            if current_rows != old_rows:
                changes.append(f"Row count changed: {old_rows} → {current_rows}")
            if current_cols != old_cols:
                changes.append(f"Column count changed: {old_cols} → {current_cols}")
            
            return {
                "is_new": False,
                "has_changes": len(changes) > 0,
                "changes": changes,
                "last_sync": last_sync
            }
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        now = time.time()
        
        # Remove old API calls (older than 1 minute)
        self.api_calls = [call_time for call_time in self.api_calls if now - call_time < 60]
        
        # Check if we're at the limit
        if len(self.api_calls) >= self.max_calls_per_minute:
            return False
        
        # Check minimum delay between calls
        if now - self.last_api_call < self.min_delay_between_calls:
            return False
        
        return True
    
    async def _wait_for_rate_limit(self):
        """Wait until we can make another API call"""
        while not self._check_rate_limit():
            now = time.time()
            
            # Calculate wait time
            wait_time = max(
                self.min_delay_between_calls - (now - self.last_api_call),
                0.1  # Minimum 100ms wait
            )
            
            await asyncio.sleep(wait_time)
    
    def _record_api_call(self):
        """Record an API call for rate limiting"""
        now = time.time()
        self.api_calls.append(now)
        self.last_api_call = now
    
    def _should_debounce(self, spreadsheet_id: str) -> bool:
        """Check if we should wait before syncing due to recent changes"""
        if spreadsheet_id not in self.pending_changes:
            return False
        
        time_since_change = time.time() - self.pending_changes[spreadsheet_id]
        return time_since_change < self.debounce_seconds
    
    def _mark_change_pending(self, spreadsheet_id: str):
        """Mark that a spreadsheet has pending changes"""
        self.pending_changes[spreadsheet_id] = time.time()
    
    def _is_cache_stale(self, spreadsheet_id: str, sheet_name: str) -> Dict[str, Any]:
        """Check if cached data is stale and needs refresh"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get metadata for cache validation
            cursor.execute("""
                SELECT sync_time, table_name, row_count 
                FROM _sheet_metadata 
                WHERE spreadsheet_id = ? AND sheet_name = ?
            """, (spreadsheet_id, sheet_name))
            
            result = cursor.fetchone()
            
            if not result:
                return {
                    "is_stale": True,
                    "reason": "no_metadata",
                    "action": "full_sync"
                }
            
            sync_time_str, table_name, expected_rows = result
            
            # Parse sync time
            try:
                sync_time = datetime.fromisoformat(sync_time_str.replace('Z', '+00:00'))
                age_seconds = (datetime.now() - sync_time.replace(tzinfo=None)).total_seconds()
            except:
                return {
                    "is_stale": True,
                    "reason": "invalid_sync_time",
                    "action": "full_sync"
                }
            
            # Check if cache is too old
            if age_seconds > self.force_refresh_threshold:
                return {
                    "is_stale": True,
                    "reason": "forced_refresh_threshold",
                    "age_hours": age_seconds / 3600,
                    "action": "full_sync"
                }
            
            # Check if cache TTL exceeded
            if age_seconds > self.cache_ttl_seconds:
                return {
                    "is_stale": True,
                    "reason": "cache_ttl_exceeded",
                    "age_minutes": age_seconds / 60,
                    "action": "change_check"
                }
            
            # Verify table actually exists and has expected data
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                actual_rows = cursor.fetchone()[0]
                
                if actual_rows != expected_rows:
                    return {
                        "is_stale": True,
                        "reason": "row_count_mismatch",
                        "expected": expected_rows,
                        "actual": actual_rows,
                        "action": "full_sync"
                    }
            except sqlite3.OperationalError:
                return {
                    "is_stale": True,
                    "reason": "table_missing",
                    "action": "full_sync"
                }
            
            return {
                "is_stale": False,
                "reason": "cache_valid",
                "age_minutes": age_seconds / 60,
                "action": "use_cache"
            }
    
    def _should_force_refresh(self, cache_status: Dict[str, Any]) -> bool:
        """Determine if we should force refresh regardless of change detection"""
        return cache_status["action"] in ["full_sync"]
    
    def _get_cache_strategy(self, spreadsheet_id: str, sheet_name: str) -> Dict[str, Any]:
        """Get comprehensive caching strategy for a sheet"""
        cache_status = self._is_cache_stale(spreadsheet_id, sheet_name)
        
        # Check for pending changes
        has_pending_changes = spreadsheet_id in self.pending_changes
        should_debounce = self._should_debounce(spreadsheet_id)
        
        strategy = {
            "cache_status": cache_status,
            "has_pending_changes": has_pending_changes,
            "should_debounce": should_debounce,
            "recommended_action": cache_status["action"]
        }
        
        # Override action based on pending changes
        if has_pending_changes and not should_debounce:
            strategy["recommended_action"] = "change_check"
        elif should_debounce:
            strategy["recommended_action"] = "wait_for_debounce"
        
        return strategy

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
        ),
        Tool(
            name="check_sheet_changes",
            description="Check if synced sheets have been modified and need re-syncing",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Google Sheets URL to check (optional - checks all if not provided)"
                    },
                    "auto_sync": {
                        "type": "boolean",
                        "description": "Automatically sync changed sheets (default: false)",
                        "default": False
                    },
                    "batch_size": {
                        "type": "integer",
                        "description": "Number of sheets to check per batch (default: 5)",
                        "default": 5
                    }
                }
            }
        ),
        Tool(
            name="batch_sync_changes",
            description="Sync multiple changed sheets with rate limiting and progress tracking",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_sheets": {
                        "type": "integer",
                        "description": "Maximum sheets to sync in one batch (default: 10)",
                        "default": 10
                    },
                    "delay_between_sheets": {
                        "type": "number",
                        "description": "Seconds to wait between sheet syncs (default: 1.0)",
                        "default": 1.0
                    }
                }
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
            error_msg = {
                "error": "Authentication failed",
                "details": "No valid credentials found. Please ensure token.json exists in the data/ directory.",
                "token_path": str(PROJECT_ROOT / 'data' / 'token.json'),
                "token_exists": (PROJECT_ROOT / 'data' / 'token.json').exists()
            }
            return [TextContent(type="text", text=json.dumps(error_msg, indent=2))]
        
        try:
            # Check if we should debounce this sync
            if service._should_debounce(spreadsheet_id):
                return [TextContent(type="text", text=json.dumps({
                    "status": "debounced",
                    "message": f"Recent changes detected. Please wait {service.debounce_seconds} seconds before syncing.",
                    "spreadsheet_id": spreadsheet_id
                }))]
            
            # Wait for rate limit if needed
            await service._wait_for_rate_limit()
            
            sheets_service = build('sheets', 'v4', credentials=creds)
            
            # Get spreadsheet metadata
            service._record_api_call()
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
                
                # Get data with row limit (with rate limiting)
                await service._wait_for_rate_limit()
                range_name = f"'{sheet_title}'!A1:Z{max_rows}"
                service._record_api_call()
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute()
                
                values = result.get('values', [])
                if not values:
                    continue
                
                # Get caching strategy for this sheet
                cache_strategy = service._get_cache_strategy(spreadsheet_id, sheet_title)
                
                # Handle different cache strategies
                if cache_strategy["recommended_action"] == "use_cache":
                    synced_sheets.append({
                        "sheet_name": sheet_title,
                        "table_name": safe_name,
                        "rows": cache_strategy["cache_status"].get("expected", len(values) - 1),
                        "status": "cached",
                        "cache_age_minutes": cache_strategy["cache_status"]["age_minutes"],
                        "last_sync": cache_strategy["cache_status"].get("last_sync")
                    })
                    continue
                elif cache_strategy["recommended_action"] == "wait_for_debounce":
                    synced_sheets.append({
                        "sheet_name": sheet_title,
                        "table_name": safe_name,
                        "status": "debounced",
                        "message": f"Waiting {service.debounce_seconds}s for changes to settle"
                    })
                    continue
                elif cache_strategy["recommended_action"] == "change_check":
                    # Check for actual changes
                    change_info = service._get_sheet_changes(spreadsheet_id, sheet_title, values)
                    
                    if not change_info["has_changes"] and not service._should_force_refresh(cache_strategy["cache_status"]):
                        synced_sheets.append({
                            "sheet_name": sheet_title,
                            "table_name": safe_name,
                            "rows": len(values) - 1,
                            "status": "no_changes",
                            "cache_status": cache_strategy["cache_status"]["reason"],
                            "last_sync": change_info.get("last_sync")
                        })
                        continue
                # If we reach here, we need to perform a full sync
                
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
                content_hash = service._calculate_content_hash(values)
                
                # Update metadata
                cursor.execute("""
                    INSERT OR REPLACE INTO _sheet_metadata 
                    (spreadsheet_id, spreadsheet_title, sheet_name, table_name, row_count, column_count, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (spreadsheet_id, title, sheet_title, safe_name, row_count, len(headers), content_hash))
                
                synced_sheets.append({
                    "sheet_name": sheet_title,
                    "table_name": safe_name,
                    "rows": row_count,
                    "columns": safe_headers,
                    "status": "synced",
                    "changes": change_info["changes"]
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
            error_msg = {
                "error": "Authentication failed",
                "details": "No valid credentials found. Please ensure token.json exists in the data/ directory.",
                "token_path": str(PROJECT_ROOT / 'data' / 'token.json'),
                "token_exists": (PROJECT_ROOT / 'data' / 'token.json').exists()
            }
            return [TextContent(type="text", text=json.dumps(error_msg, indent=2))]
        
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
    
    elif name == "check_sheet_changes":
        url = arguments.get("url")
        auto_sync = arguments.get("auto_sync", False)
        
        creds = service.get_credentials()
        if not creds:
            error_msg = {
                "error": "Authentication failed",
                "details": "No valid credentials found. Please ensure token.json exists in the data/ directory.",
                "token_path": str(PROJECT_ROOT / 'data' / 'token.json'),
                "token_exists": (PROJECT_ROOT / 'data' / 'token.json').exists()
            }
            return [TextContent(type="text", text=json.dumps(error_msg, indent=2))]
        
        try:
            sheets_service = build('sheets', 'v4', credentials=creds)
            
            # Get sheets to check
            sheets_to_check = []
            
            if url:
                # Check specific spreadsheet
                spreadsheet_id = service.extract_spreadsheet_id(url)
                if not spreadsheet_id:
                    return [TextContent(type="text", text=json.dumps({"error": "Invalid URL"}))]
                
                with sqlite3.connect(service.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT spreadsheet_id, spreadsheet_title, sheet_name, table_name 
                        FROM _sheet_metadata 
                        WHERE spreadsheet_id = ?
                    """, (spreadsheet_id,))
                    sheets_to_check = cursor.fetchall()
            else:
                # Check all synced sheets
                with sqlite3.connect(service.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT DISTINCT spreadsheet_id, spreadsheet_title, sheet_name, table_name
                        FROM _sheet_metadata
                    """)
                    sheets_to_check = cursor.fetchall()
            
            if not sheets_to_check:
                return [TextContent(type="text", text=json.dumps({
                    "status": "no_sheets",
                    "message": "No synced sheets found to check"
                }))]
            
            changes_found = []
            synced_count = 0
            
            for sheet_info in sheets_to_check:
                spreadsheet_id, spreadsheet_title, sheet_name, table_name = sheet_info
                
                try:
                    # Get current data from Google Sheets
                    range_name = f"'{sheet_name}'!A1:Z1000"  # Check first 1000 rows
                    result = sheets_service.spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range=range_name
                    ).execute()
                    
                    values = result.get('values', [])
                    change_info = service._get_sheet_changes(spreadsheet_id, sheet_name, values)
                    
                    if change_info["has_changes"]:
                        change_entry = {
                            "spreadsheet": spreadsheet_title,
                            "sheet": sheet_name,
                            "table": table_name,
                            "changes": change_info["changes"],
                            "last_sync": change_info.get("last_sync"),
                            "synced": False
                        }
                        
                        # Auto-sync if requested
                        if auto_sync:
                            # Re-sync this sheet (simplified version)
                            if values:
                                headers = values[0] if values else []
                                safe_headers = [re.sub(r'[^a-zA-Z0-9_]', '_', h.lower()) for h in headers]
                                
                                with sqlite3.connect(service.db_path) as conn:
                                    cursor = conn.cursor()
                                    
                                    # Drop and recreate table
                                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                                    columns = 'row_id INTEGER PRIMARY KEY, ' + ', '.join([f"{h} TEXT" for h in safe_headers])
                                    cursor.execute(f"CREATE TABLE {table_name} ({columns})")
                                    
                                    # Insert data
                                    for idx, row in enumerate(values[1:], 1):
                                        padded_row = row + [''] * (len(headers) - len(row))
                                        placeholders = ', '.join(['?' for _ in range(len(headers) + 1)])
                                        cursor.execute(f"INSERT INTO {table_name} VALUES ({placeholders})", [idx] + padded_row)
                                    
                                    # Update metadata
                                    content_hash = service._calculate_content_hash(values)
                                    cursor.execute("""
                                        UPDATE _sheet_metadata 
                                        SET row_count = ?, column_count = ?, content_hash = ?, sync_time = CURRENT_TIMESTAMP
                                        WHERE spreadsheet_id = ? AND sheet_name = ?
                                    """, (len(values) - 1, len(headers), content_hash, spreadsheet_id, sheet_name))
                                    
                                    conn.commit()
                                
                                change_entry["synced"] = True
                                synced_count += 1
                        
                        changes_found.append(change_entry)
                
                except Exception as e:
                    changes_found.append({
                        "spreadsheet": spreadsheet_title,
                        "sheet": sheet_name,
                        "error": str(e)
                    })
            
            result = {
                "status": "success",
                "total_sheets_checked": len(sheets_to_check),
                "sheets_with_changes": len(changes_found),
                "auto_synced": synced_count if auto_sync else 0,
                "changes": changes_found
            }
            
            if not changes_found:
                result["message"] = "All sheets are up to date"
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "batch_sync_changes":
        max_sheets = arguments.get("max_sheets", 10)
        delay_between_sheets = arguments.get("delay_between_sheets", 1.0)
        
        creds = service.get_credentials()
        if not creds:
            error_msg = {
                "error": "Authentication failed",
                "details": "No valid credentials found. Please ensure token.json exists in the data/ directory.",
                "token_path": str(PROJECT_ROOT / 'data' / 'token.json'),
                "token_exists": (PROJECT_ROOT / 'data' / 'token.json').exists()
            }
            return [TextContent(type="text", text=json.dumps(error_msg, indent=2))]
        
        try:
            # Get all sheets that need syncing
            with sqlite3.connect(service.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT spreadsheet_id, spreadsheet_title, sheet_name, table_name
                    FROM _sheet_metadata
                    ORDER BY sync_time ASC
                    LIMIT ?
                """, (max_sheets,))
                sheets_to_sync = cursor.fetchall()
            
            if not sheets_to_sync:
                return [TextContent(type="text", text=json.dumps({
                    "status": "no_sheets",
                    "message": "No sheets found to sync"
                }))]
            
            sheets_service = build('sheets', 'v4', credentials=creds)
            
            synced_sheets = []
            failed_sheets = []
            skipped_sheets = []
            
            for i, (spreadsheet_id, spreadsheet_title, sheet_name, table_name) in enumerate(sheets_to_sync):
                try:
                    # Add delay between sheets
                    if i > 0:
                        await asyncio.sleep(delay_between_sheets)
                    
                    # Check if we should skip due to debouncing
                    if service._should_debounce(spreadsheet_id):
                        skipped_sheets.append({
                            "spreadsheet": spreadsheet_title,
                            "sheet": sheet_name,
                            "reason": "debounced"
                        })
                        continue
                    
                    # Wait for rate limit
                    await service._wait_for_rate_limit()
                    
                    # Get current sheet data
                    range_name = f"'{sheet_name}'!A1:Z1000"
                    service._record_api_call()
                    result = sheets_service.spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range=range_name
                    ).execute()
                    
                    values = result.get('values', [])
                    if not values:
                        continue
                    
                    # Check for changes
                    change_info = service._get_sheet_changes(spreadsheet_id, sheet_name, values)
                    
                    if not change_info["has_changes"]:
                        skipped_sheets.append({
                            "spreadsheet": spreadsheet_title,
                            "sheet": sheet_name,
                            "reason": "no_changes"
                        })
                        continue
                    
                    # Sync the sheet
                    headers = values[0] if values else []
                    safe_headers = [re.sub(r'[^a-zA-Z0-9_]', '_', h.lower()) for h in headers]
                    
                    with sqlite3.connect(service.db_path) as conn:
                        cursor = conn.cursor()
                        
                        # Drop and recreate table
                        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                        columns = 'row_id INTEGER PRIMARY KEY, ' + ', '.join([f"{h} TEXT" for h in safe_headers])
                        cursor.execute(f"CREATE TABLE {table_name} ({columns})")
                        
                        # Insert data
                        for idx, row in enumerate(values[1:], 1):
                            padded_row = row + [''] * (len(headers) - len(row))
                            placeholders = ', '.join(['?' for _ in range(len(headers) + 1)])
                            cursor.execute(f"INSERT INTO {table_name} VALUES ({placeholders})", [idx] + padded_row)
                        
                        # Update metadata
                        content_hash = service._calculate_content_hash(values)
                        cursor.execute("""
                            UPDATE _sheet_metadata 
                            SET row_count = ?, column_count = ?, content_hash = ?, sync_time = CURRENT_TIMESTAMP
                            WHERE spreadsheet_id = ? AND sheet_name = ?
                        """, (len(values) - 1, len(headers), content_hash, spreadsheet_id, sheet_name))
                        
                        conn.commit()
                    
                    synced_sheets.append({
                        "spreadsheet": spreadsheet_title,
                        "sheet": sheet_name,
                        "rows": len(values) - 1,
                        "changes": change_info["changes"]
                    })
                    
                except Exception as e:
                    failed_sheets.append({
                        "spreadsheet": spreadsheet_title,
                        "sheet": sheet_name,
                        "error": str(e)
                    })
            
            result = {
                "status": "completed",
                "total_processed": len(sheets_to_sync),
                "synced": len(synced_sheets),
                "skipped": len(skipped_sheets),
                "failed": len(failed_sheets),
                "synced_sheets": synced_sheets,
                "skipped_sheets": skipped_sheets,
                "failed_sheets": failed_sheets,
                "rate_limit_info": {
                    "api_calls_in_last_minute": len(service.api_calls),
                    "max_calls_per_minute": service.max_calls_per_minute
                }
            }
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
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
                    server_name="TNTM Google Sheets Analytics",
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