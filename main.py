import os
import random
import requests
import asyncio
import edge_tts
import time
import json
import shutil
import urllib.parse
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
YT_CLIENT_ID = get_secret("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = get_secret("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = get_secret("YOUTUBE_REFRESH_TOKEN")
HF_TOKEN = get_secret("HF_TOKEN") 

# --- 1. BRAIN ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = "Generate a 'Cursed/Found Footage' YouTube Short script. Return JSON with: 'script', 'prompt_1_normal', 'prompt_2_uncanny', 'prompt_3_horror', 'title', 'description', 'hashtags'."
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- 2. IMAGE GENERATOR (Free via Pollinations) ---
def generate_image(prompt, filename):
    seed = random.randint(0, 999999)
    clean_prompt = urllib.parse.quote(prompt[:300])
    url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    res = requests.get(url, timeout=60)
    with open(filename, "wb") as f: f.write(res.content)
    return filename

# --- 3. VIDEO GENERATOR (Free with Smart Retry) ---
def animate_wan_with_retry(horror_prompt, max_retries=5):
    print(f"🎬 Connecting to Wan2.1 Text-to-Video...")
    for attempt in range(max_retries):
        try:
            client = Client("Wan-AI/Wan2.1", token=HF_TOKEN)
            # The official Wan space prediction
            result = client.predict(
                prompt=f"Found footage horror, grainy VHS, dark, {horror_prompt}",
                api_name="/predict"
            )
            video_filename = f"wan_climax_{int(time.time())}.mp4"
            shutil.copy(result, video_filename)
            print("✅ Video generated successfully!")
            return video_filename
        except Exception as e:
            wait_time = (attempt + 1) * 30  # Wait 30s, 60s, 90s...
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("❌ All retries failed. Falling back to static image.")
                return None

# --- 4. EDITOR ---
def create_story_video(img1, img2, video_clip, audio_path, output_filename):
    audio = AudioFileClip(audio_path)
    d = audio.duration
    
    c1 = ImageClip(img1).set_duration(d*0.3 + 1).resize(lambda t: 1+0.05*t).set_position('center')
    c2 = ImageClip(img2).set_duration(d*0.3 + 1).resize(lambda t: 1+0.08*t).set_position('center').set_start(d*0.3).crossfadein(1)
    
    if video_clip:
        c3 = VideoFileClip(video_clip).fx(vfx.loop, duration=d*0.4 + 1).resize(height=1280).set_start(d*0.6).crossfadein(0.5)
        if c3.w > 720: c3 = c3.crop(x1=c3.w/2 - 360, width=720)
    else:
        # Static fallback if video fails
        c3 = ImageClip(img2).set_duration(d*0.4 + 1).resize(lambda t: 1+0.15*t).set_start(d*0.6).crossfadein(0.5)

    final = CompositeVideoClip([c1, c2, c3], size=(720, 1280)).set_duration(d).set_audio(audio)
    final.write_videofile(output_filename, fps=24, codec='libx264', preset='ultrafast', logger=None)
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
        f_norm, f_uncanny, f_audio, f_vid = "n.jpg", "u.jpg", "v.mp3", "final.mp4"
        
        generate_image(data['prompt_1_normal'], f_norm)
        generate_image(data['prompt_2_uncanny'], f_uncanny)
        asyncio.run(make_audio(data['script'], f_audio))
        
        # Try to generate the free video clip
        video_clip = animate_wan_with_retry(data['prompt_3_horror'])
        
        final_path = create_story_video(f_norm, f_uncanny, video_clip, f_audio, f_vid)
        
        vid_id = upload_to_youtube(final_path, data['title'], data['description'], data['hashtags'])
        print(f"🚀 Success: https://youtube.com/shorts/{vid_id}")
    except Exception as e:
        print(f"❌ Error: {e}")
