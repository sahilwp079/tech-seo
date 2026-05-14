import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import api_router
import storage.chroma_store as store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Structured JSON logging — must be first
    from utils.logger import setup_logging
    setup_logging()
    # Initialise ChromaDB collections and seed knowledge base on startup
    store._get_client()
    # Preload all prompt templates into memory
    from utils.prompt_manager import prompt_manager
    prompt_manager.preload_all()
    # Mark process start in metrics collector
    from utils.metrics import metrics as _metrics
    import logging
    logging.getLogger("startup").info(
        "SEO Audit Agent started",
        extra={"version": "2.0.0"},
    )
    yield


app = FastAPI(
    title="SEO Audit Agent — Multi-Agent Platform",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
