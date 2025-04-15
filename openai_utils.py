import os
from openai import OpenAI
import json
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_playlist_data(prompt: str):
    response = client.chat.completions.create(
        model="gpt-4.1-nano-2025-04-14",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant who returns structured JSON data only. Do not add explanations."
            },
            {
                "role": "user",
                "content": f"Based on the theme '{prompt}', suggest a poetic and imaginative name for a Spotify playlist, and provide a list of 10 songs that fit the theme. "
                           "Return only JSON with the structure: {\"name\": \"playlist name\", \"songs\": [ {\"title\": \"...\", \"artist\": \"...\"}, ... ] }."
            }
        ]
    )

    content = response.choices[0].message.content
    print("🔎 Raw OpenAI content:", content)

    try:
        start = content.find('{')
        end = content.rfind('}') + 1
        json_str = content[start:end]
        data = json.loads(json_str)

        if isinstance(data, dict) and "songs" in data and "name" in data:
            return data

        return {"name": "Untitled Playlist", "songs": []}
    except Exception as e:
        print("❌ Error parsing OpenAI JSON:", e)
        return {"name": "Untitled Playlist", "songs": []}