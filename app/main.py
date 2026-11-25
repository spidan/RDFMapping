from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, Form, Response
from fastapi.staticfiles import StaticFiles
from app.query_api import router as query_router, run_mapping
from app.map_api import router as map_router
from app.sparql_api import router as sparql_router
from app import store


@asynccontextmanager
async def lifespan(app):
    store.load_all()
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/transform")
async def transform(mapping: UploadFile, source: UploadFile, clean: bool = Form(False)):
    ttl = run_mapping((await mapping.read()).decode("utf-8"), await source.read(), clean_xml=clean)
    return Response(content=ttl, media_type="text/turtle")


app.include_router(query_router)
app.include_router(map_router)
app.include_router(sparql_router)

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
