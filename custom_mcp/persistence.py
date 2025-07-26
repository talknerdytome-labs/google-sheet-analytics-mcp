"""
Context Persistence Module for MCP

This module provides functionality to persist context across conversations,
enabling the system to maintain context history and recall relevant information
from previous interactions.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Union
import uuid

from .interface import Context, ContextType

logger = logging.getLogger(__name__)


class ContextPersistence:
    """
    Handles persistence of context across conversations.
    
    This class provides methods to store, retrieve, and manage context
    history, enabling the system to maintain context across multiple
    conversations and sessions.
    """
    
    def __init__(
        self,
        storage_dir: str = "./cache/context_history",
        max_history_per_user: int = 10,
        max_history_age_days: int = 30
    ):
        """
        Initialize the context persistence manager.
        
        Args:
            storage_dir: Directory to store context history
            max_history_per_user: Maximum number of conversation histories to keep per user
            max_history_age_days: Maximum age of conversation histories in days
        """
        self.storage_dir = Path(storage_dir)
        self.max_history_per_user = max_history_per_user
        self.max_history_age_days = max_history_age_days
        
        # Create storage directory if it doesn't exist
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Cache of conversation contexts by conversation ID
        self.context_cache: Dict[str, List[Context]] = {}
        
    def get_conversation_contexts(self, conversation_id: str) -> List[Context]:
        """
        Get all contexts for a specific conversation.
        
        Args:
            conversation_id: ID of the conversation
            
        Returns:
            List of Context objects for the conversation
        """
        # Check cache first
        if conversation_id in self.context_cache:
            return self.context_cache[conversation_id]
            
        # Try to load from disk
        conversation_file = self._get_conversation_file(conversation_id)
        if conversation_file.exists():
            try:
                with open(conversation_file, "r") as f:
                    context_dicts = json.load(f)
                    
                # Convert dictionaries to Context objects
                contexts = [Context.model_validate(ctx) for ctx in context_dicts]
                
                # Update cache
                self.context_cache[conversation_id] = contexts
                
                return contexts
            except Exception as e:
                logger.error(f"Error loading conversation contexts for {conversation_id}: {e}")
                
        # No contexts found
        return []
    
    def add_context_to_conversation(self, conversation_id: str, context: Context) -> bool:
        """
        Add a context to a conversation's history.
        
        Args:
            conversation_id: ID of the conversation
            context: Context to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing contexts
            contexts = self.get_conversation_contexts(conversation_id)
            
            # Add new context
            contexts.append(context)
            
            # Update cache
            self.context_cache[conversation_id] = contexts
            
            # Save to disk
            return self._save_conversation_contexts(conversation_id, contexts)
        except Exception as e:
            logger.error(f"Error adding context to conversation {conversation_id}: {e}")
            return False
    
    def create_conversation(self, user_id: Optional[str] = None) -> str:
        """
        Create a new conversation.
        
        Args:
            user_id: Optional user ID to associate with the conversation
            
        Returns:
            ID of the new conversation
        """
        # Generate conversation ID
        conversation_id = str(uuid.uuid4())
        
        # Create conversation directory if user_id is provided
        if user_id:
            user_dir = self.storage_dir / user_id
            os.makedirs(user_dir, exist_ok=True)
            
            # Clean up old conversations if needed
            self._cleanup_old_conversations(user_id)
        
        # Initialize empty context list
        self.context_cache[conversation_id] = []
        
        # Save empty conversation to disk
        self._save_conversation_contexts(conversation_id, [])
        
        return conversation_id
    
    def get_user_conversations(self, user_id: str) -> List[str]:
        """
        Get all conversation IDs for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of conversation IDs
        """
        user_dir = self.storage_dir / user_id
        if not user_dir.exists():
            return []
            
        # Get all JSON files in the user directory
        conversation_files = list(user_dir.glob("*.json"))
        
        # Extract conversation IDs from filenames
        conversation_ids = [f.stem for f in conversation_files]
        
        return conversation_ids
    
    def _get_conversation_file(self, conversation_id: str) -> Path:
        """
        Get the file path for a conversation.
        
        Args:
            conversation_id: ID of the conversation
            
        Returns:
            Path to the conversation file
        """
        # Check if conversation is associated with a user
        for user_dir in self.storage_dir.iterdir():
            if user_dir.is_dir():
                conversation_file = user_dir / f"{conversation_id}.json"
                if conversation_file.exists():
                    return conversation_file
        
        # If not found in a user directory, use the root directory
        return self.storage_dir / f"{conversation_id}.json"
    
    def _save_conversation_contexts(self, conversation_id: str, contexts: List[Context]) -> bool:
        """
        Save conversation contexts to disk.
        
        Args:
            conversation_id: ID of the conversation
            contexts: List of Context objects to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert Context objects to dictionaries
            context_dicts = [ctx.model_dump() for ctx in contexts]
            
            # Get the file path
            conversation_file = self._get_conversation_file(conversation_id)
            
            # Save to disk
            with open(conversation_file, "w") as f:
                json.dump(context_dicts, f, indent=2)
                
            return True
        except Exception as e:
            logger.error(f"Error saving conversation contexts for {conversation_id}: {e}")
            return False
    
    def _cleanup_old_conversations(self, user_id: str) -> None:
        """
        Clean up old conversations for a user.
        
        Args:
            user_id: User ID
        """
        user_dir = self.storage_dir / user_id
        if not user_dir.exists():
            return
            
        # Get all JSON files in the user directory
        conversation_files = list(user_dir.glob("*.json"))
        
        # Sort by modification time (newest first)
        conversation_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        # Keep only the most recent conversations
        if len(conversation_files) > self.max_history_per_user:
            for f in conversation_files[self.max_history_per_user:]:
                try:
                    os.remove(f)
                    logger.info(f"Removed old conversation file: {f}")
                except Exception as e:
                    logger.error(f"Error removing old conversation file {f}: {e}")
        
        # Remove conversations older than max_history_age_days
        max_age_seconds = self.max_history_age_days * 24 * 60 * 60
        current_time = time.time()
        
        for f in conversation_files[:self.max_history_per_user]:
            if current_time - f.stat().st_mtime > max_age_seconds:
                try:
                    os.remove(f)
                    logger.info(f"Removed expired conversation file: {f}")
                except Exception as e:
                    logger.error(f"Error removing expired conversation file {f}: {e}")
                    
    def get_relevant_contexts(
        self,
        conversation_id: str,
        query: str,
        context_types: Optional[List[ContextType]] = None,
        max_contexts: int = 5
    ) -> List[Context]:
        """
        Get contexts from a conversation that are relevant to a query.
        
        This is a simple implementation that returns the most recent contexts.
        A more sophisticated implementation would use semantic similarity.
        
        Args:
            conversation_id: ID of the conversation
            query: Query to find relevant contexts for
            context_types: Optional list of context types to filter by
            max_contexts: Maximum number of contexts to return
            
        Returns:
            List of relevant Context objects
        """
        # Get all contexts for the conversation
        all_contexts = self.get_conversation_contexts(conversation_id)
        
        # Filter by context type if specified
        if context_types:
            filtered_contexts = [ctx for ctx in all_contexts if ctx.metadata.context_type in context_types]
        else:
            filtered_contexts = all_contexts
            
        # Sort by timestamp (newest first)
        filtered_contexts.sort(key=lambda ctx: ctx.metadata.timestamp, reverse=True)
        
        # Return the most recent contexts
        return filtered_contexts[:max_contexts] 