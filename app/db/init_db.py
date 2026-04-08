from app.db.database import engine
from app.db.models import Base

def init_db():
    Base.metadata.create_all(bind=engine)