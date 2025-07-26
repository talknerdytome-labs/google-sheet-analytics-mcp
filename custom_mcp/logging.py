"""
Logging module for Model Context Protocol (MCP) operations.

This module provides structured logging for MCP operations with different log levels
and formats. It includes context-aware logging and performance tracking.
"""

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, TypeVar, cast

# Configure the root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create a logger for MCP
mcp_logger = logging.getLogger("mcp")

# Set the default log level
mcp_logger.setLevel(logging.INFO)

# Create a file handler if LOG_TO_FILE is set
if os.environ.get("MCP_LOG_TO_FILE", "false").lower() == "true":
    log_dir = Path(os.environ.get("MCP_LOG_DIR", "./logs"))
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"mcp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    mcp_logger.addHandler(file_handler)

# Create a JSON handler for structured logging if enabled
if os.environ.get("MCP_STRUCTURED_LOGGING", "false").lower() == "true":
    class JsonFormatter(logging.Formatter):
        """JSON formatter for structured logging."""
        
        def format(self, record):
            """Format the record as JSON."""
            log_record = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "message": record.getMessage()
            }
            
            # Add extra fields if available
            if hasattr(record, "extra"):
                log_record.update(record.extra)
            
            # Add exception info if available
            if record.exc_info:
                log_record["exception"] = {
                    "type": record.exc_info[0].__name__,
                    "message": str(record.exc_info[1]),
                    "traceback": traceback.format_exception(*record.exc_info)
                }
            
            return json.dumps(log_record)
    
    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(JsonFormatter())
    mcp_logger.addHandler(json_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific MCP component.
    
    Args:
        name: The name of the component (e.g., 'manager', 'provider.statistical')
        
    Returns:
        logging.Logger: A logger instance
    """
    return logging.getLogger(f"mcp.{name}")


class LogContext:
    """Context manager for adding context to log messages."""
    
    def __init__(
        self, 
        logger: logging.Logger, 
        context: Dict[str, Any],
        level: int = logging.DEBUG
    ):
        """
        Initialize the log context.
        
        Args:
            logger: The logger to use
            context: The context to add to log messages
            level: The log level for the context start/end messages
        """
        self.logger = logger
        self.context = context
        self.level = level
        self.start_time = 0.0
    
    def __enter__(self):
        """Enter the context and log the start."""
        self.start_time = time.time()
        self.logger.log(
            self.level, 
            f"Starting operation",
            extra={"context": self.context, "operation_start": True}
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context and log the end."""
        duration = time.time() - self.start_time
        
        if exc_type:
            # Log exception
            self.logger.error(
                f"Operation failed: {exc_val}",
                exc_info=(exc_type, exc_val, exc_tb),
                extra={
                    "context": self.context,
                    "operation_end": True,
                    "duration": duration,
                    "success": False
                }
            )
        else:
            # Log success
            self.logger.log(
                self.level,
                f"Operation completed in {duration:.6f} seconds",
                extra={
                    "context": self.context,
                    "operation_end": True,
                    "duration": duration,
                    "success": True
                }
            )


# Type variable for function return type
T = TypeVar('T')


def log_operation(
    logger: Optional[logging.Logger] = None,
    level: int = logging.DEBUG,
    operation_name: Optional[str] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for logging function calls with timing information.
    
    Args:
        logger: The logger to use (defaults to mcp_logger)
        level: The log level for the operation
        operation_name: The name of the operation (defaults to function name)
        
    Returns:
        Callable: The decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            nonlocal logger
            if logger is None:
                logger = mcp_logger
            
            # Get operation name
            op_name = operation_name or func.__name__
            
            # Create context
            context = {
                "operation": op_name,
                "function": func.__name__,
                "module": func.__module__
            }
            
            # Add args/kwargs if debug level
            if logger.level <= logging.DEBUG:
                # Limit args/kwargs size for logging
                safe_args = [str(arg)[:100] for arg in args]
                safe_kwargs = {k: str(v)[:100] for k, v in kwargs.items()}
                context["args"] = safe_args
                context["kwargs"] = safe_kwargs
            
            # Log the operation
            with LogContext(logger, context, level):
                return func(*args, **kwargs)
        
        return cast(Callable[..., T], wrapper)
    
    return decorator


async def log_async_operation(
    logger: Optional[logging.Logger] = None,
    level: int = logging.DEBUG,
    operation_name: Optional[str] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for logging async function calls with timing information.
    
    Args:
        logger: The logger to use (defaults to mcp_logger)
        level: The log level for the operation
        operation_name: The name of the operation (defaults to function name)
        
    Returns:
        Callable: The decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            nonlocal logger
            if logger is None:
                logger = mcp_logger
            
            # Get operation name
            op_name = operation_name or func.__name__
            
            # Create context
            context = {
                "operation": op_name,
                "function": func.__name__,
                "module": func.__module__,
                "async": True
            }
            
            # Add args/kwargs if debug level
            if logger.level <= logging.DEBUG:
                # Limit args/kwargs size for logging
                safe_args = [str(arg)[:100] for arg in args]
                safe_kwargs = {k: str(v)[:100] for k, v in kwargs.items()}
                context["args"] = safe_args
                context["kwargs"] = safe_kwargs
            
            # Log the operation
            start_time = time.time()
            logger.log(
                level, 
                f"Starting async operation",
                extra={"context": context, "operation_start": True}
            )
            
            try:
                result = await func(*args, **kwargs)
                
                duration = time.time() - start_time
                logger.log(
                    level,
                    f"Async operation completed in {duration:.6f} seconds",
                    extra={
                        "context": context,
                        "operation_end": True,
                        "duration": duration,
                        "success": True
                    }
                )
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"Async operation failed: {e}",
                    exc_info=True,
                    extra={
                        "context": context,
                        "operation_end": True,
                        "duration": duration,
                        "success": False
                    }
                )
                raise
        
        return cast(Callable[..., T], wrapper)
    
    return decorator


class PerformanceTracker:
    """Track performance metrics for MCP operations."""
    
    def __init__(self):
        """Initialize the performance tracker."""
        self.operations: Dict[str, List[float]] = {}
        self.start_times: Dict[str, float] = {}
        self.logger = get_logger("performance")
    
    def start_operation(self, operation_name: str) -> None:
        """
        Start tracking an operation.
        
        Args:
            operation_name: The name of the operation
        """
        self.start_times[operation_name] = time.time()
        self.logger.debug(f"Starting operation: {operation_name}")
    
    def end_operation(self, operation_name: str) -> float:
        """
        End tracking an operation and record its duration.
        
        Args:
            operation_name: The name of the operation
            
        Returns:
            float: The duration of the operation in seconds
        """
        if operation_name not in self.start_times:
            self.logger.warning(f"Operation {operation_name} was not started")
            return 0.0
        
        duration = time.time() - self.start_times[operation_name]
        
        if operation_name not in self.operations:
            self.operations[operation_name] = []
        
        self.operations[operation_name].append(duration)
        
        self.logger.debug(
            f"Operation {operation_name} completed in {duration:.6f} seconds"
        )
        
        return duration
    
    def get_average_duration(self, operation_name: str) -> float:
        """
        Get the average duration of an operation.
        
        Args:
            operation_name: The name of the operation
            
        Returns:
            float: The average duration in seconds
        """
        if operation_name not in self.operations:
            return 0.0
        
        durations = self.operations[operation_name]
        return sum(durations) / len(durations)
    
    def get_operation_stats(self, operation_name: str) -> Dict[str, float]:
        """
        Get statistics for an operation.
        
        Args:
            operation_name: The name of the operation
            
        Returns:
            Dict[str, float]: Statistics including min, max, avg, and count
        """
        if operation_name not in self.operations:
            return {
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "count": 0
            }
        
        durations = self.operations[operation_name]
        return {
            "min": min(durations),
            "max": max(durations),
            "avg": sum(durations) / len(durations),
            "count": len(durations)
        }
    
    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """
        Get statistics for all operations.
        
        Returns:
            Dict[str, Dict[str, float]]: Statistics for all operations
        """
        return {
            op_name: self.get_operation_stats(op_name)
            for op_name in self.operations
        }
    
    def log_all_stats(self, level: int = logging.INFO) -> None:
        """
        Log statistics for all operations.
        
        Args:
            level: The log level to use
        """
        stats = self.get_all_stats()
        for op_name, op_stats in stats.items():
            self.logger.log(
                level,
                f"Operation {op_name}: "
                f"min={op_stats['min']:.6f}s, "
                f"max={op_stats['max']:.6f}s, "
                f"avg={op_stats['avg']:.6f}s, "
                f"count={op_stats['count']}"
            )


# Create a global performance tracker
performance_tracker = PerformanceTracker()


def track_performance(operation_name: Optional[str] = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for tracking function performance.
    
    Args:
        operation_name: The name of the operation (defaults to function name)
        
    Returns:
        Callable: The decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            performance_tracker.start_operation(op_name)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                performance_tracker.end_operation(op_name)
        
        return cast(Callable[..., T], wrapper)
    
    return decorator


async def track_async_performance(operation_name: Optional[str] = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for tracking async function performance.
    
    Args:
        operation_name: The name of the operation (defaults to function name)
        
    Returns:
        Callable: The decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            performance_tracker.start_operation(op_name)
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                performance_tracker.end_operation(op_name)
        
        return cast(Callable[..., T], wrapper)
    
    return decorator


# Example usage
if __name__ == "__main__":
    # Get a logger for a component
    logger = get_logger("example")
    
    # Log a message
    logger.info("This is an example log message")
    
    # Log with context
    with LogContext(logger, {"user_id": "123", "operation": "test"}):
        logger.info("Operation in progress")
    
    # Log with decorator
    @log_operation(logger=logger, level=logging.INFO)
    def example_function(a, b):
        logger.debug("Inside example function")
        return a + b
    
    result = example_function(1, 2)
    
    # Track performance
    @track_performance("example.calculation")
    def slow_function():
        time.sleep(0.1)
        return "done"
    
    slow_function()
    slow_function()
    
    # Log performance stats
    performance_tracker.log_all_stats() 