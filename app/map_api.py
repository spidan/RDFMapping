import json
from typing import Union

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.cellar import CellarError, fetch_formex
from app.query_api import run_mapping

router = APIRouter()


class MapRequest(BaseModel):
    mapping: str
    data: Union[str, dict, list]
    clean: bool = False


@router.post("/map")
async def map_json(body: MapRequest):
    """Option 1: the mapping and the data as text in one JSON body."""
    data = body.data if isinstance(body.data, str) else json.dumps(body.data, ensure_ascii=False)
    ttl = await run_in_threadpool(run_mapping, body.mapping, data.encode("utf-8"), body.clean)
    return Response(content=ttl, media_type="text/turtle")


@router.post("/map/{celex}")
async def map_celex(celex: str, request: Request, lang: str = "ENG", clean: bool = True):
    """Option 2: the mapping as the request body; the Formex is fetched from Cellar by CELEX number."""
    raw = await request.body()
    if not raw.strip():
        raise HTTPException(status_code=400, detail="Send the YARRRML mapping as the request body")
    try:
        mapping_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="The mapping must be UTF-8 text")
    try:
        formex = await run_in_threadpool(fetch_formex, celex, lang)
    except CellarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    ttl = await run_in_threadpool(run_mapping, mapping_text, formex, clean)
    return Response(content=ttl, media_type="text/turtle")
