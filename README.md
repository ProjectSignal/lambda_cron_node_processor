# Lambda Cron Node Processor

Serverless worker that transforms scraped LinkedIn node payloads into enriched Brace profiles. The Lambda consumes API-triggered events (one `nodeId` + `userId` pair), fetches the node via the Brace REST APIs, hydrates HTML from R2 when needed, generates profile narratives, maintains vector embeddings, and persists results back through the API tier.

## Invocation Contract

```json
{
  "nodeId": "<node-id-as-string>",
  "userId": "<user-id-as-string>"
}
```

Responses follow the shared platform pattern:

```json
{
  "statusCode": 200,
  "body": {
    "nodeId": "...",
    "userId": "...",
    "success": true,
    "message": "Node processed successfully"
  }
}
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `BASE_API_URL` | Brace REST API base URL (e.g. `https://backend.brace.so`) |
| `INSIGHTS_API_KEY` | `X-API-Key` credential for all REST calls |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` / `R2_ENDPOINT_URL` / `R2_REGION` | Cloudflare R2 credentials for HTML retrieval |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Optional Upstash Redis override used by embedding cache |
| `UPSTASH_VECTOR_REST_URL` / `UPSTASH_VECTOR_REST_TOKEN` | Upstash Vector index configuration |
| `JINA_EMBEDDING_API_KEY` | Embedding provider key for skills vectors |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | LLM provider credentials leveraged by the description pipeline |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_SIGNATURE_KEY`, `CLOUDFLARE_ACCOUNT_HASH` | Cloudflare Images configuration |
| `PROCESSING_TIMEOUT`, `API_TIMEOUT_SECONDS`, `API_MAX_RETRIES` | Optional tuning knobs |

## Local Smoke Test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_lambda.py  # requires API endpoint/mocks
```

`test_event.json` supplies a sample payload. Provide mock REST endpoints or tunnel to a dev stack before running.

## Packaging & Deployment

Deployment is handled through AWS CodeBuild via `buildspec.yml`. The build pipeline mirrors other Brace lambdas:

1. Install dependencies into the project root
2. Prune dev artefacts (`__pycache__`, tests, git metadata)
3. Zip the Lambda payload
4. Update the `lambda-cron-node-processor` function

Adjust the CodeBuild project to reference this repository and ensure the Lambda execution role exposes R2, Upstash, and Cloudflare permissions.
Test CI/CD pipeline trigger: Wed Sep 17 16:24:53 IST 2025
