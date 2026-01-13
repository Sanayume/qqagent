"""Logging configuration using loguru"""

import sys
from loguru import logger

def setup_logger(level: str = "INFO", log_file: str | None = None):
    """Configure loguru logger
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for log output
    """
    # Remove default handler
    logger.remove()
    
    # Console handler with colors
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )
    
    # File handler if specified
    if log_file:
        logger.add(
            log_file,
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
        )
    
    return logger


# Default logger instance
log = logger
