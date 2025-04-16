import base64
import hashlib
import json
import os
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import requests

class Config:
    CLIENT_ID = ''
    REDIRECT_URI = 'http://127.0.0.1:8888/callback'
    SCOPES = 'user-read-playback-state user-modify-playback-state streaming app-remote-control'
    TOKEN_FILE = 'spotify_token.json'

class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "/callback" in self.path:
            self.server.auth_code = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query
            ).get("code")[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization complete. You can close this window.")

def get_spotify_tokens():
    verifier = base64.urlsafe_b64encode(os.urandom(64)).decode('utf-8').rstrip('=')
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode('utf-8').rstrip('=')

    params = {
        "client_id": Config.CLIENT_ID,
        "response_type": "code",
        "redirect_uri": Config.REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": Config.SCOPES
    }
    
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8888), AuthHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    while not hasattr(server, "auth_code"):
        pass

    auth_code = server.auth_code
    server.shutdown()
    server_thread.join()

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": Config.REDIRECT_URI,
            "client_id": Config.CLIENT_ID,
            "code_verifier": verifier
        }
    )
    
    tokens = response.json()
    with open(Config.TOKEN_FILE, "w") as f:
        json.dump(tokens, f)
    
    return tokens

if __name__ == "__main__":
    tokens = get_spotify_tokens()
    print("Tokens obtained and saved successfully!")
