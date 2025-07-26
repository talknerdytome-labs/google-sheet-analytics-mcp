"""
Context Relevance Scoring Module for MCP

This module provides functionality to score the relevance of context objects
to a given query, incorporating SQLPrompt techniques for improved relevance
assessment, particularly for SQL-related contexts.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Union, Any
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .interface import Context, ContextType

logger = logging.getLogger(__name__)


class RelevanceScorer:
    """
    Scores the relevance of context objects to a given query.
    
    This class provides methods to calculate relevance scores for context objects,
    using various techniques including semantic similarity, keyword matching,
    and SQLPrompt-inspired relevance assessment for SQL-related contexts.
    """
    
    def __init__(
        self,
        use_semantic_similarity: bool = True,
        use_keyword_matching: bool = True,
        use_sqlprompt_techniques: bool = True
    ):
        """
        Initialize the relevance scorer.
        
        Args:
            use_semantic_similarity: Whether to use semantic similarity for scoring
            use_keyword_matching: Whether to use keyword matching for scoring
            use_sqlprompt_techniques: Whether to use SQLPrompt techniques for scoring
        """
        self.use_semantic_similarity = use_semantic_similarity
        self.use_keyword_matching = use_keyword_matching
        self.use_sqlprompt_techniques = use_sqlprompt_techniques
        
        # Initialize TF-IDF vectorizer for keyword matching
        self.tfidf_vectorizer = TfidfVectorizer(
            stop_words='english',
            ngram_range=(1, 2),
            max_features=10000
        )
        
        # Cache for TF-IDF matrices
        self.tfidf_cache: Dict[str, Any] = {}
        
        logger.info("Relevance Scorer initialized")
    
    def score_contexts(self, query: str, contexts: List[Context]) -> List[Context]:
        """
        Score the relevance of contexts to a query.
        
        Args:
            query: The query to score contexts against
            contexts: List of Context objects to score
            
        Returns:
            List of Context objects with updated relevance scores
        """
        if not contexts:
            return []
            
        # Create a copy of the contexts to avoid modifying the originals
        import copy
        scored_contexts = copy.deepcopy(contexts)
        
        # Calculate scores using different methods
        keyword_scores = self._calculate_keyword_scores(query, scored_contexts) if self.use_keyword_matching else None
        semantic_scores = self._calculate_semantic_scores(query, scored_contexts) if self.use_semantic_similarity else None
        sqlprompt_scores = self._calculate_sqlprompt_scores(query, scored_contexts) if self.use_sqlprompt_techniques else None
        
        # Combine scores
        for i, context in enumerate(scored_contexts):
            scores = []
            
            # Add keyword score if available
            if keyword_scores:
                scores.append(keyword_scores[i])
                
            # Add semantic score if available
            if semantic_scores:
                scores.append(semantic_scores[i])
                
            # Add SQLPrompt score if available and applicable
            if sqlprompt_scores and context.metadata.context_type in [
                ContextType.SQL_EXAMPLE,
                ContextType.DATABASE_SCHEMA,
                ContextType.DATABASE_SAMPLE
            ]:
                scores.append(sqlprompt_scores[i])
                
            # Calculate final score (weighted average)
            if scores:
                # For SQL-related contexts, give more weight to SQLPrompt scores
                if context.metadata.context_type in [
                    ContextType.SQL_EXAMPLE,
                    ContextType.DATABASE_SCHEMA,
                    ContextType.DATABASE_SAMPLE
                ] and sqlprompt_scores:
                    weights = [0.2, 0.3, 0.5]  # 20% keyword, 30% semantic, 50% SQLPrompt
                else:
                    weights = [0.5, 0.5]  # 50% keyword, 50% semantic
                    
                # Ensure weights match the number of scores
                weights = weights[:len(scores)]
                weights = [w / sum(weights) for w in weights]  # Normalize weights
                
                # Calculate weighted average
                context.metadata.relevance_score = sum(s * w for s, w in zip(scores, weights))
            else:
                context.metadata.relevance_score = 0.0
                
        return scored_contexts
    
    def _calculate_keyword_scores(self, query: str, contexts: List[Context]) -> List[float]:
        """
        Calculate relevance scores based on keyword matching using TF-IDF.
        
        Args:
            query: The query to score contexts against
            contexts: List of Context objects to score
            
        Returns:
            List of relevance scores
        """
        # Extract text from contexts
        context_texts = [context.content.text for context in contexts]
        
        # Combine query and context texts for TF-IDF
        all_texts = [query] + context_texts
        
        # Calculate TF-IDF matrix
        try:
            tfidf_matrix = self.tfidf_vectorizer.fit_transform(all_texts)
            
            # Calculate cosine similarity between query and contexts
            query_vector = tfidf_matrix[0:1]
            context_vectors = tfidf_matrix[1:]
            
            similarities = cosine_similarity(query_vector, context_vectors)[0]
            
            return similarities.tolist()
        except Exception as e:
            logger.error(f"Error calculating keyword scores: {e}")
            return [0.0] * len(contexts)
    
    def _calculate_semantic_scores(self, query: str, contexts: List[Context]) -> List[float]:
        """
        Calculate relevance scores based on semantic similarity.
        
        This is a simplified implementation. In a production system,
        you would use a pre-trained embedding model for better results.
        
        Args:
            query: The query to score contexts against
            contexts: List of Context objects to score
            
        Returns:
            List of relevance scores
        """
        # For now, use TF-IDF as a proxy for semantic similarity
        # In a real implementation, you would use a pre-trained embedding model
        return self._calculate_keyword_scores(query, contexts)
    
    def _calculate_sqlprompt_scores(self, query: str, contexts: List[Context]) -> List[float]:
        """
        Calculate relevance scores using SQLPrompt techniques.
        
        This method incorporates SQLPrompt techniques for scoring SQL-related contexts,
        including schema matching, example similarity, and query pattern matching.
        
        Args:
            query: The query to score contexts against
            contexts: List of Context objects to score
            
        Returns:
            List of relevance scores
        """
        scores = []
        
        # Extract potential SQL entities from the query
        query_entities = self._extract_sql_entities(query)
        
        for context in contexts:
            score = 0.0
            
            # Score based on context type
            if context.metadata.context_type == ContextType.SQL_EXAMPLE:
                # For SQL examples, score based on query similarity and entity overlap
                score = self._score_sql_example(query, query_entities, context)
            elif context.metadata.context_type == ContextType.DATABASE_SCHEMA:
                # For schema contexts, score based on entity overlap
                score = self._score_schema_context(query_entities, context)
            elif context.metadata.context_type == ContextType.DATABASE_SAMPLE:
                # For sample data contexts, score based on entity overlap
                score = self._score_sample_context(query_entities, context)
            else:
                # For other contexts, use a generic scoring method
                score = 0.0
                
            scores.append(score)
            
        return scores
    
    def _extract_sql_entities(self, query: str) -> Dict[str, List[str]]:
        """
        Extract potential SQL entities from a query.
        
        Args:
            query: The query to extract entities from
            
        Returns:
            Dictionary of extracted entities
        """
        entities = {
            "tables": [],
            "columns": [],
            "aggregations": [],
            "conditions": [],
            "joins": False,
            "groupby": False,
            "orderby": False,
            "limit": False
        }
        
        # Extract potential table names (capitalized words or words followed by "table")
        table_pattern = r'\b([A-Z][a-z]+|[a-z]+(?=\s+table))\b'
        entities["tables"] = list(set(re.findall(table_pattern, query)))
        
        # Extract potential column names (words near "column", "field", or "attribute")
        column_pattern = r'\b([a-z_]+)(?:\s+(?:column|field|attribute))\b|\b(?:column|field|attribute)\s+([a-z_]+)\b'
        column_matches = re.findall(column_pattern, query)
        entities["columns"] = list(set(m[0] or m[1] for m in column_matches if m[0] or m[1]))
        
        # Check for aggregation functions
        agg_pattern = r'\b(average|avg|sum|count|min|max|mean)\b'
        entities["aggregations"] = list(set(re.findall(agg_pattern, query.lower())))
        
        # Check for conditions
        condition_pattern = r'\b(where|if|when|equals|equal to|greater than|less than|between)\b'
        entities["conditions"] = list(set(re.findall(condition_pattern, query.lower())))
        
        # Check for joins
        entities["joins"] = bool(re.search(r'\b(join|combine|merge|relate)\b', query.lower()))
        
        # Check for group by
        entities["groupby"] = bool(re.search(r'\b(group by|grouped by|group|categorize)\b', query.lower()))
        
        # Check for order by
        entities["orderby"] = bool(re.search(r'\b(order by|sort|sorted by|arrange)\b', query.lower()))
        
        # Check for limit
        entities["limit"] = bool(re.search(r'\b(limit|top|first|last)\b', query.lower()))
        
        return entities
    
    def _score_sql_example(self, query: str, query_entities: Dict[str, List[str]], context: Context) -> float:
        """
        Score an SQL example context based on similarity to the query.
        
        Args:
            query: The query to score against
            query_entities: Extracted entities from the query
            context: The SQL example context
            
        Returns:
            Relevance score
        """
        score = 0.0
        
        # Get the example question and SQL
        example_question = ""
        example_sql = ""
        
        if context.content.structured_data and isinstance(context.content.structured_data, dict):
            example_question = context.content.structured_data.get("question", "")
            example_sql = context.content.structured_data.get("sql", "")
        else:
            # Try to extract from text content
            lines = context.content.text.split("\n")
            for i, line in enumerate(lines):
                if "question:" in line.lower():
                    example_question = line.split(":", 1)[1].strip()
                elif "sql:" in line.lower() and i < len(lines) - 1:
                    example_sql = lines[i+1].strip()
        
        # Calculate query similarity
        if example_question:
            # Use TF-IDF similarity between query and example question
            try:
                tfidf_matrix = self.tfidf_vectorizer.fit_transform([query, example_question])
                similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
                score += similarity * 0.5  # 50% weight for question similarity
            except Exception as e:
                logger.error(f"Error calculating query similarity: {e}")
        
        # Calculate entity overlap
        if example_sql:
            # Extract entities from example SQL
            example_entities = self._extract_sql_entities_from_sql(example_sql)
            
            # Calculate entity overlap score
            entity_score = self._calculate_entity_overlap(query_entities, example_entities)
            score += entity_score * 0.5  # 50% weight for entity overlap
        
        return score
    
    def _score_schema_context(self, query_entities: Dict[str, List[str]], context: Context) -> float:
        """
        Score a schema context based on entity overlap.
        
        Args:
            query_entities: Extracted entities from the query
            context: The schema context
            
        Returns:
            Relevance score
        """
        score = 0.0
        
        # Extract database entities from context
        db_tables = []
        db_columns = []
        
        for entity in context.metadata.database_entities:
            if entity.table_name and entity.table_name not in db_tables:
                db_tables.append(entity.table_name)
                
            if entity.column_name and entity.column_name not in db_columns:
                db_columns.append(entity.column_name)
        
        # Calculate table overlap
        if query_entities["tables"] and db_tables:
            table_overlap = sum(1 for t in query_entities["tables"] if any(db_t.lower() == t.lower() for db_t in db_tables))
            table_score = table_overlap / len(query_entities["tables"]) if query_entities["tables"] else 0.0
            score += table_score * 0.6  # 60% weight for table overlap
        
        # Calculate column overlap
        if query_entities["columns"] and db_columns:
            column_overlap = sum(1 for c in query_entities["columns"] if any(db_c.lower() == c.lower() for db_c in db_columns))
            column_score = column_overlap / len(query_entities["columns"]) if query_entities["columns"] else 0.0
            score += column_score * 0.4  # 40% weight for column overlap
        
        return score
    
    def _score_sample_context(self, query_entities: Dict[str, List[str]], context: Context) -> float:
        """
        Score a sample data context based on entity overlap.
        
        Args:
            query_entities: Extracted entities from the query
            context: The sample data context
            
        Returns:
            Relevance score
        """
        # Similar to schema scoring but with different weights
        score = 0.0
        
        # Extract database entities from context
        db_tables = []
        db_columns = []
        
        for entity in context.metadata.database_entities:
            if entity.table_name and entity.table_name not in db_tables:
                db_tables.append(entity.table_name)
                
            if entity.column_name and entity.column_name not in db_columns:
                db_columns.append(entity.column_name)
        
        # Calculate table overlap
        if query_entities["tables"] and db_tables:
            table_overlap = sum(1 for t in query_entities["tables"] if any(db_t.lower() == t.lower() for db_t in db_tables))
            table_score = table_overlap / len(query_entities["tables"]) if query_entities["tables"] else 0.0
            score += table_score * 0.7  # 70% weight for table overlap
        
        # Calculate column overlap
        if query_entities["columns"] and db_columns:
            column_overlap = sum(1 for c in query_entities["columns"] if any(db_c.lower() == c.lower() for db_c in db_columns))
            column_score = column_overlap / len(query_entities["columns"]) if query_entities["columns"] else 0.0
            score += column_score * 0.3  # 30% weight for column overlap
        
        return score
    
    def _extract_sql_entities_from_sql(self, sql: str) -> Dict[str, Any]:
        """
        Extract SQL entities from an SQL query.
        
        Args:
            sql: The SQL query to extract entities from
            
        Returns:
            Dictionary of extracted entities
        """
        entities = {
            "tables": [],
            "columns": [],
            "aggregations": [],
            "conditions": [],
            "joins": False,
            "groupby": False,
            "orderby": False,
            "limit": False
        }
        
        # Extract tables (FROM and JOIN clauses)
        from_pattern = r'FROM\s+([a-zA-Z0-9_]+)'
        join_pattern = r'JOIN\s+([a-zA-Z0-9_]+)'
        
        from_tables = re.findall(from_pattern, sql, re.IGNORECASE)
        join_tables = re.findall(join_pattern, sql, re.IGNORECASE)
        
        entities["tables"] = list(set(from_tables + join_tables))
        
        # Extract columns (SELECT, WHERE, GROUP BY, ORDER BY clauses)
        select_pattern = r'SELECT\s+(.*?)\s+FROM'
        where_pattern = r'WHERE\s+(.*?)(?:GROUP BY|ORDER BY|LIMIT|$)'
        groupby_pattern = r'GROUP BY\s+(.*?)(?:ORDER BY|LIMIT|$)'
        orderby_pattern = r'ORDER BY\s+(.*?)(?:LIMIT|$)'
        
        # Extract columns from SELECT clause
        select_match = re.search(select_pattern, sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_columns = select_match.group(1).split(',')
            for col in select_columns:
                # Remove aggregation functions and aliases
                col = re.sub(r'(AVG|SUM|COUNT|MIN|MAX)\s*\(([^)]+)\)', r'\2', col, flags=re.IGNORECASE)
                col = re.sub(r'AS\s+[a-zA-Z0-9_]+', '', col, flags=re.IGNORECASE)
                col = col.strip()
                
                # Remove table qualifiers
                if '.' in col:
                    col = col.split('.')[1]
                    
                if col and col != '*':
                    entities["columns"].append(col)
        
        # Check for aggregation functions
        agg_pattern = r'(AVG|SUM|COUNT|MIN|MAX)\s*\('
        entities["aggregations"] = list(set(re.findall(agg_pattern, sql, re.IGNORECASE)))
        
        # Check for joins
        entities["joins"] = bool(re.search(r'\bJOIN\b', sql, re.IGNORECASE))
        
        # Check for group by
        entities["groupby"] = bool(re.search(r'\bGROUP BY\b', sql, re.IGNORECASE))
        
        # Check for order by
        entities["orderby"] = bool(re.search(r'\bORDER BY\b', sql, re.IGNORECASE))
        
        # Check for limit
        entities["limit"] = bool(re.search(r'\bLIMIT\b', sql, re.IGNORECASE))
        
        return entities
    
    def _calculate_entity_overlap(self, query_entities: Dict[str, Any], example_entities: Dict[str, Any]) -> float:
        """
        Calculate the overlap between query entities and example entities.
        
        Args:
            query_entities: Entities extracted from the query
            example_entities: Entities extracted from the example
            
        Returns:
            Overlap score
        """
        score = 0.0
        total_weight = 0.0
        
        # Table overlap
        if query_entities["tables"] and example_entities["tables"]:
            weight = 0.3
            total_weight += weight
            
            overlap = sum(1 for t in query_entities["tables"] if any(et.lower() == t.lower() for et in example_entities["tables"]))
            if query_entities["tables"]:
                score += (overlap / len(query_entities["tables"])) * weight
        
        # Aggregation overlap
        if query_entities["aggregations"] and example_entities["aggregations"]:
            weight = 0.2
            total_weight += weight
            
            overlap = sum(1 for a in query_entities["aggregations"] if any(ea.lower() == a.lower() for ea in example_entities["aggregations"]))
            if query_entities["aggregations"]:
                score += (overlap / len(query_entities["aggregations"])) * weight
        
        # Feature overlap (joins, group by, etc.)
        features = ["joins", "groupby", "orderby", "limit"]
        for feature in features:
            if query_entities[feature] and example_entities[feature]:
                weight = 0.1
                total_weight += weight
                score += weight
        
        # Normalize score
        return score / total_weight if total_weight > 0 else 0.0 