#!/usr/bin/env python3

import os
import json
import sys
from lambda_handler import lambda_handler

# Load environment variables from both local and parent .env files
import sys
sys.path.append('..')
from dotenv import load_dotenv

# Load from local .env first (higher priority)
load_dotenv('.env')
# Load from parent .env as fallback
load_dotenv('../.env')

# Override with any hardcoded values if needed (for testing only)
# os.environ["BASE_API_URL"] = "https://your-base-api-url.com"  # Uncomment to override
# os.environ["INSIGHTS_API_KEY"] = "your-api-key-here"  # Uncomment to override

print(f"🔑 Environment Check:")
print(f"   - OPENAI_API_KEY: {'✅ Available' if os.getenv('OPENAI_API_KEY') else '❌ Missing'}")
print(f"   - ANTHROPIC_API_KEY: {'✅ Available' if os.getenv('ANTHROPIC_API_KEY') else '❌ Missing'}")
print(f"   - GEMINI_API_KEY: {'✅ Available' if os.getenv('GEMINI_API_KEY') else '❌ Missing'}")
print(f"   - DEEPSEEK_API_KEY: {'✅ Available' if os.getenv('DEEPSEEK_API_KEY') else '❌ Missing'}")
print(f"   - MISTRAL_API_KEY: {'✅ Available' if os.getenv('MISTRAL_API_KEY') else '❌ Missing'}")
print()
print(f"🔧 API Configuration:")
print(f"   - BASE_API_URL: {'✅ ' + os.getenv('BASE_API_URL', 'Not Set') if os.getenv('BASE_API_URL') else '❌ Missing'}")
print(f"   - INSIGHTS_API_KEY: {'✅ Available' if os.getenv('INSIGHTS_API_KEY') else '❌ Missing'}")
print()
print(f"☁️ Storage Configuration:")
print(f"   - R2_ACCESS_KEY_ID: {'✅ Available' if os.getenv('R2_ACCESS_KEY_ID') else '❌ Missing'}")
print(f"   - R2_SECRET_ACCESS_KEY: {'✅ Available' if os.getenv('R2_SECRET_ACCESS_KEY') else '❌ Missing'}")
print(f"   - R2_BUCKET_NAME: {'✅ ' + os.getenv('R2_BUCKET_NAME', 'Not Set') if os.getenv('R2_BUCKET_NAME') else '❌ Missing'}")
print(f"   - R2_ENDPOINT_URL: {'✅ Available' if os.getenv('R2_ENDPOINT_URL') else '❌ Missing'}")
print()
print(f"🔍 Vector & Search Configuration:")
print(f"   - UPSTASH_VECTOR_REST_URL: {'✅ Available' if os.getenv('UPSTASH_VECTOR_REST_URL') else '❌ Missing'}")
print(f"   - UPSTASH_VECTOR_REST_TOKEN: {'✅ Available' if os.getenv('UPSTASH_VECTOR_REST_TOKEN') else '❌ Missing'}")
print(f"   - JINA_EMBEDDING_API_KEY: {'✅ Available' if os.getenv('JINA_EMBEDDING_API_KEY') else '❌ Missing'}")
print("-" * 50)

# Mock AWS Lambda context
class MockContext:
    def __init__(self):
        self.function_name = "node_processor_test"
        self.function_version = "$LATEST"
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:node_processor_test"
        self.memory_limit_in_mb = 512
        self.remaining_time_in_millis = lambda: 300000

def test_lambda():
    """Test the Lambda function with the provided nodeId and userId"""

    # Load test event
    with open('test_event.json', 'r') as f:
        event = json.load(f)

    print(f"🚀 Testing Lambda with event: {event}")
    print("-" * 50)

    # Create mock context
    context = MockContext()

    try:
        # Call the Lambda handler
        result = lambda_handler(event, context)

        print(f"✅ Lambda execution completed!")
        print(f"Status Code: {result['statusCode']}")

        # Parse and display the response
        response_body = result.get('body', {})
        if isinstance(response_body, str):
            response_body = json.loads(response_body)

        if result['statusCode'] == 200 and response_body.get('success'):
            print(f"🎉 SUCCESS!")
            print(f"📊 Node Processing Complete:")
            print(f"   - Node ID: {response_body.get('nodeId')}")
            print(f"   - User ID: {response_body.get('userId')}")
            print(f"   - Status: {response_body.get('message')}")
            print(f"   - Webpages: {response_body.get('webpageIds')}")
            print(f"   - ✅ Node has been processed successfully")
            if response_body.get('details'):
                print(f"   - Details: {response_body.get('details')}")
            print()
            print("📝 Note: Node processing includes HTML scraping, analysis,")
            print("    and storage of insights via the REST API.")

        else:
            print(f"❌ FAILED!")
            print(f"Error: {response_body.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_lambda()
