"""PKCE helpers shared by the providers."""

import base64
import hashlib
import os


def generate_verifier() -> str:
    """MyAnimeList requires a 43-128 character verifier and only supports the plain method."""
    return base64.urlsafe_b64encode(os.urandom(64)).decode().rstrip("=")[:128]


def challenge_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def generate_state() -> str:
    return base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip("=")
