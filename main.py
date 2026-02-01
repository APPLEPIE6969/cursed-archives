import os
import random
import requests
import asyncio
import time
import re
import urllib.parse
import io
import base64
import PIL.Image
import numpy as np
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# --- CRITICAL FIX FOR MOVIEPY ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- CONFIGURATION ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")

gemini_client = genai.Client(api_key=GEMINI_KEY)

# --- 1. BRAIN (Gemini 3 Flash Preview) ---
def get_horror_concept():
    print("🧠 Gemini 3 is picking characters and creating prompts...")
    character_list = """
    Snow White, Cinderella, Ariel, Belle, Jasmine, Elsa, Anna, Moana, Rapunzel, Tiana, Mulan, 
    Mickey Mouse, Donald Duck, Goofy, Winnie the Pooh, Simba, Nemo, Dory, Mike, Sulley, 
    WALL-E, EVE, Buzz Lightyear, Woody, Hiro, Baymax, Maleficent, Ursula, Scar, Jafar, 
    Hans, Dr. Facilier, Cruella de Vil, Queen of Hearts, Gaston, Mario, Luigi, Peach, 
    Bowser, Yoshi, Wario, Pikachu, Ash Ketchum, Link, Zelda, Samus, Kirby, Superman, 
    Batman, Joker, Spider-Man, Iron Man, Darth Vader, Yoda, SpongeBob, Homer Simpson.
    """
    
    prompt = f"""
    Step 1: Choose 4 random characters from this list: {character_list}.
    Step 2: For each character, create a hyper-detailed image generation prompt in this style: 
    "A horrifying, gore-filled horror version of [Character], realistic textures, blood-stained, dark atmosphere, 8k found footage style."
    Step 3: Write a cohesive horror script for a YouTube Short that connects all 4 characters. 
    Step 4: Provide a title, description, and hashtags.
    Return ONLY JSON with keys: 'characters' (list of 4 strings), 'image_prompts' (list of 4 prompts), 'script', 'title', 'desc', 'tags'.
    """

    response = gemini_client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    import json
    return json.loads(response.text)

# --- 2. IMAGE GENERATOR (Pollinations) ---
def generate_horror_image(prompt, filename):
    print(f"🎨 Generating Image: {filename}")
    seed = random.randint(0, 999999)
    clean_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                with open(filename, "wb") as f:
                    f.write(response.content)
                return filename
        except:
            time.sleep(5)
    return None

# --- 3. ANIMATOR (FramePack-F1 via Gradio) ---
def animate_with_framepack(image_path, index):
    print(f"🎬 Animating Image {index} with FramePack...")
    try:
        # Gemini generates a specific motion prompt for the video
        motion_prompt = f"The horror character moves slightly, eyes glowing, breathing heavily, scary motion."
        
        client = Client("linoyts/FramePack-F1")
        result = client.predict(
            image=handle_file(image_path),
            prompt=motion_prompt,
            api_name="/predict"
        )
        # Result is usually a path to an mp4
        output_filename = f"vid_{index}.mp4"
        shutil.copy(result, output_filename)
        return output_filename
    except Exception as e:
        print(f"⚠️ FramePack failed: {e}. Using static pan fallback.")
        return None

# --- 4. VOICE (Chatterbox via Gradio) ---
def generate_voiceover(text):
    print("🎙️ Generating Voiceover with Chatterbox...")
    try:
        client = Client("OLAVAUD/Chatterbox_Unlimited")
        result = client.predict(
            text=text,
            voice="Baritone", # Example param, check Space for actual voice names
            api_name="/predict"
        )
        output_audio = "voiceover.wav"
        shutil.copy(result, output_audio)
        return output_audio
    except:
        print("⚠️ Chatterbox failed. Falling back to simple file.")
        return None

# --- 5. YOUTUBE UPLOADER ---
def upload_video(path, title, desc, tags):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", 
                        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    youtube = build("youtube", "v3", credentials=creds)
    
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": f"{desc}\n{tags}", "categoryId": "24"},
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(path, chunksize=-1, resumable=True)
    )
    response = request.execute()
    print(f"✅ Uploaded! ID: {response['id']}")

# --- MAIN EXECUTION ---
import shutil

async def main():
    # 1. Get Plan
    data = get_horror_concept()
    
    # 2. Generate 4 Images & Animate them
    video_clips = []
    for i in range(4):
        img_file = f"img_{i}.jpg"
        generate_horror_image(data['image_prompts'][i], img_file)
        
        vid_file = animate_with_framepack(img_file, i)
        if vid_file:
            video_clips.append(VideoFileClip(vid_file))
        else:
            # Fallback: Create a 3-second zooming clip from the static image
            clip = ImageClip(img_file).set_duration(3).resize(lambda t: 1 + 0.04*t).set_fps(24)
            video_clips.append(clip)

    # 3. Final Assembly
    final_video = concatenate_videoclips(video_clips, method="compose")
    
    # 4. Generate Voice matching video length
    audio_file = generate_voiceover(data['script'])
    if audio_file:
        audio_clip = AudioFileClip(audio_file)
        # If audio is longer/shorter, we adjust video speed
        final_video = final_video.set_audio(audio_clip).set_duration(audio_clip.duration)
    
    final_video.write_videofile("output_short.mp4", codec="libx264", audio_codec="aac", fps=24)
    
    # 5. Upload
    upload_video("output_short.mp4", data['title'], data['desc'], data['tags'])

if __name__ == "__main__":
    asyncio.run(main())
