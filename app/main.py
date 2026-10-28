"""API d'administration de conteneurs Docker étiquetés adminapi.managed=true."""

from fastapi import FastAPI, HTTPException

from app import docker_client

app = FastAPI(title="API d'administration de conteneurs")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/containers")
def lister_containers():
    return docker_client.lister()


@app.get("/containers/{identifiant}")
def lire_container(identifiant: str):
    conteneur = docker_client.lire(identifiant)
    if conteneur is None:
        raise HTTPException(status_code=404, detail="Conteneur inconnu ou non géré")
    return conteneur
