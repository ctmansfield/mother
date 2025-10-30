# vLLM + OpenAI Proxy quickstart
- Direct (host): http://127.0.0.1:5005/v1/models
- Proxy (host):  http://127.0.0.1:8001/v1/...
  - header: x-api-key: supersecret
- Mother hits vLLM at: http://vllm-5005:8000/v1
