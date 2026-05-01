from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.init_db import init_db
from app.routes.account import router as account_router
from app.routes.brokers import router as brokers_router
from app.routes.health import router as health_router
from app.routes.history import router as history_router
from app.routes.kis import router as kis_router
from app.routes.logs import router as logs_router
from app.routes.market import router as market_router
from app.routes.market_analysis import router as market_analysis_router
from app.routes.market_profiles import router as market_profiles_router
from app.routes.ops import router as ops_router
from app.routes.orders import router as orders_router
from app.routes.positions import router as positions_router
from app.routes.portfolio import router as portfolio_router
from app.routes.signals import router as signals_router
from app.routes.trading import router as trading_router
from app.services.scheduler_service import scheduler_service

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    scheduler_service.start()


@app.on_event("shutdown")
def on_shutdown():
    scheduler_service.stop()


app.include_router(health_router)
app.include_router(brokers_router)
app.include_router(kis_router)
app.include_router(account_router)
app.include_router(positions_router)
app.include_router(portfolio_router)
app.include_router(market_router)
app.include_router(market_profiles_router)
app.include_router(history_router)
app.include_router(orders_router)
app.include_router(logs_router)
app.include_router(market_analysis_router)
app.include_router(signals_router)
app.include_router(trading_router)
app.include_router(ops_router)


@app.get("/")
def read_root():
    return {
        "message": f"{settings.app_name} is running",
        "default_symbol": settings.default_symbol,
        "env": settings.app_env,
    }
