"""
Model Context Protocol (MCP) Provider Base Class

This module defines the base class for all context providers in the MCP system.
Context providers are responsible for generating, storing, and retrieving specific
types of context (e.g., statistical, document, code).
"""

import abc
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from ..interface import (
    Context,
    ContextContent,
    ContextMetadata,
    ContextProviderInterface,
    ContextQuery,
    ContextType
)

logger = logging.getLogger(__name__)


class BaseContextProvider(ContextProviderInterface):
    """
    Base class for all context providers.
    
    This class implements common functionality for context providers and
    defines the interface that all providers must implement.
    """
    
    def __init__(self, name: str, supported_types: List[ContextType]):
        """
        Initialize the context provider.
        
        Args:
            name: The name of this provider
            supported_types: List of context types supported by this provider
        """
        self._name = name
        self._supported_types = supported_types
        self._context_store: Dict[str, Context] = {}
        logger.info(f"Initialized {name} provider supporting types: {supported_types}")
    
    @property
    def provider_name(self) -> str:
        """Get the name of this context provider."""
        return self._name
    
    @property
    def supported_context_types(self) -> List[ContextType]:
        """Get the context types supported by this provider."""
        return self._supported_types
    
    async def can_handle(self, query: ContextQuery) -> bool:
        """
        Determine if this provider can handle the given query.
        
        The base implementation checks if the query's context type is supported
        by this provider. Subclasses should override this method to provide
        more specific handling logic.
        
        Args:
            query: The query to check
            
        Returns:
            True if this provider can handle the query, False otherwise
        """
        if query.context_type is None:
            # If no specific type is requested, check if we can handle the query content
            return self._can_handle_query_content(query)
        
        return query.context_type in self._supported_types
    
    def _can_handle_query_content(self, query: ContextQuery) -> bool:
        """
        Determine if this provider can handle the content of the query.
        
        Subclasses should override this method to provide specific logic
        for determining if they can handle a query based on its content.
        
        Args:
            query: The query to check
            
        Returns:
            True if this provider can handle the query content, False otherwise
        """
        # Default implementation always returns False
        # Subclasses should override this method
        return False
    
    async def get(self, query: ContextQuery) -> List[Context]:
        """
        Retrieve context based on the provided query parameters.
        
        This base implementation provides a simple in-memory lookup.
        Subclasses should override this method to provide more sophisticated
        retrieval logic.
        
        Args:
            query: The query parameters for context retrieval
            
        Returns:
            A list of Context objects matching the query
        """
        # This is a simple implementation that just returns all contexts
        # Subclasses should override this with more sophisticated retrieval logic
        results = []
        
        for context in self._context_store.values():
            # Filter by context type if specified
            if query.context_type and context.metadata.context_type != query.context_type:
                continue
                
            # Filter by tags if specified
            if query.tags and not all(tag in context.metadata.tags for tag in query.tags):
                continue
                
            # Filter by minimum relevance if specified
            if (query.min_relevance is not None and 
                (context.metadata.relevance_score is None or 
                 context.metadata.relevance_score < query.min_relevance)):
                continue
                
            results.append(context)
        
        # Sort by relevance score (if available)
        results.sort(
            key=lambda c: c.metadata.relevance_score if c.metadata.relevance_score is not None else 0,
            reverse=True
        )
        
        # Limit results
        return results[:query.max_results]
    
    async def set(self, context: Context) -> str:
        """
        Store a new context object.
        
        Args:
            context: The context object to store
            
        Returns:
            The ID of the stored context
        """
        # Generate a context ID if not provided
        if not context.metadata.context_id:
            context.metadata.context_id = str(uuid.uuid4())
            
        # Set timestamp if not provided
        if not context.metadata.timestamp:
            context.metadata.timestamp = time.time()
        
        # Store the context
        self._context_store[context.metadata.context_id] = context
        
        logger.info(f"Stored context with ID: {context.metadata.context_id}")
        return context.metadata.context_id
    
    async def update(self, context_id: str, updates: Dict[str, Any]) -> Context:
        """
        Update an existing context object.
        
        Args:
            context_id: The ID of the context to update
            updates: Dictionary of fields to update
            
        Returns:
            The updated Context object
        """
        if context_id not in self._context_store:
            raise ValueError(f"Context not found: {context_id}")
            
        context = self._context_store[context_id]
        
        # Update metadata fields
        metadata_updates = updates.get("metadata", {})
        for key, value in metadata_updates.items():
            if hasattr(context.metadata, key):
                setattr(context.metadata, key, value)
        
        # Update content fields
        content_updates = updates.get("content", {})
        for key, value in content_updates.items():
            if hasattr(context.content, key):
                setattr(context.content, key, value)
        
        logger.info(f"Updated context with ID: {context_id}")
        return context
    
    async def delete(self, context_id: str) -> bool:
        """
        Delete a context object.
        
        Args:
            context_id: The ID of the context to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        if context_id not in self._context_store:
            logger.warning(f"Context not found for deletion: {context_id}")
            return False
            
        del self._context_store[context_id]
        logger.info(f"Deleted context with ID: {context_id}")
        return True
    
    def _create_context(
        self,
        text: str,
        context_type: ContextType,
        structured_data: Optional[Dict[str, Any]] = None,
        relevance_score: Optional[float] = None,
        tags: Optional[List[str]] = None
    ) -> Context:
        """
        Helper method to create a new Context object.
        
        Args:
            text: The text content of the context
            context_type: The type of context
            structured_data: Optional structured data to include
            relevance_score: Optional relevance score
            tags: Optional list of tags
            
        Returns:
            A new Context object
        """
        if tags is None:
            tags = []
            
        metadata = ContextMetadata(
            context_id=str(uuid.uuid4()),
            context_type=context_type,
            source=self.provider_name,
            timestamp=time.time(),
            relevance_score=relevance_score,
            tags=tags
        )
        
        content = ContextContent(
            text=text,
            structured_data=structured_data
        )
        
        return Context(metadata=metadata, content=content) 