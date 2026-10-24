

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.rag import close_qdrant
from app.database import Base, engine
from app import models
from app.auth import router as auth_router
from app.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("STARTUP: before database setup", flush=True)
    Base.metadata.create_all(bind=engine)
    print("STARTUP: database setup complete", flush=True)
    yield

app = FastAPI(
    title="Secure Customer AI Chatbot",
    description="Secure customer support API for invoices and customer records",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/")
def home():
    return {"message": "Secure Customer AI Chatbot API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
