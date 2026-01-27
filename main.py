import os
import random
import requests
import asyncio
import edge_tts
import time
import re
import urllib.parse
import io
import json
import numpy as np
from gradio_client import Client
from groq import Groq
import PIL.Image

# --- 🛠️ COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import *
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURATION ---
def get_secret(key):
    val = os.environ.get(key)
    return val.strip() if val else None

GROQ_KEY = get_secret("GROQ_API_KEY")
GEMINI_KEY = get_secret("GEMINI_API_KEY") # Note: If you have Google GenAI key
YT_CLIENT_ID = get_secret("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = get_secret("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = get_secret("YOUTUBE_REFRESH_TOKEN")
HF_TOKEN = get_secret("HF_TOKEN") # Optional but helps with rate limits

# --- 1. BRAIN (Groq) ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = "Generate a 'Cursed/Dark Fantasy' YouTube Short script. Return JSON with keys: 'script', 'prompt_1_normal', 'prompt_2_uncanny', 'prompt_3_horror', 'title', 'description', 'hashtags'."
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- 2. ARTIST (Pollinations) ---
def generate_image(prompt, filename):
    seed = random.randint(0, 999999)
    clean_prompt = urllib.parse.quote(prompt[:300])
    url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    res = requests.get(url, timeout=60)
    with open(filename, "wb") as f: f.write(res.content)
    return filename

# --- 3. ANIMATOR (Free Wan 2.1 via Gradio) ---
def animate_wan_free(image_path, prompt):
    print(f"🎬 Attempting Free Video Generation...")
    try:
        # Using a reliable community Space for Wan 2.1
        # If this one fails, you can swap the string for another Wan Space
        client = Client("Wan-Video/Wan2.1-I2V-14B-720P", token=HF_TOKEN)
        
        result = client.predict(
            input_video=None, 
            input_image=image_path,
            prompt=f"Horror style, found footage, {prompt}",
            api_name="/predict"
        )
        
        # Result is a path to a temp .mp4 file
        video_filename = f"wan_free_{int(time.time())}.mp4"
        import shutil
        shutil.copy(result, video_filename)
        return video_filename
    except Exception as e:
        print(f"⚠️ Free Gen Failed: {e}")
        return None

# --- 4. EDITOR & UPLOADER (Simplified) ---
def create_story_video(img1, img2, horror_element, audio_path, output_filename):
    audio = AudioFileClip(audio_path)
    d = audio.duration
    c1 = ImageClip(img1).set_duration(d*0.3 + 1).resize(lambda t: 1+0.05*t).set_position('center')
    c2 = ImageClip(img2).set_duration(d*0.3 + 1).resize(lambda t: 1+0.08*t).set_position('center').set_start(d*0.3).crossfadein(1)
    
    if horror_element.endswith(".mp4"):
        c3 = VideoFileClip(horror_element).fx(vfx.loop, duration=d*0.4 + 1).resize(height=1280).set_start(d*0.6).crossfadein(0.5)
        if c3.w > 720: c3 = c3.crop(x1=c3.w/2 - 360, width=720)
    else:
        c3 = ImageClip(horror_element).set_duration(d*0.4 + 1).resize(lambda t: 1+0.2*t).set_start(d*0.6).crossfadein(0.5)

    final = CompositeVideoClip([c1, c2, c3], size=(720, 1280)).set_duration(d).set_audio(audio)
    final.write_videofile(output_filename, fps=24, codec='libx264', preset='ultrafast')
    return output_filename

async def make_audio(text, filename):
    await edge_tts.Communicate(text, "en-US-ChristopherNeural").save(filename)

def upload_to_youtube(video_path, title, description, tags):
    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    service = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title, "description": f"{description}\n\n{tags}", "tags": tags.split(','), "categoryId": "1"}, "status": {"privacyStatus": "public"}}
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    res = service.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return res['id']

if __name__ == "__main__":
    try:
        data = get_concept()
        f_norm, f_uncanny, f_horror, f_audio, f_vid = "n.jpg", "u.jpg", "h.jpg", "v.mp3", "final.mp4"
        generate_image(data['prompt_1_normal'], f_norm)
        generate_image(data['prompt_2_uncanny'], f_uncanny)
        generate_image(data['prompt_3_horror'], f_horror)
        asyncio.run(make_audio(data['script'], f_audio))
        
        video_clip = animate_wan_free(f_horror, data['prompt_3_horror'])
        final_path = create_story_video(f_norm, f_uncanny, video_clip or f_horror, f_audio, f_vid)
        
        vid_id = upload_to_youtube(final_path, data['title'], data['description'], data['hashtags'])
        print(f"🚀 Success: https://youtube.com/shorts/{vid_id}")
    except Exception as e:
        print(f"❌ Error: {e}")
