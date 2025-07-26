# Model Context Protocol (MCP)

The Model Context Protocol (MCP) is a framework for managing context in LLM applications. It provides a unified interface for retrieving, storing, and manipulating context from various sources, ensuring that the most relevant information is provided to the LLM.

## Overview

MCP enhances the Conversational Data Insights system with the following capabilities:

- **Context Management**: Unified interface for managing context from different sources
- **Context Prioritization**: Automatic ranking of context by relevance
- **Token Management**: Optimization of context within token limits
- **Context Persistence**: Storage of context across conversations
- **Context Versioning**: Tracking changes to context over time
- **SQLPrompt Integration**: Specialized techniques for improving SQL generation

## Directory Structure

```
mcp/
├── __init__.py
├── interface.py        # Core data structures and protocols
├── manager.py          # Context manager implementation
├── persistence.py      # Context persistence system
├── token_management.py # Token limit management
├── relevance.py        # Context relevance scoring
├── versioning.py       # Context version management
├── logging.py          # MCP logging utilities
├── providers/          # Context provider implementations
│   ├── __init__.py
│   ├── base.py         # Base provider class
│   ├── statistical.py  # Statistical context provider
│   ├── document.py     # Documentation context provider
│   └── sql_examples.py # SQL examples provider
└── sqlprompt/          # SQLPrompt components
    ├── __init__.py
    ├── similarity.py        # Similarity search for examples
    ├── templates.py         # Prompt templates for SQL generation
    ├── entity_extraction.py # Database entity extraction
    └── adaptive_selection.py # Adaptive example selection
```

## Key Components

### Interface

The interface layer (`interface.py`) defines the core data structures and protocols:

- `Context`: The fundamental unit of context information
- `ContextMetadata`: Metadata about a context (source, priority, etc.)
- `ContextContent`: The actual content of a context
- `ContextQuery`: Parameters for querying context
- `ContextProviderInterface`: Protocol for context providers

### Manager

The context manager (`manager.py`) coordinates operations between providers and features:

- Routing queries to appropriate providers
- Aggregating results from multiple providers
- Managing token limits
- Handling persistence and versioning

### Providers

Context providers (`providers/`) are the sources of context information:

- `StatisticalContextProvider`: Database statistics
- `DocumentContextProvider`: Documentation and schema information
- `SQLExamplesProvider`: Example SQL queries

### SQLPrompt

SQLPrompt (`sqlprompt/`) is a specialized technique for improving SQL generation:

- `SimilaritySearch`: Finding similar examples
- `SQLPromptTemplate`: Optimized prompt templates
- `EntityExtraction`: Database entity identification
- `AdaptiveSelection`: Example selection based on history

## Advanced Features

### Context Persistence

The persistence system (`persistence.py`) stores context across conversations:

- File-based storage
- User association
- Conversation management
- Context retrieval by ID or query

### Token Management

The token management system (`token_management.py`) ensures that context stays within token limits:

- Token estimation
- Context truncation
- Priority-based selection
- Reserved tokens for system messages

### Context Relevance Scoring

The relevance scoring system (`relevance.py`) ranks context by relevance to the query:

- Keyword matching
- Semantic similarity
- Entity matching
- Recency weighting

### Context Versioning

The versioning system (`versioning.py`) tracks changes to context over time:

- Version creation
- Parent-child relationships
- Version comparison
- History tracking

## Usage

### Basic Usage

```python
from mcp.manager import ContextManager
from mcp.interface import ContextQuery
from mcp.providers.statistical import StatisticalContextProvider
from mcp.providers.sql_examples import SQLExamplesProvider

# Create the context manager
manager = ContextManager(
    token_limit=4000,
    persistence_enabled=True
)

# Register providers
manager.register_provider(StatisticalContextProvider(
    provider_name="statistics",
    cache_dir="./cache"
))
manager.register_provider(SQLExamplesProvider(
    provider_name="sql_examples",
    examples_file="./data/sql_examples.json"
))

# Create a conversation
manager.create_conversation(user_id="user123")

# Get context for a query
contexts = await manager.get_context(
    ContextQuery(
        query="What is the average sales by product category?",
        context_type=None,  # Query all providers
        max_results=10
    )
)

# Use the contexts in your LLM prompt
for context in contexts:
    print(f"Context: {context.content.text}")
```

### SQLPrompt Usage

```python
from mcp.sqlprompt.similarity import SimilaritySearch
from mcp.sqlprompt.templates import SQLPromptTemplate

# Create a similarity search instance
similarity_search = SimilaritySearch()

# Find similar examples
examples = similarity_search.find_similar_examples(
    query="What is the average sales by product category?",
    examples=sql_examples,
    max_results=3
)

# Generate a prompt with examples
template = SQLPromptTemplate()
prompt = template.generate_prompt(
    query="What is the average sales by product category?",
    schema=database_schema,
    examples=examples
)

# Generate SQL using the prompt
sql = await generate_sql_from_question(
    question="What is the average sales by product category?",
    prompt=prompt,
    schema=database_schema
)
```

## Documentation

For more detailed information, see the following documentation:

- [MCP Implementation Guide](../docs/mcp_implementation.md)
- [Custom Context Providers](../docs/custom_context_providers.md)
- [System Architecture](../docs/system_architecture.md)
- [Extending Context Types](../docs/extending_context_types.md)
- [SQL Examples Best Practices](../docs/sql_examples_best_practices.md)

## Testing

The MCP implementation includes comprehensive tests:

- Unit tests: `backend/tests/test_mcp.py`
- SQLPrompt tests: `backend/tests/test_sqlprompt.py`
- Integration tests: `backend/tests/test_mcp_integration.py`
- Benchmarks: `backend/tests/benchmark_mcp.py`
- SQL evaluation: `backend/tests/evaluate_sql_generation.py`

Run the tests using pytest:

```bash
cd backend
pytest tests/test_mcp.py tests/test_sqlprompt.py tests/test_mcp_integration.py
```

## Contributing

When contributing to the MCP module, please follow these guidelines:

1. Follow the existing code style and conventions
2. Add tests for new functionality
3. Update documentation for significant changes
4. Use the logging utilities for appropriate logging
5. Consider performance implications for context operations

## License

This module is part of the Conversational Data Insights system and is subject to the same license as the parent project. 