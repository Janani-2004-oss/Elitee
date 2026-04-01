"""
FastAPI application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import router
from app import logger as log


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    log.emit({"event": "service_startup", "status": "initializing_db"})
    try:
        await init_db()
        log.emit({"event": "service_startup", "status": "db_initialized"})
    except Exception as e:
        log.emit({"event": "service_startup", "status": "db_init_failed", "error": str(e)})
        # We might not want to crash the whole app if DB is down, 
        # but for this generator it's fine if it screams loudly.
        raise
    
    log.emit({"event": "service_status", "status": "ready", "port": settings.port})
    
    yield
    
    # Shutdown actions
    log.emit({"event": "service_shutdown", "status": "shutting_down"})


app = FastAPI(
    title="Order Service",
    description="Signal generator for observability system. Simulates traffic, errors, and latency.",
    version="1.0.0",
    lifespan=lifespan,
)

# Standard permissive CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
