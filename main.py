import os, random, requests, asyncio, time, urllib.parse, shutil, re, json
import PIL.Image
import numpy as np
import edge_tts
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# Google YouTube Imports
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- MOVIEPY COMPATIBILITY ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- CONFIG ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")

client_gemini = genai.Client(api_key=GEMINI_KEY)

# --- 1. VOICE ENGINE (With Fallback) ---
async def generate_voice_with_fallback(text, lang_code="en", filename="voice.mp3"):
    clean_text = re.sub(r'\[.*?\]', '', text).strip()
    
    # PRIMARY: Chatterbox
    print(f"🎙️ PRIMARY: Attempting Chatterbox...")
    try:
        client = Client("ResembleAI/Chatterbox-Multilingual-TTS")
        result = client.predict(clean_text, lang_code, 0.5, 0.8, fn_index=0)
        if result and os.path.exists(result):
            shutil.copy(result, filename)
            return os.path.abspath(filename)
    except Exception as e:
        print(f"⚠️ Chatterbox Failed: {e}")

    # SECONDARY: Edge-TTS
    print(f"🎙️ SECONDARY: Attempting Edge-TTS...")
    try:
        voice = "en-US-ChristopherNeural" 
        communicate = edge_tts.Communicate(clean_text, voice, rate="+0%", pitch="-10Hz")
        await communicate.save(filename)
        return os.path.abspath(filename)
    except Exception as e:
        print(f"❌ Voice Failed: {e}")
        return None

# --- 2. IMAGE & ANIMATION ---
def generate_horror_image(prompt, filename):
    try:
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=720&height=1280&model=flux"
        res = requests.get(url, timeout=30)
        with open(filename, "wb") as f: f.write(res.content)
        return os.path.abspath(filename)
    except: return None

def animate_horror(image_path, index):
    try:
        client = Client("linoyts/FramePack-F1")
        result = client.predict(handle_file(image_path), "horror movement", fn_index=0)
        out = f"vid_{index}.mp4"
        shutil.copy(result, out)
        return os.path.abspath(out)
    except: return None

# --- 3. YOUTUBE UPLOADER ---
def upload_to_youtube(video_path, title, description, tags):
    print(f"🚀 Uploading to YouTube: {title}")
    try:
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
                "categoryId": "24" # Entertainment
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
    except Exception as e:
        print(f"❌ YouTube Upload Failed: {e}")
        return None

# --- 4. MAIN PIPELINE ---
async def main():
    # Prompt Gemini for Content
    prompt_text = (
        "Pick 2 iconic characters. Write a 20-word scary found footage script. No brackets []. "
        "Return JSON: {'lang': 'en', 'script': '...', 'prompts': ['...', '...'], "
        "'title': 'Scary Title', 'desc': 'Scary Description', 'tags': '#horror,#short'}"
    )
    
    try:
        response = client_gemini.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt_text,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
    except:
        data = {
            "lang": "en", "script": "It's standing right behind you.", 
            "prompts": ["horror monster"], "title": "Cursed Discovery", 
            "desc": "A terrifying archive found.", "tags": "#horror"
        }

    # Voice
    audio_path = await generate_voice_with_fallback(data['script'], data.get('lang', 'en'))
    if not audio_path: return 

    audio_clip = AudioFileClip(audio_path)
    clip_duration = audio_clip.duration / len(data['prompts'])

    # Visuals
    clips = []
    for i, p in enumerate(data['prompts']):
        img = generate_horror_image(p, f"img_{i}.jpg")
        if img:
            vid = animate_horror(img, i)
            if vid: clips.append(VideoFileClip(vid).subclip(0, clip_duration).resize(height=1280))
            else: clips.append(ImageClip(img).set_duration(clip_duration).resize(lambda t: 1+0.05*t).set_fps(24))

    # Render & Upload
    if clips:
        output_file = "output_short.mp4"
        video = concatenate_videoclips(clips, method="compose").set_audio(audio_clip)
        video.write_videofile(output_file, fps=24, codec="libx264")
        
        # FINAL STEP: Post to YouTube
        upload_to_youtube(output_file, data['title'], data['desc'], data['tags'])

if __name__ == "__main__":
    asyncio.run(main())
