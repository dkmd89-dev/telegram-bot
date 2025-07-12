import requests

def get_youtube_thumbnail(video_id: str) -> bytes | None:
    url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    resp = requests.get(url)
    if resp.status_code != 200:
        url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        resp = requests.get(url)

    return resp.content if resp.status_code == 200 else None