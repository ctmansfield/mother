import os
import secrets
from fastapi import FastAPI, Request, Response
import httpx

UP = os.getenv("UPSTREAM", "http://vllm-5005:8000")
API_KEY = os.getenv("OPENAI_PROXY_KEY")  # optional
app = FastAPI()


@app.get("/health")
async def health():
    return {"ok": True, "upstream": UP}


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy(path: str, request: Request):
    if API_KEY:
        key = request.headers.get("x-api-key") or ""
        if not secrets.compare_digest(key, API_KEY):
            return Response(
                status_code=401,
                content=b'{"error":"unauthorized"}',
                media_type="application/json",
            )
    url = f"{UP}/v1/{path}"
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.request(request.method, url, headers=headers, content=body)
    passthru = {
        k: v
        for k, v in r.headers.items()
        if k.lower() in ("content-type", "cache-control")
    }
    return Response(content=r.content, status_code=r.status_code, headers=passthru)
