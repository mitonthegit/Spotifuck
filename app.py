import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, redirect, session, render_template, jsonify, url_for
from spotify_client import SpotifyClient
from anonymizer import Anonymizer
import threading
import time
import logging
import signal
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'

class Stats:
    def __init__(self):
        self.searches = 0
        self.streams = 0
        self.plays = 0
        self.logs = []
        self.hourly_data = {
            'searches': [0] * 24,
            'streams': [0] * 24,
            'plays': [0] * 24
        }
        self.lock = threading.Lock()

    def add_log(self, message, action_type):
        with self.lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hour = datetime.now().hour

            self.logs.insert(0, {"time": timestamp, "message": message})
            if len(self.logs) > 100:
                self.logs.pop()

            log_prefix = "STAT:"
            if action_type == 'search':
                self.searches += 1
                self.hourly_data['searches'][hour] += 1
                logger.info(f"{log_prefix} Search performed - Total: {self.searches}")
            elif action_type == 'stream':
                self.streams += 1
                self.hourly_data['streams'][hour] += 1
                logger.info(f"{log_prefix} Stream started - Total: {self.streams}")
            elif action_type == 'play':
                self.plays += 1
                self.hourly_data['plays'][hour] += 1
                logger.info(f"{log_prefix} Full play recorded - Total: {self.plays}")

    def get_stats(self):
        with self.lock:
            stats_data = {
                'searches': self.searches,
                'streams': self.streams,
                'plays': self.plays,
                'logs': self.logs.copy(),
                'hourly_data': {
                    'searches': self.hourly_data['searches'].copy(),
                    'streams': self.hourly_data['streams'].copy(),
                    'plays': self.hourly_data['plays'].copy(),
                },
                'is_running': is_running,
                'is_authorized': spotify_client.is_authorized() if spotify_client else False
            }
            return stats_data

stats = Stats()
spotify_client = SpotifyClient()
anonymizer = None
anonymizer_thread = None
is_running = False
shutdown_event = threading.Event()

def anonymizer_job():
    global is_running, anonymizer

    if anonymizer is None:
        try:
            logger.info("Initializing Anonymizer instance in worker thread...")
            anonymizer = Anonymizer()
            logger.info("Anonymizer initialized successfully in worker thread.")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to initialize Anonymizer in worker thread: {e}", exc_info=True)
            is_running = False
            return

    logger.info("Anonymizer job thread started.")
    
    try:
        logger.info("Attempting immediate playback on start...")
        success = anonymizer.start_immediate_playback(spotify_client, stats)
        if not success:
            logger.warning("Initial playback failed, will retry in main loop")
    except Exception as e:
        logger.error(f"Error during initial playback: {str(e)}", exc_info=True)
    
    while is_running and not shutdown_event.is_set():
        try:
            if not spotify_client.is_authorized():
                logger.warning("Spotify client is no longer authorized. Attempting to refresh token...")
                if not spotify_client.refresh_token():
                    logger.error("Failed to refresh token. Stopping anonymizer.")
                    is_running = False
                    break

            anonymizer.ensure_continuous_playback(spotify_client, stats)

            if anonymizer.can_perform_search():
                term = anonymizer.get_random_search()
                if term:
                    result = spotify_client.search(term)
                    stats.add_log(f"Performed search: '{term}'", 'search')
                    anonymizer.update_search_metrics()
                else:
                    logger.warning("Skipping search action: No search term generated.")

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error in anonymizer job loop: {str(e)}", exc_info=True)
            time.sleep(5)

    logger.info("Anonymizer job thread stopped.")

@app.route('/')
def index():
    auth_url = None
    is_auth = spotify_client.is_authorized()
    if not is_auth:
        auth_url = spotify_client.get_auth_url()
    return render_template('index.html', auth_url=auth_url, is_authorized=is_auth,
                          is_running=is_running)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        logger.error("Callback received without authorization code.")
        return redirect(url_for('index'))

    result = spotify_client.get_token(code)
    if not result:
        logger.error("Failed to get token from Spotify after callback.")
        return redirect(url_for('index'))

    logger.info("Spotify authorization successful via callback.")
    return redirect(url_for('index'))

@app.route('/stats')
def get_stats():
    return jsonify(stats.get_stats())

@app.route('/start', methods=['POST'])
def start_anonymizer():
    global anonymizer_thread, is_running, anonymizer

    if not spotify_client.is_authorized():
        logger.warning("Start request failed: Not authorized with Spotify.")
        return jsonify({'status': 'error', 'message': 'Not authorized with Spotify'}), 401

    if is_running:
        logger.warning("Start request failed: Anonymizer already running.")
        return jsonify({'status': 'error', 'message': 'Anonymizer already running'}), 409

    device = spotify_client.get_active_device()
    if not device:
        logger.error("Start request failed: No active Spotify device found. Please open Spotify on a device first.")
        return jsonify({
            'status': 'error', 
            'message': 'No active Spotify device found. Please open Spotify on a device first.'
        }), 400

    if anonymizer is None:
        try:
            logger.info("Initializing Anonymizer instance before starting thread...")
            anonymizer = Anonymizer()
            logger.info("Anonymizer initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Anonymizer in start endpoint: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': f'Failed to initialize anonymizer: {e}'}), 500

    shutdown_event.clear()
    
    is_running = True
    anonymizer_thread = threading.Thread(target=anonymizer_job, daemon=True)
    anonymizer_thread.start()
    
    logger.info("Started anonymizer thread.")
    stats.add_log("Anonymizer started", 'system')
    return jsonify({'status': 'success', 'message': 'Anonymizer started'})

@app.route('/stop', methods=['POST'])
def stop_anonymizer():
    global is_running, anonymizer_thread

    if not is_running:
        logger.warning("Stop request ignored: Anonymizer not running.")
        return jsonify({'status': 'error', 'message': 'Anonymizer not running'}), 409

    shutdown_event.set()
    is_running = False

    if anonymizer_thread and anonymizer_thread.is_alive():
        logger.info("Waiting for anonymizer thread to stop...")
        try:
            anonymizer_thread.join(timeout=5.0)
            if anonymizer_thread.is_alive():
                logger.warning("Anonymizer thread did not stop gracefully within timeout.")
            else:
                logger.info("Anonymizer thread stopped.")
        except Exception as e:
            logger.error(f"Error while waiting for thread to stop: {e}")

    anonymizer_thread = None
    stats.add_log("Anonymizer stopped", 'system')
    logger.info("Anonymizer stopped.")
    return jsonify({'status': 'success', 'message': 'Anonymizer stopped'})

def signal_handler(sig, frame):
    global is_running
    
    if is_running:
        shutdown_event.set()
        is_running = False
        
        if anonymizer_thread and anonymizer_thread.is_alive():
            try:
                anonymizer_thread.join(timeout=3.0)
            except:
                pass
    
    logger.info("Exiting application...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
        app.run(debug=True, port=6969, host='0.0.0.0')
