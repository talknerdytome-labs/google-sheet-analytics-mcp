"""
Model Context Protocol (MCP) Manager

This module implements the context manager component that coordinates between
different context providers and handles context routing, persistence, and retrieval.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Set, Type

from .interface import (
    Context, 
    ContextMetadata,
    ContextQuery,
    ContextPriority,
    ContextProviderInterface,
    ContextType,
    ContextContent,
    DatabaseEntityReference
)
from .persistence import ContextPersistence
from .token_management import TokenManager
from .relevance import RelevanceScorer

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Central manager for the Model Context Protocol.
    
    The ContextManager coordinates between different context providers,
    routes queries to appropriate providers, and handles context persistence.
    """
    
    def __init__(
        self,
        token_limit: int = 4096,
        persistence_enabled: bool = True,
        persistence_storage_dir: str = "./cache/context_history",
        model_size: str = "medium",
        reserved_tokens: int = 500,
        truncation_strategy: str = "priority_based",
        use_sqlprompt_relevance: bool = True
    ):
        """
        Initialize the context manager.
        
        Args:
            token_limit: Default token limit for context generation
            persistence_enabled: Whether to enable context persistence across conversations
            persistence_storage_dir: Directory to store persisted contexts
            model_size: Size of the model ("small", "medium", "large", "xlarge", "xxlarge")
            reserved_tokens: Number of tokens to reserve for the prompt and response
            truncation_strategy: Strategy for truncating context ("priority_based" or "proportional")
            use_sqlprompt_relevance: Whether to use SQLPrompt techniques for relevance scoring
        """
        self.providers: Dict[str, ContextProviderInterface] = {}
        self.context_cache: Dict[str, Context] = {}
        self.provider_by_type: Dict[ContextType, Set[str]] = {
            ct: set() for ct in ContextType
        }
        self.token_limit = token_limit
        self.persistence_enabled = persistence_enabled
        
        # Initialize persistence manager if enabled
        self.persistence = ContextPersistence(storage_dir=persistence_storage_dir) if persistence_enabled else None
        
        # Initialize token manager
        self.token_manager = TokenManager(
            model_size=model_size,
            custom_token_limit=token_limit,
            reserved_tokens=reserved_tokens,
            truncation_strategy=truncation_strategy
        )
        
        # Initialize relevance scorer
        self.relevance_scorer = RelevanceScorer(
            use_semantic_similarity=True,
            use_keyword_matching=True,
            use_sqlprompt_techniques=use_sqlprompt_relevance
        )
        
        # Track active conversation ID
        self.active_conversation_id: Optional[str] = None
        
        logger.info(f"Context Manager initialized with token limit: {token_limit}")
        if persistence_enabled:
            logger.info(f"Context persistence enabled with storage dir: {persistence_storage_dir}")
    
    def register_provider(self, provider: ContextProviderInterface) -> None:
        """
        Register a context provider with the manager.
        
        Args:
            provider: The provider to register
        """
        provider_name = provider.provider_name
        if provider_name in self.providers:
            logger.warning(f"Provider '{provider_name}' already registered, replacing")
            
        self.providers[provider_name] = provider
        
        # Register provider for each supported context type
        for context_type in provider.supported_context_types:
            self.provider_by_type[context_type].add(provider_name)
            
        logger.info(f"Registered provider '{provider_name}' for types: {provider.supported_context_types}")
    
    def create_conversation(self, user_id: Optional[str] = None) -> str:
        """
        Create a new conversation and set it as active.
        
        Args:
            user_id: Optional user ID to associate with the conversation
            
        Returns:
            ID of the new conversation
        """
        if not self.persistence_enabled or not self.persistence:
            self.active_conversation_id = str(uuid.uuid4())
            return self.active_conversation_id
            
        conversation_id = self.persistence.create_conversation(user_id)
        self.active_conversation_id = conversation_id
        return conversation_id
    
    def set_active_conversation(self, conversation_id: str) -> None:
        """
        Set the active conversation ID.
        
        Args:
            conversation_id: ID of the conversation to set as active
        """
        self.active_conversation_id = conversation_id
    
    async def get_context(self, query: ContextQuery) -> List[Context]:
        """
        Get context from registered providers based on the query.
        
        Args:
            query: The query parameters
            
        Returns:
            List of Context objects matching the query
        """
        # Analyze query to extract database entities if present
        query_analysis = await self._analyze_query(query.query)
        
        # Update query with extracted entities if not already specified
        if not query.tables_of_interest and "tables" in query_analysis:
            query.tables_of_interest = query_analysis["tables"]
            
        if not query.columns_of_interest and "columns" in query_analysis:
            query.columns_of_interest = query_analysis["columns"]
        
        # Determine which providers to query
        providers_to_query = []
        
        if query.context_type:
            # If a specific context type is requested, query only providers that support it
            provider_names = self.provider_by_type.get(query.context_type, set())
            providers_to_query = [self.providers[name] for name in provider_names]
        else:
            # Otherwise, query all providers
            providers_to_query = list(self.providers.values())
        
        # Filter providers that can handle this query
        capable_providers = []
        for provider in providers_to_query:
            if await provider.can_handle(query):
                capable_providers.append(provider)
        
        if not capable_providers:
            logger.warning(f"No providers can handle query: {query}")
            return []
        
        # Query all capable providers in parallel
        tasks = [provider.get(query) for provider in capable_providers]
        results = await asyncio.gather(*tasks)
        
        # Flatten results
        all_contexts = []
        for provider_results in results:
            all_contexts.extend(provider_results)
            
        # Cache results for future use
        for context in all_contexts:
            self.context_cache[context.metadata.context_id] = context
        
        # Apply priority and relevance filtering
        filtered_contexts = self._filter_contexts(all_contexts, query)
        
        # Score contexts using relevance scorer
        scored_contexts = self.relevance_scorer.score_contexts(query.query, filtered_contexts)
        
        # Sort by priority first, then by relevance score
        scored_contexts.sort(
            key=lambda c: (
                c.metadata.priority.value,
                c.metadata.relevance_score if c.metadata.relevance_score is not None else 0
            ),
            reverse=True
        )
        
        # Get historical contexts if persistence is enabled and we have an active conversation
        historical_contexts = []
        if self.persistence_enabled and self.persistence and self.active_conversation_id:
            historical_contexts = self.persistence.get_relevant_contexts(
                conversation_id=self.active_conversation_id,
                query=query.query,
                context_types=[query.context_type] if query.context_type else None,
                max_contexts=3  # Limit to avoid context overload
            )
            
            # Score historical contexts
            if historical_contexts:
                scored_historical_contexts = self.relevance_scorer.score_contexts(query.query, historical_contexts)
                
                # Add historical contexts to the results
                scored_contexts.extend(scored_historical_contexts)
                
                # Re-sort with historical contexts included
                scored_contexts.sort(
                    key=lambda c: (
                        c.metadata.priority.value,
                        c.metadata.relevance_score if c.metadata.relevance_score is not None else 0
                    ),
                    reverse=True
                )
        
        # Use token manager to optimize contexts
        optimized_contexts = self.token_manager.optimize_contexts(scored_contexts)
        
        # Store contexts in conversation history
        if self.persistence_enabled and self.persistence and self.active_conversation_id:
            for context in optimized_contexts:
                self.persistence.add_context_to_conversation(
                    conversation_id=self.active_conversation_id,
                    context=context
                )
                    
        return optimized_contexts[:query.max_results]
    
    def _filter_contexts(self, contexts: List[Context], query: ContextQuery) -> List[Context]:
        """
        Filter contexts based on query parameters.
        
        Args:
            contexts: List of contexts to filter
            query: Query parameters
            
        Returns:
            Filtered list of contexts
        """
        filtered = []
        
        for context in contexts:
            # Filter by minimum priority if specified
            if (query.min_priority is not None and 
                context.metadata.priority.value < query.min_priority.value):
                continue
                
            # Filter by minimum relevance if specified
            if (query.min_relevance is not None and 
                (context.metadata.relevance_score is None or 
                 context.metadata.relevance_score < query.min_relevance)):
                continue
                
            # Filter by context type if specified
            if query.context_type and context.metadata.context_type != query.context_type:
                continue
                
            # Filter by tags if specified
            if query.tags and not all(tag in context.metadata.tags for tag in query.tags):
                continue
                
            # Filter database-specific contexts
            if context.metadata.context_type in [
                ContextType.DATABASE_SCHEMA, 
                ContextType.DATABASE_SAMPLE
            ]:
                # Check if the context is relevant to tables of interest
                if query.tables_of_interest:
                    relevant_to_tables = False
                    for entity in context.metadata.database_entities:
                        if entity.table_name in query.tables_of_interest:
                            relevant_to_tables = True
                            break
                            
                    if not relevant_to_tables:
                        # Lower priority but don't exclude completely
                        context.metadata.priority = ContextPriority.LOW
                
                # Skip sample data if not requested
                if context.metadata.context_type == ContextType.DATABASE_SAMPLE and not query.include_sample_data:
                    continue
                    
            # Filter query history if not requested
            if context.metadata.context_type == ContextType.QUERY_HISTORY and not query.include_query_history:
                continue
                
            filtered.append(context)
            
        return filtered
    
    async def _analyze_query(self, query_text: str) -> Dict:
        """
        Analyze a query to extract relevant information.
        
        This method aggregates analysis results from all providers.
        
        Args:
            query_text: The query text to analyze
            
        Returns:
            Dictionary with analysis results
        """
        results = {}
        
        # Query all providers in parallel
        tasks = []
        for provider in self.providers.values():
            tasks.append(provider.analyze_query(query_text))
            
        provider_results = await asyncio.gather(*tasks)
        
        # Merge results
        for provider_result in provider_results:
            results.update(provider_result)
            
        return results
    
    async def create_context(self, context: Context) -> str:
        """
        Create a new context.
        
        Args:
            context: The context to create
            
        Returns:
            The ID of the created context
        """
        # Generate context ID if not provided
        if not context.metadata.context_id:
            context.metadata.context_id = str(uuid.uuid4())
            
        # Set timestamp if not provided
        if not context.metadata.timestamp:
            context.metadata.timestamp = time.time()
            
        # Find a provider that can handle this context type
        provider_name = next(
            iter(self.provider_by_type.get(context.metadata.context_type, [])), 
            None
        )
        
        if not provider_name:
            logger.warning(f"No provider found for context type: {context.metadata.context_type}")
            return ""
            
        provider = self.providers[provider_name]
        
        # Store the context
        context_id = await provider.set(context)
        
        # Cache the context
        self.context_cache[context_id] = context
        
        # Store in conversation history if enabled
        if self.persistence_enabled and self.persistence and self.active_conversation_id:
            self.persistence.add_context_to_conversation(
                conversation_id=self.active_conversation_id,
                context=context
            )
            
        return context_id
    
    async def update_context(self, context_id: str, updates: Dict) -> Context:
        """
        Update an existing context.
        
        Args:
            context_id: The ID of the context to update
            updates: Dictionary of fields to update
            
        Returns:
            The updated Context object
        """
        # Find the context in cache
        if context_id not in self.context_cache:
            logger.warning(f"Context not found in cache: {context_id}")
            return None
            
        context = self.context_cache[context_id]
        
        # Find the provider for this context type
        provider_name = next(
            iter(self.provider_by_type.get(context.metadata.context_type, [])), 
            None
        )
        
        if not provider_name:
            logger.warning(f"No provider found for context type: {context.metadata.context_type}")
            return None
            
        provider = self.providers[provider_name]
        
        # Update the context
        updated_context = await provider.update(context_id, updates)
        
        # Update cache
        self.context_cache[context_id] = updated_context
        
        return updated_context
    
    async def delete_context(self, context_id: str) -> bool:
        """
        Delete a context.
        
        Args:
            context_id: The ID of the context to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        # Find the context in cache
        if context_id not in self.context_cache:
            logger.warning(f"Context not found in cache: {context_id}")
            return False
            
        context = self.context_cache[context_id]
        
        # Find the provider for this context type
        provider_name = next(
            iter(self.provider_by_type.get(context.metadata.context_type, [])), 
            None
        )
        
        if not provider_name:
            logger.warning(f"No provider found for context type: {context.metadata.context_type}")
            return False
            
        provider = self.providers[provider_name]
        
        # Delete the context
        success = await provider.delete(context_id)
        
        # Remove from cache if successful
        if success:
            del self.context_cache[context_id]
            
        return success
    
    async def merge_contexts(self, contexts: List[Context], max_tokens: Optional[int] = None) -> Context:
        """
        Merge multiple context objects into a single context.
        
        Args:
            contexts: List of contexts to merge
            max_tokens: Maximum number of tokens in the merged context
            
        Returns:
            A merged Context object
        """
        if not contexts:
            return None
            
        # Use token manager to optimize contexts if max_tokens is specified
        if max_tokens:
            # Temporarily override token limit
            original_token_limit = self.token_manager.token_limit
            self.token_manager.token_limit = max_tokens
            self.token_manager.available_tokens = max_tokens - self.token_manager.reserved_tokens
            
            # Optimize contexts
            contexts_to_merge = self.token_manager.optimize_contexts(contexts)
            
            # Restore original token limit
            self.token_manager.token_limit = original_token_limit
            self.token_manager.available_tokens = original_token_limit - self.token_manager.reserved_tokens
        else:
            contexts_to_merge = contexts
            
        # Create a new context with merged content
        merged_text = "\n\n".join(ctx.content.text for ctx in contexts_to_merge)
        
        # Use the highest priority and relevance score
        priority = max(ctx.metadata.priority for ctx in contexts_to_merge)
        relevance_score = max(
            (ctx.metadata.relevance_score for ctx in contexts_to_merge if ctx.metadata.relevance_score is not None),
            default=None
        )
        
        # Collect all tags
        tags = set()
        for ctx in contexts_to_merge:
            tags.update(ctx.metadata.tags)
            
        # Collect all database entities
        database_entities = []
        for ctx in contexts_to_merge:
            database_entities.extend(ctx.metadata.database_entities)
            
        # Create merged metadata
        merged_metadata = ContextMetadata(
            context_id=str(uuid.uuid4()),
            context_type=contexts_to_merge[0].metadata.context_type,
            source="context_manager",
            timestamp=time.time(),
            relevance_score=relevance_score,
            priority=priority,
            tags=list(tags),
            database_entities=database_entities,
            query_tokens=[]  # No specific query tokens for merged context
        )
        
        # Create merged content
        merged_content = ContextContent(
            text=merged_text,
            structured_data=None  # No structured data for merged context
        )
        
        # Create merged context
        merged_context = Context(
            metadata=merged_metadata,
            content=merged_content
        )
        
        return merged_context
    
    def _estimate_token_count(self, contexts: List[Context]) -> int:
        """
        Estimate the total token count for a list of contexts.
        
        Args:
            contexts: List of Context objects
            
        Returns:
            Estimated token count
        """
        return sum(self.token_manager.estimate_context_tokens(ctx) for ctx in contexts) 