import pathlib, re, subprocess, tempfile
from fastapi import APIRouter, UploadFile, Form, HTTPException
from rdflib import Graph

from app.clean_formex import clean as clean_formex

router = APIRouter()
MAX_ROWS = 5000


def run_mapping(mapping_text: str, source_bytes: bytes, clean_xml: bool = False) -> str:
    if clean_xml:
        try:
            source_bytes = clean_formex(source_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not clean the XML: {e}")
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        mapping_text = re.sub(r"[\w.\-/]+\.xml(?=~xpath)", "source.xml", mapping_text)
        (d / "mapping.yml").write_text(mapping_text, encoding="utf-8")
        (d / "source.xml").write_bytes(source_bytes)
        try:
            subprocess.run(["yarrrml-parser", "-i", "mapping.yml", "-o", "mapping.rml.ttl"],
                           cwd=d, check=True, capture_output=True, text=True, timeout=60)
            subprocess.run(["java", "-jar", "/opt/rmlmapper.jar", "-m", "mapping.rml.ttl",
                            "-o", "out.ttl", "-s", "turtle"],
                           cwd=d, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=400, detail=e.stderr or e.stdout)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Mapping timed out")
        return (d / "out.ttl").read_text(encoding="utf-8")


@router.post("/query")
async def query(mapping: UploadFile, source: UploadFile, sparql: str = Form(...),
                clean: bool = Form(False)):
    if re.search(r"\bSERVICE\b", sparql, re.I):
        raise HTTPException(status_code=400, detail="SERVICE clauses are not allowed")

    ttl = run_mapping((await mapping.read()).decode("utf-8"), await source.read(), clean_xml=clean)

    g = Graph()
    try:
        g.parse(data=ttl, format="turtle")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not parse mapping output: {e}")

    try:
        res = g.query(sparql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SPARQL error: {e}")
    if res.type != "SELECT":
        raise HTTPException(status_code=400, detail="Only SELECT queries are supported")

    columns = [str(v) for v in res.vars]
    rows = [[None if t is None else str(t) for t in row] for row in res]
    return {"columns": columns, "rows": rows[:MAX_ROWS],
            "total": len(rows), "truncated": len(rows) > MAX_ROWS}
