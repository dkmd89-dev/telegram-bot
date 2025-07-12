# yt_music_bot/api/navidrome_api.py

import requests
from urllib.parse import quote
from config import Config
from logger import log_error, log_info

class NavidromeAPI:
    BASE_PARAMS = {
        "u": Config.NAVIDROME_USER,
        "p": quote(Config.NAVIDROME_PASS),
        "v": "1.16.1",
        "c": "yt_music_bot",
        "f": "json",
    }

    @staticmethod
    def build_url(endpoint: str) -> str:
        base = Config.NAVIDROME_URL.rstrip("/")
        return f"{base}/rest/{quote(endpoint)}.view"

    @classmethod
    def make_request(cls, endpoint: str, extra_params=None, method="get"):
        params = cls.BASE_PARAMS.copy()
        if extra_params:
            params.update(extra_params)
        url = cls.build_url(endpoint)
        try:
            if method.lower() == "post":
                response = requests.post(url, params=params, timeout=30)
            else:
                response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            log_info(f"API-Anfrage erfolgreich: {endpoint}", {"params": params})
            return response.json()["subsonic-response"]
        except Exception as e:
            log_error(f"API-Fehler für {endpoint}: {str(e)}", {"params": params})
            raise