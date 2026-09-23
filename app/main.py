from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(
    title=getattr(settings, "PROJECT_NAME", "Waste Management CRM"),
    openapi_url=f"{getattr(settings, 'API_V1_STR', '/api/v1')}/openapi.json",
)

# Origins permitted to access the backend API
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "https://swayambhuinfo.com",
    "https://www.swayambhuinfo.com",
    "https://swayambhu-innovative-solutions.vercel.app/",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = getattr(settings, "API_V1_STR", "/api/v1")
app.include_router(api_router, prefix=api_prefix)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}