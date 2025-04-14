import os
from openai import OpenAI
import json
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_song_list_from_prompt(prompt: str):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant who only returns structured data."},
            {"role": "user", "content": f"Give me a list of 10 songs about '{prompt}' as a JSON array. Each item should be an object with 'title' and 'artist'."}
        ]
    )

    content = response.choices[0].message.content
    print("🔎 Raw OpenAI content:", content)

    try:
        # Try to extract JSON (OpenAI sometimes includes markdown or explanation)
        start = content.find('[')
        end = content.rfind(']') + 1
        json_str = content[start:end]
        # new starts
        data = json.loads(json_str)

        # If it's a dict with 'songs', return that
        if isinstance(data, dict) and "songs" in data:
            return data["songs"]

        # If it's already a list, return as-is
        if isinstance(data, list):
            return data

        return []
        # new ends
        # return json.loads(json_str).get("songs", [])
        # return json.loads(json_str)
    except Exception as e:
        print("❌ Error parsing OpenAI JSON:", e)
        return []