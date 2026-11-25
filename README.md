# RDFMapping
## Commands to setup the service
- docker build -t rml-service .
- docker run --rm -p 8000:8000 -v rdf-data:/data rml-service

(`-v rdf-data:/data` keeps the stored graphs when the container restarts; without it they are lost.)

## Using the map endpoints
Start the service first (commands above), then run these in PowerShell from the repository root. Use `curl.exe`, not the `curl` alias.

### Option 1: POST /map (mapping and data as text in a JSON body)
Build the JSON body once:
```powershell
$mapping = [IO.File]::ReadAllText("$PWD\resources\formex_32026R1744.yml")
$data    = [IO.File]::ReadAllText("$PWD\resources\32026R1744.xml")
$body    = @{ mapping = $mapping; data = $data; clean = $true } | ConvertTo-Json
[IO.File]::WriteAllText("$env:TEMP\body.json", $body, (New-Object Text.UTF8Encoding $false))
```
Send it:
```powershell
curl.exe -s -X POST "http://localhost:8000/map" -H "Content-Type: application/json" --data-binary "@$env:TEMP\body.json" -o out_map.ttl
```

### Option 2: POST /map/{celex} (mapping as the body, Formex fetched from Cellar)
```powershell
curl.exe -s -X POST "http://localhost:8000/map/32026R1744" -H "Content-Type: text/plain" --data-binary "@resources/formex_32026R1744.yml" -o out_celex.ttl
```


## SPARQL endpoint (GET and POST)
The service keeps RDF graphs (one named graph per act) and answers standard SPARQL 1.1 Protocol queries over all of them at `/sparql`. Run these in PowerShell from the repository root with `curl.exe`.

### 1. Put a graph into the store
**With the web page:** open http://localhost:8000, run a transform, type the graph IRI (the field is pre-filled with `http://publications.europa.eu/resource/celex/`, add the CELEX number) and click **Store graph**. The page sends the shown Turtle to `PUT /graphs`.

**With curl:** map something first (see above), then store the Turtle under a graph IRI, for example the CELEX IRI:
```powershell
curl.exe -s -X PUT "http://localhost:8000/graphs?graph=http://publications.europa.eu/resource/celex/32026R1744" -H "Content-Type: text/turtle" --data-binary "@out_map.ttl"
```
Putting the same IRI again replaces that graph. List and delete:
```powershell
curl.exe -s "http://localhost:8000/graphs"
curl.exe -s -X DELETE "http://localhost:8000/graphs?graph=http://publications.europa.eu/resource/celex/32026R1744"
```

### 2. Query with GET (query in the URL)
```powershell
curl.exe -s -G "http://localhost:8000/sparql" --data-urlencode "query=SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5" -H "Accept: application/sparql-results+json"
```

### 3. Query with POST (for long queries)
Raw query as the body:
```powershell
curl.exe -s -X POST "http://localhost:8000/sparql" -H "Content-Type: application/sparql-query" -H "Accept: application/sparql-results+json" --data-binary "SELECT ?s WHERE { ?s ?p ?o } LIMIT 5"
```
or as a form field:
```powershell
curl.exe -s -X POST "http://localhost:8000/sparql" --data-urlencode "query=SELECT ?s WHERE { ?s ?p ?o } LIMIT 5"
```
(One query per request. To send a query from a file use `--data-binary "@query.sparql"`; `resources/gap_analysis_queries.sparql` holds many queries, so copy one out first.)

### How graphs are stored
- Each graph is a named graph in the service, identified by the IRI you gave. Storing the same IRI again replaces it.
- Every graph is also saved as a Turtle file in `/data/graphs` inside the container (file name = the URL-encoded IRI). The service reloads these files at startup, so graphs survive a restart **only if** the container was started with `-v rdf-data:/data`.
- Without `-v rdf-data:/data` the graphs are lost when the container is removed.
- Check what is stored: `curl.exe -s "http://localhost:8000/graphs"`
- Query only one graph: add `--data-urlencode "default-graph-uri=<graph IRI>"` (GET with `-G`), or use `GRAPH <iri> { ... }` in the query. Without it, a query sees all stored graphs together.

### Result formats (Accept header)
- SELECT: `application/sparql-results+json` (default), `application/sparql-results+xml`, `text/csv`, `text/tab-separated-values`
- ASK: JSON or XML
- CONSTRUCT / DESCRIBE: `text/turtle` (default), `application/rdf+xml`, `application/n-triples`, `application/ld+json`

A malformed query returns 400, an unsupported `Accept` 406. Read-only: updates and `SERVICE` are refused. `default-graph-uri` limits a query to the named graph(s); without it, a query sees all stored graphs together (use `GRAPH ?g { ... }` to tell them apart).
