import asyncio
import datetime
import gzip
from datetime import UTC
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from clients import ServiceClients, get_clients
from logging_config import setup_logger
from bs.parseHtmlForDescription import run_scraper_base


logger = setup_logger(__name__)


class NodeProcessor:
    """Execute node processing via the shared REST APIs."""

    def __init__(self, config, clients: Optional[ServiceClients] = None):
        self.config = config
        self.clients = clients or get_clients()
        self.api = self.clients.api
        self.r2_client = self.clients.r2_client

    async def process(self, node_id: str, user_id: str) -> Dict[str, Any]:
        """Process a node by fetching its data and delegating to the scraper pipeline."""
        logger.info("Processing node %s for user %s", node_id, user_id)

        try:
            node_data = await self._fetch_node(node_id=node_id, user_id=user_id)
        except Exception as exc:  # pragma: no cover - API issues logged below
            logger.error("Failed to load node %s: %s", node_id, exc)
            return {
                "success": False,
                "statusCode": 404,
                "message": f"Node {node_id} not found",
            }

        if not node_data:
            logger.warning("Node %s responded with empty payload", node_id)
            return {
                "success": False,
                "statusCode": 404,
                "message": "Node not found",
            }

        username = node_data.get("linkedinUsername")
        html_path = node_data.get("htmlPath")
        created_at = node_data.get("createdAt", datetime.datetime.now(UTC))

        logger.info("Node payload received: name=%s username=%s html=%s", node_data.get("name"), username, html_path)

        profile_html: Optional[str] = None
        if html_path and not node_data.get("apiScraped", False):
            profile_html = await self._download_file_from_r2(html_path)

        try:
            scraper_result = await run_scraper_base(
                profile_html,
                node_data.get("name", username),
                username,
                node_id,
                user_id,
                created_at,
                node_data,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Processing failed for node %s", node_id)
            await self._mark_node_error(node_id=node_id, error_message=str(exc))
            return {
                "success": False,
                "statusCode": 500,
                "message": str(exc),
            }

        scraper_result = scraper_result or {}
        success = bool(scraper_result.get("success"))
        webpage_ids = scraper_result.get("webpage_ids") or []
        effective_node_id = scraper_result.get("effective_node_id", node_id)
        deduplicated = bool(scraper_result.get("deduplicated"))
        skipped = bool(scraper_result.get("skipped"))
        changed_fields = scraper_result.get("changed_fields") or []
        merged_from_node_id = scraper_result.get("merged_from_node_id")

        if not success:
            error_message = scraper_result.get("error", "Node processing failed")
            logger.error(
                "Processing result for node %s indicates failure: %s",
                node_id,
                error_message,
            )
            await self._mark_node_error(node_id=node_id, error_message=error_message)
            return {
                "success": False,
                "statusCode": 500,
                "message": error_message,
                "webpageIds": webpage_ids,
                "effectiveNodeId": effective_node_id,
                "deduplicated": deduplicated,
                "skipped": skipped,
            }

        logger.info("Processing complete for node %s", effective_node_id)

        response: Dict[str, Any] = {
            "success": True,
            "statusCode": 200,
            "message": "Node processed successfully" if not skipped else "Node already up to date",
            "webpageIds": webpage_ids,
            "effectiveNodeId": effective_node_id,
            "deduplicated": deduplicated,
            "skipped": skipped,
        }

        details: Dict[str, Any] = {}
        if changed_fields:
            details["changedFields"] = changed_fields
        if merged_from_node_id:
            details["mergedFromNodeId"] = merged_from_node_id
        if deduplicated:
            details.setdefault("note", "Node merged into existing profile")
        if details:
            response["details"] = details

        return response

    async def _fetch_node(self, node_id: str, user_id: str) -> Dict[str, Any]:
        """Load node details from the REST API."""
        def _call_api() -> Dict[str, Any]:
            # API Route: nodes.getById, Input: {"nodeId": node_id, "userId": user_id}, Output: {"success": bool, "data": {...}}
            response = self.api.get(f"nodes/{node_id}", params={"userId": user_id})
            if isinstance(response, dict) and response.get("success") is False:
                raise RuntimeError(response.get("message") or "Node lookup failed")
            if isinstance(response, dict) and "data" in response:
                return response["data"]
            return response

        return await asyncio.to_thread(_call_api)

    async def _mark_node_error(self, node_id: str, error_message: str) -> None:
        """Flag the node as errored through the API."""
        def _call_api() -> Dict[str, Any]:
            payload = {
                "nodeId": node_id,
                "errorMessage": error_message,
            }
            # API Route: nodes.markError, Input: payload, Output: {"success": bool}
            return self.api.request("POST", "nodes/mark-error", payload)

        try:
            await asyncio.to_thread(_call_api)
        except Exception as exc:  # pragma: no cover - logging side effect only
            logger.error("Failed to mark node %s as error via API: %s", node_id, exc)

    async def _download_file_from_r2(self, html_path: str, max_retries: int = 3, initial_backoff: float = 0.5) -> Optional[str]:
        """Download profile HTML from R2 storage with retries."""
        bucket_name = self.config.R2_BUCKET_NAME
        retry_count = 0

        while retry_count < max_retries:
            try:
                await asyncio.to_thread(
                    self.r2_client.head_object,
                    Bucket=bucket_name,
                    Key=html_path,
                )
            except ClientError as err:
                if err.response.get("Error", {}).get("Code") == "404":
                    logger.warning("HTML path %s not found in bucket %s", html_path, bucket_name)
                    return None
                raise

            try:
                response = await asyncio.to_thread(
                    self.r2_client.get_object,
                    Bucket=bucket_name,
                    Key=html_path,
                )
            except Exception as exc:  # pragma: no cover - boto errors logged below
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = initial_backoff * (2 ** (retry_count - 1))
                    logger.warning("Download attempt %s failed for %s: %s. Retrying in %.2fs", retry_count, html_path, exc, wait_time)
                    await asyncio.sleep(wait_time)
                    continue
                logger.error("Exhausted retries downloading %s: %s", html_path, exc)
                return None

            body = response["Body"]
            if html_path.endswith(".html.gz"):
                with gzip.GzipFile(fileobj=body) as gz_stream:
                    return gz_stream.read().decode("utf-8")
            return body.read().decode("utf-8")

        return None

    def generate_description(self, node_data: Dict[str, Any]):
        """Synchronous helper maintained for backward compatibility."""
        node_id = node_data.get("_id")
        user_id = node_data.get("userId")
        if not node_id or not user_id:
            raise ValueError("node_data must include '_id' and 'userId' keys")
        return asyncio.run(self.process(node_id=node_id, user_id=user_id))
