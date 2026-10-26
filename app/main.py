import pathlib, re, subprocess, tempfile
from fastapi import FastAPI, UploadFile, HTTPException, Response
from fastapi.staticfiles import StaticFiles

app = FastAPI()
                   
@app.post("/transform")
async def transform(mapping: UploadFile, source: UploadFile):
    mapping_text = (await mapping.read()).decode("utf-8")
    source_bytes = await source.read()

    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)

        # Make the source name in the mapping match the uploaded file
        mapping_text = re.sub(r"[\w.\-/]+\.xml(?=~xpath)", "source.xml", mapping_text)
        (d / "mapping.yml").write_text(mapping_text, encoding="utf-8")
        (d / "source.xml").write_bytes(source_bytes)

        try:
            subprocess.run(["yarrrml-parser", "-i", "mapping.yml", "-o", "mapping.rml.ttl"],
                           cwd=d, check=True, capture_output=True, text=True, timeout=60)
            subprocess.run(["java", "-jar", "/opt/rmlmapper.jar",
                            "-m", "mapping.rml.ttl", "-o", "out.ttl", "-s", "turtle"],
                           cwd=d, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=400, detail=e.stderr or e.stdout)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Mapping timed out")

        return Response(content=(d / "out.ttl").read_text(encoding="utf-8"),
                        media_type="text/turtle")

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")