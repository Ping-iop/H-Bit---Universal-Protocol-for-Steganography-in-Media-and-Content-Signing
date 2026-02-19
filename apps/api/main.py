from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.api.routes import router

app = FastAPI(
    title="H-Bit REST API",
    description="Universal API for the H-Bit Authentication Protocol",
    version="1.0.0b1",
)

# CORS middleware for Browser Extensions and third-party integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "H-Bit API"}
