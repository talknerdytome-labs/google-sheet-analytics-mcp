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
import logging
import gc
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
MAX_ROWS_PER_SYNC = 100000  # Default limit - balances completeness with performance

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        """Initialize SQLite database with metadata table and optimal settings for large datasets"""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            # Configure SQLite for better concurrency and performance with 1M+ rows
            conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
            conn.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and performance  
            conn.execute("PRAGMA cache_size=100000")  # Increased cache for large datasets (100K pages)
            conn.execute("PRAGMA temp_store=memory")  # Store temp tables in memory
            conn.execute("PRAGMA mmap_size=1073741824")  # 1GB memory map for large datasets
            conn.execute("PRAGMA busy_timeout=10000")  # 10 second timeout for better concurrency
            
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
            
            # Add indexes for commonly queried columns
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metadata_spreadsheet 
                ON _sheet_metadata(spreadsheet_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metadata_sync_time 
                ON _sheet_metadata(sync_time)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metadata_table_name 
                ON _sheet_metadata(table_name)
            """)
    
    def _get_db_connection(self) -> sqlite3.Connection:
        """Get a database connection with optimal settings for large datasets"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=100000")
        conn.execute("PRAGMA temp_store=memory")
        conn.execute("PRAGMA mmap_size=1073741824")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn
    
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
    
    def _calculate_content_hash_streaming(self, chunks) -> str:
        """Calculate hash progressively for large datasets"""
        hasher = hashlib.md5()
        row_count = 0
        
        for chunk in chunks:
            # For very large datasets, sample every 10th row after first 1000
            for i, row in enumerate(chunk):
                if row_count < 1000 or row_count % 10 == 0:
                    hasher.update(json.dumps(row, sort_keys=True).encode())
                row_count += 1
        
        return hasher.hexdigest()
    
    async def _fetch_sheet_chunked(self, sheets_service, spreadsheet_id: str, sheet_name: str, 
                                  total_rows: int, chunk_size: int = 50000):
        """Fetch sheet data in chunks for large datasets"""
        chunks_fetched = 0
        row_offset = 0
        
        # Determine actual data range (columns)
        await self._wait_for_rate_limit()
        self._record_api_call()
        
        # Get first row to determine column range
        sample_range = f"'{sheet_name}'!1:1"
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sample_range
        ).execute()
        
        first_row = result.get('values', [[]])[0] if result.get('values') else []
        if not first_row:
            return
        
        # Calculate actual column range (A to last column with data)
        last_col = self._number_to_column(len(first_row))
        
        while row_offset < total_rows:
            # Calculate chunk range
            start_row = row_offset + 1
            end_row = min(row_offset + chunk_size, total_rows)
            range_name = f"'{sheet_name}'!A{start_row}:{last_col}{end_row}"
            
            # Fetch chunk with rate limiting
            await self._wait_for_rate_limit()
            self._record_api_call()
            
            chunk_result = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            chunk_data = chunk_result.get('values', [])
            if chunk_data:
                # Include headers in first chunk
                if chunks_fetched == 0 and row_offset > 0:
                    chunk_data = [first_row] + chunk_data
                yield chunk_data
            
            chunks_fetched += 1
            row_offset = end_row
            
            # Progress callback placeholder
            progress = (row_offset / total_rows) * 100
            logger.info(f"Fetched {row_offset}/{total_rows} rows ({progress:.1f}%)")
    
    def _number_to_column(self, n: int) -> str:
        """Convert column number to letter (1=A, 26=Z, 27=AA, etc.)"""
        result = ""
        while n > 0:
            n -= 1
            result = chr(n % 26 + ord('A')) + result
            n //= 26
        return result
    
    def _get_sheet_changes(self, cursor: sqlite3.Cursor, spreadsheet_id: str, sheet_name: str, values: List[List[str]]) -> Dict[str, Any]:
        """Check if sheet has changed since last sync"""
        current_hash = self._calculate_content_hash(values)
        current_rows = len(values) - 1 if values else 0
        current_cols = len(values[0]) if values else 0
        
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
        
        # Prevent memory leak: keep only recent API calls (last 2 minutes)
        self.api_calls = [call_time for call_time in self.api_calls if now - call_time < 120]
    
    def cleanup(self):
        """Clean up service state (call at end of tool execution)"""
        # Clear rate limiting state to prevent cross-session contamination
        self.api_calls.clear()
        self.last_api_call = 0
        
        # Clear pending changes state  
        self.pending_changes.clear()
    
    def _should_debounce(self, spreadsheet_id: str) -> bool:
        """Check if we should wait before syncing due to recent changes"""
        if spreadsheet_id not in self.pending_changes:
            return False
        
        time_since_change = time.time() - self.pending_changes[spreadsheet_id]
        return time_since_change < self.debounce_seconds
    
    def _mark_change_pending(self, spreadsheet_id: str):
        """Mark that a spreadsheet has pending changes"""
        self.pending_changes[spreadsheet_id] = time.time()
    
    def _is_cache_stale(self, cursor: sqlite3.Cursor, spreadsheet_id: str, sheet_name: str) -> Dict[str, Any]:
        """Check if cached data is stale and needs refresh"""
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
    
    def _get_cache_strategy(self, cursor: sqlite3.Cursor, spreadsheet_id: str, sheet_name: str) -> Dict[str, Any]:
        """Get comprehensive caching strategy for a sheet"""
        cache_status = self._is_cache_stale(cursor, spreadsheet_id, sheet_name)
        
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

