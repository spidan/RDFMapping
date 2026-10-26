FROM python:3.12-slim

# Java for RMLMapper, Node for yarrrml-parser
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless nodejs npm curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @rmlio/yarrrml-parser

# Download an RMLMapper release jar
RUN curl -fL -o /opt/rmlmapper.jar "https://github.com/RMLio/rmlmapper-java/releases/download/v8.1.0/rmlmapper-8.1.0-r380-all.jar" \
    && unzip -tq /opt/rmlmapper.jar

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]