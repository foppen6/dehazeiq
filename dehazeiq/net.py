"""Säkra internetanslutningar i den packade appen.

Python i appen hittar inte alltid datorns rotcertifikat (särskilt på Mac), och då misslyckas
alla HTTPS-hämtningar med CERTIFICATE_VERIFY_FAILED. Här används certifi:s certifikatlista
(följer med appen) för alla hämtningar via urllib.
"""

import os
import ssl
import urllib.request

_done = False


def context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def setup():
    global _done
    if _done:
        return
    _done = True
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:  # noqa: BLE001
        pass
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context()))
    urllib.request.install_opener(opener)
