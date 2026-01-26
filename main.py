import os
import random
import requests
import asyncio
import edge_tts
import time
import re
import google.generativeai as genai
from groq import Groq
from gradio_client import Client
from moviepy.editor import *

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

genai.configure(api_key=GEMINI_KEY)

# --- 1. BRAIN (Groq) ---
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = """
    Generate a 'Cursed/Dark Fantasy' YouTube Short concept.
    1. Pick a character (Pokemon, Disney, SpongeBob, Mario, Shrek).
    2. Write a 1-sentence creepy 'Urban Legend' style fact for the voiceover.
    3. Return JSON with: 'voiceover', 'prompt_cute', 'prompt_dark', 'title', 'description', 'hashtags'.
    
    WRITING RULES (STRICT):
    - DO NOT mention 'AI', 'Generated', or 'Computer' in the Title, Description, or Voiceover.
    - Write as if this is found footage or a cursed discovery.
    - Title Example: "What they found inside Pikachu..." or "The SpongeBob Incident (1999)"
    - Description: "Recovered footage from the lost archive. Viewer discretion advised."
    
    VISUAL RULES:
    - prompt_cute: "A centered portrait of [Character], innocent, studio lighting"
    - prompt_dark: "A centered portrait of [Character], horrifying, 8k, hyper-realistic, dark fantasy, monster"
    """
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3-8b-8192",
        response_format={"type": "json_object"}
    )
    import json
    return json.loads(completion.choices[0].message.content)

# --- 2. ARTIST (Pollinations) ---
def generate_image(prompt, filename):
    seed = random.randint(0, 999999)
    url = f"https://pollinations.ai/p/{prompt.replace(' ', '%20')}?width=720&height=1280&seed={seed}&model=flux"
    response = requests.get(url)
    with open(filename, "wb") as f:
        f.write(response.content)
    return filename

# --- 3. ANIMATOR (FILM) ---
def morph_images(img1, img2):
    try:
        client = Client("jbilcke-hf/film-interpolation")
    except:
        client = Client("google/frame-interpolation")
    return client.predict(img1, img2, 2, api_name="/predict")

# --- 4. VOICE ---
async def make_audio(text, filename):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(filename)

# --- 5. EDITOR ---
def assemble_video(video_path, audio_path, output_filename):
    clip = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    clip = clip.fx(vfx.speedx, 0.7).fx(vfx.time_mirror)
    final_clip = concatenate_videoclips([clip, clip]) # Double loop
    final_clip = final_clip.loop(duration=audio.duration + 1)
    final_clip = final_clip.set_audio(audio)
    final_clip.write_videofile(output_filename, fps=24, codec='libx264', preset='ultrafast')
    return output_filename

# --- 6. JUDGE (Gemini 3 Preview) ---
def pick_winner(candidates):
    print("👨‍⚖️ Gemini 3 Preview is judging...")
    uploaded_files = [genai.upload_file(c['dark_image']) for c in candidates]
    
    # Force Gemini 3 Preview
    model_name = "gemini-3-flash-preview"
    try:
        model = genai.GenerativeModel(model_name)
    except:
        print(f"Fallback: Could not load {model_name}, using 1.5")
        model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = "Pick the SCARIEST and most REALISTIC image. Reply ONLY with the number (1, 2, or 3)."
    
    try:
        response = model.generate_content([prompt, *uploaded_files])
        match = re.search(r'\d+', response.text)
        return int(match.group()) - 1 if match else 0
    except:
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
            "categoryId": "1" # Film & Animation
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

# --- NOTIFIER (Telegram Group) ---
def notify_group(message):
    if TG_TOKEN and TG_CHAT:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {'chat_id': TG_CHAT, 'text': message}
        requests.post(url, data=payload)

# --- MAIN ---
if __name__ == "__main__":
    candidates = []
    
    # 3 Batches
    for i in range(3):
        try:
            print(f"--- Batch {i+1} ---")
            data = get_concept()
            f_cute, f_dark, f_audio, f_vid = f"cute_{i}.jpg", f"dark_{i}.jpg", f"voice_{i}.mp3", f"vid_{i}.mp4"
            
            generate_image(data['prompt_cute'], f_cute)
            generate_image(data['prompt_dark'], f_dark)
            asyncio.run(make_audio(data['voiceover'], f_audio))
            
            raw = morph_images(f_cute, f_dark)
            assemble_video(raw, f_audio, f_vid)
            
            candidates.append({
                "video": f_vid, "dark_image": f_dark,
                "title": data['title'], "desc": data['description'], "tags": data['hashtags']
            })
        except Exception as e:
            print(f"Batch Error: {e}")
            pass
        time.sleep(5)

    if candidates:
        # Pick Winner
        winner_idx = pick_winner(candidates)
        w = candidates[winner_idx]
        print(f"🏆 Selected Batch {winner_idx+1}")
        
        # Upload
        vid_id = upload_to_youtube(w['video'], w['title'], w['desc'], w['tags'])
        
        # Notify Group Chat
        notify_group(f"💀 New Lore Uploaded!\nTitle: {w['title']}\nLink: https://youtube.com/shorts/{vid_id}")
    else:
        print("Generation failed.")
        notify_group("⚠️ Bot failed to generate video today.")
