"""Service client factories for the cron node processor Lambda."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import boto3
import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from upstash_redis import Redis
from upstash_redis.asyncio import Redis as AsyncRedis
from upstash_vector import Index

from config import config
from logging_config import setup_logger

logger = setup_logger(__name__)


class ApiClient:
    """Thin wrapper over ``requests`` providing retries and authentication."""

    def __init__(self, base_url: str, api_key: str, timeout: int, max_retries: int):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._session: Session = Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST", "PUT", "PATCH", "DELETE")
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def _headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json"
        }

    def _url(self, route: str) -> str:
        route = route.lstrip("/")
        if not route.startswith("api/"):
            route = f"api/{route}"
        return f"{self._base_url}/{route}"

    def request(self, method: str, route: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute an HTTP request and return the JSON body."""
        url = self._url(route)
        logger.debug("API %s %s", method.upper(), url)
        response = self._session.request(
            method=method.upper(),
            url=url,
            headers=self._headers(),
            data=json.dumps(payload or {}),
            timeout=self._timeout
        )
        if response.status_code >= 400:
            logger.error("API request failed: %s %s -> %s %s", method, url, response.status_code, response.text)
            raise RuntimeError(f"API request failed with status {response.status_code}: {response.text}")
        if not response.text:
            return {}
        return response.json()

    def get(self, route: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._url(route)
        logger.debug("API GET %s", url)
        response = self._session.get(
            url,
            headers=self._headers(),
            params=params,
            timeout=self._timeout
        )
        if response.status_code >= 400:
            logger.error("API GET failed: %s -> %s %s", url, response.status_code, response.text)
            raise RuntimeError(f"API GET failed with status {response.status_code}: {response.text}")
        if not response.text:
            return {}
        return response.json()


class ServiceClients:
    """Aggregate external service clients for reuse inside a Lambda container."""

    def __init__(self):
        self.api = ApiClient(
            base_url=config.BASE_API_URL,
            api_key=config.API_KEY,
            timeout=config.API_TIMEOUT_SECONDS,
            max_retries=config.API_MAX_RETRIES,
        )
        self.r2_client = boto3.client(
            "s3",
            region_name=config.R2_REGION,
            aws_access_key_id=config.R2_ACCESS_KEY_ID,
            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
            endpoint_url=config.R2_ENDPOINT_URL,
            config=boto3.session.Config(retries={"max_attempts": 3}, max_pool_connections=5),
        )
        self.redis_client = self._init_redis()
        self.async_redis_client = self._init_async_redis()
        self.upstash_index = Index(
            url=config.UPSTASH_VECTOR_REST_URL,
            token=config.UPSTASH_VECTOR_REST_TOKEN,
        )

    def _init_redis(self) -> Redis:
        if config.UPSTASH_REDIS_REST_URL and config.UPSTASH_REDIS_REST_TOKEN:
            logger.info("Using explicit Upstash Redis credentials")
            return Redis(
                url=config.UPSTASH_REDIS_REST_URL,
                token=config.UPSTASH_REDIS_REST_TOKEN,
            )
        logger.info("Using Redis.from_env() for credential discovery")
        return Redis.from_env()

    def _init_async_redis(self) -> AsyncRedis:
        if config.UPSTASH_REDIS_REST_URL and config.UPSTASH_REDIS_REST_TOKEN:
            return AsyncRedis(
                url=config.UPSTASH_REDIS_REST_URL,
                token=config.UPSTASH_REDIS_REST_TOKEN,
            )
        return AsyncRedis.from_env()


_clients: Optional[ServiceClients] = None


def get_clients() -> ServiceClients:
    global _clients
    if _clients is None:
        _clients = ServiceClients()
    return _clients
