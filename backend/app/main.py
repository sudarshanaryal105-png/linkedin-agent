from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import generation, linkedin_auth, posts, publish, uploads

settings = get_settings()

app = FastAPI(title="LinkedIn AI Content Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(linkedin_auth.router)
app.include_router(uploads.router)
app.include_router(generation.router)
app.include_router(posts.router)
app.include_router(publish.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
