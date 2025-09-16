"""API-first helpers for bs modules."""

from typing import Optional

from logging_config import setup_logger

from clients import get_clients

logger = setup_logger(__name__)

_clients = get_clients()
redis_client = _clients.redis_client
async_redis_client = _clients.async_redis_client
upstash_index = _clients.upstash_index


def get_or_create_webpage_document(url: str, name: str, user_id: Optional[str] = None):
    """Create or fetch a webpage document through the REST API."""
    payload = {
        "url": url,
        "name": name,
    }
    if user_id:
        payload["userId"] = user_id

    # API Route: webpages.getOrCreate, Input: payload, Output: {"webpageId": str}
    response = _clients.api.request("POST", "webpages/get-or-create", payload)
    webpage_id = response.get("webpageId") or response.get("data", {}).get("webpageId")
    if webpage_id:
        logger.info("Resolved webpage %s to id %s", url, webpage_id)
        return webpage_id

    logger.warning("webpages/get-or-create returned no id for %s; falling back to URL", url)
    return url


__all__ = [
    "redis_client",
    "async_redis_client",
    "upstash_index",
    "get_or_create_webpage_document",
]
