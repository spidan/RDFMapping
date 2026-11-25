"""SPARQL 1.1 Protocol endpoint (query operation) over the stored graphs.

GET  /sparql?query=...
POST /sparql   (application/x-www-form-urlencoded with query=...,
                or application/sparql-query with the query as the body)

Plus a few routes to put graphs into the store:
GET /graphs, PUT /graphs?graph=<iri>, DELETE /graphs?graph=<iri>
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.algebra import traverse

from app import store

router = APIRouter()

# media type -> (rdflib format, content type we answer with); the first entry is the default
TABLE_FORMATS = {
    "application/sparql-results+json": ("json", "application/sparql-results+json"),
    "application/sparql-results+xml": ("xml", "application/sparql-results+xml"),
    "text/csv": ("csv", "text/csv"),
    "text/tab-separated-values": ("tsv", "text/tab-separated-values"),
    "application/json": ("json", "application/sparql-results+json"),
}
ASK_FORMATS = {k: v for k, v in TABLE_FORMATS.items() if v[0] in ("json", "xml")}
GRAPH_FORMATS = {
    "text/turtle": ("turtle", "text/turtle"),
    "application/rdf+xml": ("xml", "application/rdf+xml"),
    "application/n-triples": ("nt", "application/n-triples"),
    "application/ld+json": ("json-ld", "application/ld+json"),
}
UPLOAD_FORMATS = {"text/turtle": "turtle", "application/n-triples": "nt",
                  "application/rdf+xml": "xml"}


def negotiate(accept: Optional[str], available: dict):
    """Pick a format from the Accept header; no header or */* gives the default."""
    default = next(iter(available))
    if not accept or not accept.strip():
        return available[default]
    wanted = []
    for part in accept.split(","):
        bits = [b.strip() for b in part.split(";")]
        q = 1.0
        for b in bits[1:]:
            if b.startswith("q="):
                try:
                    q = float(b[2:])
                except ValueError:
                    q = 0.0
        if bits[0] and q > 0:
            wanted.append((q, bits[0].lower()))
    for _, media in sorted(wanted, key=lambda w: -w[0]):
        if media in available:
            return available[media]
        if media == "*/*":
            return available[default]
        if media.endswith("/*"):
            for k, v in available.items():
                if k.startswith(media[:-1]):
                    return v
    return None


def run_query(query: str, default_graphs: list, accept: Optional[str]) -> Response:
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="No SPARQL query given (parameter 'query')")
    try:
        pq = prepareQuery(query)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed SPARQL query: {e}")

    services = []
    traverse(pq.algebra, visitPost=lambda n: services.append(1)
             if getattr(n, "name", None) == "ServiceGraphPattern" else None)
    if services:
        raise HTTPException(status_code=400, detail="SERVICE clauses are not allowed")

    kind = pq.algebra.name  # SelectQuery, AskQuery, ConstructQuery, DescribeQuery
    if kind == "SelectQuery":
        available = TABLE_FORMATS
    elif kind == "AskQuery":
        available = ASK_FORMATS
    else:
        available = GRAPH_FORMATS
    chosen = negotiate(accept, available)
    if chosen is None:
        raise HTTPException(status_code=406,
                            detail="Supported result formats: " + ", ".join(available))
    fmt, content_type = chosen

    try:
        with store.lock:
            res = store.view(default_graphs).query(pq)
            body = res.serialize(format=fmt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    return Response(content=body, media_type=content_type)


@router.get("/sparql")
async def sparql_get(request: Request, query: Optional[str] = Query(None)):
    graphs = request.query_params.getlist("default-graph-uri")
    return await run_in_threadpool(run_query, query or "", graphs, request.headers.get("accept"))


@router.post("/sparql")
async def sparql_post(request: Request):
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    graphs = request.query_params.getlist("default-graph-uri")
    if ctype == "application/sparql-query":
        try:
            query = (await request.body()).decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="The query must be UTF-8 text")
    elif ctype == "application/x-www-form-urlencoded":
        form = await request.form()
        if "update" in form:
            raise HTTPException(status_code=400, detail="SPARQL updates are not supported")
        query = form.get("query") or ""
        graphs += form.getlist("default-graph-uri")
    else:
        raise HTTPException(status_code=415,
                            detail="Use application/x-www-form-urlencoded or application/sparql-query")
    return await run_in_threadpool(run_query, query, graphs, request.headers.get("accept"))


# ---- putting graphs into the store ----

@router.get("/graphs")
async def graphs_list():
    return await run_in_threadpool(store.list_graphs)


@router.put("/graphs")
async def graphs_put(request: Request, graph: str = Query(...)):
    ctype = request.headers.get("content-type", "text/turtle").split(";")[0].strip().lower()
    fmt = UPLOAD_FORMATS.get(ctype, "turtle")
    try:
        data = (await request.body()).decode("utf-8")
        n = await run_in_threadpool(store.put_graph, graph, data, fmt)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="The data must be UTF-8 text")
    except store.StoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"graph": graph, "triples": n}


@router.delete("/graphs")
async def graphs_delete(graph: str = Query(...)):
    try:
        found = await run_in_threadpool(store.delete_graph, graph)
    except store.StoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not found:
        raise HTTPException(status_code=404, detail="No such graph")
    return Response(status_code=204)
