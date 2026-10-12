from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .router import router

app = FastAPI(
    title="RolePilot Career Page ATS Inspector",
    description="Stateless microservice to inspect career pages, extract ATS signatures, and probe public board APIs.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "rolepilot-inspector",
        "version": "1.0.0"
    }
