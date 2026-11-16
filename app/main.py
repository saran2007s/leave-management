from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routers.admin_router import router as admin_router
from app.routers.auth_router import router as auth_router
from app.routers.leave_router import router as leave_router
from app.routers.team_router import router as team_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ensure all database tables exist when the server starts
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Leave Management System", lifespan=lifespan)

# Register API routers
app.include_router(auth_router)
app.include_router(leave_router)
app.include_router(team_router)
app.include_router(admin_router)