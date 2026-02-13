from fastapi import FastAPI

from db import engine, Base
import models
import router

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.include_router(router.gsc_router)

@app.get("/")
def root():
    return {"message": "Welcome to the GSC API"}

@app.get("/help")
def help():
    return{
        "endpoints": {
            "request-verification": "POST /api/gsc/request-verification",
            "callback": "GET /api/gsc/callback",
            "verify-result": "GET /api/gsc/verify-result",
            "metrics": "GET /api/gsc/metrics"
        },
        "example_payload": {
            "site_url": "https://example.com"
        }
    }