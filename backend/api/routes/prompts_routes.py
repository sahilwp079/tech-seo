"""Prompts API — list, preview, and hot-reload prompt templates."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.prompt_manager import prompt_manager

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("")
async def list_prompts():
    """List all available prompt template names."""
    names = prompt_manager.list_prompts()
    return {
        "prompts": names,
        "count":   len(names),
        "dir":     str(prompt_manager.raw_path("").parent),
    }


@router.get("/{name}")
async def get_prompt(name: str):
    """Return the raw template content for a prompt."""
    if not prompt_manager.exists(name):
        raise HTTPException(404, f"Prompt '{name}' not found")
    return {
        "name":    name,
        "content": prompt_manager.load(name),
        "path":    str(prompt_manager.raw_path(name)),
    }


class RenderRequest(BaseModel):
    variables: dict = {}


@router.post("/{name}/render")
async def render_prompt(name: str, body: RenderRequest):
    """Render a prompt template with the provided variables (for testing)."""
    if not prompt_manager.exists(name):
        raise HTTPException(404, f"Prompt '{name}' not found")
    rendered = prompt_manager.render(name, **body.variables)
    return {"name": name, "rendered": rendered, "variables_used": list(body.variables.keys())}


@router.post("/{name}/reload")
async def reload_prompt(name: str):
    """Force reload a prompt from disk (clears cache for this template)."""
    if not prompt_manager.exists(name):
        raise HTTPException(404, f"Prompt '{name}' not found")
    content = prompt_manager.reload(name)
    return {"name": name, "reloaded": True, "length": len(content)}


@router.post("/reload-all")
async def reload_all_prompts():
    """Clear the entire prompt cache — all templates reload from disk on next use."""
    prompt_manager.reload_all()
    return {"reloaded": True, "available": prompt_manager.list_prompts()}
