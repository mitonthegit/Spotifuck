import requests
import base64
import os
import json
import time
from urllib.parse import urlencode
import random
import logging

logger = logging.getLogger(__name__)


class SpotifyClient:
    def __init__(self):
        self.client_id = os.environ.get(
            "SPOTIFY_CLIENT_ID", ""
        )
        self.client_secret = os.environ.get(
            "SPOTIFY_CLIENT_SECRET", ""
        )
        self.redirect_uri = os.environ.get(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:6969/callback"
        )
        self.token_info = None
        self.token_file = "token_info.json"
        self.load_token()

    def load_token(self):
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, "r") as f:
                    self.token_info = json.load(f)
                    logger.info(f"Loaded token info from {self.token_file}")

                if (
                    self.token_info
                    and self.token_info.get("expires_at", 0) < (time.time() + 60)
                ):
                    logger.info(
                        "Token expired or nearing expiration, attempting refresh."
                    )
                    if not self.refresh_token():
                        logger.warning(
                            "Token refresh failed during load. Authorization may be lost."
                        )
                        self.token_info = None
                elif not self.token_info:
                    logger.warning(
                        f"Token file {self.token_file} contained invalid data."
                    )

        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            logger.error(f"Error loading token from {self.token_file}: {str(e)}")
            self.token_info = None
            if os.path.exists(self.token_file):
                try:
                    os.remove(self.token_file)
                    logger.info(
                        f"Removed potentially corrupted token file: {self.token_file}"
                    )
                except OSError as del_e:
                    logger.error(f"Failed to remove corrupted token file: {del_e}")

    def save_token(self):
        if self.token_info:
            try:
                with open(self.token_file, "w") as f:
                    json.dump(self.token_info, f, indent=4)
                logger.info(f"Saved token info to {self.token_file}")
            except IOError as e:
                logger.error(f"Error saving token to {self.token_file}: {str(e)}")
        else:
            logger.warning("Attempted to save token, but token_info is None.")

    def is_authorized(self):
        return (
            self.token_info is not None
            and self.token_info.get("access_token") is not None
            and self.token_info.get("expires_at", 0) > time.time()
        )

    def get_auth_url(self):
        scopes = [
            "user-read-private",
            "user-read-email",
            "user-modify-playback-state",
            "user-read-playback-state",
            "user-read-currently-playing",
            "playlist-read-private",
            "playlist-read-collaborative",
        ]
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
        }
        auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"
        logger.info(f"Generated authorization URL: {auth_url}")
        return auth_url

    def get_token(self, code):
        try:
            auth_str = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_str.encode("utf-8")
            auth_header = base64.b64encode(auth_bytes).decode("utf-8")

            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            }

            logger.info("Requesting token with authorization code...")
            response = requests.post(
                "https://accounts.spotify.com/api/token",
                headers=headers,
                data=data,
                timeout=10,
            )
            response.raise_for_status()

            token_info = response.json()
            if "access_token" not in token_info:
                logger.error("Token response did not contain 'access_token'.")
                return False

            token_info["expires_at"] = int(time.time()) + token_info.get(
                "expires_in", 3600
            )
            self.token_info = token_info
            self.save_token()
            logger.info("Successfully obtained and saved new token.")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting token: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            self.token_info = None
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during get_token: {str(e)}")
            self.token_info = None
            return False

    def refresh_token(self):
        if not self.token_info or "refresh_token" not in self.token_info:
            logger.error("Cannot refresh token: No token info or refresh token available.")
            return False

        try:
            auth_str = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_str.encode("utf-8")
            auth_header = base64.b64encode(auth_bytes).decode("utf-8")

            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.token_info["refresh_token"],
            }

            logger.info("Attempting to refresh token...")
            response = requests.post(
                "https://accounts.spotify.com/api/token",
                headers=headers,
                data=data,
                timeout=10,
            )
            response.raise_for_status()

            new_token_info = response.json()
            if "access_token" not in new_token_info:
                logger.error("Refresh token response did not contain 'access_token'.")
                return False

            if "refresh_token" not in new_token_info:
                new_token_info["refresh_token"] = self.token_info["refresh_token"]
                logger.debug("Preserved original refresh token.")

            new_token_info["expires_at"] = int(time.time()) + new_token_info.get(
                "expires_in", 3600
            )
            self.token_info = new_token_info
            self.save_token()
            logger.info("Token refreshed successfully.")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Error refreshing token: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
                if e.response.status_code == 400:
                    logger.error("Refresh token might be invalid. Clearing token info.")
                    self.token_info = None
                    if os.path.exists(self.token_file):
                        try:
                            os.remove(self.token_file)
                            logger.info(f"Removed invalid token file: {self.token_file}")
                        except OSError as del_e:
                            logger.error(f"Failed to remove invalid token file: {del_e}")

            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during refresh_token: {str(e)}")
            return False

    def _get_auth_header(self):
        if not self.token_info or not self.token_info.get("access_token"):
            logger.warning("_get_auth_header: No access token available.")
            return None

        if self.token_info.get("expires_at", 0) < (time.time() + 60):
            logger.info(
                "_get_auth_header: Token expired or nearing expiration, attempting refresh."
            )
            if not self.refresh_token():
                logger.error(
                    "_get_auth_header: Token refresh failed. Cannot provide auth header."
                )
                return None

        if not self.token_info or not self.token_info.get("access_token"):
            logger.error("_get_auth_header: Still no access token after checking/refreshing.")
            return None

        return {
            "Authorization": f"Bearer {self.token_info['access_token']}",
            "Content-Type": "application/json",
        }

    def start_stream(self, context_uri=None):
        headers = self._get_auth_header()
        if not headers:
            return False

        device = self.get_active_device()
        if not device:
            return False

        if not context_uri:
            response = requests.get(
                "https://api.spotify.com/v1/browse/featured-playlists?limit=5",
                headers=headers,
            )
            if response.status_code == 200:
                playlists = response.json().get("playlists", {}).get("items", [])
                if playlists:
                    playlist = random.choice(playlists)
                    context_uri = playlist["uri"]
                    logger.info(f"Selected featured playlist: {playlist['name']}")

        data = {}
        if context_uri:
            if "playlist" in context_uri or "album" in context_uri or "artist" in context_uri:
                data["context_uri"] = context_uri
                logger.info(f"Starting playback of context: {context_uri}")

        endpoint = f"https://api.spotify.com/v1/me/player/play?device_id={device['id']}"
        response = requests.put(endpoint, headers=headers, json=data)

        if response.status_code in (200, 204):
            logger.info(f"Successfully started playback on device: {device['name']}")
            return context_uri if context_uri else True
        else:
            logger.error(f"Failed to start playback. Status code: {response.status_code}")
            return False

    def search(self, query, type="track", limit=20):
        headers = self._get_auth_header()
        if not headers:
            logger.error("Cannot search: Not authorized.")
            return None

        if not query:
            logger.warning("Cannot search: Empty query provided.")
            return None

        params = {
            "q": query,
            "type": type,
            "limit": max(1, min(limit, 50)),
            "market": "from_token",
        }
        logger.debug(
            f"Performing search: query='{query}', type='{type}', limit={params['limit']}"
        )

        try:
            response = requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            results = response.json()
            logger.debug(f"Search successful for '{query}'.")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during search for '{query}': {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding search response for '{query}': {str(e)}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during search: {str(e)}")
            return None

    def get_active_device(self):
        headers = self._get_auth_header()
        if not headers:
            logger.error("Cannot get devices: Not authorized.")
            return None

        try:
            response = requests.get(
                "https://api.spotify.com/v1/me/player/devices",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()

            devices_data = response.json()
            devices = devices_data.get("devices", [])

            if not devices:
                logger.warning("No devices found for this user.")
                return None

            active_devices = [d for d in devices if d.get("is_active")]

            if active_devices:
                selected_device = active_devices[0]
                logger.info(
                    f"Found active device: {selected_device.get('name')} (ID: {selected_device.get('id')})"
                )
                return selected_device
            else:
                logger.warning("No active device found. Selecting a random available device.")
                selected_device = random.choice(devices)
                logger.info(
                    f"Selected fallback device: {selected_device.get('name')} (ID: {selected_device.get('id')})"
                )
                return selected_device

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting devices: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            return None
        except (KeyError, json.JSONDecodeError, IndexError) as e:
            logger.error(f"Error parsing devices response: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred getting devices: {str(e)}")
            return None

    def play_song(self, uri):
        headers = self._get_auth_header()
        if not headers:
            logger.error("Cannot play song: Not authorized.")
            return False

        device = self.get_active_device()
        if not device:
            logger.warning("Cannot play song: No active/available device found.")
            return False

        if not uri:
            logger.error("Cannot play song: No URI provided.")
            return False

        data = {
            "uris": [uri] if isinstance(uri, str) else uri,
        }
        logger.debug(f"Preparing to play URIs: {data['uris']}")

        endpoint = f"https://api.spotify.com/v1/me/player/play"
        params = {"device_id": device["id"]}
        logger.info(
            f"Requesting song playback: PUT {endpoint}?device_id={device['id']} with data={json.dumps(data)}"
        )

        try:
            response = requests.put(
                endpoint, headers=headers, params=params, json=data, timeout=10
            )

            if response.status_code in (200, 202, 204):
                logger.info(
                    f"Song playback request successful (Status: {response.status_code}) for URIs {data['uris']}"
                )
                return True
            else:
                logger.error(f"Song playback request failed: {response.status_code}")
                try:
                    error_details = response.json()
                    logger.error(f"Error details: {json.dumps(error_details)}")
                except json.JSONDecodeError:
                    logger.error(f"Response body: {response.text}")
                logger.error(
                    f"Request details: PUT {endpoint}, Params: {params}, Headers: {headers}, Data: {json.dumps(data)}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during song playback request: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during play_song: {str(e)}")
            return False
