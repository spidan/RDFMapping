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