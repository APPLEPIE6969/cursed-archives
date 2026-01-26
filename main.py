import os
import random
import requests
import asyncio
import edge_tts
import time
import re
import urllib.parse
import io
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

# --- 1. BRAIN (Groq - GPT-OSS 120B) ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = """
    Generate a 'Cursed/Dark Fantasy' YouTube Short concept.
    1. Pick a character (Pokemon, Disney, SpongeBob, Mario, Shrek).
    2. Write a 1-sentence creepy 'Urban Legend' style fact for the voiceover.
    3. Return JSON with: 'voiceover', 'prompt_cute', 'prompt_dark', 'title', 'description', 'hashtags'.
    
    WRITING RULES:
    - NO 'AI' mentions. Found footage style.
    - Title: Clickbait (e.g. "The Truth about Pikachu").
    - Visuals: "A centered portrait of..."
    """
    
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",
        response_format={"type": "json_object"}
    )
    import json
    return json.loads(completion.choices[0].message.content)

# --- 2. ARTIST (Pollinations - DIRECT API) ---
def generate_image(prompt, filename):
    seed = random.randint(0, 999999)
    
    # Clean the prompt for URL
    clean_prompt = urllib.parse.quote(prompt[:250]) # Limit length to prevent errors
    
    # 1. Try Primary Model (Flux) via DIRECT API
    # Note: 'image.pollinations.ai' is the developer endpoint (less blocking)
    url_primary = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    
    # 2. Backup Model (Turbo) - Lighter, rarely blocks
    url_backup = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&model=turbo&nologo=true"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://google.com"
    }
    
    # Retry Loop
    for attempt in range(3):
        try:
            # Use primary URL for first 2 attempts, then backup
            target_url = url_primary if attempt < 2 else url_backup
            print(f"   🎨 Generating image (Attempt {attempt+1})...")
            
            response = requests.get(target_url, headers=headers, timeout=40)
            
            if response.status_code == 200:
                # Verify it is actually an image
                image_data = io.BytesIO(response.content)
                img = PIL.Image.open(image_data)
                img = img.convert("RGB") # Fix PNG/RGBA issues
                img.save(filename, "JPEG")
                return filename
            else:
                print(f"   ⚠️ Server returned {response.status_code}. Retrying...")
                time.sleep(2)
                
        except Exception as e:
            print(f"   ⚠️ Error: {e}")
            time.sleep(2)
            
    raise Exception("All image generation attempts failed. GitHub IPs might be temporarily blocked.")

# --- 3. ANIMATOR (Local Ghost Fade) ---
def morph_images(img1, img2):
    print("👻 Generating Ghost-Fade Transformation (Local)...")
    
    try:
        # Load images
        clip1 = ImageClip(img1).set_duration(3)
        clip2 = ImageClip(img2).set_duration(3)
        
        # Create a Composite
        video = CompositeVideoClip([
            clip1,
            clip2.set_start(1.5).crossfadein(1.5)
        ]).set_duration(4)
        
        output_filename = f"morph_{int(time.time())}.mp4"
        
        # Write file
        video.write_videofile(
            output_filename, 
            fps=24, 
            codec="libx264", 
            preset="ultrafast", 
            verbose=False, 
            logger=None
        )
        return output_filename
        
    except Exception as e:
        print(f"Animation Error: {e}")
        raise e

# --- 4. VOICE ---
async def make_audio(text, filename):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(filename)

# --- 5. EDITOR ---
def assemble_video(video_path, audio_path, output_filename):
    clip = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    
    # Speed up slightly and boomerang
    clip = clip.fx(vfx.speedx, 1.1)
    clip_reversed = clip.fx(vfx.time_mirror)
    final_clip = concatenate_videoclips([clip, clip_reversed])
    
    # Loop video to match audio length
    final_clip = final_clip.loop(duration=audio.duration + 1)
    final_clip = final_clip.set_audio(audio)
    
    final_clip.write_videofile(output_filename, fps=24, codec='libx264', preset='ultrafast')
    return output_filename

# --- 6. JUDGE (Gemini 3 Flash Preview) ---
def pick_winner(candidates):
    print("👨‍⚖️ Gemini 3 is judging...")
    client = genai.Client(api_key=GEMINI_KEY)
    
    images = []
    for c in candidates:
        images.append(PIL.Image.open(c['dark_image']))
        
    prompt = "Pick the SCARIEST and most REALISTIC image. Reply ONLY with the number (1, 2, or 3)."
    
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

# --- 7. UPLOADER (YouTube) ---
def upload_to_youtube(video_path, title, description, tags):
    print(f"🚀 Uploading: {title}")
    
    creds = Credentials(
        None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET
    )
    
    youtube = build("youtube", "v3", credentials=creds)
    
    body = {
        "snippet": {
            "title": title,
            "description": f"{description}\n\n{tags}",
            "tags": tags.split(','),
            "categoryId": "1"
        },
        "status": {
            "privacyStatus": "public", 
            "selfDeclaredMadeForKids": False
        }
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
            
    print(f"✅ Video ID: {response['id']}")
    return response['id']

# --- NOTIFIER ---
def notify_group(message):
    if TG_TOKEN and TG_CHAT:
        try:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            payload = {'chat_id': TG_CHAT, 'text': message}
            requests.post(url, data=payload)
        except:
            pass

# --- MAIN ---
if __name__ == "__main__":
    candidates = []
    
    # 3 Batches
    for i in range(3):
        try:
            print(f"\n--- Batch {i+1} ---")
            data = get_concept()
            f_cute, f_dark, f_audio, f_vid = f"cute_{i}.jpg", f"dark_{i}.jpg", f"voice_{i}.mp3", f"vid_{i}.mp4"
            
            # Create Assets
            generate_image(data['prompt_cute'], f_cute)
            generate_image(data['prompt_dark'], f_dark)
            asyncio.run(make_audio(data['voiceover'], f_audio))
            
            # Animate
            raw = morph_images(f_cute, f_dark)
            
            # Final Edit
            assemble_video(raw, f_audio, f_vid)
            
            candidates.append({
                "video": f_vid, "dark_image": f_dark,
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
        notify_group(f"💀 New Lore Uploaded!\nTitle: {w['title']}\nLink: https://youtube.com/shorts/{vid_id}")
    else:
        print("All batches failed.")
        notify_group("⚠️ Bot failed to generate video today.")
