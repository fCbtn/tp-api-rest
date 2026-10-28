"""Accès à l'API Docker Engine.

Ne manipule que les conteneurs portant le label adminapi.managed=true : le
filtrage est fait par Docker lui-même, via le paramètre « filters ». Les
conteneurs créés ici reçoivent ce label.
"""

import json
import os

import requests

DOCKER_API_URL = os.environ.get("DOCKER_API_URL", "http://127.0.0.1:2375")
LABEL_CLE = "adminapi.managed"
LABEL = f"{LABEL_CLE}=true"

session = requests.Session()


class Conflit(Exception):
    """L'état actuel empêche l'action : nom déjà pris, ou conteneur déjà dans cet état."""


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
    return [_format(c) for c in _lister_bruts({"label": [LABEL]})]


def lire(identifiant):
    """Un conteneur géré par son identifiant, ou None s'il est inconnu ou non géré."""
    bruts = _lister_bruts({"label": [LABEL], "id": [identifiant]})
    return _format(bruts[0]) if bruts else None


def _tirer_image(image):
    """Télécharge une image absente de la machine."""
    reponse = session.post(
        f"{DOCKER_API_URL}/images/create", params={"fromImage": image}, timeout=300
    )
    reponse.raise_for_status()


def creer(nom, image):
    """Crée et démarre un conteneur géré ; lève Conflit si le nom est déjà pris."""
    corps = {"Image": image, "Labels": {LABEL_CLE: "true"}}
    reponse = session.post(
        f"{DOCKER_API_URL}/containers/create", params={"name": nom}, json=corps, timeout=30
    )
    if reponse.status_code == 404:  # image absente : on la télécharge puis on réessaie
        _tirer_image(image)
        reponse = session.post(
            f"{DOCKER_API_URL}/containers/create", params={"name": nom}, json=corps, timeout=300
        )
    if reponse.status_code == 409:
        raise Conflit("un conteneur porte déjà ce nom")
    reponse.raise_for_status()

    identifiant = reponse.json()["Id"]
    session.post(f"{DOCKER_API_URL}/containers/{identifiant}/start", timeout=30).raise_for_status()
    return lire(identifiant)


def arreter(identifiant):
    """Arrête un conteneur ; lève Conflit s'il est déjà arrêté."""
    reponse = session.post(f"{DOCKER_API_URL}/containers/{identifiant}/stop", timeout=30)
    if reponse.status_code == 304:
        raise Conflit("le conteneur est déjà arrêté")
    reponse.raise_for_status()
    return lire(identifiant)


def demarrer(identifiant):
    """Démarre un conteneur ; lève Conflit s'il tourne déjà."""
    reponse = session.post(f"{DOCKER_API_URL}/containers/{identifiant}/start", timeout=30)
    if reponse.status_code == 304:
        raise Conflit("le conteneur tourne déjà")
    reponse.raise_for_status()
    return lire(identifiant)


def supprimer(identifiant):
    """Supprime un conteneur, même s'il tourne."""
    reponse = session.delete(
        f"{DOCKER_API_URL}/containers/{identifiant}", params={"force": "true"}, timeout=30
    )
    reponse.raise_for_status()
