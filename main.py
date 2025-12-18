"""
Spike AI - Analytics and SEO Query API
FastAPI application providing natural language querying for GA4 and SEO data.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import sys
from datetime import datetime

from config import get_settings, init_google_credentials
from models import QueryType
from orchestrator import QueryOrchestrator
from api.routes import router, set_orchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Completely silence internal client logs (LiteLLM dependency)
logging.getLogger("openai").setLevel(logging.CRITICAL)
logging.getLogger("openai._base_client").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("litellm").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting Spike AI")
    
    try:
        settings = get_settings()
        logger.info(f"Loaded settings: port={settings.port}, model={settings.llm_model}")
        
        creds_path = init_google_credentials()
        logger.info(f"Loaded credentials: {creds_path}")
        
        orchestrator = QueryOrchestrator()
        set_orchestrator(orchestrator)
        logger.info("Orchestrator initialized")
        
        yield
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    finally:
        logger.info("Shutting down")


# Create FastAPI app
app = FastAPI(
    title="Spike AI",
    description="Natural language query API for GA4 Analytics and SEO data",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": f"Internal server error: {str(exc)}",
            "query_type": QueryType.UNKNOWN.value,
            "answer": "An unexpected error occurred while processing your request."
        }
    )


if __name__ == "__main__":
    import uvicorn
    import sys
    
    settings = get_settings()
    
    dev_mode = "--dev" in sys.argv
    
    if dev_mode:
        logger.info("Starting in development mode with auto-reload")
    
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=dev_mode,  # Auto-reload in dev mode
        reload_dirs=["."] if dev_mode else None,
        reload_includes=["*.py"] if dev_mode else None
    )

