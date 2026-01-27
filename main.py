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

# --- 1. BRAIN (Groq) ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = "Generate a 'Cursed/Found Footage' YouTube Short script. Return JSON with: 'script', 'prompt_1_normal', 'prompt_2_uncanny', 'prompt_3_horror', 'title', 'description', 'hashtags'."
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- 2. IMAGE GENERATOR (Pollinations) ---
def generate_image(prompt, filename, max_retries=3):
    seed = random.randint(0, 999999)
    # Using the optimized 2026 endpoint
    clean_prompt = urllib.parse.quote(prompt[:300])
    url = f"https://gen.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    
    for attempt in range(max_retries):
        try:
            print(f"🎨 Generating Image: {filename} (Attempt {attempt+1})...")
            res = requests.get(url, timeout=120)
            res.raise_for_status()
            with open(filename, "wb") as f: 
                f.write(res.content)
            return filename
        except Exception as e:
            print(f"⚠️ Image generation error: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                PIL.Image.new('RGB', (720, 1280), (30, 30, 30)).save(filename)
                return filename

# --- 3. VIDEO GENERATOR (Wan 2.1 via Gradio Client) ---
def animate_wan_with_retry(horror_prompt, max_retries=3):
    print(f"🎬 Connecting to Wan-AI/Wan2.1 Space...")
    for attempt in range(max_retries):
        try:
            client = Client("Wan-AI/Wan2.1", token=HF_TOKEN)
            # Official API signature for Wan 2.1 Text-to-Video
            result = client.predict(
                prompt=f"found footage horror, grainy VHS, unstable camera, {horror_prompt}",
                negative_prompt="bright, cheerful, clean, high quality, 4k",
                guide_scale=5.0,
                num_inference_steps=30,
                api_name="/predict"
            )
            
            video_filename = "wan_climax.mp4"
            shutil.copy(result, video_filename)
            print("✅ Video generated successfully via Wan 2.1!")
            return video_filename
        except Exception as e:
            print(f"⚠️ Video Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                print("⏳ Space busy or queue full. Waiting 60s...")
                time.sleep(60)
            else:
                return None

# --- 4. AUDIO GENERATOR (Edge-TTS) ---
async def make_audio(text, filename):
    print(f"🎙️ Generating Voiceover...")
    await edge_tts.Communicate(text, "en-US-ChristopherNeural").save(filename)

# --- 5. EDITOR (MoviePy) ---
def create_story_video(img1, img2, video_clip, audio_path, output_filename):
    print("🎬 Assembling Final Video...")
    audio = AudioFileClip(audio_path)
    d = audio.duration
    
    # Clips timings: 30% Normal, 30% Uncanny, 40% Horror Climax
    c1 = ImageClip(img1).set_duration(d*0.3 + 1).resize(lambda t: 1+0.05*t).set_position('center')
    c2 = ImageClip(img2).set_duration(d*0.3 + 1).resize(lambda t: 1+0.08*t).set_position('center').set_start(d*0.3).crossfadein(1)
    
    if video_clip and os.path.exists(video_clip):
        c3 = VideoFileClip(video_clip).fx(vfx.loop, duration=d*0.4 + 1).resize(height=1280).set_start(d*0.6).crossfadein(0.5)
        # Vertical Crop
        if c3.w > 720: 
            c3 = c3.crop(x1=c3.w/2 - 360, width=720)
    else:
        # Fallback to shaking uncanny image if video fails
        c3 = ImageClip(img2).set_duration(d*0.4 + 1).resize(lambda t: 1+0.2*t).set_start(d*0.6).crossfadein(0.5)

    final = CompositeVideoClip([c1, c2, c3], size=(720, 1280)).set_duration(d).set_audio(audio)
    final.write_videofile(output_filename, fps=24, codec='libx264', preset='ultrafast', logger=None)
    return output_filename

# --- 6. UPLOADER (YouTube) ---
def upload_to_youtube(video_path, title, description, tags):
    print("🚀 Uploading to YouTube...")
    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    service = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title, 
            "description": f"{description}\n\n{tags}", 
            "tags": tags.split(','), 
            "categoryId": "1"
        }, 
        "status": {"privacyStatus": "public"}
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    res = service.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return res['id']

# --- 7. CLEANUP ---
def cleanup(files):
    for f in files:
        if os.path.exists(f):
            os.remove(f)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    temp_files = ["n.jpg", "u.jpg", "v.mp3", "wan_climax.mp4", "final_video.mp4"]
    try:
        data = get_concept()
        print(f"📝 Story: {data['title']}")
        
        generate_image(data['prompt_1_normal'], "n.jpg")
        generate_image(data['prompt_2_uncanny'], "u.jpg")
        asyncio.run(make_audio(data['script'], "v.mp3"))
        
        video_clip = animate_wan_with_retry(data['prompt_3_horror'])
        
        final_path = create_story_video("n.jpg", "u.jpg", video_clip, "v.mp3", "final_video.mp4")
        
        vid_id = upload_to_youtube(final_path, data['title'], data['description'], data['hashtags'])
        print(f"🔥 Successfully posted: https://youtube.com/shorts/{vid_id}")
        
    except Exception as e:
        print(f"❌ Automation Failed: {e}")
    finally:
        # Cleanup small files to keep the repo clean, but keep the final video log
        cleanup(["n.jpg", "u.jpg", "v.mp3", "wan_climax.mp4"])
