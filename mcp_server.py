#!/usr/bin/env python3

import asyncio
import sqlite3
import json
from typing import Any, Sequence
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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sheets-mcp-server")

# Database connection
def get_db_connection():
    import os
    db_path = os.path.join(os.path.dirname(__file__), "app_db.sqlite")
    return sqlite3.connect(db_path)

server = Server("sheets-mcp-server")

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available data resources"""
    return [
        Resource(
            uri=AnyUrl("sheets://data/sheet1"),
            name="Bookings Data (Google Sheets)",
            description="Your Google Sheets 'Bookings Data' - 50,300+ transaction records from 1vPhBuILVtGm3kukIhO4wWtK-uoksiUKQGSX1pR9ieLQ",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """Read resource data"""
    if str(uri) == "sheets://data/sheet1":
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get sample data
        cursor.execute("SELECT * FROM sheet1 LIMIT 5")
        rows = cursor.fetchall()
        
        # Get column names
        cursor.execute("PRAGMA table_info(sheet1)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Get row count
        cursor.execute("SELECT COUNT(*) FROM sheet1")
        count = cursor.fetchone()[0]
        
        conn.close()
        
        data = {
            "total_rows": count,
            "columns": columns,
            "sample_data": [dict(zip(columns, row)) for row in rows]
        }
        
        return json.dumps(data, indent=2)
    
    raise ValueError(f"Unknown resource: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="query_database",
            description="Execute SQL queries on the Google Sheets data",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL query to execute"
                    }
                },
                "required": ["query"]
            },
        ),
        Tool(
            name="describe_table",
            description="Get schema information about the data table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to describe",
                        "default": "sheet1"
                    }
                }
            },
        ),
        Tool(
            name="get_connected_sheet_info",
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
    if name == "query_database":
        query = arguments.get("query") if arguments else None
        if not query:
            raise ValueError("Query is required")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query)
            results = cursor.fetchall()
            
            # Get column names
            column_names = [description[0] for description in cursor.description] if cursor.description else []
            
            # Format results
            if results:
                formatted_results = []
                for row in results:
                    formatted_results.append(dict(zip(column_names, row)))
                
                result_text = f"Query executed successfully. Found {len(results)} rows.\n\n"
                result_text += json.dumps(formatted_results, indent=2, default=str)
            else:
                result_text = "Query executed successfully. No rows returned."
                
        except Exception as e:
            result_text = f"Error executing query: {str(e)}"
        finally:
            conn.close()
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "describe_table":
        table_name = arguments.get("table_name", "sheet1") if arguments else "sheet1"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            schema = cursor.fetchall()
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            # Get sample data
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
            sample_data = cursor.fetchall()
            
            result_text = f"Table: {table_name}\n"
            result_text += f"Total rows: {count}\n\n"
            result_text += "Schema:\n"
            for col in schema:
                result_text += f"  - {col[1]} ({col[2]})\n"
            
            if sample_data:
                result_text += "\nSample data:\n"
                column_names = [col[1] for col in schema]
                for row in sample_data:
                    result_text += f"  {dict(zip(column_names, row))}\n"
            
        except Exception as e:
            result_text = f"Error describing table: {str(e)}"
        finally:
            conn.close()
        
        return [TextContent(type="text", text=result_text)]
    
    elif name == "get_connected_sheet_info":
        result_text = "Connected Google Sheet Information\n"
        result_text += "====================================\n\n"
        result_text += "Sheet Name: Bookings Data\n"
        result_text += "Sheet ID: 1vPhBuILVtGm3kukIhO4wWtK-uoksiUKQGSX1pR9ieLQ\n"
        result_text += "Sheet URL: https://docs.google.com/spreadsheets/d/1vPhBuILVtGm3kukIhO4wWtK-uoksiUKQGSX1pR9ieLQ/edit\n"
        result_text += "Active Sheet: Sheet1\n"
        result_text += "Data Range: A:I (9 columns)\n"
        result_text += "Last Sync: Recent (50,300+ records)\n"
        result_text += "Date Range: 2023-01-01 to 2025-07-05\n\n"
        result_text += "Available Data:\n"
        result_text += "- Transaction records (bookings)\n"
        result_text += "- Customer information\n"
        result_text += "- Financial data\n"
        result_text += "- Date/time stamps\n"
        
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
    asyncio.run(main())