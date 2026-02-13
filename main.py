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
            "request-verification": "POST /api/v1/gsc/request-verification",
            "callback": "GET /api/v1/gsc/callback",
            "verify-result": "GET /api/v1/gsc/verify-result",
            "metrics": "GET /api/v1/gsc/metrics"
        },
        "example_payload": {
            "site_url": "https://example.com"
        }
    }