"""Logging configuration for Hydra."""

import logging
import os
import sys
from pathlib import Path


def setup_logging(level=None, log_file=None):
    """Setup logging configuration.
    
    Args:
        level: Logging level (default: INFO)
        log_file: Optional log file path
    """
    if level is None:
        level = os.getenv('HYDRA_LOG_LEVEL', 'INFO').upper()
    
    # Create .hydra/logs directory if needed
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            *([] if not log_file else [logging.FileHandler(log_file)])
        ]
    )
    
    # Reduce verbosity of some noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)


def get_logger(name):
    """Get a logger with the given name."""
    return logging.getLogger(name)


# Setup default logging when module is imported
if not logging.getLogger().hasHandlers():
    setup_logging()