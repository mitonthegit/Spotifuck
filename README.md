Client Secret and Client ID must be set in "spotify_client.py", alternatively use env variables.
All relevant configuration values are at the top of "anonymizer.py".
To use head to https://developers.spotify.com, create a bot and use the redirect URL of http://127.0.0.1:6969/callback.

That is all the setup that is needed, visit webui at http://127.0.0.1:6969/ for the rest and to start.
This requires an active spotify device to be active and it will play on that. Librespot can achieve an emulated device, although getting the token isn't pretty. See optional_client/README.md for info on emulating a client and scripts provided.

Not thoroughly tested for bugs, but it seems to work as intended as far as I am aware.

`pip install -r requirements.txt`
# FEATURES

- Highly configurable, and relatively compact codebase..
- Performs bogus search queries, constantly.
- Starts song streams with a percent change of finishing the song.
- Plays full songs start to finish + 5 second grace period before applying next song gamble.
- Included scripts needed to get Librespot (premium only) to emulate a permanent device.

The intention of this project was to learn and experiment with disinformation that hopefully reaches targeted advertisements.