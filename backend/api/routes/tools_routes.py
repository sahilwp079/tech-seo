"""Tool Registry API — introspection and invocation endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools import tool_registry

router = APIRouter(prefix="/tools", tags=["tools"])


class InvokeRequest(BaseModel):
    input: dict = {}


@router.get("")
async def list_tools():
    """List all registered tools with their input schemas."""
    return {"tools": tool_registry.list_tools(), "count": len(tool_registry.names())}


@router.get("/stats")
async def tool_stats():
    """Return per-tool call counts and error rates."""
    return {"stats": tool_registry.stats()}


@router.post("/{tool_name}/invoke")
async def invoke_tool(tool_name: str, body: InvokeRequest):
    """
    Directly invoke a registered tool (for testing / admin use).
    Returns a ToolOutput with success, data, error, duration_ms.
    """
    if tool_name not in tool_registry:
        raise HTTPException(404, f"Tool '{tool_name}' not registered. Available: {tool_registry.names()}")
    result = await tool_registry.invoke(tool_name, body.input)
    return result
