"""
SQLPrompt Templates Module

This module provides optimized prompt templates for Text-to-SQL conversion
based on the SQLPrompt research paper.
"""

from typing import Dict, List, Optional, Union
import re


class PromptTemplate:
    """
    Implements optimized prompt templates for Text-to-SQL conversion.
    
    Based on the SQLPrompt research paper, these templates are designed
    to maximize the effectiveness of in-context learning with minimal
    labeled examples.
    """
    
    @staticmethod
    def format_schema(schema_info: Dict) -> str:
        """
        Format database schema information for inclusion in prompts.
        
        Args:
            schema_info: Dictionary containing database schema information
            
        Returns:
            Formatted schema string
        """
        schema_str = "Database Schema:\n"
        
        for table_name, table_info in schema_info.items():
            schema_str += f"Table: {table_name}\n"
            schema_str += "Columns:\n"
            
            for column in table_info.get("columns", []):
                col_name = column.get("name", "")
                col_type = column.get("type", "")
                pk_str = " (PRIMARY KEY)" if column.get("primary_key", False) else ""
                fk_str = ""
                
                if column.get("foreign_keys"):
                    fk_targets = column.get("foreign_keys", [])
                    if fk_targets:
                        fk_str = f" (FOREIGN KEY to {', '.join(fk_targets)})"
                
                schema_str += f"  - {col_name}: {col_type}{pk_str}{fk_str}\n"
            
            schema_str += "\n"
        
        return schema_str
    
    @staticmethod
    def format_example(example: Dict[str, str]) -> str:
        """
        Format a single example for inclusion in prompts.
        
        Args:
            example: Dictionary with 'question' and 'sql' keys
            
        Returns:
            Formatted example string
        """
        question = example.get("question", "")
        sql = example.get("sql", "")
        
        return f"Question: {question}\nSQL: {sql}\n\n"
    
    @staticmethod
    def format_examples(examples: List[Dict[str, str]]) -> str:
        """
        Format multiple examples for inclusion in prompts.
        
        Args:
            examples: List of dictionaries with 'question' and 'sql' keys
            
        Returns:
            Formatted examples string
        """
        if not examples:
            return ""
            
        examples_str = "Examples:\n\n"
        for example in examples:
            examples_str += PromptTemplate.format_example(example)
            
        return examples_str
    
    @staticmethod
    def text_to_sql_prompt(
        question: str,
        schema_info: Dict,
        examples: Optional[List[Dict[str, str]]] = None,
        max_examples: int = 3
    ) -> str:
        """
        Generate a prompt for Text-to-SQL conversion.
        
        Args:
            question: Natural language question
            schema_info: Database schema information
            examples: Optional list of similar examples
            max_examples: Maximum number of examples to include
            
        Returns:
            Formatted prompt string
        """
        # Format schema
        schema_str = PromptTemplate.format_schema(schema_info)
        
        # Format examples (if provided)
        examples_str = ""
        if examples:
            # Sort examples by similarity if available
            if all("similarity" in ex for ex in examples):
                examples = sorted(examples, key=lambda x: x.get("similarity", 0), reverse=True)
                
            # Limit to max_examples
            examples = examples[:max_examples]
            examples_str = PromptTemplate.format_examples(examples)
        
        # Build the prompt
        prompt = f"""You are a SQL expert. Your task is to convert natural language questions into SQL queries.

{schema_str}

{examples_str}Please write a SQL query to answer the following question:

Question: {question}

SQL:"""
        
        return prompt
    
    @staticmethod
    def sql_explanation_prompt(
        question: str,
        sql: str,
        results: Optional[List[Dict]] = None
    ) -> str:
        """
        Generate a prompt for explaining SQL query results.
        
        Args:
            question: Original natural language question
            sql: Generated SQL query
            results: Optional query results
            
        Returns:
            Formatted prompt string
        """
        results_str = ""
        if results:
            results_str = "Query Results:\n"
            
            # Format results as a table if they exist
            if results:
                # Get column names from first result
                if results and isinstance(results[0], dict):
                    columns = list(results[0].keys())
                    results_str += "| " + " | ".join(columns) + " |\n"
                    results_str += "| " + " | ".join(["---"] * len(columns)) + " |\n"
                    
                    # Add rows
                    for row in results[:5]:  # Limit to first 5 rows
                        results_str += "| " + " | ".join(str(row.get(col, "")) for col in columns) + " |\n"
                        
                    if len(results) > 5:
                        results_str += "... (showing 5 of " + str(len(results)) + " rows)\n"
        
        prompt = f"""You are an expert at explaining database query results. Please explain the following SQL query and its results in plain English.

Original Question: {question}

SQL Query:
{sql}

{results_str}

Please provide a clear, concise explanation of the query results that directly answers the original question:"""
        
        return prompt
    
    @staticmethod
    def clarification_prompt(
        question: str,
        schema_info: Dict
    ) -> str:
        """
        Generate a prompt for asking clarifying questions.
        
        Args:
            question: Original natural language question
            schema_info: Database schema information
            
        Returns:
            Formatted prompt string
        """
        # Format schema
        schema_str = PromptTemplate.format_schema(schema_info)
        
        prompt = f"""You are a helpful assistant that helps users query a database. The user has asked a question that requires clarification before it can be converted to SQL.

{schema_str}

User Question: {question}

What specific clarification is needed to convert this question to SQL? Please phrase your response as a clarifying question to the user:"""
        
        return prompt 