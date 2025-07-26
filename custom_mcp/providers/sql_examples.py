"""
SQL Examples Provider for MCP

This module implements a specialized context provider for storing and retrieving
high-quality natural language to SQL query pairs for in-context learning.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..interface import (
    Context,
    ContextContent,
    ContextMetadata,
    ContextPriority,
    ContextQuery,
    ContextType,
    DatabaseEntityReference
)
from ..providers.base import BaseContextProvider
from ..sqlprompt.similarity import SimilaritySearch

logger = logging.getLogger(__name__)


class SQLExamplesProvider(BaseContextProvider):
    """
    Specialized context provider for SQL examples.
    
    This provider stores and retrieves high-quality natural language to SQL query
    pairs for in-context learning, implementing the SQLPrompt approach.
    """
    
    def __init__(
        self,
        examples_file: Optional[str] = None,
        cache_dir: Optional[str] = None,
        similarity_model: str = "all-MiniLM-L6-v2"
    ):
        """
        Initialize the SQL examples provider.
        
        Args:
            examples_file: Path to JSON file containing initial examples
            cache_dir: Directory to cache embeddings and examples
            similarity_model: Name of the sentence transformer model to use
        """
        super().__init__("sql_examples_provider", [ContextType.QUERY_HISTORY])
        self.examples_file = examples_file
        self.cache_dir = cache_dir
        self.similarity_search = SimilaritySearch(
            model_name=similarity_model,
            cache_dir=cache_dir
        )
        
        # Load initial examples if provided
        if examples_file and os.path.exists(examples_file):
            self._load_examples_from_file(examples_file)
        elif cache_dir:
            # Try to load from cache
            self.similarity_search.load_from_cache()
            
    def _load_examples_from_file(self, file_path: str) -> None:
        """
        Load examples from a JSON file.
        
        Args:
            file_path: Path to JSON file containing examples
        """
        try:
            with open(file_path, 'r') as f:
                examples = json.load(f)
                
            if isinstance(examples, list):
                self.similarity_search.add_examples(examples)
                logger.info(f"Loaded {len(examples)} examples from {file_path}")
            else:
                logger.error(f"Invalid examples format in {file_path}. Expected a list.")
        except Exception as e:
            logger.error(f"Error loading examples from {file_path}: {e}")
    
    def _can_handle_query_content(self, query: ContextQuery) -> bool:
        """
        Determine if this provider can handle the query content.
        
        Args:
            query: The query to check
            
        Returns:
            True if this provider can handle the query, False otherwise
        """
        # This provider can handle any query that might need SQL examples
        return True
    
    async def get(self, query: ContextQuery) -> List[Context]:
        """
        Retrieve SQL examples relevant to the query.
        
        Args:
            query: The query parameters
            
        Returns:
            List of Context objects with relevant SQL examples
        """
        # Find similar examples
        similar_examples = self.similarity_search.find_similar(
            query.query,
            top_k=query.max_results
        )
        
        # Convert to Context objects
        contexts = []
        for i, example in enumerate(similar_examples):
            # Extract question and SQL
            question = example.get('question', '')
            sql = example.get('sql', '')
            similarity = example.get('similarity', 0.0)
            
            # Create context
            context_id = f"sql_example_{int(time.time())}_{i}"
            
            # Create metadata
            metadata = ContextMetadata(
                context_id=context_id,
                context_type=ContextType.QUERY_HISTORY,
                source="sql_examples_provider",
                timestamp=time.time(),
                relevance_score=similarity,
                priority=self._calculate_priority(similarity),
                tags=["sql_example"],
                query_tokens=question.lower().split()
            )
            
            # Create content
            content = ContextContent(
                text=f"Question: {question}\nSQL: {sql}",
                structured_data={
                    "question": question,
                    "sql": sql,
                    "similarity": similarity
                }
            )
            
            # Create context
            context = Context(metadata=metadata, content=content)
            contexts.append(context)
            
            # Store in context store
            self._context_store[context_id] = context
        
        return contexts
    
    def _calculate_priority(self, similarity: float) -> ContextPriority:
        """
        Calculate priority based on similarity score.
        
        Args:
            similarity: Similarity score (0.0 to 1.0)
            
        Returns:
            ContextPriority value
        """
        if similarity >= 0.9:
            return ContextPriority.CRITICAL
        elif similarity >= 0.8:
            return ContextPriority.HIGH
        elif similarity >= 0.6:
            return ContextPriority.MEDIUM
        elif similarity >= 0.4:
            return ContextPriority.LOW
        else:
            return ContextPriority.BACKGROUND
    
    async def add_example(self, question: str, sql: str, success: bool = True) -> str:
        """
        Add a new SQL example.
        
        Args:
            question: Natural language question
            sql: SQL query
            success: Whether the SQL query was successful
            
        Returns:
            ID of the created context
        """
        # Only add successful examples
        if not success:
            return ""
            
        # Create example
        example = {
            'question': question,
            'sql': sql
        }
        
        # Add to similarity search
        self.similarity_search.add_examples([example])
        
        # Create context
        context_id = f"sql_example_{int(time.time())}"
        
        # Create metadata
        metadata = ContextMetadata(
            context_id=context_id,
            context_type=ContextType.QUERY_HISTORY,
            source="sql_examples_provider",
            timestamp=time.time(),
            priority=ContextPriority.MEDIUM,
            tags=["sql_example"],
            query_tokens=question.lower().split()
        )
        
        # Create content
        content = ContextContent(
            text=f"Question: {question}\nSQL: {sql}",
            structured_data={
                "question": question,
                "sql": sql
            }
        )
        
        # Create context
        context = Context(metadata=metadata, content=content)
        
        # Store context
        await self.set(context)
        
        return context_id
    
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze a query to extract relevant information.
        
        This is a placeholder implementation that returns an empty dictionary.
        In a real implementation, this would extract entities, intents, etc.
        
        Args:
            query: The query to analyze
            
        Returns:
            Dictionary with analysis results
        """
        # This is a placeholder implementation
        return {} 