#!/usr/bin/env python3
"""Smoke-test harness for lambda_cron_node_processor."""

import json
import os
import sys

from dotenv import load_dotenv

# Ensure project root is importable
sys.path.append(os.path.dirname(__file__))

from lambda_handler import lambda_handler

# Load environment variables for local execution
load_dotenv('.env')
load_dotenv('../.env')

REQUIRED_ENV_VARS = [
    "BASE_API_URL",
    "INSIGHTS_API_KEY",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    "R2_ENDPOINT_URL",
]

print("🔎 Environment variable check")
for var in REQUIRED_ENV_VARS:
    print(f" - {var}: {'✅' if os.getenv(var) else '❌'}")
print("-" * 50)


class MockContext:
    """Minimal Lambda context used for local execution."""

    def __init__(self) -> None:
        self.function_name = "lambda-cron-node-processor-test"
        self.function_version = "$LATEST"
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:lambda-cron-node-processor-test"
        self.memory_limit_in_mb = 512

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 30000


def run_event() -> None:
    with open('test_event.json', 'r', encoding='utf-8') as handle:
        event = json.load(handle)

    print("🚀 Executing lambda handler with event:")
    print(json.dumps(event, indent=2))
    print("-" * 50)

    response = lambda_handler(event, MockContext())
    print(f"Status: {response['statusCode']}")
    print("Body:")
    print(response['body'])


if __name__ == '__main__':
    run_event()
