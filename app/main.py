"""API d'administration de conteneurs Docker étiquetés adminapi.managed=true."""

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import docker_client

app = FastAPI(title="API d'administration de conteneurs")


class ConteneurACreer(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    image: Literal["nginx:alpine", "redis:alpine", "httpd:alpine"]


def _gere_ou_404(identifiant):
    """Renvoie le conteneur géré, ou lève 404 s'il est inconnu ou non géré."""
    conteneur = docker_client.lire(identifiant)
    if conteneur is None:
        raise HTTPException(status_code=404, detail="Conteneur inconnu ou non géré")
    return conteneur


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/containers")
def lister_containers():
    return docker_client.lister()


@app.get("/containers/{identifiant}")
def lire_container(identifiant: str):
    return _gere_ou_404(identifiant)


@app.post("/containers", status_code=201)
def creer_container(corps: ConteneurACreer):
    try:
        return docker_client.creer(corps.name, corps.image)
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))


@app.post("/containers/{identifiant}/stop")
def arreter_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    try:
        return docker_client.arreter(conteneur["id"])
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))


@app.post("/containers/{identifiant}/start")
def demarrer_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    try:
        return docker_client.demarrer(conteneur["id"])
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))


@app.delete("/containers/{identifiant}", status_code=204)
def supprimer_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    docker_client.supprimer(conteneur["id"])
