import asyncio
import json
from typing import Any, Dict, Tuple

from dotenv import load_dotenv

# Load environment variables FIRST, before importing config
load_dotenv('.env')
load_dotenv('../.env')

from config import config
from logging_config import setup_logger
from processor import NodeProcessor

logger = setup_logger(__name__)

_processor: NodeProcessor | None = None

def _get_processor() -> NodeProcessor:
    """Return a singleton NodeProcessor instance for the Lambda container."""
    global _processor
    if _processor is None:
        logger.info("Initializing node processor")
        config.validate()
        _processor = NodeProcessor(config=config)
    return _processor

def _extract_ids(event: Dict[str, Any]) -> Tuple[str | None, str | None]:
    """Extract nodeId and userId from the incoming event payload."""
    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body or "{}")
        except json.JSONDecodeError:
            logger.warning("Unable to decode event body as JSON; falling back to top-level keys")
            body = {}

    if isinstance(body, dict) and body:
        node_id = body.get("nodeId")
        user_id = body.get("userId")
        if node_id or user_id:
            return node_id, user_id

    return event.get("nodeId"), event.get("userId")

async def _run(event: Dict[str, Any]) -> Dict[str, Any]:
    """Execute node processing for the supplied identifiers."""
    node_id, user_id = _extract_ids(event)
    if not node_id or not user_id:
        return {
            "statusCode": 400,
            "body": {
                "success": False,
                "error": "nodeId and userId required",
            },
        }

    processor = _get_processor()

    try:
        result = await processor.process(node_id=node_id, user_id=user_id)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unhandled error while processing node %s", node_id)
        return {
            "statusCode": 500,
            "body": {
                "success": False,
                "nodeId": node_id,
                "userId": user_id,
                "error": str(exc),
            },
        }

    success = bool(result.get("success"))
    status_code = 200 if success else result.get("statusCode", 500)

    response_body: Dict[str, Any] = {
        "nodeId": node_id,
        "userId": user_id,
        "success": success,
        "message": result.get(
            "message",
            "Node processed successfully" if success else "Node processing failed",
        ),
    }

    passthrough_fields = (
        "webpageIds",
        "effectiveNodeId",
        "deduplicated",
        "skipped",
        "details",
    )
    for field in passthrough_fields:
        if field in result and result[field] is not None:
            response_body[field] = result[field]

    return {
        "statusCode": status_code,
        "body": response_body,
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda entry point (synchronous wrapper invoking async runtime)."""
    return asyncio.run(_run(event))
