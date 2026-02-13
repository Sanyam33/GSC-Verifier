from fastapi import FastAPI

from db import engine, Base
import models
import router

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.include_router(router.gsc_router)

@app.get("/")
async def root():
    return {"message": "Welcome to the GSC API"}

