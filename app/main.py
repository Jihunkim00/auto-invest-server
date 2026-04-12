from fastapi import FastAPI
from app.config import get_settings
from app.db.init_db import init_db
from app.routes.health import router as health_router
from app.routes.account import router as account_router
from app.routes.positions import router as positions_router
from app.routes.market import router as market_router
from app.routes.orders import router as orders_router
from app.routes.logs import router as logs_router
from app.routes.market_analysis import router as market_analysis_router
from app.routes.signals import router as signals_router
from app.routes.trading import router as trading_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(health_router)
app.include_router(account_router)
app.include_router(positions_router)
app.include_router(market_router)
app.include_router(orders_router)
app.include_router(logs_router)
app.include_router(market_analysis_router)
app.include_router(signals_router)
app.include_router(trading_router)


@app.get("/")
def read_root():
    return {
        "message": f"{settings.app_name} is running",
        "default_symbol": settings.default_symbol,
        "env": settings.app_env,
    }