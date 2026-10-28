"""API d'administration de conteneurs Docker étiquetés adminapi.managed=true."""

import os
import secrets
from collections import Counter
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app import docker_client, netbox_client

app = FastAPI(title="API d'administration de conteneurs")

# Compteur de remédiations déclenchées par le webhook (un seul worker uvicorn).
remediations = 0


class ConteneurACreer(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    image: Literal["nginx:alpine", "redis:alpine", "httpd:alpine"]


class Alerte(BaseModel):
    alert: Literal["container_down"]
    container: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")


# Descriptions des codes d'erreur, pour la documentation OpenAPI.
ERREURS = {
    401: {"description": "Token absent ou inconnu"},
    403: {"description": "Rôle insuffisant"},
    404: {"description": "Conteneur inconnu ou non géré par l'API"},
    409: {"description": "Conflit avec l'état actuel"},
}


def _docs(*codes):
    return {code: ERREURS[code] for code in codes}


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


def verifier_secret(x_webhook_secret: str | None = Header(default=None)):
    """Vérifie le secret partagé du webhook ; 401 s'il est absent ou faux."""
    attendu = os.environ.get("WEBHOOK_SECRET", "")
    if not attendu or not x_webhook_secret or not secrets.compare_digest(x_webhook_secret, attendu):
        raise HTTPException(status_code=401, detail="Secret de webhook absent ou faux")


# --- utilitaires ----------------------------------------------------------


def _gere_ou_404(identifiant):
    """Renvoie le conteneur géré, ou lève 404 s'il est inconnu ou non géré."""
    conteneur = docker_client.lire(identifiant)
    if conteneur is None:
        raise HTTPException(status_code=404, detail="Conteneur inconnu ou non géré")
    return conteneur


# --- lecture --------------------------------------------------------------


@app.get("/health", summary="Vérifie que l'API répond")
def health():
    return {"status": "ok"}


@app.get(
    "/containers",
    summary="Liste les conteneurs gérés",
    dependencies=[Depends(exiger_lecture)],
    responses=_docs(401),
)
def lister_containers():
    return docker_client.lister()


@app.get(
    "/containers/{identifiant}",
    summary="Détail d'un conteneur géré",
    dependencies=[Depends(exiger_lecture)],
    responses=_docs(401, 404),
)
def lire_container(identifiant: str):
    return _gere_ou_404(identifiant)


# --- écriture -------------------------------------------------------------


@app.post(
    "/containers",
    status_code=201,
    summary="Crée et démarre un conteneur",
    dependencies=[Depends(exiger_admin)],
    responses=_docs(401, 403, 409),
)
def creer_container(corps: ConteneurACreer):
    try:
        conteneur = docker_client.creer(corps.name, corps.image)
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))
    netbox_client.creer_vm(conteneur["name"])
    return conteneur


@app.post(
    "/containers/{identifiant}/stop",
    summary="Arrête un conteneur",
    dependencies=[Depends(exiger_admin)],
    responses=_docs(401, 403, 404, 409),
)
def arreter_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    try:
        resultat = docker_client.arreter(conteneur["id"])
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))
    netbox_client.maj_statut(resultat["name"], "offline")
    return resultat


@app.post(
    "/containers/{identifiant}/start",
    summary="Démarre un conteneur arrêté",
    dependencies=[Depends(exiger_admin)],
    responses=_docs(401, 403, 404, 409),
)
def demarrer_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    try:
        resultat = docker_client.demarrer(conteneur["id"])
    except docker_client.Conflit as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))
    netbox_client.maj_statut(resultat["name"], "active")
    return resultat


@app.delete(
    "/containers/{identifiant}",
    status_code=204,
    summary="Supprime un conteneur",
    dependencies=[Depends(exiger_admin)],
    responses=_docs(401, 403, 404),
)
def supprimer_container(identifiant: str):
    conteneur = _gere_ou_404(identifiant)
    docker_client.supprimer(conteneur["id"])
    netbox_client.supprimer_vm(conteneur["name"])


# --- webhook --------------------------------------------------------------


@app.post(
    "/webhooks/alerts",
    status_code=202,
    summary="Reçoit une alerte et redémarre le conteneur visé",
    dependencies=[Depends(verifier_secret)],
    responses=_docs(401, 404),
)
def recevoir_alerte(alerte: Alerte):
    global remediations
    conteneur = docker_client.lire_par_nom(alerte.container)
    if conteneur is None:
        raise HTTPException(status_code=404, detail="Conteneur inconnu ou non géré")
    if conteneur["state"] != "running":
        docker_client.demarrer(conteneur["id"])
        netbox_client.maj_statut(conteneur["name"], "active")
        remediations += 1
    return {"status": "accepted"}


# --- métriques ------------------------------------------------------------


@app.get("/metrics", summary="Métriques au format Prometheus")
def metriques():
    etats = Counter(c["state"] for c in docker_client.lister())
    for etat in ("running", "exited"):
        etats.setdefault(etat, 0)

    lignes = [
        "# HELP adminapi_containers Nombre de conteneurs gérés, par état.",
        "# TYPE adminapi_containers gauge",
    ]
    for etat in sorted(etats):
        lignes.append(f'adminapi_containers{{state="{etat}"}} {etats[etat]}')
    lignes += [
        "# HELP adminapi_remediations_total Redémarrages déclenchés par une alerte.",
        "# TYPE adminapi_remediations_total counter",
        f"adminapi_remediations_total {remediations}",
    ]
    return Response(content="\n".join(lignes) + "\n", media_type="text/plain")
