import os
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
    system_prompt = "You are a creative assistant helping users write inspiring playlist prompts. Your job is to come up with fun, vivid, and inspiring prompts that help users describe the vibe or theme of a playlist they want to generate."
    user_prompt = (
        "Give me a unique and descriptive playlist prompt example that helps inspire users. "
        "It should describe a different theme, mood, or idea, music genre or artist. It should not be generic. "
        "It should be one sentence, no longer than 12 words."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9
        )

        content = response.choices[0].message.content.strip()
        result = content.strip("-• ").strip()
        return [result] if result else ["A sunrise rave on Mars"]
    except Exception as e:
        print("🔥 Error fetching placeholders from OpenAI:", str(e))
        return ["A sunrise rave on Mars", "Lo-fi jazz in a post-apocalyptic café"]
