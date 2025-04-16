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
    
def generate_prompt_placeholders():
    system_prompt = "You are a creative assistant helping users write inspiring playlist prompts. Your job is to come up with fun, vivid, and inspiring prompts that help users describe the vibe or theme of a playlist they want to generate."
    user_prompt = (
        "Give me a unique and descriptive playlist prompt examples that help inspire users. "
        "It should describe a different theme, mood, or idea, music genre or artist. It should not be generic. "
        "It should be one sentence, no longer than 12 words."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano-2025-04-14",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9
        )

        content = response.choices[0].message.content.strip()
        placeholders = [line.strip("-• ") for line in content.split("\n") if line.strip()]
        return placeholders[:1]  # Only return first one non-empty line
    except Exception as e:
        print("🔥 Error fetching placeholders from OpenAI:", str(e))
        return ["A sunrise rave on Mars", "Lo-fi jazz in a post-apocalyptic café"]
