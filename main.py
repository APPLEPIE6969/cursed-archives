import os
import random
import requests
import asyncio
import edge_tts
import time
import re
import urllib.parse
import io
import numpy as np
from groq import Groq
from moviepy.editor import *

# NEW Google SDK
from google import genai
import PIL.Image

# Google & YouTube Imports
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

# --- 1. BRAIN (Groq - Storyteller Mode) ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = """
    Generate a 'Cursed/Dark Fantasy' YouTube Short script (approx 45 seconds).
    1. Pick a character (Pokemon, Disney, SpongeBob, Mario, Shrek).
    2. Write a 3-part 'Found Footage' style narrative:
       - Part 1: The innocent discovery.
       - Part 2: The realization that something is wrong.
       - Part 3: The Jumpscare / Monster reveal.
    3. Return JSON with keys:
       'script': (The full voiceover text, approx 80 words),
       'prompt_1_normal': (Visual: "A centered portrait of [Character], innocent, studio lighting, 8k"),
       'prompt_2_uncanny': (Visual: "A centered portrait of [Character], slightly distorted, shadowy, uncanny valley, 8k"),
       'prompt_3_horror': (Visual: "A centered portrait of [Character], horrifying monster, gore, teeth, hyper-realistic, 8k"),
       'title': (Clickbait title),
       'description': (SEO description),
       'hashtags': (Tags string)
    """
    
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",
        response_format={"type": "json_object"}
    )
    import json
    return json.loads(completion.choices[0].message.content)

# --- 2. ARTIST (Pollinations - Direct API) ---
def generate_image(prompt, filename):
    seed = random.randint(0, 999999)
    clean_prompt = urllib.parse.quote(prompt[:300])
    
    # URL 1: Flux (Best Quality)
    url_primary = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    # URL 2: Turbo (Backup)
    url_backup = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=turbo&nologo=true"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    for attempt in range(3):
        try:
            target_url = url_primary if attempt < 2 else url_backup
            print(f"   🎨 Gen Image ({filename}) - Attempt {attempt+1}...")
            
            response = requests.get(target_url, headers=headers, timeout=40)
            
            if response.status_code == 200:
                image_data = io.BytesIO(response.content)
                img = PIL.Image.open(image_data).convert("RGB")
                img.save(filename, "JPEG")
                return filename
            time.sleep(2)
        except Exception as e:
            print(f"   ⚠️ Error: {e}")
            time.sleep(2)
            
    raise Exception(f"Failed to generate {filename}")

# --- 3. EDITOR (Cinematic Camera Animation) ---
def create_story_video(img1, img2, img3, audio_path, output_filename):
    print("🎬 Animating Cinematic Video...")
    
    audio = AudioFileClip(audio_path)
    total_duration = audio.duration
    
    # Split time: 30% Normal, 30% Uncanny, 40% Horror
    d1 = total_duration * 0.3
    d2 = total_duration * 0.3
    d3 = total_duration * 0.4
    
    # --- HELPER: Zoom Function ---
    # zooms in from scale 1.0 to 1.X over time t
    def zoom_in(t, speed=0.04):
        return 1 + speed * t

    # --- CLIP 1: Normal (Slow Zoom In) ---
    clip1 = (ImageClip(img1)
             .set_duration(d1 + 1)
             .resize(lambda t: zoom_in(t, 0.05)) # Smooth zoom
             .set_position(('center', 'center')))
    
    # --- CLIP 2: Uncanny (Slow Zoom + Drift) ---
    clip2 = (ImageClip(img2)
             .set_duration(d2 + 1)
             .resize(lambda t: zoom_in(t, 0.08)) # Faster zoom
             .set_position(('center', 'center'))
             .set_start(d1)
             .crossfadein(1.0))
             
    # --- CLIP 3: Horror (Aggressive Zoom + Shake) ---
    # We add a "shake" by calculating random position offsets
    def shake(t):
        if t < 0.5: return ('center', 'center') # Still for first 0.5s
        # Random jitter
        x_jitter = np.random.randint(-5, 5)
        y_jitter = np.random.randint(-5, 5)
        return (360 + x_jitter - 360, 640 + y_jitter - 640) # Centered + jitter

    clip3 = (ImageClip(img3)
             .set_duration(d3 + 1)
             .resize(lambda t: zoom_in(t, 0.2)) # Extreme zoom
             .set_position('center') # Keep centered mostly
             .set_start(d1 + d2)
             .crossfadein(0.5))
             
    # Combine
    final_video = CompositeVideoClip([clip1, clip2, clip3], size=(720, 1280))
    final_video = final_video.set_duration(total_duration).set_audio(audio)
    
    final_video.write_videofile(
        output_filename, 
        fps=24, 
        codec='libx264', 
        preset='ultrafast',
        verbose=False, 
        logger=None
    )
    return output_filename

# --- 4. VOICE ---
async def make_audio(text, filename):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(filename)

# --- 5. JUDGE (Gemini 3) ---
def pick_winner(candidates):
    print("👨‍⚖️ Gemini 3 is reviewing the footage...")
    client = genai.Client(api_key=GEMINI_KEY)
    
    images = []
    for c in candidates:
        images.append(PIL.Image.open(c['img_horror']))
        
    prompt = "Pick the image that looks like the most realistic and terrifying found footage monster. Reply ONLY with number 1, 2, or 3."
    
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=[prompt, *images]
        )
        match = re.search(r'\d+', response.text)
        return int(match.group()) - 1 if match else 0
    except Exception as e:
        print(f"Judge Error: {e}. Defaulting to #1")
        return 0

# --- 6. UPLOADER (YouTube) ---
def upload_to_youtube(video_path, title, description, tags):
    print(f"🚀 Uploading: {title}")
    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    youtube = build("youtube", "v3", credentials=creds)
    
    body = {
        "snippet": {
            "title": title,
            "description": f"{description}\n\n{tags}",
            "tags": tags.split(','),
            "categoryId": "1"
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status: print(f"Uploaded {int(status.progress() * 100)}%")
    
    print(f"✅ Video ID: {response['id']}")
    return response['id']

# --- NOTIFIER ---
def notify_group(message):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={'chat_id': TG_CHAT, 'text': message})
        except: pass

# --- MAIN ---
if __name__ == "__main__":
    candidates = []
    
    # 3 Batches
    for i in range(3):
        try:
            print(f"\n--- Batch {i+1} ---")
            # 1. Get Story
            data = get_concept()
            
            # 2. Define Filenames
            f_norm = f"batch{i}_normal.jpg"
            f_uncanny = f"batch{i}_uncanny.jpg"
            f_horror = f"batch{i}_horror.jpg"
            f_audio = f"batch{i}_voice.mp3"
            f_vid = f"batch{i}_final.mp4"
            
            # 3. Create Assets
            generate_image(data['prompt_1_normal'], f_norm)
            generate_image(data['prompt_2_uncanny'], f_uncanny)
            generate_image(data['prompt_3_horror'], f_horror)
            asyncio.run(make_audio(data['script'], f_audio))
            
            # 4. Edit Video (With Animation)
            create_story_video(f_norm, f_uncanny, f_horror, f_audio, f_vid)
            
            candidates.append({
                "video": f_vid, "img_horror": f_horror,
                "title": data['title'], "desc": data['description'], "tags": data['hashtags']
            })
            print("✅ Batch Success")
        except Exception as e:
            print(f"❌ Batch Failed: {e}")
            pass
        time.sleep(5)

    if candidates:
        winner_idx = pick_winner(candidates)
        w = candidates[winner_idx]
        print(f"🏆 Selected Batch {winner_idx+1}")
        vid_id = upload_to_youtube(w['video'], w['title'], w['desc'], w['tags'])
        notify_group(f"💀 New Story Uploaded!\nTitle: {w['title']}\nLink: https://youtube.com/shorts/{vid_id}")
    else:
        print("All batches failed.")
        notify_group("⚠️ Bot failed to generate video today.")
