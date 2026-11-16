from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

# Mount static assets and configure Jinja2 templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Register API routers
app.include_router(auth_router)
app.include_router(leave_router)
app.include_router(team_router)
app.include_router(admin_router)


# ---------- Frontend HTML Page Routes ----------

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/dashboard")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/request", include_in_schema=False)
def request_page(request: Request):
    return templates.TemplateResponse(request, "request.html")


@app.get("/approvals", include_in_schema=False)
def approvals_page(request: Request):
    return templates.TemplateResponse(request, "approvals.html")


@app.get("/calendar", include_in_schema=False)
def calendar_page(request: Request):
    return templates.TemplateResponse(request, "calendar.html")


@app.get("/admin", include_in_schema=False)
def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html")