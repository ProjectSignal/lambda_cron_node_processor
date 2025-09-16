from typing import Dict, Any
import json
import logging
from logging_config import setup_logger

logger = setup_logger(__name__)

class CustomCallback:
    def __init__(self):
        self.logger = logger

    def on_request_start(
        self,
        provider: str,
        model: str,
        messages: list,
        **kwargs
    ):
        self.logger.info(f"Starting request to {provider} using model {model}")
        
    def on_request_end(
        self,
        provider: str,
        model: str,
        response: Dict[str, Any],
        **kwargs
    ):
        self.logger.info(f"Request completed for {provider} using model {model}")
        
    def on_request_error(
        self,
        provider: str,
        model: str,
        error: Exception,
        **kwargs
    ):
        self.logger.error(f"Error in request to {provider} using model {model}: {str(error)}")
