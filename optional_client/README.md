Okay so librespot in rust is good. I wanted to stick to python only as MY codebase so I ran the following for this:
https://github.com/kokarare1212/librespot-python

Venv or you will run into problems.
```
Windows:
python -m venv venv
.\venv\Scripts\activate

Linux/Mac:
python3 -m venv venv
source venv/bin/activate
```
Then:

```
pip install -r requirements.txt
cargo install librespot
```

Make sure to fill your client_id into BOTH `spotify_player.py` and `spotify_auth.py`.

This requires creating a new app on developers.spotify.com or modifying the callback url to match up.
Once you have a refresh token and an access token you're gold and player will autorenew.
Easy solution is just to have a headless web player but I took this approach instead.
It kinda works! This was definitely the easiest approach I could find programatically to getting the token, there are also examples on librespot (rust) for getting the token which is a much better approach but this is a python project and I was using librespot binary anyways. Emulating device was more of a afterthough, however this works. Available at https://github.com/librespot-org/librespot
