"""
Feedback Loop Module for SQLPrompt

This module provides functionality to collect and process feedback on SQL examples,
enabling the system to improve example quality over time based on query success.
"""

import logging
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Union, Any
import uuid

logger = logging.getLogger(__name__)


class SQLFeedbackEntry:
    """
    Represents feedback for an SQL example.
    """
    
    def __init__(
        self,
        feedback_id: str,
        example_id: str,
        query: str,
        generated_sql: str,
        was_successful: bool,
        error_message: Optional[str] = None,
        user_rating: Optional[int] = None,
        timestamp: float = None
    ):
        """
        Initialize a feedback entry.
        
        Args:
            feedback_id: Unique identifier for this feedback
            example_id: ID of the SQL example
            query: The original query
            generated_sql: The SQL that was generated
            was_successful: Whether the query was successful
            error_message: Error message if the query failed
            user_rating: Optional user rating (1-5)
            timestamp: When the feedback was recorded
        """
        self.feedback_id = feedback_id
        self.example_id = example_id
        self.query = query
        self.generated_sql = generated_sql
        self.was_successful = was_successful
        self.error_message = error_message
        self.user_rating = user_rating
        self.timestamp = timestamp or time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        return {
            "feedback_id": self.feedback_id,
            "example_id": self.example_id,
            "query": self.query,
            "generated_sql": self.generated_sql,
            "was_successful": self.was_successful,
            "error_message": self.error_message,
            "user_rating": self.user_rating,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SQLFeedbackEntry':
        """
        Create a feedback entry from a dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            SQLFeedbackEntry object
        """
        return cls(
            feedback_id=data["feedback_id"],
            example_id=data["example_id"],
            query=data["query"],
            generated_sql=data["generated_sql"],
            was_successful=data["was_successful"],
            error_message=data.get("error_message"),
            user_rating=data.get("user_rating"),
            timestamp=data.get("timestamp", time.time())
        )


class SQLExampleQuality:
    """
    Represents the quality metrics for an SQL example.
    """
    
    def __init__(
        self,
        example_id: str,
        success_count: int = 0,
        failure_count: int = 0,
        average_rating: float = 0.0,
        rating_count: int = 0,
        last_used: float = None
    ):
        """
        Initialize quality metrics.
        
        Args:
            example_id: ID of the SQL example
            success_count: Number of successful uses
            failure_count: Number of failed uses
            average_rating: Average user rating
            rating_count: Number of ratings
            last_used: Timestamp of last use
        """
        self.example_id = example_id
        self.success_count = success_count
        self.failure_count = failure_count
        self.average_rating = average_rating
        self.rating_count = rating_count
        self.last_used = last_used or time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        return {
            "example_id": self.example_id,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "average_rating": self.average_rating,
            "rating_count": self.rating_count,
            "last_used": self.last_used
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SQLExampleQuality':
        """
        Create quality metrics from a dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            SQLExampleQuality object
        """
        return cls(
            example_id=data["example_id"],
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            average_rating=data.get("average_rating", 0.0),
            rating_count=data.get("rating_count", 0),
            last_used=data.get("last_used", time.time())
        )
    
    def add_feedback(self, feedback: SQLFeedbackEntry) -> None:
        """
        Update metrics based on feedback.
        
        Args:
            feedback: Feedback entry
        """
        # Update success/failure counts
        if feedback.was_successful:
            self.success_count += 1
        else:
            self.failure_count += 1
            
        # Update rating if provided
        if feedback.user_rating is not None:
            new_total = self.average_rating * self.rating_count + feedback.user_rating
            self.rating_count += 1
            self.average_rating = new_total / self.rating_count
            
        # Update last used timestamp
        self.last_used = feedback.timestamp
    
    @property
    def success_rate(self) -> float:
        """
        Calculate success rate.
        
        Returns:
            Success rate (0.0 to 1.0)
        """
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    @property
    def quality_score(self) -> float:
        """
        Calculate overall quality score.
        
        Returns:
            Quality score (0.0 to 1.0)
        """
        # Weight success rate and user ratings
        success_weight = 0.7
        rating_weight = 0.3
        
        # Normalize rating to 0.0-1.0 scale
        normalized_rating = self.average_rating / 5.0 if self.rating_count > 0 else 0.5
        
        # Calculate weighted score
        return (self.success_rate * success_weight) + (normalized_rating * rating_weight)


class FeedbackManager:
    """
    Manages feedback collection and processing for SQL examples.
    
    This class provides methods to record feedback, calculate quality metrics,
    and recommend examples based on their performance.
    """
    
    def __init__(self, storage_dir: str = "./cache/sqlprompt/feedback"):
        """
        Initialize the feedback manager.
        
        Args:
            storage_dir: Directory to store feedback data
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.feedback_dir = self.storage_dir / "entries"
        self.feedback_dir.mkdir(exist_ok=True)
        
        self.quality_dir = self.storage_dir / "quality"
        self.quality_dir.mkdir(exist_ok=True)
        
        # Cache of feedback entries by example ID
        self.feedback_cache: Dict[str, List[SQLFeedbackEntry]] = {}
        
        # Cache of quality metrics by example ID
        self.quality_cache: Dict[str, SQLExampleQuality] = {}
        
        # Load quality metrics
        self._load_quality_metrics()
        
        logger.info(f"Feedback Manager initialized with storage dir: {storage_dir}")
    
    def record_feedback(
        self,
        example_id: str,
        query: str,
        generated_sql: str,
        was_successful: bool,
        error_message: Optional[str] = None,
        user_rating: Optional[int] = None
    ) -> str:
        """
        Record feedback for an SQL example.
        
        Args:
            example_id: ID of the SQL example
            query: The original query
            generated_sql: The SQL that was generated
            was_successful: Whether the query was successful
            error_message: Error message if the query failed
            user_rating: Optional user rating (1-5)
            
        Returns:
            Feedback ID
        """
        # Create feedback entry
        feedback_id = str(uuid.uuid4())
        feedback = SQLFeedbackEntry(
            feedback_id=feedback_id,
            example_id=example_id,
            query=query,
            generated_sql=generated_sql,
            was_successful=was_successful,
            error_message=error_message,
            user_rating=user_rating
        )
        
        # Add to cache
        if example_id not in self.feedback_cache:
            self.feedback_cache[example_id] = []
            
        self.feedback_cache[example_id].append(feedback)
        
        # Save to disk
        self._save_feedback(feedback)
        
        # Update quality metrics
        self.update_quality_metrics(example_id, feedback)
        
        return feedback_id
    
    def update_quality_metrics(self, example_id: str, feedback: Optional[SQLFeedbackEntry] = None) -> SQLExampleQuality:
        """
        Update quality metrics for an example.
        
        Args:
            example_id: ID of the SQL example
            feedback: Optional new feedback entry
            
        Returns:
            Updated quality metrics
        """
        # Get existing metrics or create new ones
        quality = self.quality_cache.get(example_id)
        if not quality:
            quality = SQLExampleQuality(example_id=example_id)
            self.quality_cache[example_id] = quality
            
        # Update with new feedback if provided
        if feedback:
            quality.add_feedback(feedback)
            
        # Save to disk
        self._save_quality_metrics(example_id)
        
        return quality
    
    def get_quality_metrics(self, example_id: str) -> Optional[SQLExampleQuality]:
        """
        Get quality metrics for an example.
        
        Args:
            example_id: ID of the SQL example
            
        Returns:
            Quality metrics or None if not found
        """
        # Check cache first
        if example_id in self.quality_cache:
            return self.quality_cache[example_id]
            
        # Try to load from disk
        quality_file = self.quality_dir / f"{example_id}.json"
        if quality_file.exists():
            try:
                with open(quality_file, "r") as f:
                    quality_data = json.load(f)
                    
                quality = SQLExampleQuality.from_dict(quality_data)
                self.quality_cache[example_id] = quality
                
                return quality
            except Exception as e:
                logger.error(f"Error loading quality metrics for {example_id}: {e}")
                
        return None
    
    def get_feedback_entries(self, example_id: str) -> List[SQLFeedbackEntry]:
        """
        Get all feedback entries for an example.
        
        Args:
            example_id: ID of the SQL example
            
        Returns:
            List of feedback entries
        """
        # Check cache first
        if example_id in self.feedback_cache:
            return self.feedback_cache[example_id]
            
        # Try to load from disk
        feedback_file = self.feedback_dir / f"{example_id}.json"
        if feedback_file.exists():
            try:
                with open(feedback_file, "r") as f:
                    feedback_data = json.load(f)
                    
                entries = [SQLFeedbackEntry.from_dict(entry) for entry in feedback_data]
                self.feedback_cache[example_id] = entries
                
                return entries
            except Exception as e:
                logger.error(f"Error loading feedback entries for {example_id}: {e}")
                
        return []
    
    def get_top_examples(self, n: int = 10) -> List[str]:
        """
        Get the top-performing examples.
        
        Args:
            n: Number of examples to return
            
        Returns:
            List of example IDs sorted by quality score
        """
        # Ensure all quality metrics are loaded
        self._load_quality_metrics()
        
        # Sort by quality score
        sorted_examples = sorted(
            self.quality_cache.values(),
            key=lambda q: q.quality_score,
            reverse=True
        )
        
        # Return top n example IDs
        return [q.example_id for q in sorted_examples[:n]]
    
    def get_examples_needing_improvement(self, threshold: float = 0.5, n: int = 10) -> List[str]:
        """
        Get examples that need improvement.
        
        Args:
            threshold: Quality score threshold
            n: Maximum number of examples to return
            
        Returns:
            List of example IDs with quality scores below threshold
        """
        # Ensure all quality metrics are loaded
        self._load_quality_metrics()
        
        # Filter examples below threshold
        low_quality = [
            q for q in self.quality_cache.values()
            if q.quality_score < threshold and (q.success_count + q.failure_count) >= 3
        ]
        
        # Sort by quality score (lowest first)
        sorted_examples = sorted(
            low_quality,
            key=lambda q: q.quality_score
        )
        
        # Return top n example IDs
        return [q.example_id for q in sorted_examples[:n]]
    
    def _save_feedback(self, feedback: SQLFeedbackEntry) -> None:
        """
        Save feedback entry to disk.
        
        Args:
            feedback: Feedback entry to save
        """
        example_id = feedback.example_id
        feedback_file = self.feedback_dir / f"{example_id}.json"
        
        # Get existing entries
        entries = self.get_feedback_entries(example_id)
        
        # Add new entry
        entries.append(feedback)
        
        # Convert to dictionaries
        entries_data = [entry.to_dict() for entry in entries]
        
        # Save to disk
        try:
            with open(feedback_file, "w") as f:
                json.dump(entries_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving feedback for {example_id}: {e}")
    
    def _save_quality_metrics(self, example_id: str) -> None:
        """
        Save quality metrics to disk.
        
        Args:
            example_id: ID of the SQL example
        """
        quality = self.quality_cache.get(example_id)
        if not quality:
            return
            
        quality_file = self.quality_dir / f"{example_id}.json"
        
        try:
            with open(quality_file, "w") as f:
                json.dump(quality.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving quality metrics for {example_id}: {e}")
    
    def _load_quality_metrics(self) -> None:
        """
        Load all quality metrics from disk.
        """
        try:
            for quality_file in self.quality_dir.glob("*.json"):
                example_id = quality_file.stem
                
                if example_id in self.quality_cache:
                    continue
                    
                try:
                    with open(quality_file, "r") as f:
                        quality_data = json.load(f)
                        
                    quality = SQLExampleQuality.from_dict(quality_data)
                    self.quality_cache[example_id] = quality
                except Exception as e:
                    logger.error(f"Error loading quality metrics for {example_id}: {e}")
        except Exception as e:
            logger.error(f"Error loading quality metrics: {e}")
    
    def get_quality_report(self) -> Dict[str, Any]:
        """
        Generate a quality report for all examples.
        
        Returns:
            Dictionary with quality statistics
        """
        # Ensure all quality metrics are loaded
        self._load_quality_metrics()
        
        if not self.quality_cache:
            return {
                "total_examples": 0,
                "average_quality": 0.0,
                "average_success_rate": 0.0,
                "average_rating": 0.0,
                "top_examples": [],
                "examples_needing_improvement": []
            }
        
        # Calculate statistics
        total_examples = len(self.quality_cache)
        quality_scores = [q.quality_score for q in self.quality_cache.values()]
        success_rates = [q.success_rate for q in self.quality_cache.values()]
        
        # Calculate average rating
        rated_examples = [q for q in self.quality_cache.values() if q.rating_count > 0]
        average_rating = sum(q.average_rating for q in rated_examples) / len(rated_examples) if rated_examples else 0.0
        
        return {
            "total_examples": total_examples,
            "average_quality": sum(quality_scores) / total_examples,
            "average_success_rate": sum(success_rates) / total_examples,
            "average_rating": average_rating,
            "top_examples": self.get_top_examples(5),
            "examples_needing_improvement": self.get_examples_needing_improvement(0.5, 5)
        } 