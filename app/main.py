from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.init_db import init_db
from app.routes.account import router as account_router
from app.routes.automation import router as automation_router
from app.routes.agent import router as agent_router
from app.routes.agent_chat import router as agent_chat_router
from app.routes.agent_execution import router as agent_execution_router
from app.routes.agent_live import router as agent_live_router
from app.routes.agent_operations import router as agent_operations_router
from app.routes.agent_plans import router as agent_plans_router
from app.routes.agent_schedules import router as agent_schedules_router
from app.routes.brokers import router as brokers_router
from app.routes.health import router as health_router
from app.routes.history import router as history_router
from app.routes.kis import router as kis_router
from app.routes.logs import router as logs_router
from app.routes.market import router as market_router
from app.routes.market_analysis import router as market_analysis_router
from app.routes.market_profiles import router as market_profiles_router
from app.routes.market_sessions import router as market_sessions_router
from app.routes.ops import router as ops_router
from app.routes.orders import router as orders_router
from app.routes.positions import router as positions_router
from app.routes.portfolio import router as portfolio_router
from app.routes.scheduler import router as scheduler_router
from app.routes.signals import router as signals_router
from app.routes.strategy import router as strategy_router
from app.routes.strategy_auto_buy_operations import (
    router as strategy_auto_buy_operations_router,
)
from app.routes.strategy_auto_buy_scheduler import (
    router as strategy_auto_buy_scheduler_router,
)
from app.routes.strategy_dry_run import router as strategy_dry_run_router
from app.routes.strategy_live_exit import router as strategy_live_exit_router
from app.routes.strategy_live import (
    compat_router as strategy_live_auto_buy_compat_router,
    router as strategy_live_router,
)
from app.routes.strategy_performance import router as strategy_performance_router
from app.routes.strategy_positions import router as strategy_positions_router
from app.routes.strategy_risk import router as strategy_risk_router
from app.routes.trading import router as trading_router
from app.services.runtime_diagnostics import (
    configure_runtime_logging,
    log_startup_state,
)
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
    configure_runtime_logging(settings)
    init_db()
    scheduler_service.start()
    log_startup_state(settings, scheduler_service)


@app.on_event("shutdown")
def on_shutdown():
    scheduler_service.stop()


app.include_router(health_router)
app.include_router(agent_router)
app.include_router(agent_chat_router)
app.include_router(agent_plans_router)
app.include_router(agent_execution_router)
app.include_router(agent_schedules_router)
app.include_router(agent_live_router)
app.include_router(agent_operations_router)
app.include_router(brokers_router)
app.include_router(kis_router)
app.include_router(account_router)
app.include_router(automation_router)
app.include_router(positions_router)
app.include_router(portfolio_router)
app.include_router(market_router)
app.include_router(market_profiles_router)
app.include_router(market_sessions_router)
app.include_router(history_router)
app.include_router(orders_router)
app.include_router(logs_router)
app.include_router(market_analysis_router)
app.include_router(signals_router)
app.include_router(strategy_router)
app.include_router(strategy_auto_buy_operations_router)
app.include_router(strategy_auto_buy_scheduler_router)
app.include_router(strategy_dry_run_router)
app.include_router(strategy_live_router)
app.include_router(strategy_live_auto_buy_compat_router)
app.include_router(strategy_live_exit_router)
app.include_router(strategy_performance_router)
app.include_router(strategy_positions_router)
app.include_router(strategy_risk_router)
app.include_router(trading_router)
app.include_router(ops_router)
app.include_router(scheduler_router)


@app.get("/")
def read_root():
    return {
        "message": f"{settings.app_name} is running",
        "default_symbol": settings.default_symbol,
        "env": settings.app_env,
    }
