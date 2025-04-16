import json
import time
import subprocess
import requests
from datetime import datetime, timedelta

class Config:
    CLIENT_ID = ''
    TOKEN_FILE = 'spotify_token.json'
    REFRESH_BUFFER = 300 

class SpotifyPlayer:
    def __init__(self):
        self.token_data = None
        self.process = None
        self.load_tokens()

    def load_tokens(self):
        try:
            with open(Config.TOKEN_FILE, 'r') as f:
                self.token_data = json.load(f)
        except FileNotFoundError:
            raise Exception("Token file not found. Please run spotify_auth.py first.")

    def refresh_token(self):
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.token_data['refresh_token'],
                "client_id": Config.CLIENT_ID
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")
        
        new_tokens = response.json()
        new_tokens['refresh_token'] = new_tokens.get(
            'refresh_token', 
            self.token_data['refresh_token']
        )
        
        self.token_data = new_tokens
        with open(Config.TOKEN_FILE, 'w') as f:
            json.dump(self.token_data, f)

    def start_librespot(self):
        if self.process:
            self.stop_librespot()
        
        self.process = subprocess.Popen([
            "librespot",
            "-n", "SpotifyPlayer",
            "-b", "96",
            "-k", self.token_data['access_token']
        ])

    def stop_librespot(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def run(self):
        while True:
            try:
                self.refresh_token()
                self.start_librespot()
                
                expires_in = int(self.token_data.get('expires_in', 3600))
                sleep_time = expires_in - Config.REFRESH_BUFFER
                print(f"Running librespot for {sleep_time} seconds...")
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"Error: {e}")
                self.stop_librespot()
                time.sleep(10)

if __name__ == "__main__":
    player = SpotifyPlayer()
    player.run()
