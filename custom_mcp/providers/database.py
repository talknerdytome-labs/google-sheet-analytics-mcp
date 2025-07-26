"""
Database Context Provider for MCP

This module implements a specialized context provider for database interactions,
incorporating principles from the Model Context Protocol research.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import sqlalchemy
from sqlalchemy import inspect, MetaData, Table, text
import pandas as pd

from ..interface import Context, ContextQuery, ContextType, ContextContent, ContextMetadata, ContextPriority, DatabaseEntityReference
from ..providers.base import BaseContextProvider

logger = logging.getLogger(__name__)


class DatabaseContextProvider(BaseContextProvider):
    """
    Specialized context provider for database interactions.
    
    This provider extracts and manages context related to database schema,
    sample data, query history, and statistical profiles to enhance
    the model's ability to generate accurate SQL and interpret data.
    """
    
    def __init__(self, engine, max_sample_rows: int = 5, cache_ttl: int = 3600):
        """
        Initialize the database context provider.
        
        Args:
            engine: SQLAlchemy engine for database connection
            max_sample_rows: Maximum number of sample rows to include in context
            cache_ttl: Time-to-live for cached schema information (seconds)
        """
        super().__init__("database_provider", [ContextType.STATISTICAL])
        self.engine = engine
        self.max_sample_rows = max_sample_rows
        self.cache_ttl = cache_ttl
        self.schema_cache = {}
        self.schema_cache_timestamp = 0
        self.query_history = []
        
    def _can_handle_query_content(self, query: ContextQuery) -> bool:
        """
        Determine if this provider can handle the query content.
        
        Checks if the query appears to be related to database or data analysis.
        
        Args:
            query: The query to check
            
        Returns:
            True if this provider can handle the query, False otherwise
        """
        # Check for database-related keywords in the query
        db_keywords = [
            "database", "table", "column", "sql", "query", "select", 
            "data", "schema", "record", "field", "row", "join",
            "average", "sum", "count", "group by", "order by",
            "where", "from", "insert", "update", "delete"
        ]
        
        query_lower = query.query.lower()
        return any(keyword in query_lower for keyword in db_keywords)
    
    async def get(self, query: ContextQuery) -> List[Context]:
        """
        Retrieve database context based on the query.
        
        Provides schema information, sample data, and relevant statistics
        tailored to the specific query.
        
        Args:
            query: The query parameters
            
        Returns:
            List of Context objects with database information
        """
        # Refresh schema cache if needed
        await self._ensure_fresh_schema_cache()
        
        # Analyze the query to determine relevant tables and columns
        relevant_tables = self._identify_relevant_tables(query.query)
        
        contexts = []
        
        # Generate schema context
        schema_context = await self._generate_schema_context(relevant_tables)
        if schema_context:
            contexts.append(schema_context)
        
        # Generate sample data context
        for table_name in relevant_tables:
            sample_context = await self._generate_sample_data_context(table_name)
            if sample_context:
                contexts.append(sample_context)
        
        # Generate query history context if available
        history_context = await self._generate_query_history_context(query.query)
        if history_context:
            contexts.append(history_context)
        
        return contexts
    
    async def _ensure_fresh_schema_cache(self) -> None:
        """Refresh the schema cache if it has expired."""
        current_time = time.time()
        if current_time - self.schema_cache_timestamp > self.cache_ttl:
            await self._refresh_schema_cache()
    
    async def _refresh_schema_cache(self) -> None:
        """Refresh the cached schema information."""
        try:
            metadata = MetaData()
            metadata.reflect(bind=self.engine)
            
            self.schema_cache = {}
            for table_name, table in metadata.tables.items():
                columns = []
                for column in table.columns:
                    columns.append({
                        "name": column.name,
                        "type": str(column.type),
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "foreign_keys": [fk.target_fullname for fk in column.foreign_keys]
                    })
                
                self.schema_cache[table_name] = {
                    "columns": columns,
                    "primary_key": [c.name for c in table.primary_key.columns],
                    "indexes": [idx.name for idx in table.indexes]
                }
            
            self.schema_cache_timestamp = time.time()
            logger.info(f"Refreshed schema cache with {len(self.schema_cache)} tables")
        except Exception as e:
            logger.error(f"Error refreshing schema cache: {e}")
    
    def _identify_relevant_tables(self, query_text: str) -> List[str]:
        """
        Identify tables that are relevant to the given query.
        
        Args:
            query_text: The natural language query
            
        Returns:
            List of table names that are likely relevant
        """
        # Simple implementation: check for table names in the query
        relevant_tables = []
        query_lower = query_text.lower()
        
        for table_name in self.schema_cache.keys():
            # Check if table name appears in the query
            if table_name.lower() in query_lower:
                relevant_tables.append(table_name)
                continue
                
            # Check if any column names from this table appear in the query
            columns = self.schema_cache[table_name]["columns"]
            for column in columns:
                if column["name"].lower() in query_lower:
                    relevant_tables.append(table_name)
                    break
        
        # If no tables were identified, return all tables
        if not relevant_tables:
            return list(self.schema_cache.keys())
            
        return relevant_tables
    
    async def _generate_schema_context(self, table_names: List[str]) -> Optional[Context]:
        """
        Generate context with schema information for the specified tables.
        
        Args:
            table_names: List of table names to include
            
        Returns:
            Context object with schema information, or None if no tables found
        """
        if not table_names:
            return None
            
        schema_text = "Database Schema:\n\n"
        structured_data = {"tables": {}}
        
        for table_name in table_names:
            if table_name not in self.schema_cache:
                continue
                
            table_info = self.schema_cache[table_name]
            
            # Add to text representation
            schema_text += f"Table: {table_name}\n"
            schema_text += "Columns:\n"
            
            for column in table_info["columns"]:
                pk_marker = " (PK)" if column["name"] in table_info["primary_key"] else ""
                fk_info = f" -> {column['foreign_keys'][0]}" if column["foreign_keys"] else ""
                nullable = "" if column["nullable"] else " NOT NULL"
                
                schema_text += f"  - {column['name']}: {column['type']}{nullable}{pk_marker}{fk_info}\n"
            
            schema_text += "\n"
            
            # Add to structured data
            structured_data["tables"][table_name] = table_info
        
        return self._create_context(
            text=schema_text,
            context_type=ContextType.STATISTICAL,
            structured_data=structured_data,
            relevance_score=1.0,
            tags=["schema", "database"]
        )
    
    async def _generate_sample_data_context(self, table_name: str) -> Optional[Context]:
        """
        Generate context with sample data from the specified table.
        
        Args:
            table_name: The name of the table
            
        Returns:
            Context object with sample data, or None if table not found
        """
        if table_name not in self.schema_cache:
            return None
            
        try:
            query = f"SELECT * FROM {table_name} LIMIT {self.max_sample_rows}"
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
                
            if not rows:
                return None
                
            # Convert to dataframe for easier handling
            df = pd.DataFrame(rows, columns=result.keys())
            
            # Create text representation
            sample_text = f"Sample data from table '{table_name}':\n\n"
            sample_text += df.to_string(index=False) + "\n\n"
            sample_text += f"(Showing {len(rows)} of many rows)"
            
            # Create structured representation
            structured_data = {
                "table_name": table_name,
                "sample_rows": df.to_dict(orient="records")
            }
            
            return self._create_context(
                text=sample_text,
                context_type=ContextType.STATISTICAL,
                structured_data=structured_data,
                relevance_score=0.9,
                tags=["sample_data", "database", table_name]
            )
        except Exception as e:
            logger.error(f"Error generating sample data for {table_name}: {e}")
            return None
    
    async def _generate_query_history_context(self, query_text: str) -> Optional[Context]:
        """
        Generate context based on query history for similar queries.
        
        Args:
            query_text: The current query
            
        Returns:
            Context object with query history, or None if no relevant history
        """
        if not self.query_history:
            return None
            
        # Find similar queries (simple implementation)
        similar_queries = []
        query_lower = query_text.lower()
        
        for hist_entry in self.query_history:
            # Simple similarity: check for common words
            hist_query = hist_entry["query"].lower()
            common_words = set(query_lower.split()) & set(hist_query.split())
            
            if len(common_words) >= 2:  # At least 2 common words
                similar_queries.append(hist_entry)
        
        if not similar_queries:
            return None
            
        # Sort by timestamp (most recent first)
        similar_queries.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Take the most recent 3
        recent_queries = similar_queries[:3]
        
        # Create text representation
        history_text = "Related query history:\n\n"
        
        for i, entry in enumerate(recent_queries, 1):
            history_text += f"{i}. Query: {entry['query']}\n"
            history_text += f"   SQL: {entry['sql']}\n"
            history_text += f"   Timestamp: {time.ctime(entry['timestamp'])}\n\n"
        
        return self._create_context(
            text=history_text,
            context_type=ContextType.STATISTICAL,
            structured_data={"similar_queries": recent_queries},
            relevance_score=0.8,
            tags=["query_history", "database"]
        )
    
    def record_query(self, natural_query: str, sql_query: str, success: bool) -> None:
        """
        Record a query in the history for future reference.
        
        Args:
            natural_query: The natural language query
            sql_query: The generated SQL query
            success: Whether the query was successful
        """
        self.query_history.append({
            "query": natural_query,
            "sql": sql_query,
            "success": success,
            "timestamp": time.time()
        })
        
        # Keep history to a reasonable size
        if len(self.query_history) > 100:
            self.query_history = self.query_history[-100:]
            
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze a query to extract relevant information.
        
        Args:
            query: The query to analyze
            
        Returns:
            Dictionary with analysis results
        """
        # Simple implementation to extract tables and columns from the query
        tables = self._identify_relevant_tables(query)
        
        result = {
            "tables": tables,
            "columns": []
        }
        
        # Extract columns for each table
        for table_name in tables:
            if table_name in self.schema_cache:
                for column in self.schema_cache[table_name]["columns"]:
                    if column["name"].lower() in query.lower():
                        result["columns"].append({
                            "table": table_name,
                            "column": column["name"]
                        })
        
        return result
        
    async def merge_contexts(self, contexts: List[Context], max_tokens: Optional[int] = None) -> Context:
        """
        Merge multiple contexts into a single context.
        
        Args:
            contexts: List of contexts to merge
            max_tokens: Maximum number of tokens in the merged context
            
        Returns:
            Merged context
        """
        if not contexts:
            return None
            
        if len(contexts) == 1:
            return contexts[0]
            
        # Combine text from all contexts
        merged_text = "Combined Database Context:\n\n"
        
        # Combine structured data
        merged_structured_data = {
            "tables": {},
            "sample_data": {}
        }
        
        # Track all tags
        all_tags = set()
        
        # Highest relevance score
        max_relevance = 0.0
        
        for context in contexts:
            # Add text with separator
            merged_text += context.content.text + "\n\n---\n\n"
            
            # Merge structured data
            if context.content.structured_data:
                if "tables" in context.content.structured_data:
                    merged_structured_data["tables"].update(context.content.structured_data["tables"])
                    
                if "table_name" in context.content.structured_data and "sample_rows" in context.content.structured_data:
                    table_name = context.content.structured_data["table_name"]
                    merged_structured_data["sample_data"][table_name] = context.content.structured_data["sample_rows"]
            
            # Add tags
            all_tags.update(context.metadata.tags)
            
            # Update max relevance
            max_relevance = max(max_relevance, context.metadata.relevance_score or 0.0)
        
        # Create merged context
        return self._create_context(
            text=merged_text,
            context_type=ContextType.STATISTICAL,
            structured_data=merged_structured_data,
            relevance_score=max_relevance,
            tags=list(all_tags)
        ) 