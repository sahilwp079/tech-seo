"""Contracts API — schema introspection and compliance reporting."""

from fastapi import APIRouter, HTTPException

from contracts.validator import contract_validator

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("")
async def list_contracts():
    """List all agents with registered output contracts."""
    return {
        "agents": contract_validator.registered_agents(),
        "count":  len(contract_validator.registered_agents()),
    }


@router.get("/{agent_name}/schema")
async def get_contract_schema(agent_name: str):
    """Return the full JSON Schema for an agent's output contract."""
    schema = contract_validator.schema_for(agent_name)
    if not schema:
        raise HTTPException(404, f"No contract registered for agent '{agent_name}'")
    return {"agent": agent_name, "schema": schema}


@router.get("/{agent_name}/validate")
async def validate_example(agent_name: str):
    """Return an example payload structure for an agent contract."""
    schema = contract_validator.schema_for(agent_name)
    if not schema:
        raise HTTPException(404, f"No contract registered for agent '{agent_name}'")
    return {
        "agent":       agent_name,
        "schema":      schema,
        "description": f"POST to /contracts/{agent_name}/validate with a payload to validate it",
    }
