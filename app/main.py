from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.auth import get_current_user, router as auth_router
from app.database import Base, engine
from app.models import User
from app.schemas import UserOut


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ensure all database tables exist when the server starts
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Leave Management System", lifespan=lifespan)

# Register routers
app.include_router(auth_router)


@app.get("/api/me", response_model=UserOut, tags=["auth"])
def read_current_user(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently logged-in user."""
    return current_user