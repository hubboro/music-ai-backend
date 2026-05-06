import os
import random
from openai import OpenAI
import json
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_playlist_data(prompt: str):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are a music curator with deep knowledge of songs across all genres and eras. You have impeccable taste and understand how music creates mood and atmosphere. Return structured JSON only."
            },
            {
                "role": "user",
                "content": (
                    f"Create a Spotify playlist for this mood or theme: '{prompt}'\n\n"
                    "Rules:\n"
                    "- Choose 10 songs that genuinely capture the feeling — avoid the most obvious choices\n"
                    "- Mix well-known songs with lesser-known deeper cuts for variety\n"
                    "- Vary genres and eras unless the theme clearly calls for one style\n"
                    "- Use exact artist names and song titles as they appear on Spotify\n"
                    "- Give the playlist a short, poetic name (3–6 words) that evokes the mood, not a literal description\n\n"
                    "Return JSON: {\"name\": \"...\", \"songs\": [{\"title\": \"...\", \"artist\": \"...\"}, ...]}"
                )
            }
        ]
    )

    try:
        data = json.loads(response.choices[0].message.content)
        if isinstance(data, dict) and "songs" in data and "name" in data:
            return data
        return {"name": "Untitled Playlist", "songs": []}
    except Exception as e:
        print("❌ Error parsing OpenAI JSON:", e)
        return {"name": "Untitled Playlist", "songs": []}

def generate_prompt_placeholders():
    try:
        path = os.path.join(os.path.dirname(__file__), "placeholders.json")
        with open(path) as f:
            examples = json.load(f)
        return [random.choice(examples)]
    except Exception as e:
        print("🔥 Error loading placeholders:", str(e))
        return ["a late summer evening, windows open, nowhere to be"]
