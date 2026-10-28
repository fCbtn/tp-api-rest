"""Accès à l'API Docker Engine.

Ne manipule que les conteneurs portant le label adminapi.managed=true : le
filtrage est fait par Docker lui-même, via le paramètre « filters ».
"""

import json
import os

import requests

DOCKER_API_URL = os.environ.get("DOCKER_API_URL", "http://127.0.0.1:2375")
LABEL = "adminapi.managed=true"

session = requests.Session()


def _format(conteneur):
    """Met un conteneur Docker au format du contrat (id, name, image, state)."""
    return {
        "id": conteneur["Id"],
        "name": conteneur["Names"][0].lstrip("/"),
        "image": conteneur["Image"],
        "state": conteneur["State"],
    }


def _lister_bruts(filtres):
    """Interroge /containers/json avec un filtre, renvoie la liste brute de Docker."""
    reponse = session.get(
        f"{DOCKER_API_URL}/containers/json",
        params={"all": "true", "filters": json.dumps(filtres)},
        timeout=10,
    )
    reponse.raise_for_status()
    return reponse.json()


def lister():
    """Tous les conteneurs gérés, quel que soit leur état."""
    bruts = _lister_bruts({"label": [LABEL]})
    return [_format(c) for c in bruts]


def lire(identifiant):
    """Un conteneur géré par son identifiant, ou None s'il est inconnu ou non géré."""
    bruts = _lister_bruts({"label": [LABEL], "id": [identifiant]})
    return _format(bruts[0]) if bruts else None
