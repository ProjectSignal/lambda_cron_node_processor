"""
config/settings.py
==================

Centralised configuration for the cron node processor Lambda.
The module exposes a singleton ``config`` instance that surfaces all external
service credentials and runtime tuning values. MongoDB settings have been
replaced by REST API configuration to align with the shared Brace architecture.
"""

import os
from typing import Optional

from .llm_helper import LLMManager
from .model_config import MODEL_CONFIGS
from .callback import CustomCallback


class Config:
    """Unified configuration for node processing Lambda"""

    def __init__(self):
        # API configuration
        self.BASE_API_URL = self._get_env("BASE_API_URL", required=True).rstrip("/")
        self.API_KEY = self._get_env("INSIGHTS_API_KEY", required=True)
        self.API_TIMEOUT_SECONDS = int(self._get_env("API_TIMEOUT_SECONDS", default="30"))
        self.API_MAX_RETRIES = int(self._get_env("API_MAX_RETRIES", default="3"))

        # Lambda runtime configuration
        self.PROCESSING_TIMEOUT = int(self._get_env("PROCESSING_TIMEOUT", default="30"))
        self.WORKER_ID = self._get_env(
            "WORKER_ID",
            default=self._get_env("AWS_LAMBDA_FUNCTION_NAME", default="local-worker")
        )

        # R2 Configuration
        self.R2_ACCESS_KEY_ID = self._get_env("R2_ACCESS_KEY_ID", required=True)
        self.R2_SECRET_ACCESS_KEY = self._get_env("R2_SECRET_ACCESS_KEY", required=True)
        self.R2_BUCKET_NAME = self._get_env("R2_BUCKET_NAME", required=True)
        self.R2_ENDPOINT_URL = self._get_env("R2_ENDPOINT_URL", required=True)
        self.R2_REGION = self._get_env("R2_REGION", default="auto")

        # Redis Configuration
        self.UPSTASH_REDIS_REST_URL = self._get_env("UPSTASH_REDIS_REST_URL")
        self.UPSTASH_REDIS_REST_TOKEN = self._get_env("UPSTASH_REDIS_REST_TOKEN")

        # Vector Configuration
        self.UPSTASH_VECTOR_REST_URL = self._get_env("UPSTASH_VECTOR_REST_URL", required=True)
        self.UPSTASH_VECTOR_REST_TOKEN = self._get_env("UPSTASH_VECTOR_REST_TOKEN", required=True)
        self.JINA_EMBEDDING_API_KEY = self._get_env("JINA_EMBEDDING_API_KEY", required=True)

        # External service configuration
        self.OPENAI_API_KEY = self._get_env("OPENAI_API_KEY", required=True)
        self.ANTHROPIC_API_KEY = self._get_env("ANTHROPIC_API_KEY")
        self.CLOUDFLARE_ACCOUNT_ID = self._get_env("CLOUDFLARE_ACCOUNT_ID", required=True)
        self.CLOUDFLARE_API_TOKEN = self._get_env("CLOUDFLARE_API_TOKEN", required=True)
        self.CLOUDFLARE_SIGNATURE_KEY = self._get_env("CLOUDFLARE_SIGNATURE_KEY", required=True)
        self.CLOUDFLARE_ACCOUNT_HASH = self._get_env("CLOUDFLARE_ACCOUNT_HASH", required=True)
        self.RAPID_API_KEY = self._get_env("RAPID_API_KEY")
        self.RAPID_API_HOST = self._get_env("RAPID_API_HOST")

        # Model configuration
        self.MODEL_CONFIGS = MODEL_CONFIGS
        self.NODE_CONCURRENCY = int(self._get_env("NODE_CONCURRENCY", default="1"))

        # Lazy initialised helpers
        self._llm_manager: Optional[LLMManager] = None

    def _get_env(self, key: str, default: Optional[str] = None, required: bool = False) -> str:
        """Retrieve an environment variable with optional requirement enforcement."""
        value = os.getenv(key, default)

        if required and not value:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Required environment variable %s is not set", key)
            raise ValueError(f"Required environment variable {key} is not set")

        if value and key.startswith((
            "UPSTASH_",
            "R2_",
            "OPENAI_",
            "CLOUDFLARE_",
            "JINA_",
            "BASE_API_URL",
            "INSIGHTS_API_KEY"
        )):
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Loaded environment variable: %s", key)

        return value

    @property
    def llm_manager(self) -> LLMManager:
        """Access the lazily instantiated LLM manager."""
        if self._llm_manager is None:
            self._llm_manager = LLMManager()
        return self._llm_manager

    def get_custom_callback(self):
        """Return the custom callback used by LLM operations."""
        return CustomCallback()

    def validate(self):
        """Validate that all required configuration values are present."""
        import logging
        logger = logging.getLogger(__name__)

        required_vars = [
            "BASE_API_URL",
            "API_KEY",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
            "R2_ENDPOINT_URL",
            "OPENAI_API_KEY",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_SIGNATURE_KEY",
            "CLOUDFLARE_ACCOUNT_HASH",
            "UPSTASH_VECTOR_REST_URL",
            "UPSTASH_VECTOR_REST_TOKEN",
            "JINA_EMBEDDING_API_KEY",
        ]

        missing_vars = [var for var in required_vars if not getattr(self, var)]
        if missing_vars:
            logger.error("Missing required environment variables: %s", ", ".join(missing_vars))
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

        if self.UPSTASH_REDIS_REST_URL and self.UPSTASH_REDIS_REST_TOKEN:
            logger.info("Redis configuration: using explicit credentials")
        else:
            logger.info("Redis configuration: using from_env() fallback")

        logger.info("Configuration validation completed successfully")


# Global config instance
config = Config()

__all__ = ['Config', 'config', 'LLMManager', 'MODEL_CONFIGS', 'CustomCallback']
