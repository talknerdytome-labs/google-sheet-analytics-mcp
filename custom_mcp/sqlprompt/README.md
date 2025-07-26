# SQLPrompt Integration

This directory contains the implementation of SQLPrompt techniques for in-context learning with minimal labeled data for Text-to-SQL conversion.

## Overview

SQLPrompt is a research approach that improves Text-to-SQL conversion by using in-context learning with minimal labeled examples. The key ideas from the research paper "SQLPrompt: In-Context Text-to-SQL with Minimal Labeled Data" have been integrated into the Model Context Protocol (MCP) architecture.

## Components

### Similarity Search (`similarity.py`)

The `SimilaritySearch` class provides semantic similarity search for SQL examples. It uses sentence transformers to find the most relevant SQL examples for a given natural language query. Key features:

- Semantic similarity using sentence embeddings
- Fallback to keyword matching when sentence transformers are not available
- Caching of embeddings and examples for performance
- Configurable similarity thresholds and example selection

### Prompt Templates (`templates.py`)

The `PromptTemplate` class provides optimized prompt templates for Text-to-SQL conversion. These templates are designed to maximize the effectiveness of in-context learning with minimal labeled examples. Key features:

- Schema formatting for optimal LLM consumption
- Example formatting for in-context learning
- Specialized templates for different tasks (SQL generation, explanation, clarification)
- Support for multiple examples with similarity-based ranking

## SQL Examples Provider

The `SQLExamplesProvider` class in `../providers/sql_examples.py` integrates SQLPrompt with the MCP architecture. It stores and retrieves high-quality natural language to SQL query pairs for in-context learning. Key features:

- Loading examples from JSON files
- Caching examples for performance
- Relevance-based example selection
- Priority calculation based on similarity scores
- Feedback loop for improving example quality

## Usage

### Adding SQL Examples

SQL examples can be added in several ways:

1. **Initial Examples File**: Provide a JSON file with examples when initializing the provider:

```python
provider = SQLExamplesProvider(examples_file="path/to/examples.json")
```

2. **API Endpoint**: Use the `/sql-examples` endpoint to add examples:

```http
POST /sql-examples
Content-Type: application/json

{
  "question": "Show me all customers from Germany",
  "sql": "SELECT * FROM customers WHERE country = 'Germany';"
}
```

3. **Bulk Upload**: Use the `/sql-examples/upload` endpoint to upload a JSON file with multiple examples.

4. **Automatic Learning**: Successful queries are automatically added to the examples store.

### Example JSON Format

```json
[
  {
    "question": "Show me all customers from Germany",
    "sql": "SELECT * FROM customers WHERE country = 'Germany';"
  },
  {
    "question": "What are the top 5 products by sales?",
    "sql": "SELECT p.product_name, SUM(od.quantity * od.unit_price) as total_sales FROM order_details od JOIN products p ON od.product_id = p.product_id GROUP BY p.product_name ORDER BY total_sales DESC LIMIT 5;"
  }
]
```

## References

- "SQLPrompt: In-Context Text-to-SQL with Minimal Labeled Data" research paper 