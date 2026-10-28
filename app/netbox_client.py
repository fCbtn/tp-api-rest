"""Synchronisation de l'inventaire dans NetBox.

Chaque conteneur géré a sa machine virtuelle, du même nom, dans le cluster
docker-local. Les fonctions tolèrent l'absence de la VM (un conteneur créé
hors de l'API n'en a pas) : dans ce cas, elles ne font rien.
"""

import os

import requests

NETBOX_URL = os.environ.get("NETBOX_URL", "http://127.0.0.1:8080")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "")
CLUSTER = "docker-local"

session = requests.Session()

_cluster_id = None


def _api(methode, chemin, **options):
    entetes = {"Authorization": f"Bearer {NETBOX_TOKEN}", "Accept": "application/json"}
    reponse = session.request(
        methode, f"{NETBOX_URL}/api{chemin}", headers=entetes, timeout=10, **options
    )
    reponse.raise_for_status()
    return reponse


def _id_cluster():
    """Identifiant du cluster docker-local (mémorisé après le premier appel)."""
    global _cluster_id
    if _cluster_id is None:
        resultats = _api(
            "GET", "/virtualization/clusters/", params={"name": CLUSTER}
        ).json()["results"]
        _cluster_id = resultats[0]["id"] if resultats else None
    return _cluster_id


def _id_vm(nom):
    """Identifiant de la VM de ce nom dans le cluster, ou None."""
    resultats = _api(
        "GET",
        "/virtualization/virtual-machines/",
        params={"name": nom, "cluster_id": _id_cluster()},
    ).json()["results"]
    return resultats[0]["id"] if resultats else None


def creer_vm(nom):
    """Crée la machine virtuelle du conteneur, statut active."""
    _api(
        "POST",
        "/virtualization/virtual-machines/",
        json={"name": nom, "cluster": _id_cluster(), "status": "active"},
    )


def maj_statut(nom, statut):
    """Passe la VM à « active » ou « offline ». Ne fait rien si la VM n'existe pas."""
    identifiant = _id_vm(nom)
    if identifiant:
        _api(
            "PATCH",
            f"/virtualization/virtual-machines/{identifiant}/",
            json={"status": statut},
        )


def supprimer_vm(nom):
    """Supprime la VM du conteneur. Ne fait rien si elle n'existe pas."""
    identifiant = _id_vm(nom)
    if identifiant:
        _api("DELETE", f"/virtualization/virtual-machines/{identifiant}/")
