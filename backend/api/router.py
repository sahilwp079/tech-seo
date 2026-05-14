from fastapi import APIRouter

from api.routes.audit_routes         import router as audit_router
from api.routes.ws_routes            import router as ws_router
from api.routes.supervisor_routes    import router as supervisor_router
from api.routes.tools_routes         import router as tools_router
from api.routes.contracts_routes     import router as contracts_router
from api.routes.prompts_routes       import router as prompts_router
from api.routes.observability_routes import router as observability_router

api_router = APIRouter()
api_router.include_router(audit_router)
api_router.include_router(ws_router)
api_router.include_router(supervisor_router)
api_router.include_router(tools_router)
api_router.include_router(contracts_router)
api_router.include_router(prompts_router)
api_router.include_router(observability_router)
