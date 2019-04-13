import requests
import json
import base64
from redis import Redis
from datetime import datetime as dt, timedelta as td

TOKEN = None
REDIS = None


def redis():
    global REDIS

    if REDIS:
        return REDIS

    REDIS = Redis(db=4, decode_responses=True)
    return REDIS


def token():
    global TOKEN
    
    CLIENT_ID = "be4f42656df44b069dbe23bd50694e28"
    CLIENT_SECRET = "a99719578040478f8955dea3ed07b855"
    CLIENT_SIGNATURE = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode('ascii'))

    if TOKEN:
        expires = TOKEN.get('expires')
        if not isinstance(expires, dt):
            expires = dt.fromtimestamp(expires)

        if expires > dt.now():
            return TOKEN.get("token_type", "Bearer") + " " + TOKEN.get("access_token", "")

    cached = redis().get("spotify_token")
    if cached:
        TOKEN = json.loads(cached)
        TOKEN['expires'] = dt.now() + td(seconds=TOKEN.get('expires_in', 3600))
        return TOKEN.get("token_type", "Bearer") + " " + TOKEN.get("access_token", "")

    res = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": "Basic " + CLIENT_SIGNATURE.decode('ascii'),
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data="grant_type=client_credentials"
    )

    if res.status_code == 200:
        TOKEN = json.loads(res.text)
        redis().setex("spotify_token", res.text, TOKEN.get("expires_in", 3600))
        return TOKEN.get("token_type", "Bearer") + " " + TOKEN.get("access_token", "")
    else:
        raise Exception(res.text)


def search(q="", type="artist,track,album", limit=10):
    req = requests.request(
        method="get",
        url="https://api.spotify.com/v1/search",
        params={
            "q": q,
            "type": type,
            "limit": limit
        },
        headers={
            "Authorization": token()
        }
    )

    cached = redis().get("spotify_request:{}".format(req.url))
    if cached:
        data = json.loads(cached)
        return data

    res = requests.get(
        "https://api.spotify.com/v1/search",
        headers={
            "Authorization": token()
        },
        params={
            "q": q,
            "type": type,
            "limit": limit
        }
    )

    if res.status_code == 200:
        data = json.loads(res.text)
        redis().setex("spotify_request:{}".format(req.url), res.text, 3600)
        return data
    else:
        raise Exception(res.text)


if __name__ == "__main__":
    try:
        while True:
            try:
                cmd, type, query = parts = input().split(" ", maxsplit=2)
            except KeyboardInterrupt: exit(0)
            except: continue
    
            data = search(query, type)
    
            types = type.split(",")
            if "artist" in types:
                for n, artist in enumerate(data.get("artists", {}).get("items")):
                    print("{:>2}. {}".format(n+1, artist.get("name","--")))


            if "track" in types:
                for n, track in enumerate(data.get("tracks", {}).get("items")):
                    print("{:>2}. {} by {}".format(
                            n+1, 
                            track.get("name", "--"),
                            track.get("artists", [{}])[0].get("name", "--")
                    ))



            if "album" in types:
                for n, album in enumerate(data.get("albums", {}).get("items")):
                    print("{:>2}. {} by {}".format(
                        n+1,
                        album.get("name", "--"),
                        album.get("artists", [{}])[0].get("name", "--")
                    ))

    except KeyboardInterrupt:
        exit(0)
           


