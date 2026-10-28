"""API d'administration de conteneurs Docker étiquetés adminapi.managed=true."""

from fastapi import FastAPI

app = FastAPI(title="API d'administration de conteneurs")


@app.get("/health")
def health():
    return {"status": "ok"}