# Service instances will be created per tool call to prevent session state issues

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
                        "description": "Maximum rows to sync per sheet (default: 100000)",
                        "default": 100000
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
        # Create fresh service instance for this tool call
        service = GoogleSheetsService()
        
        url = arguments.get("url")
        max_rows = arguments.get("max_rows", MAX_ROWS_PER_SYNC)
        target_sheets = arguments.get("sheets", [])
        
        # Enhanced input validation
        if not url or not isinstance(url, str) or not url.strip():
            return [TextContent(type="text", text=json.dumps({
                "error": "Google Sheets URL is required",
                "details": "Please provide a valid Google Sheets URL",
                "examples": [
                    "https://docs.google.com/spreadsheets/d/1ABC123.../edit",
                    "1ABC123DEF456..."
                ],
                "tip": "Copy the URL from your browser when viewing the Google Sheet"
            }))]
        
        url = url.strip()  # Clean the URL
        spreadsheet_id = service.extract_spreadsheet_id(url)
        if not spreadsheet_id:
            return [TextContent(type="text", text=json.dumps({
                "error": "Invalid Google Sheets URL format",
                "details": "Could not extract spreadsheet ID from the provided URL",
                "examples": [
                    "https://docs.google.com/spreadsheets/d/1ABC123.../edit",
                    "1ABC123DEF456..."
                ],
                "tip": "Make sure to copy the complete URL from your browser"
            }))]
        
        creds = service.get_credentials()
        if not creds:
            error_msg = {
                "error": "Authentication failed",
                "details": "No valid credentials found. Please ensure token.json exists in the data/ directory.",
                "token_path": str(PROJECT_ROOT / 'data' / 'token.json'),
                "token_exists": (PROJECT_ROOT / 'data' / 'token.json').exists()
            }
            return [TextContent(type="text", text=json.dumps(error_msg, indent=2))]
        
        conn = None
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
            
            # Connect to database with optimal settings
            conn = service._get_db_connection()
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
                
                # Get sheet dimensions to determine if chunking is needed
                sheet_properties = sheet['properties']
                grid_properties = sheet_properties.get('gridProperties', {})
                sheet_rows = grid_properties.get('rowCount', 0)
                sheet_cols = grid_properties.get('columnCount', 0)
                
                # Determine actual data rows (may be less than sheet dimensions)
                actual_rows = min(sheet_rows, max_rows)
                
                # Decide whether to use chunked fetching
                use_chunking = actual_rows > 10000
                chunk_size = 50000 if actual_rows > 100000 else 10000
                
                values = []
                headers = None
                
                if use_chunking and actual_rows > 0:
                    # Use chunked fetching for large sheets
                    logger.info(f"Using chunked fetching for {sheet_title}: {actual_rows} rows")
                    
                    async for chunk in service._fetch_sheet_chunked(
                        sheets_service, spreadsheet_id, sheet_title, actual_rows, chunk_size
                    ):
                        if not headers:
                            headers = chunk[0] if chunk else []
                            values = chunk
                        else:
                            # Append data rows (skip header in subsequent chunks)
                            values.extend(chunk[1:] if len(chunk) > 1 else [])
                        
                        # Break if we've reached max_rows
                        if len(values) >= max_rows:
                            values = values[:max_rows]
                            break
                else:
                    # Use traditional single fetch for smaller sheets
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
                
                # Initialize change_info for this sheet iteration
                change_info = None
                
                # Get caching strategy for this sheet
                cache_strategy = service._get_cache_strategy(cursor, spreadsheet_id, sheet_title)
                
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
                    change_info = service._get_sheet_changes(cursor, spreadsheet_id, sheet_title, values)
                    
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
                # Ensure change_info is set for full sync scenarios
                if change_info is None:
                    change_info = service._get_sheet_changes(cursor, spreadsheet_id, sheet_title, values)
                
                # Create table
                headers = values[0] if values else []
                safe_headers = [re.sub(r'[^a-zA-Z0-9_]', '_', h.lower()) for h in headers]
                
                # Drop existing table
                cursor.execute(f"DROP TABLE IF EXISTS {safe_name}")
                
                # Create new table with row ID and optimized column types
                columns = 'row_id INTEGER PRIMARY KEY, ' + ', '.join([f"{h} TEXT" for h in safe_headers])
                cursor.execute(f"CREATE TABLE {safe_name} ({columns})")
                
                # Prepare data for bulk insert
                data_rows = values[1:] if len(values) > 1 else []
                row_count = len(data_rows)
                
                if row_count > 0:
                    # Use bulk insert with executemany for performance
                    bulk_data = []
                    for idx, row in enumerate(data_rows, 1):
                        # Pad row to match headers
                        padded_row = row + [''] * (len(headers) - len(row))
                        bulk_data.append([idx] + padded_row)
                    
                    # Insert in batches for optimal performance
                    batch_size = 10000
                    placeholders = ', '.join(['?' for _ in range(len(headers) + 1)])
                    
                    for i in range(0, len(bulk_data), batch_size):
                        batch = bulk_data[i:i + batch_size]
                        cursor.executemany(f"INSERT INTO {safe_name} VALUES ({placeholders})", batch)
                        
                        # Log progress for large datasets
                        if row_count > 10000:
                            progress = min(i + batch_size, row_count)
                            logger.info(f"Inserted {progress}/{row_count} rows into {safe_name}")
                
                total_rows += row_count
                
                # Calculate content hash efficiently
                if use_chunking and row_count > 100000:
                    # Use sampling for very large datasets
                    sample_size = min(10000, row_count)
                    sample_indices = range(0, row_count, row_count // sample_size)
                    sample_values = [values[0]] + [values[i+1] for i in sample_indices if i+1 < len(values)]
                    content_hash = service._calculate_content_hash(sample_values)
                else:
                    content_hash = service._calculate_content_hash(values)
                
                # Add indexes after bulk insert for better performance
                if row_count > 10000:
                    # Create indexes on commonly queried columns (first few columns often used)
                    for i, header in enumerate(safe_headers[:3]):
                        try:
                            cursor.execute(f"CREATE INDEX idx_{safe_name}_{header} ON {safe_name}({header})")
                        except:
                            pass  # Index creation might fail for some columns
                
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
                
                # Memory cleanup for large datasets
                if row_count > 50000:
                    del values
                    if 'bulk_data' in locals():
                        del bulk_data
                    gc.collect()
                    logger.info(f"Memory cleanup performed after syncing {sheet_title}")
            
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
        finally:
            # Clean up resources
            if conn:
                try:
                    conn.close()
                except:
                    pass
            service.cleanup()
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "query_sheets":
        # Create fresh service instance for this tool call
        service = GoogleSheetsService()
        
        query = arguments.get("query", "")
        
        # Security: Block destructive SQL operations
        if query:
            dangerous_commands = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 'CREATE', 'PRAGMA']
            query_upper = query.strip().upper()
            
            if any(cmd in query_upper for cmd in dangerous_commands):
                return [TextContent(type="text", text=json.dumps({
                    "error": "Only SELECT queries are allowed for data analysis",
                    "details": "Destructive operations (DROP, DELETE, etc.) are not permitted",
                    "tip": "Use SELECT statements to query your synced data safely"
                }))]
        
        try:
            with service._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Add automatic LIMIT if not present for safety
                query_lower = query.strip().lower()
                if 'limit' not in query_lower:
                    # Add a reasonable default limit
                    query = f"{query} LIMIT 10000"
                
                cursor.execute(query)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                
                # Stream results instead of fetchall for large datasets
                result_rows = []
                total_fetched = 0
                max_display_rows = 1000  # Maximum rows to return to client
                
                while True:
                    # Fetch in batches
                    batch = cursor.fetchmany(1000)
                    if not batch:
                        break
                    
                    total_fetched += len(batch)
                    
                    # Only keep rows up to display limit
                    if len(result_rows) < max_display_rows:
                        remaining = max_display_rows - len(result_rows)
                        result_rows.extend(batch[:remaining])
                
                result = {
                    "columns": columns,
                    "rows": result_rows,
                    "total_rows": total_fetched,
                    "limited": total_fetched > max_display_rows,
                    "display_limit": max_display_rows
                }
                
                if total_fetched > max_display_rows:
                    result["note"] = f"Showing first {max_display_rows} of {total_fetched} rows. Add LIMIT to your query to control results."
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "list_synced_sheets":
        # Create fresh service instance for this tool call
        service = GoogleSheetsService()
        
        try:
            with service._get_db_connection() as conn:
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
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_sheets":
        # Create fresh service instance for this tool call
        service = GoogleSheetsService()
        
        question = arguments.get("question", "")
        
        try:
            with service._get_db_connection() as conn:
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
            
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_sheet_preview":
        # Create fresh service instance for this tool call
        service = GoogleSheetsService()
        
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
        # Create fresh service instance for this tool call
        service = GoogleSheetsService()
        
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
                
                with service._get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT spreadsheet_id, spreadsheet_title, sheet_name, table_name 
                        FROM _sheet_metadata 
                        WHERE spreadsheet_id = ?
                    """, (spreadsheet_id,))
                    sheets_to_check = cursor.fetchall()
            else:
                # Check all synced sheets
                with service._get_db_connection() as conn:
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
                    # First check sheet metadata for quick change detection
                    sheet_meta = sheets_service.spreadsheets().get(
                        spreadsheetId=spreadsheet_id,
                        ranges=[f"'{sheet_name}'"],
                        fields="sheets(properties)"
                    ).execute()
                    
                    # Get sheet dimensions for efficient checking
                    sheet_props = sheet_meta['sheets'][0]['properties']
                    grid_props = sheet_props.get('gridProperties', {})
                    current_rows = grid_props.get('rowCount', 0)
                    
                    # For large sheets, use sampling instead of fetching all data
                    if current_rows > 10000:
                        # Sample approach: check first 100, last 100, and some random rows
                        sample_ranges = [
                            f"'{sheet_name}'!A1:Z100",  # First 100 rows
                            f"'{sheet_name}'!A{max(1, current_rows-100)}:Z{current_rows}"  # Last 100 rows
                        ]
                        
                        batch_result = sheets_service.spreadsheets().values().batchGet(
                            spreadsheetId=spreadsheet_id,
                            ranges=sample_ranges
                        ).execute()
                        
                        # Combine samples for hash calculation
                        values = []
                        for range_data in batch_result.get('valueRanges', []):
                            values.extend(range_data.get('values', []))
                    else:
                        # For smaller sheets, get all data
                        range_name = f"'{sheet_name}'!A1:Z{min(current_rows, 5000)}"
                        result = sheets_service.spreadsheets().values().get(
                            spreadsheetId=spreadsheet_id,
                            range=range_name
                        ).execute()
                        values = result.get('values', [])
                    
                    # Check for changes
                    with service._get_db_connection() as temp_conn:
                        temp_cursor = temp_conn.cursor()
                        
                        # Quick check: compare row counts first
                        temp_cursor.execute("""
                            SELECT row_count FROM _sheet_metadata 
                            WHERE spreadsheet_id = ? AND sheet_name = ?
                        """, (spreadsheet_id, sheet_name))
                        
                        stored_row_count = temp_cursor.fetchone()
                        if stored_row_count and stored_row_count[0] != current_rows:
                            change_info = {
                                "has_changes": True,
                                "changes": [f"Row count changed: {stored_row_count[0]} → {current_rows}"]
                            }
                        else:
                            change_info = service._get_sheet_changes(temp_cursor, spreadsheet_id, sheet_name, values)
                    
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
                                
                                with service._get_db_connection() as conn:
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
        # Create fresh service instance for this tool call
        service = GoogleSheetsService()
        
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
            with service._get_db_connection() as conn:
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
                    
                    # Get sheet dimensions first
                    service._record_api_call()
                    sheet_meta = sheets_service.spreadsheets().get(
                        spreadsheetId=spreadsheet_id,
                        ranges=[f"'{sheet_name}'"],
                        fields="sheets(properties)"
                    ).execute()
                    
                    # Get actual dimensions
                    sheet_props = sheet_meta['sheets'][0]['properties']
                    grid_props = sheet_props.get('gridProperties', {})
                    total_rows = grid_props.get('rowCount', 0)
                    total_cols = grid_props.get('columnCount', 0)
                    
                    # Determine column range dynamically
                    last_col = service._number_to_column(min(total_cols, 26))  # Limit to Z for compatibility
                    
                    # Get current sheet data with dynamic range
                    range_name = f"'{sheet_name}'!A1:{last_col}{min(total_rows, 10000)}"
                    service._record_api_call()
                    result = sheets_service.spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range=range_name
                    ).execute()
                    
                    values = result.get('values', [])
                    if not values:
                        continue
                    
                    # Check for changes
                    # Create temporary connection for change detection (this will be fixed in Phase 1b)  
                    with service._get_db_connection() as temp_conn:
                        temp_cursor = temp_conn.cursor()
                        change_info = service._get_sheet_changes(temp_cursor, spreadsheet_id, sheet_name, values)
                    
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
                    
                    with service._get_db_connection() as conn:
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
    """Main entry point with proper cleanup"""
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
    except KeyboardInterrupt:
        print("Server shutting down gracefully...", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        raise
    finally:
        # Clean up any remaining database connections
        # With our new architecture, this is mostly handled by per-tool cleanup
        pass

if __name__ == "__main__":
    asyncio.run(main())