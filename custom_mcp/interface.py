"""
Model Context Protocol (MCP) Interface

This module defines the core interfaces and abstract base classes for the Model Context Protocol.
MCP provides a standardized way to manage context for AI models, enabling modular and extensible
context providers.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ContextType(str, Enum):
    """Enumeration of supported context types."""
    STATISTICAL = "statistical"
    DOCUMENT = "document"
    CODE = "code"
    GENERAL = "general"
    DATABASE_SCHEMA = "database_schema"  # New: Specific type for database schema
    DATABASE_SAMPLE = "database_sample"  # New: Specific type for database samples
    QUERY_HISTORY = "query_history"      # New: Specific type for query history


class ContextPriority(int, Enum):
    """Priority levels for context objects."""
    CRITICAL = 5    # Must be included (e.g., schema for the exact table being queried)
    HIGH = 4        # Very relevant (e.g., sample data for the queried table)
    MEDIUM = 3      # Moderately relevant (e.g., related tables' schema)
    LOW = 2         # Somewhat relevant (e.g., similar past queries)
    BACKGROUND = 1  # Contextual information (e.g., general database statistics)


class DatabaseRelationship(BaseModel):
    """Model for database relationships."""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str = "foreign_key"  # Could be foreign_key, implicit, etc.


class DatabaseEntityReference(BaseModel):
    """Reference to a database entity (table or column)."""
    table_name: str
    column_name: Optional[str] = None
    confidence: float = 1.0  # Confidence that this entity is relevant to the query


class ContextMetadata(BaseModel):
    """Metadata for context objects."""
    context_id: str
    context_type: ContextType
    source: str
    timestamp: float
    relevance_score: Optional[float] = None
    priority: ContextPriority = ContextPriority.MEDIUM  # New: Priority level
    version: str = "1.0"
    tags: List[str] = []
    # New: Database-specific metadata
    database_entities: List[DatabaseEntityReference] = Field(default_factory=list)
    query_tokens: List[str] = Field(default_factory=list)  # Tokens from the query this context is relevant to


class ContextContent(BaseModel):
    """Content of a context object."""
    text: str
    structured_data: Optional[Dict[str, Any]] = None
    # New: Database-specific fields
    schema_info: Optional[Dict[str, Any]] = None  # Database schema information
    sample_data: Optional[Dict[str, Any]] = None  # Sample data from tables
    relationships: List[DatabaseRelationship] = Field(default_factory=list)  # Database relationships


class Context(BaseModel):
    """A complete context object combining metadata and content."""
    metadata: ContextMetadata
    content: ContextContent


class ContextQuery(BaseModel):
    """Query parameters for retrieving context."""
    query: str
    context_type: Optional[ContextType] = None
    max_results: int = 5
    min_relevance: Optional[float] = None
    tags: List[str] = []
    # New: Database-specific query parameters
    tables_of_interest: List[str] = Field(default_factory=list)  # Tables specifically mentioned in the query
    columns_of_interest: List[str] = Field(default_factory=list)  # Columns specifically mentioned in the query
    include_sample_data: bool = True  # Whether to include sample data in the response
    include_query_history: bool = True  # Whether to include query history in the response
    min_priority: Optional[ContextPriority] = None  # Minimum priority level to include


class MCPInterface(ABC):
    """
    Abstract base class defining the Model Context Protocol interface.
    
    This interface defines the standard operations for context management:
    - get: Retrieve context for a given query
    - set: Store new context
    - update: Modify existing context
    - delete: Remove context
    """
    
    @abstractmethod
    async def get(self, query: ContextQuery) -> List[Context]:
        """
        Retrieve context based on the provided query parameters.
        
        Args:
            query: The query parameters for context retrieval
            
        Returns:
            A list of Context objects matching the query
        """
        pass
    
    @abstractmethod
    async def set(self, context: Context) -> str:
        """
        Store a new context object.
        
        Args:
            context: The context object to store
            
        Returns:
            The ID of the stored context
        """
        pass
    
    @abstractmethod
    async def update(self, context_id: str, updates: Dict[str, Any]) -> Context:
        """
        Update an existing context object.
        
        Args:
            context_id: The ID of the context to update
            updates: Dictionary of fields to update
            
        Returns:
            The updated Context object
        """
        pass
    
    @abstractmethod
    async def delete(self, context_id: str) -> bool:
        """
        Delete a context object.
        
        Args:
            context_id: The ID of the context to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        pass
    
    # New: Method for merging contexts
    @abstractmethod
    async def merge_contexts(self, contexts: List[Context], max_tokens: Optional[int] = None) -> Context:
        """
        Merge multiple context objects into a single context.
        
        This is useful for combining related contexts while respecting token limits.
        
        Args:
            contexts: List of contexts to merge
            max_tokens: Maximum number of tokens in the merged context
            
        Returns:
            A merged Context object
        """
        pass


class ContextProviderInterface(MCPInterface):
    """
    Abstract base class for context providers.
    
    Context providers are specialized implementations that handle specific types of context,
    such as statistical data, documents, code, etc.
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Get the name of this context provider.
        
        Returns:
            The provider name as a string
        """
        pass
    
    @property
    @abstractmethod
    def supported_context_types(self) -> List[ContextType]:
        """
        Get the context types supported by this provider.
        
        Returns:
            List of supported ContextType values
        """
        pass
    
    @abstractmethod
    async def can_handle(self, query: ContextQuery) -> bool:
        """
        Determine if this provider can handle the given query.
        
        Args:
            query: The query to check
            
        Returns:
            True if this provider can handle the query, False otherwise
        """
        pass
    
    # New: Method for analyzing query to extract database entities
    @abstractmethod
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze a query to extract relevant information.
        
        Args:
            query: The query to analyze
            
        Returns:
            Dictionary with analysis results, including identified entities
        """
        pass 