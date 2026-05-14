"""FetchPageTool — HTTP GET a URL, return structured page data."""

import time
import httpx
from pydantic import BaseModel, HttpUrl

from tools.base_tool import BaseTool
from utils.retry import http_retry


class FetchPageInput(BaseModel):
    url:            str
    timeout:        int  = 10
    follow_redirects: bool = True
    user_agent:     str  = "SEOAuditBot/1.0"


class FetchPageTool(BaseTool):
    name        = "fetch_page"
    description = "Fetch a single URL via HTTP GET. Returns status code, headers, HTML body, page size, and response time."
    input_model = FetchPageInput

    def _get_retry(self):
        return http_retry(max_attempts=3)

    async def _execute(self, input_data: FetchPageInput) -> dict:
        t0 = time.monotonic()
        async with httpx.AsyncClient(
            timeout=input_data.timeout,
            follow_redirects=input_data.follow_redirects,
            headers={"User-Agent": input_data.user_agent},
        ) as client:
            resp = await client.get(input_data.url)

        ms = int((time.monotonic() - t0) * 1000)
        ct = resp.headers.get("content-type", "")
        return {
            "url":               str(resp.url),
            "status_code":       resp.status_code,
            "content_type":      ct,
            "html":              resp.text if "html" in ct else "",
            "page_size_bytes":   len(resp.content),
            "crawl_duration_ms": ms,
            "response_headers":  dict(resp.headers),
        }
