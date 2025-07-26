"""
SQLPrompt Similarity Search Module

This module provides functions for finding relevant SQL examples
based on semantic similarity to the current query.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import torch
    import sentence_transformers
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning("sentence-transformers package not found. Semantic similarity search will use fallback methods.")
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class SimilaritySearch:
    """
    Implements semantic similarity search for SQL examples.
    
    This class provides methods to find the most relevant SQL examples
    for a given natural language query based on semantic similarity.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_dir: Optional[str] = None):
        """
        Initialize the similarity search engine.
        
        Args:
            model_name: Name of the sentence transformer model to use
            cache_dir: Directory to cache embeddings
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.model = None
        self.example_embeddings = {}
        self.example_data = {}
        
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name)
                logger.info(f"Initialized similarity search with model: {model_name}")
            except Exception as e:
                logger.error(f"Error loading sentence transformer model: {e}")
                self.model = None
        
        # Create cache directory if it doesn't exist
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
    
    def add_examples(self, examples: List[Dict[str, str]]) -> None:
        """
        Add examples to the similarity search index.
        
        Args:
            examples: List of dictionaries with 'question' and 'sql' keys
        """
        if not self.model:
            logger.warning("Sentence transformer model not available. Examples added but semantic search disabled.")
            for i, example in enumerate(examples):
                self.example_data[str(i)] = example
            return
            
        # Extract questions for embedding
        questions = [example['question'] for example in examples]
        
        # Generate embeddings
        embeddings = self.model.encode(questions, convert_to_tensor=True)
        
        # Store embeddings and examples
        for i, (example, embedding) in enumerate(zip(examples, embeddings)):
            example_id = str(i)
            self.example_embeddings[example_id] = embedding
            self.example_data[example_id] = example
        
        logger.info(f"Added {len(examples)} examples to similarity search index")
        
        # Cache embeddings if cache directory is specified
        if self.cache_dir:
            self._save_to_cache()
    
    def find_similar(self, query: str, top_k: int = 3) -> List[Dict[str, Union[str, float]]]:
        """
        Find examples similar to the given query.
        
        Args:
            query: Natural language query
            top_k: Number of similar examples to return
            
        Returns:
            List of dictionaries with 'question', 'sql', and 'similarity' keys
        """
        if not self.model or not self.example_embeddings:
            logger.warning("Semantic search not available. Using fallback method.")
            return self._fallback_search(query, top_k)
            
        # Generate query embedding
        query_embedding = self.model.encode(query, convert_to_tensor=True)
        
        # Calculate similarities
        similarities = {}
        for example_id, example_embedding in self.example_embeddings.items():
            similarity = util.pytorch_cos_sim(query_embedding, example_embedding).item()
            similarities[example_id] = similarity
        
        # Sort by similarity
        sorted_examples = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        
        # Return top_k examples
        results = []
        for example_id, similarity in sorted_examples[:top_k]:
            example = self.example_data[example_id].copy()
            example['similarity'] = similarity
            results.append(example)
            
        return results
    
    def _fallback_search(self, query: str, top_k: int) -> List[Dict[str, Union[str, float]]]:
        """
        Fallback search method when semantic search is not available.
        
        Uses simple keyword matching to find relevant examples.
        
        Args:
            query: Natural language query
            top_k: Number of similar examples to return
            
        Returns:
            List of dictionaries with 'question', 'sql', and 'similarity' keys
        """
        query_words = set(query.lower().split())
        
        # Calculate overlap score for each example
        scores = []
        for example_id, example in self.example_data.items():
            question_words = set(example['question'].lower().split())
            overlap = len(query_words.intersection(question_words))
            scores.append((example_id, overlap / max(len(query_words), len(question_words))))
        
        # Sort by score
        sorted_examples = sorted(scores, key=lambda x: x[1], reverse=True)
        
        # Return top_k examples
        results = []
        for example_id, score in sorted_examples[:top_k]:
            example = self.example_data[example_id].copy()
            example['similarity'] = score
            results.append(example)
            
        return results
    
    def _save_to_cache(self) -> None:
        """Save embeddings and examples to cache."""
        if not self.cache_dir:
            return
            
        cache_path = Path(self.cache_dir)
        
        # Save example data
        with open(cache_path / "example_data.json", "w") as f:
            json.dump(self.example_data, f)
            
        # Save embeddings if using sentence transformers
        if SENTENCE_TRANSFORMERS_AVAILABLE and self.example_embeddings:
            embeddings_dict = {
                k: v.cpu().numpy().tolist() for k, v in self.example_embeddings.items()
            }
            with open(cache_path / "example_embeddings.json", "w") as f:
                json.dump(embeddings_dict, f)
                
        logger.info(f"Saved {len(self.example_data)} examples to cache")
    
    def load_from_cache(self) -> bool:
        """
        Load embeddings and examples from cache.
        
        Returns:
            True if loaded successfully, False otherwise
        """
        if not self.cache_dir:
            return False
            
        cache_path = Path(self.cache_dir)
        
        # Load example data
        try:
            with open(cache_path / "example_data.json", "r") as f:
                self.example_data = json.load(f)
        except FileNotFoundError:
            logger.warning("Example data cache not found")
            return False
            
        # Load embeddings if using sentence transformers
        if SENTENCE_TRANSFORMERS_AVAILABLE and self.model:
            try:
                with open(cache_path / "example_embeddings.json", "r") as f:
                    embeddings_dict = json.load(f)
                    
                for k, v in embeddings_dict.items():
                    self.example_embeddings[k] = sentence_transformers.util.pytorch_cos_sim(
                        torch.tensor([v]), torch.tensor([v])
                    )[0]
            except FileNotFoundError:
                logger.warning("Example embeddings cache not found")
                return False
                
        logger.info(f"Loaded {len(self.example_data)} examples from cache")
        return True 