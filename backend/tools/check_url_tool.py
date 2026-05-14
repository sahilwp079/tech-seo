"""CheckUrlTool — HEAD (with GET fallback) to verify a URL is reachable."""

import httpx
from pydantic import BaseModel

from tools.base_tool import BaseTool
from utils.retry import http_retry


class CheckUrlInput(BaseModel):
    url:     str
    timeout: int = 10


class CheckUrlTool(BaseTool):
    name        = "check_url"
    description = "Checks whether a URL is reachable. Sends HEAD; falls back to GET on failure. Returns HTTP status code."
    input_model = CheckUrlInput

    def _get_retry(self):
        return http_retry(max_attempts=2)

    async def _execute(self, input_data: CheckUrlInput) -> dict:
        async with httpx.AsyncClient(
            timeout=input_data.timeout,
            follow_redirects=True,
            headers={"User-Agent": "SEOAuditBot/1.0"},
        ) as client:
            try:
                resp = await client.head(input_data.url)
                return {"url": input_data.url, "status_code": resp.status_code, "method": "HEAD"}
            except Exception:
                resp = await client.get(input_data.url)
                return {"url": input_data.url, "status_code": resp.status_code, "method": "GET"}
