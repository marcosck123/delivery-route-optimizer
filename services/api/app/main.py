import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import settings
from .database import create_tables
from .routes import auth as auth_router
from .routes import deliveries as deliveries_router
from .routes import geocode_cache as geocode_cache_router
from .routes import jet as jet_router
from .routes import routes as routes_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("App startup — criando tabelas se necessário")
    create_tables()
    yield
    logger.info("App shutdown")


app = FastAPI(
    title="Delivery Route Optimizer",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(routes_router.router)
app.include_router(deliveries_router.router)
app.include_router(jet_router.router)
app.include_router(geocode_cache_router.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": __version__}
