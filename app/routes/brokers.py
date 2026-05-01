from fastapi import APIRouter

from app.brokers.factory import get_broker_status
from app.config import get_settings

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.get("/status")
def broker_status():
    return get_broker_status(get_settings())
