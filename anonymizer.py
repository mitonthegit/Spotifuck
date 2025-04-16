import random
import time
import os
import json
import requests
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class Anonymizer:
    def __init__(self):
        self.search_words = self.load_word_list()
        self.max_searches_per_minute = 50
        self.next_search_time = time.time() + random.uniform(0.5, 1.5)
        self.last_search_time = 0
        self.search_count = 0
        self.search_count_reset_time = time.time()
        self.current_song = None
        self.song_start_time = 0
        self.min_song_duration_range = (10, 15)  # random range min, max
        self.full_song_chance = 0.20  # 1.0 = guaranteed, 0.1 = 10% chance
        self.song_duration_ms = 0
        self.safety_buffer = 5

        logger.info("Anonymizer initialized with %d search terms", len(self.search_words))
        logger.info("Min song duration range: %d-%d s, Continue chance: %.1f%%",
                    self.min_song_duration_range[0], self.min_song_duration_range[1], 
                    self.full_song_chance * 100)
        logger.info("Search settings: Random Delay (1-5s), Max/Min: %d",
                    self.max_searches_per_minute)

    def load_word_list(self):
        wordlist_path = Path("wordlist.txt")
        if not wordlist_path.exists():
            default_words = [
                "music", "songs", "pop", "rock", "dance", "hip hop", "country",
                "jazz", "classical", "electronic", "rap", "indie", "top hits",
                "best songs", "popular", "trending", "new music", "charts",
                "summer hits", "workout", "party", "chill", "focus", "relax",
                "throwback", "love songs", "breakup", "happy", "sad",
                "2023 hits", "2022 hits", "2021 hits", "2020 hits", "2019 hits",
                "80s", "90s", "2000s", "viral", "tiktok", "youtube",
                "relaxing", "study", "sleep", "meditate", "yoga"
            ]
            try:
                with open(wordlist_path, 'w') as f:
                    f.write('\n'.join(default_words))
                logger.info("Created default wordlist with %d terms", len(default_words))
                return default_words
            except IOError as e:
                logger.error(f"Failed to create default wordlist: {e}")
                return []
        try:
            with open(wordlist_path, 'r') as f:
                words = [line.strip() for line in f if line.strip()]
                logger.info("Loaded %d search terms from wordlist", len(words))
                return words
        except IOError as e:
            logger.error(f"Failed to load wordlist from {wordlist_path}: {e}")
            return []

    def get_random_context_type(self):
        return random.choice(['playlist', 'album', 'artist'])

    def get_random_search(self):
        if not self.search_words:
            logger.warning("Search word list is empty.")
            return ""
        num_words = random.randint(1, 3)
        k = min(num_words, len(self.search_words))
        search_words = random.sample(self.search_words, k)
        return ' '.join(search_words)

    def start_immediate_playback(self, spotify_client, stats):
        logger.info("Starting immediate playback after anonymizer start")
        
        self.current_song = None
        self.song_duration_ms = 0
        
        success = self._start_new_stream(spotify_client, stats)
        if success:
            logger.info("Successfully started initial playback")
            stats.add_log("Started initial playback", 'stream')
            return True
        else:
            logger.error("Failed to start initial playback")
            stats.add_log("Failed to start initial playback", 'system')
            return False

    def can_perform_search(self):
        current_time = time.time()
        if current_time - self.search_count_reset_time >= 60:
            self.search_count = 0
            self.search_count_reset_time = current_time
        if (current_time >= self.next_search_time and
            self.search_count < self.max_searches_per_minute):
            return True
        return False

    def update_search_metrics(self):
        current_time = time.time()
        self.last_search_time = current_time
        self.search_count += 1
        delay = random.uniform(1.0, 5.0)
        self.next_search_time = current_time + delay
        logger.debug("Search metrics updated. Count: %d/%d. Next search possible in %.2f s",
                     self.search_count, self.max_searches_per_minute, delay)

    def should_change_song(self):
        if not self.current_song:
            logger.debug("No current song/context, reason: START_NEW")
            return "START_NEW"

        current_time = time.time()
        time_played = current_time - self.song_start_time
        current_item_name = self.current_song.get('name', self.current_song.get('uri', 'Unknown Item'))

        if 'min_duration' not in self.current_song:
            min_duration = random.uniform(self.min_song_duration_range[0], self.min_song_duration_range[1])
            self.current_song['min_duration'] = min_duration
            logger.debug(f"Set random minimum duration for {current_item_name}: {min_duration:.1f}s")
        else:
            min_duration = self.current_song['min_duration']

        if time_played < min_duration:
            return False

        if 'continue_roll' not in self.current_song:
            roll = random.random()
            self.current_song['continue_roll'] = roll
            logger.debug(f"Generated continue roll for {current_item_name}: {roll:.2f}")
        else:
            roll = self.current_song['continue_roll']

        if roll < self.full_song_chance:
            if self.song_duration_ms > 0:
                song_duration_seconds = (self.song_duration_ms / 1000) + self.safety_buffer
                if time_played >= song_duration_seconds:
                    logger.info(
                        f"Song completed duration for {current_item_name} "
                        f"({time_played:.1f}s >= {song_duration_seconds:.1f}s). Reason: COMPLETED"
                    )
                    return "COMPLETED"
                else:
                    return False
            else:
                default_duration = 180
                if time_played >= default_duration:
                    logger.info(
                        f"Reached default duration for {current_item_name} without duration info "
                        f"({time_played:.1f}s >= {default_duration}s). Reason: COMPLETED_DEFAULT"
                    )
                    return "COMPLETED"
                
                logger.debug(
                    f"Continue playing {current_item_name} (roll={roll:.2f} < {self.full_song_chance:.2f}, "
                    f"time_played={time_played:.1f}s)"
                )
                return False
        else:
            reason = "CONTEXT_CHANGE" if self.song_duration_ms <= 0 else "SKIP_EARLY"
            logger.info(
                f"Min duration met ({time_played:.1f}s >= {min_duration:.1f}s) and continue chance failed "
                f"(Roll {roll:.2f} >= {self.full_song_chance:.2f}). "
                f"Reason: {reason} for: {current_item_name}"
            )
            return reason

    def ensure_continuous_playback(self, spotify_client, stats):
        change_reason = self.should_change_song()

        if change_reason:
            logger.debug(f"Change needed. Reason: {change_reason}")

            if self.current_song and change_reason == "COMPLETED":
                song_name = self.current_song.get('name', 'Unknown Song')
                artist_name = 'Unknown Artist'
                artists = self.current_song.get('artists')
                if artists and isinstance(artists, list) and len(artists) > 0:
                    artist_info = artists[0]
                    if isinstance(artist_info, dict):
                        artist_name = artist_info.get('name', 'Unknown Artist')

                logger.info(f"Logging completed song: {song_name} by {artist_name}")
                stats.add_log(
                    f"Completed full song: {song_name} by {artist_name}",
                    'play'
                )

            success = self._start_new_stream(spotify_client, stats)
            if not success:
                logger.warning("Failed to start a new stream. Will retry on next cycle.")
                self.current_song = None

    def _start_new_stream(self, spotify_client, stats):
        self.song_duration_ms = 0

        if random.random() < 0.2:
            logger.info("Attempting to start a featured playlist/context stream")
            context_uri_played = spotify_client.start_stream()
            if context_uri_played:
                display_name = context_uri_played if isinstance(context_uri_played, str) else "Featured/Recommended"
                log_message = f"Started streaming context: {display_name}"
                stats.add_log(log_message, 'stream')
                logger.info(log_message)
                self.current_song = {
                    'name': 'Playlist/Context Stream',
                    'uri': context_uri_played if isinstance(context_uri_played, str) else 'spotify:context:various',
                    'artists': [{'name': 'Various Artists'}]
                }
                self.song_start_time = time.time()
                return True
            else:
                logger.warning("Failed to start featured playlist/context stream. Falling back to search.")

        search_query = self.get_random_search()
        if not search_query:
            logger.warning("Could not generate search query. Skipping song search.")
            return False

        logger.info(f"Searching for songs with query: '{search_query}'")
        search_result = spotify_client.search(search_query)
        if not search_result:
            logger.warning(f"Search for '{search_query}' returned no result object.")
            return False

        song = self.get_random_song(search_result)
        if not song:
            logger.warning(f"No suitable songs found in search results for '{search_query}'.")
            return False

        song_name = song.get('name', 'Unknown Song')
        artist_name = 'Unknown Artist'
        artists = song.get('artists')
        if artists and isinstance(artists, list) and len(artists) > 0:
            artist_info = artists[0]
            if isinstance(artist_info, dict):
                artist_name = artist_info.get('name', 'Unknown Artist')

        logger.info(f"Attempting to play song: {song_name} by {artist_name}")

        self.song_duration_ms = song.get('duration_ms', 0)
        if self.song_duration_ms > 0:
            logger.info(f"Song duration: {self.song_duration_ms/1000:.1f} seconds")
        else:
            logger.warning(f"Song '{song_name}' has zero or missing duration_ms.")

        song_uri = song.get('uri')
        if not song_uri:
            logger.error(f"Song '{song_name}' has no URI. Cannot play.")
            return False

        if spotify_client.play_song(song_uri):
            self.current_song = song
            self.song_start_time = time.time()
            stats.add_log(f"Streaming song: {song_name} by {artist_name}", 'stream')
            logger.info(f"Successfully started streaming: {song_name} by {artist_name}")
            return True
        else:
            logger.warning(f"Failed to play song: {song_name} (URI: {song_uri})")
            self.current_song = None
            return False

    def get_random_song(self, search_result):
        if not search_result or 'tracks' not in search_result or 'items' not in search_result['tracks']:
            logger.debug("get_random_song: Invalid search result format or no tracks.")
            return None
        items = search_result['tracks']['items']
        if not items:
            logger.debug("get_random_song: No items found in tracks.")
            return None
        valid_items = [
            item for item in items
            if item and isinstance(item, dict) and
               item.get('uri') and
               not item.get('is_local', False) and
               item.get('is_playable', True) and
               item.get('duration_ms', 0) > 0
        ]
        if not valid_items:
             logger.debug("No valid (non-local, playable, with URI & duration) tracks found.")
             return None
        return random.choice(valid_items)
