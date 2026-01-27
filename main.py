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
    return val.strip() if val else ""

GROQ_KEY = get_secret("GROQ_API_KEY")
YT_CLIENT_ID = get_secret("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = get_secret("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = get_secret("YOUTUBE_REFRESH_TOKEN")
HF_TOKEN = get_secret("HF_TOKEN") 

# --- 1. BRAIN ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = "Generate a 'Cursed/Found Footage' YouTube Short script. Return JSON with: 'script', 'prompt_1_normal', 'prompt_2_uncanny', 'prompt_3_horror', 'title', 'description', 'hashtags' (provide as a single string separated by spaces)."
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- 2. IMAGE GENERATOR (Fixed Pollinations URL) ---
def generate_image(prompt, filename, max_retries=3):
    seed = random.randint(0, 999999)
    # Switched back to the most stable direct endpoint
    clean_prompt = urllib.parse.quote(prompt[:250])
    url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&nologo=true"
    
    for attempt in range(max_retries):
        try:
            print(f"🎨 Generating Image: {filename} (Attempt {attempt+1})...")
            res = requests.get(url, timeout=60)
            res.raise_for_status()
            with open(filename, "wb") as f: 
                f.write(res.content)
            return filename
        except Exception as e:
            print(f"⚠️ Image Error: {e}")
            time.sleep(5)
    
    # Fallback: Dark image so the video doesn't crash
    PIL.Image.new('RGB', (720, 1280), (20, 20, 20)).save(filename)
    return filename

# --- 3. VIDEO GENERATOR (Positional API fix) ---
def animate_wan_with_retry(horror_prompt, max_retries=2):
    print(f"🎬 Connecting to Wan-AI/Wan2.1...")
    for attempt in range(max_retries):
        try:
            client = Client("Wan-AI/Wan2.1", token=HF_TOKEN)
            # Using positional arguments instead of api_name to avoid mapping errors
            result = client.predict(
                f"found footage horror, grainy vhs, {horror_prompt}", # prompt
                "bright, clean, 4k, cheerful", # negative_prompt
                5.0, # guide_scale
                30,  # num_inference_steps
            )
            video_filename = "wan_climax.mp4"
            shutil.copy(result, video_filename)
            return video_filename
        except Exception as e:
            print(f"⚠️ Video Attempt {attempt+1} failed: {e}")
            time.sleep(30)
    return None

# --- 4. EDITOR (Refined Subclipping) ---
def create_story_video(img1, img2, video_clip, audio_path, output_filename):
    audio = AudioFileClip(audio_path)
    d = audio.duration
    
    c1 = ImageClip(img1).set_duration(d*0.3 + 1).resize(lambda t: 1+0.04*t).set_position('center')
    c2 = ImageClip(img2).set_duration(d*0.3 + 1).resize(lambda t: 1+0.06*t).set_position('center').set_start(d*0.3).crossfadein(1)
    
    if video_clip and os.path.exists(video_clip):
        c3 = VideoFileClip(video_clip).resize(height=1280).set_start(d*0.6).crossfadein(0.5)
        # Ensure the clip doesn't exceed the audio length
        if c3.duration > (d * 0.4):
            c3 = c3.subclip(0, d * 0.4 + 1)
        if c3.w > 720: 
            c3 = c3.crop(x1=c3.w/2 - 360, width=720)
    else:
        c3 = ImageClip(img2).set_duration(d*0.4 + 1).resize(lambda t: 1+0.15*t).set_start(d*0.6).crossfadein(0.5)

    final = CompositeVideoClip([c1, c2, c3], size=(720, 1280)).set_duration(d).set_audio(audio)
    final.write_videofile(output_filename, fps=24, codec='libx264', audio_codec='aac')
    return output_filename

async def make_audio(text, filename):
    await edge_tts.Communicate(text, "en-US-ChristopherNeural").save(filename)

# --- 5. UPLOADER (Fixed Type Check) ---
def upload_to_youtube(video_path, title, description, tags):
    # Fix for 'list' object has no attribute 'split'
    if isinstance(tags, list):
        tag_list = tags
        tag_str = " ".join(tags)
    else:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        tag_str = tags

    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    service = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title[:100], 
            "description": f"{description}\n\n{tag_str}", 
            "tags": tag_list[:20], 
            "categoryId": "1"
        }, 
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    res = service.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return res['id']

if __name__ == "__main__":
    try:
        data = get_concept()
        print(f"📝 Concept: {data['title']}")
        
        generate_image(data['prompt_1_normal'], "n.jpg")
        generate_image(data['prompt_2_uncanny'], "u.jpg")
        asyncio.run(make_audio(data['script'], "v.mp3"))
        
        video_clip = animate_wan_with_retry(data['prompt_3_horror'])
        
        final_path = create_story_video("n.jpg", "u.jpg", video_clip, "v.mp3", "final.mp4")
        
        vid_id = upload_to_youtube(final_path, data['title'], data['description'], data['hashtags'])
        print(f"🚀 Success! https://youtube.com/shorts/{vid_id}")
    except Exception as e:
        print(f"❌ Critical Failure: {e}")
