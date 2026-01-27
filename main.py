import os
import random
import requests
import asyncio
import edge_tts
import time
import re
import urllib.parse
import io
import base64
import json
import numpy as np
import fal_client
from groq import Groq
import PIL.Image

# --- 🛠️ COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import *
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURATION ---
GROQ_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
FAL_KEY = os.environ.get("FAL_KEY")

# --- 1. BRAIN (Groq) ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = """
    Generate a 'Cursed/Dark Fantasy' YouTube Short script.
    Return JSON with: 'script', 'prompt_1_normal', 'prompt_2_uncanny', 'prompt_3_horror', 'title', 'description', 'hashtags'.
    Character: Pick a popular character (SpongeBob, Shrek, etc.) but make it horrifying.
    """
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile", # Updated model name for stability
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- 2. ARTIST (Pollinations) ---
def generate_image(prompt, filename):
    seed = random.randint(0, 999999)
    clean_prompt = urllib.parse.quote(prompt[:300])
    url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    
    response = requests.get(url, timeout=120)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        return filename
    raise Exception("Image gen failed")

# --- 3. ANIMATOR (Wan 2.1/2.2 via Fal.ai) ---
def animate_wan_segment(image_path, prompt):
    if not FAL_KEY:
        return None

    print(f"⚡ Generating Wan 2.1 Video for: {prompt[:30]}")
    try:
        # Upload local image to Fal to get a URL
        image_url = fal_client.upload_file(image_path)
        
        # Using Wan 2.1 (T2V or I2V)
        # Change to 'fal-ai/wan/v2.1/i2v/14b' if you want 14B quality
        result = fal_client.subscribe(
            "fal-ai/wan/v2.1/i2v/1.3b", 
            arguments={
                "image_url": image_url,
                "prompt": f"extreme horror, character moves towards camera, distorted, found footage, {prompt}",
            },
            with_logs=True,
        )
        
        video_url = result['video']['url']
        video_filename = f"wan_{int(time.time())}.mp4"
        
        with open(video_filename, "wb") as f:
            f.write(requests.get(video_url).content)
            
        return video_filename
    except Exception as e:
        print(f"⚠️ Wan Video Failed: {e}")
        return None

# --- 4. EDITOR ---
def create_story_video(img1, img2, horror_element, audio_path, output_filename):
    audio = AudioFileClip(audio_path)
    d1, d2, d3 = audio.duration * 0.3, audio.duration * 0.3, audio.duration * 0.4
    
    clip1 = ImageClip(img1).set_duration(d1+1).resize(lambda t: 1+0.05*t).set_position('center')
    clip2 = ImageClip(img2).set_duration(d2+1).resize(lambda t: 1+0.08*t).set_position('center').set_start(d1).crossfadein(1.0)
    
    if horror_element.endswith(".mp4"):
        clip3_raw = VideoFileClip(horror_element)
        clip3 = clip3_raw.fx(vfx.loop, duration=d3+1).resize(height=1280)
        if clip3.w > 720: clip3 = clip3.crop(x1=clip3.w/2 - 360, width=720)
        clip3 = clip3.set_start(d1+d2).crossfadein(0.5)
    else:
        clip3 = ImageClip(horror_element).set_duration(d3+1).resize(lambda t: 1+0.2*t).set_position('center').set_start(d1+d2).crossfadein(0.5)

    final = CompositeVideoClip([clip1, clip2, clip3], size=(720, 1280))
    final = final.set_duration(audio.duration).set_audio(audio)
    final.write_videofile(output_filename, fps=24, codec='libx264', preset='ultrafast')
    return output_filename

# --- 5-7. UPLOADER & LOGIC (Kept same as yours but optimized) ---
async def make_audio(text, filename):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(filename)

def upload_to_youtube(video_path, title, description, tags):
    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    youtube = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title, "description": f"{description}\n\n{tags}", "tags": tags.split(','), "categoryId": "1"}, "status": {"privacyStatus": "public"}}
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    res = None
    while res is None:
        _, res = request.next_chunk()
    return res['id']

if __name__ == "__main__":
    try:
        data = get_concept()
        f_norm, f_uncanny, f_horror, f_audio, f_vid = "n.jpg", "u.jpg", "h.jpg", "v.mp3", "final.mp4"
        
        generate_image(data['prompt_1_normal'], f_norm)
        generate_image(data['prompt_2_uncanny'], f_uncanny)
        generate_image(data['prompt_3_horror'], f_horror)
        asyncio.run(make_audio(data['script'], f_audio))
        
        video_clip = animate_wan_segment(f_horror, data['prompt_3_horror'])
        final_path = create_story_video(f_norm, f_uncanny, video_clip or f_horror, f_audio, f_vid)
        
        vid_id = upload_to_youtube(final_path, data['title'], data['description'], data['hashtags'])
        print(f"🚀 Uploaded: https://youtube.com/shorts/{vid_id}")
    except Exception as e:
        print(f"❌ Critical Failure: {e}")
