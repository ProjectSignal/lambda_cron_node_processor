import os
import asyncio  # Added asyncio import for sleep
from typing import List, Dict, Optional, Any
from litellm import ModelResponse
import litellm
from openai import OpenAIError
from .model_config import MODEL_CONFIGS
from .callback import CustomCallback
import time
from logging_config import setup_logger

logger = setup_logger(__name__)

class LLMManager:   
    def __init__(self):
        logger.info("Initializing LLMManager")
        self.callbacks = []
        self.custom_callback = CustomCallback()
        self.callbacks.append(self.custom_callback)
        litellm.callbacks = self.callbacks
        
        try:
            self._set_credentials()
        except Exception as e:
            logger.error(f"Failed to set credentials: {str(e)}")
            raise

    def _set_credentials(self):
        # Set standard API keys
        for provider, config in MODEL_CONFIGS.items():
            if config.get("api_key"):
                os.environ[f"{provider.upper()}_API_KEY"] = config["api_key"]
        
        # Set AWS credentials for Bedrock
        for provider, config in MODEL_CONFIGS.items():
            if provider == "anthropic_aws":
                if config.get("aws_access_key_id"):
                    os.environ["AWS_ACCESS_KEY_ID"] = config["aws_access_key_id"]
                if config.get("aws_secret_access_key"):
                    os.environ["AWS_SECRET_ACCESS_KEY"] = config["aws_secret_access_key"]
                if config.get("aws_region_name"):
                    os.environ["AWS_REGION_NAME"] = config["aws_region_name"]
    
    async def get_completion(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        fallback: bool = True,
        response_format: Optional[Dict[str, Any]] = None,
        stop: Optional[List[str]] = None,
        temperature: Optional[float] = None,
    ) -> ModelResponse:
        """Get completion from LLM provider with retry logic and fallback"""
        logger.info(f"Getting completion from provider: {provider}")
        
        try:
            config = MODEL_CONFIGS[provider]
        except KeyError:
            logger.error(f"Invalid provider: {provider}")
            raise ValueError(f"Provider {provider} not found in MODEL_CONFIGS")

        model = config["model"]
        max_retries = config.get("allowed_fails", 3)  # Default to 3 if not specified
        cooldown_time = config.get("cooldown_time", 60)  # Default to 60 seconds if not specified
        logger.info(f"Using model: {model} with max_retries: {max_retries}")

        # Build model params with logging
        try:
            model_params = self._build_model_params(config, messages, stop, response_format, temperature)
        except Exception as e:
            logger.error(f"Error building model parameters: {str(e)}")
            raise

        # Primary model attempts with retry logic
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            try:
                if retry_count > 0:
                    logger.info(f"Retry attempt {retry_count}/{max_retries} for primary model {model}")
                else:
                    logger.info(f"Sending request to primary model {model}")
                    
                response = await litellm.acompletion(**model_params)
                logger.info("Primary model request successful")
                return response
                
            except OpenAIError as e:
                retry_count += 1
                last_error = e
                logger.error(f"Error with primary model (attempt {retry_count}/{max_retries}): {str(e)}")
                
                if retry_count <= max_retries:
                    # Implement cooldown between retries
                    logger.info(f"Cooling down for {cooldown_time} seconds before next retry")
                    await asyncio.sleep(cooldown_time)
                else:
                    logger.warning(f"Max retries ({max_retries}) reached for primary model")
                    break

        # Attempt fallback if enabled and available
        if fallback and "fallback_model" in config:
            logger.info("Moving to fallback model after exhausting primary model retries")
            return await self._try_fallback(config, model_params, last_error)
        
        # If we got here, all retries failed and there's no fallback
        raise last_error

    async def _try_fallback(self, config: Dict, model_params: Dict, original_error: Exception) -> ModelResponse:
        """Helper method to handle fallback logic"""
        try:
            fallback_model = config["fallback_model"]
            logger.info(f"Attempting fallback to {fallback_model}")
            model_params["model"] = fallback_model
            response = await litellm.acompletion(**model_params)
            logger.info("Fallback request successful")
            return response
            
        except OpenAIError as e:
            logger.error(f"Fallback also failed: {str(e)}")
            # Re-raise original error to maintain error context
            raise original_error

    def _build_model_params(
        self, 
        config: Dict, 
        messages: List, 
        stop: Optional[List[str]], 
        response_format: Optional[Dict],
        temperature: Optional[float] = None,
    ) -> Dict:
        """Helper method to build model parameters"""
        # Filter out last assistant message for non-Anthropic models
        filtered_messages = messages
        model_name = config["model"].lower()
        if not ("anthropic" in model_name or "claude" in model_name) and messages:
            if messages[-1].get("role") == "assistant":
                filtered_messages = messages[:-1]
                self.logger.debug("Filtered out last assistant message for non-Anthropic model")

        model_params = {
            "model": config["model"],
            "messages": filtered_messages,
            "max_tokens": config.get("max_tokens"),
            "temperature": temperature if temperature is not None else config.get("temperature"),
        }

        if stop:
            model_params["stop"] = stop
            logger.info(f"Using stop sequences: {stop}")

        if response_format:
            model_params["response_format"] = response_format
            logger.info(f"Using response format: {response_format}")

        # Add AWS-specific parameters for Bedrock
        if config.get("aws_access_key_id"):
            model_params.update({
                "aws_access_key_id": config["aws_access_key_id"],
                "aws_secret_access_key": config.get("aws_secret_access_key"),
                "aws_region_name": config.get("aws_region_name")
            })

        return model_params
