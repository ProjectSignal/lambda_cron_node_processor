#!/usr/bin/env python3
"""Backwards-compatible entry point preserved for local smoke testing."""

from __future__ import annotations

import json
import os

from lambda_handler import lambda_handler
from test_lambda import MockContext  # Reuse helper


def main() -> None:
    node_id = os.getenv("TEST_NODE_ID", "example-node-id")
    user_id = os.getenv("TEST_USER_ID", "example-user-id")

    event = {
        "nodeId": node_id,
        "userId": user_id,
    }

    print("Running lambda with event:")
    print(json.dumps(event, indent=2))
    response = lambda_handler(event, MockContext())
    print(response)


if __name__ == "__main__":
    main()
