import os
import time
import asyncio
from datetime import datetime

import sounddevice as sd
import soundfile as sf
from shazamio import Shazam
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# === CONFIGURATION ===
DEVICE_NAME = "Voicemeeter Out B1"
DEVICE_INDEX = None  # To be set by search
SAMPLE_RATE = 44100
CHANNELS = 2
CAPTURE_DURATION = 10  # seconds
OUTPUT_DIR = "recordings"
CAPTURE_INTERVAL = 60  # seconds between captures

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Setup Spotify client
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id="638dd6bbf60e4bf8ab15df0075f9b78e",
    client_secret="b3026109c51c4eaf8216500cf9c93adf"
))

def find_device_index_by_name(name):
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if name.lower() in device['name'].lower() and device['max_input_channels'] > 0:
            print(f"🎚️ Found device '{device['name']}' at index {i}")
            return i
    print(f"❌ No input device found with name containing '{name}'")
    return None

def lookup_spotify_metadata(title, artist):
    query = f"track:{title} artist:{artist}"
    print(f"🎧 Looking up on Spotify: {query}")
    try:
        results = sp.search(q=query, type='track', limit=1)
        if results['tracks']['items']:
            track = results['tracks']['items'][0]
            features = sp.audio_features(track['id'])[0]
            print(f"🎼 Spotify Metadata: BPM={features['tempo']}, Danceability={features['danceability']}, Energy={features['energy']}")
            return features
        else:
            print("❌ Song not found on Spotify.")
    except Exception as e:
        print(f"❌ Spotify error: {e}")
    return None

async def identify_song(file_path):
    # Simulated Shazam result
    print(f"🔍 [MOCK] Running Shazam on: {file_path}")
    try:
        title = "Stardust Redux"
        artist = "Perkulatot0r"
        print(f"✅ [MOCK] Found: {title} by {artist}")
        lookup_spotify_metadata(title, artist)
        return title, artist
    except Exception as e:
        print(f"❌ Error: {e}")
    return None, None

# async def identify_song(file_path):
#     shazam = Shazam()
#     print(f"🔍 Running Shazam on: {file_path}")
#     try:
#         result = await shazam.recognize(file_path)
#         retry_ms = result.get("retryms")
#         if retry_ms:
#             print(f"⚠️ Shazam is rate-limiting: wait {retry_ms / 1000:.1f} seconds")
#             await asyncio.sleep(retry_ms / 1000)

#         if "track" in result:
#             title = result["track"].get("title")
#             artist = result["track"].get("subtitle")
#             print(f"✅ Found: {title} by {artist}")
#             lookup_spotify_metadata(title, artist)
#             return title, artist
#         else:
#             print("❌ No song recognized.")
#     except Exception as e:
#         print(f"❌ Error: {e}")

#     return None, None


def record_audio(file_path):
    global DEVICE_INDEX
    print(f"🎙️ Recording {CAPTURE_DURATION}s from device {DEVICE_INDEX}...")
    try:
        recording = sd.rec(int(CAPTURE_DURATION * SAMPLE_RATE),
                           samplerate=SAMPLE_RATE,
                           channels=CHANNELS,
                           device=DEVICE_INDEX)
        sd.wait()
        sf.write(file_path, recording, SAMPLE_RATE)
        print(f"💾 Saved to {file_path}")
        return True
    except Exception as e:
        print(f"❌ Recording failed: {e}")
        return False

async def main_loop():
    global DEVICE_INDEX
    DEVICE_INDEX = find_device_index_by_name(DEVICE_NAME)
    if DEVICE_INDEX is None:
        return

    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(OUTPUT_DIR, f"capture_{timestamp}.wav")

        if record_audio(filename):
            await identify_song(filename)

        print(f"⏱ Waiting {CAPTURE_INTERVAL} seconds...")
        time.sleep(CAPTURE_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("👋 Exiting...")
