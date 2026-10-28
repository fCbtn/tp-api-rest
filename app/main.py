"""API d'administration de conteneurs Docker étiquetés adminapi.managed=true."""

import os
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import docker_client

app = FastAPI(title="API d'administration de conteneurs")


class ConteneurACreer(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    image: Literal["nginx:alpine", "redis:alpine", "httpd:alpine"]


# --- authentification -----------------------------------------------------


def _role(authorization):
    """Rôle correspondant au token Bearer fourni, ou None si absent/inconnu."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    jeton = authorization[len("Bearer ") :]
    admin = os.environ.get("API_TOKEN_ADMIN", "")
    lecteur = os.environ.get("API_TOKEN_READER", "")
    if admin and secrets.compare_digest(jeton, admin):
        return "admin"
    if lecteur and secrets.compare_digest(jeton, lecteur):
        return "lecteur"
    return None


def exiger_lecture(authorization: str | None = Header(default=None)):
    """Admin ou lecteur ; 401 si le token est absent ou inconnu."""
    if _role(authorization) is None:
        raise HTTPException(status_code=401, detail="Token absent ou inconnu")


def exiger_admin(authorization: str | None = Header(default=None)):
    """Admin uniquement ; 401 si token absent/inconnu, 403 si rôle lecteur."""
    role = _role(authorization)
    if role is None:
        raise HTTPException(status_code=401, detail="Token absent ou inconnu")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Rôle insuffisant")


# --- utilitaires ----------------------------------------------------------


def _gere_ou_404(identifiant):
    """Renvoie le conteneur géré, ou lève 404 s'il est inconnu ou non géré."""
    conteneur = docker_client.lire(identifiant)
    if conteneur is None:
        raise HTTPException(status_code=404, detail="Conteneur inconnu ou non géré")
    return conteneur


# --- routes ---------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/containers", dependencies=[Depends(exiger_lecture)])
def lister_containers():
    return docker_client.lister()


@app.get("/containers/{identifiant}", dependencies=[Depends(exiger_lecture)])
def lire_container(identifiant: str):
    return _gere_ou_404(identifiant)


@app.post("/containers", status_code=201, dependencies=[Depends(exiger_admin)])
def creer_container(corps: ConteneurACreer):
    try:
        return docker_client.creer(corps.name, corps.image)
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))


@app.post("/containers/{identifiant}/stop", dependencies=[Depends(exiger_admin)])
def arreter_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    try:
        return docker_client.arreter(conteneur["id"])
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))


@app.post("/containers/{identifiant}/start", dependencies=[Depends(exiger_admin)])
def demarrer_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    try:
        return docker_client.demarrer(conteneur["id"])
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))


@app.delete("/containers/{identifiant}", status_code=204, dependencies=[Depends(exiger_admin)])
def supprimer_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    docker_client.supprimer(conteneur["id"])
