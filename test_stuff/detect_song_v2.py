from acrcloud.recognizer import ACRCloudRecognizer

config = {
    "host": "YOUR_HOST",
    "access_key": "5ec40e94e1d42a65045d9568923e8ee5",
    "access_secret": "KgE7cWbqOyGrwhTjDrfpKXdmUOKQOMZURmcKFt3s",
    "timeout": 10  # seconds
}

recognizer = ACRCloudRecognizer(config)

def identify_song_acr(file_path):
    result = recognizer.recognize_by_file(file_path, 0)
    import json
    parsed = json.loads(result)
    if parsed['status']['msg'] == 'Success':
        music = parsed['metadata']['music'][0]
        title = music['title']
        artist = music['artists'][0]['name']
        print(f"✅ ACR Found: {title} by {artist}")
        return title, artist
    else:
        print("❌ ACRCloud couldn't identify the song.")
        return None, None
