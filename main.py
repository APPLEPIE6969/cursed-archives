import os, random, requests, asyncio, time, urllib.parse, shutil, re, json
import PIL.Image
import numpy as np
import edge_tts
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file
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

# --- 1. VOICE ENGINE (TRIPLE FAILOVER) ---
async def generate_voice_with_fallbacks(text, lang_code="en", filename="voice.mp3"):
    clean_text = re.sub(r'\[.*?\]', '', text).strip()
    
    # Tier 1: Chatterbox
    print(f"🎙️ Tier 1: Chatterbox...")
    try:
        client = Client("ResembleAI/Chatterbox-Multilingual-TTS")
        res = client.predict(clean_text, lang_code, 0.5, 0.8, fn_index=0)
        if res: shutil.copy(res, filename); return os.path.abspath(filename)
    except Exception as e: print(f"⚠️ Chatterbox Fail: {e}")

    # Tier 2: Kokoro-TTS
    print(f"🎙️ Tier 2: Kokoro-TTS...")
    try:
        client = Client("hexgrad/Kokoro-TTS")
        res = client.predict(text=clean_text, voice="af_sky", speed=1, api_name="/predict")
        audio = res[0] if isinstance(res, tuple) else res
        if audio: shutil.copy(audio, filename); return os.path.abspath(filename)
    except Exception as e: print(f"⚠️ Kokoro Fail: {e}")

    # Tier 3: Edge-TTS
    print(f"🎙️ Tier 3: Edge-TTS...")
    try:
        comm = edge_tts.Communicate(clean_text, "en-US-ChristopherNeural", rate="+0%", pitch="-10Hz")
        await comm.save(filename); return os.path.abspath(filename)
    except Exception as e: print(f"❌ All Voice Failed: {e}"); return None

# --- 2. VIDEO & IMAGE GENERATION ---
def generate_horror_image(prompt, filename):
    try:
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=720&height=1280&seed={random.randint(0,999)}&model=flux"
        r = requests.get(url, timeout=30)
        with open(filename, "wb") as f: f.write(r.content)
        return os.path.abspath(filename)
    except: return None

def generate_slop_video(prompt, target_duration, index):
    """Loops slop.club generations at 9:16 until duration is met."""
    print(f"🎬 Scene {index}: Generating 9:16 Slop (Target: {target_duration}s)...")
    collected = []
    current_dur = 0
    try:
        client = Client("slop-club/slop-engine")
        while current_dur < target_duration:
            # Param 1: Prompt, Param 4: Aspect Ratio (1 = 9:16)
            res = client.predict(prompt, "blurry, low quality", random.randint(0, 1000), 1, api_name="/generate")
            path = res if isinstance(res, str) else res[0]
            clip = VideoFileClip(path)
            current_dur += clip.duration
            collected.append(clip)
            if len(collected) >= 4: break # Limit calls
        
        if collected:
            final = concatenate_videoclips(collected).subclip(0, target_duration)
            out = f"slop_{index}.mp4"
            final.write_videofile(out, codec="libx264")
            return out
    except Exception as e: print(f"⚠️ Slop Fail: {e}"); return None

# --- 3. YOUTUBE UPLOADER ---
def upload_to_youtube(video_path, title, description, tags):
    print(f"🚀 Uploading {video_path}...")
    try:
        creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
        youtube = build("youtube", "v3", credentials=creds)
        body = {"snippet": {"title": title, "description": f"{description}\n\n{tags}", "tags": tags.split(','), "categoryId": "24"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        print("✅ YouTube Upload Successful!")
    except Exception as e: print(f"❌ YouTube Error: {e}")

# --- 4. MAIN WORKFLOW ---
async def main():
    # A. Content Generation
    prompt_txt = "Choose 2 iconic characters. Write a 30-word horror story. NO brackets []. Return JSON: {'lang':'en','script':'...','prompts':['...','...'],'title':'...','desc':'...','tags':'...'}"
    resp = client_gemini.models.generate_content(model="gemini-3-flash-preview", contents=prompt_txt, config=types.GenerateContentConfig(response_mime_type="application/json"))
    data = json.loads(resp.text)

    # B. Voice Generation
    audio_path = await generate_voice_with_fallbacks(data['script'], data.get('lang', 'en'))
    if not audio_path: return
    audio_clip = AudioFileClip(audio_path)
    dur_per_clip = audio_clip.duration / len(data['prompts'])

    # C. Video Assembly
    final_clips = []
    for i, p in enumerate(data['prompts']):
        # Attempt Slop.club First
        vid_path = generate_slop_video(p, dur_per_clip, i)
        
        if vid_path:
            final_clips.append(VideoFileClip(vid_path).resize(height=1280))
        else:
            # Fallback to Manual Zooming Image
            print(f"🪄 Scene {i}: Manual Zoom Fallback...")
            img = generate_horror_image(p, f"img_{i}.jpg")
            if img:
                final_clips.append(ImageClip(img).set_duration(dur_per_clip).resize(lambda t: 1 + 0.1*(t/dur_per_clip)).set_fps(24))

    # D. Final Render
    if final_clips:
        output_file = "output_short.mp4"
        video = concatenate_videoclips(final_clips, method="compose").set_audio(audio_clip).set_duration(audio_clip.duration)
        video.write_videofile(output_file, fps=24, codec="libx264", audio_codec="aac")
        
        # E. Upload
        upload_to_youtube(output_file, data['title'], data['desc'], data['tags'])

if __name__ == "__main__":
    asyncio.run(main())
