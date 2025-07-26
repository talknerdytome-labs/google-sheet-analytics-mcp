"""
Token Management Module for MCP

This module provides functionality to manage token usage and context window limits,
ensuring that the context provided to language models stays within token limits.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Union

from .interface import Context, ContextPriority

logger = logging.getLogger(__name__)

# Default token limits for different model sizes
DEFAULT_TOKEN_LIMITS = {
    "small": 2048,    # Small models like GPT-3
    "medium": 4096,   # Medium models like GPT-3.5
    "large": 8192,    # Large models like early GPT-4
    "xlarge": 16384,  # Extra large models like newer GPT-4
    "xxlarge": 32768, # Very large models like Claude 3 Opus
}


class TokenManager:
    """
    Manages token usage and context window limits.
    
    This class provides methods to estimate token counts, optimize context
    selection, and ensure that the context provided to language models
    stays within token limits.
    """
    
    def __init__(
        self,
        model_size: str = "medium",
        custom_token_limit: Optional[int] = None,
        reserved_tokens: int = 500,
        truncation_strategy: str = "priority_based"
    ):
        """
        Initialize the token manager.
        
        Args:
            model_size: Size of the model ("small", "medium", "large", "xlarge", "xxlarge")
            custom_token_limit: Custom token limit (overrides model_size)
            reserved_tokens: Number of tokens to reserve for the prompt and response
            truncation_strategy: Strategy for truncating context ("priority_based" or "proportional")
        """
        self.token_limit = custom_token_limit or DEFAULT_TOKEN_LIMITS.get(model_size, 4096)
        self.reserved_tokens = reserved_tokens
        self.truncation_strategy = truncation_strategy
        
        # Available tokens for context
        self.available_tokens = self.token_limit - self.reserved_tokens
        
        logger.info(f"Token Manager initialized with limit: {self.token_limit}, " 
                   f"reserved: {self.reserved_tokens}, available: {self.available_tokens}")
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text.
        
        This is a simple approximation based on word count.
        For production use, consider using a tokenizer from the specific LLM library.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        # Simple approximation: 1 token ≈ 4 characters for English text
        return len(text) // 4 + 1
    
    def estimate_context_tokens(self, context: Context) -> int:
        """
        Estimate the number of tokens in a context object.
        
        Args:
            context: Context object to estimate tokens for
            
        Returns:
            Estimated token count
        """
        # Estimate tokens in the text content
        text_tokens = self.estimate_tokens(context.content.text)
        
        # Add tokens for structured data if present
        structured_tokens = 0
        if context.content.structured_data:
            # Convert to string and estimate
            structured_text = str(context.content.structured_data)
            structured_tokens = self.estimate_tokens(structured_text)
        
        return text_tokens + structured_tokens
    
    def optimize_contexts(self, contexts: List[Context]) -> List[Context]:
        """
        Optimize a list of contexts to fit within token limits.
        
        Args:
            contexts: List of Context objects to optimize
            
        Returns:
            Optimized list of Context objects
        """
        # If total tokens are within limits, return all contexts
        total_tokens = sum(self.estimate_context_tokens(ctx) for ctx in contexts)
        if total_tokens <= self.available_tokens:
            return contexts
        
        # Apply truncation strategy
        if self.truncation_strategy == "priority_based":
            return self._priority_based_truncation(contexts)
        elif self.truncation_strategy == "proportional":
            return self._proportional_truncation(contexts)
        else:
            # Default to priority-based
            return self._priority_based_truncation(contexts)
    
    def _priority_based_truncation(self, contexts: List[Context]) -> List[Context]:
        """
        Truncate contexts based on priority.
        
        Keeps contexts with higher priority and drops lower priority ones.
        
        Args:
            contexts: List of Context objects to truncate
            
        Returns:
            Truncated list of Context objects
        """
        # Sort by priority (highest first)
        sorted_contexts = sorted(
            contexts,
            key=lambda c: (
                c.metadata.priority.value,
                c.metadata.relevance_score if c.metadata.relevance_score is not None else 0
            ),
            reverse=True
        )
        
        # Keep adding contexts until we hit the token limit
        result = []
        current_tokens = 0
        
        for ctx in sorted_contexts:
            ctx_tokens = self.estimate_context_tokens(ctx)
            if current_tokens + ctx_tokens <= self.available_tokens:
                result.append(ctx)
                current_tokens += ctx_tokens
            else:
                # Try to truncate the context text if it's too long
                truncated_ctx = self._truncate_context_text(ctx, self.available_tokens - current_tokens)
                if truncated_ctx:
                    result.append(truncated_ctx)
                break
        
        return result
    
    def _proportional_truncation(self, contexts: List[Context]) -> List[Context]:
        """
        Truncate contexts proportionally based on priority.
        
        Allocates token budget proportionally to context priority.
        
        Args:
            contexts: List of Context objects to truncate
            
        Returns:
            Truncated list of Context objects
        """
        # Calculate total priority points
        total_priority = sum(ctx.metadata.priority.value for ctx in contexts)
        
        # Allocate tokens proportionally to priority
        result = []
        remaining_tokens = self.available_tokens
        
        # Sort by priority (highest first)
        sorted_contexts = sorted(
            contexts,
            key=lambda c: (
                c.metadata.priority.value,
                c.metadata.relevance_score if c.metadata.relevance_score is not None else 0
            ),
            reverse=True
        )
        
        for ctx in sorted_contexts:
            # Calculate token budget for this context
            priority_ratio = ctx.metadata.priority.value / total_priority
            token_budget = int(self.available_tokens * priority_ratio)
            
            # Ensure we don't exceed remaining tokens
            token_budget = min(token_budget, remaining_tokens)
            
            # Truncate context if needed
            ctx_tokens = self.estimate_context_tokens(ctx)
            if ctx_tokens <= token_budget:
                # Context fits within budget
                result.append(ctx)
                remaining_tokens -= ctx_tokens
            else:
                # Truncate context to fit budget
                truncated_ctx = self._truncate_context_text(ctx, token_budget)
                if truncated_ctx:
                    result.append(truncated_ctx)
                    remaining_tokens -= self.estimate_context_tokens(truncated_ctx)
        
        return result
    
    def _truncate_context_text(self, context: Context, token_budget: int) -> Optional[Context]:
        """
        Truncate context text to fit within token budget.
        
        Args:
            context: Context to truncate
            token_budget: Token budget for the truncated context
            
        Returns:
            Truncated context or None if truncation is not possible
        """
        if token_budget < 50:  # Minimum sensible budget
            return None
            
        # Create a copy of the context
        import copy
        truncated_context = copy.deepcopy(context)
        
        # Estimate character count from token budget (rough approximation)
        char_budget = token_budget * 4
        
        # Truncate text
        text = truncated_context.content.text
        if len(text) > char_budget:
            # Try to truncate at sentence boundary
            truncated_text = self._truncate_at_sentence(text, char_budget)
            truncated_context.content.text = truncated_text
            
            # Add truncation notice
            truncated_context.content.text += "\n[Content truncated due to token limits]"
        
        return truncated_context
    
    def _truncate_at_sentence(self, text: str, char_limit: int) -> str:
        """
        Truncate text at a sentence boundary.
        
        Args:
            text: Text to truncate
            char_limit: Character limit
            
        Returns:
            Truncated text
        """
        if len(text) <= char_limit:
            return text
            
        # Find the last sentence boundary before the limit
        text_to_limit = text[:char_limit]
        sentence_boundaries = [m.end() for m in re.finditer(r'[.!?]\s+', text_to_limit)]
        
        if sentence_boundaries:
            # Truncate at the last sentence boundary
            return text[:sentence_boundaries[-1]]
        else:
            # No sentence boundary found, truncate at word boundary
            words = text_to_limit.split()
            return ' '.join(words[:-1])  # Exclude the last (potentially incomplete) word 