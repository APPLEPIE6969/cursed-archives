import os, random, requests, asyncio, time, urllib.parse, shutil, re, json
import PIL.Image
import numpy as np
import edge_tts
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# --- MOVIEPY COMPATIBILITY ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- CONFIG ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client_gemini = genai.Client(api_key=GEMINI_KEY)

# --- 1. VOICE ENGINE (With Fallback) ---
async def generate_voice_with_fallback(text, lang_code="en", filename="voice.mp3"):
    clean_text = re.sub(r'\[.*?\]', '', text).strip()
    
    # --- PRIMARY: Chatterbox ---
    print(f"🎙️ PRIMARY: Attempting Chatterbox (Emotional AI)...")
    try:
        client = Client("ResembleAI/Chatterbox-Multilingual-TTS")
        result = client.predict(
            clean_text,     # arg 0: Text
            lang_code,      # arg 1: Language ('en')
            0.5,            # arg 2: Speed
            0.8,            # arg 3: Exaggeration
            fn_index=0      
        )
        if result and os.path.exists(result):
            shutil.copy(result, filename)
            print("✅ Chatterbox Success!")
            return os.path.abspath(filename)
    except Exception as e:
        print(f"⚠️ Chatterbox Failed: {e}")

    # --- SECONDARY: Edge-TTS Fallback ---
    print(f"🎙️ SECONDARY: Attempting Edge-TTS Fallback...")
    try:
        # Using a deep, slightly eerie voice for horror
        voice = "en-US-ChristopherNeural" 
        communicate = edge_tts.Communicate(clean_text, voice, rate="+0%", pitch="-10Hz")
        await communicate.save(filename)
        print("✅ Edge-TTS Fallback Success!")
        return os.path.abspath(filename)
    except Exception as e:
        print(f"❌ Both Voice Engines Failed: {e}")
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

# --- 3. MAIN PIPELINE ---
async def main():
    # Prompt Gemini for Content
    prompt_text = (
        "Pick 2 iconic characters. Write a 20-word scary found footage script. "
        "No brackets []. Return JSON: {'lang': 'en', 'script': '...', 'prompts': ['...', '...']}"
    )
    
    try:
        response = client_gemini.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt_text,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
    except:
        data = {"lang": "en", "script": "It's standing right behind you.", "prompts": ["horror monster"]}

    # Generate Voice (with logic to switch to Edge-TTS if Chatterbox fails)
    audio_path = await generate_voice_with_fallback(data['script'], data.get('lang', 'en'))
    
    if not audio_path:
        print("🛑 STOPPING: No voice generated.")
        return 

    audio_clip = AudioFileClip(audio_path)
    clip_duration = audio_clip.duration / len(data['prompts'])

    clips = []
    for i, p in enumerate(data['prompts']):
        img = generate_horror_image(p, f"img_{i}.jpg")
        if img:
            vid = animate_horror(img, i)
            if vid:
                clips.append(VideoFileClip(vid).subclip(0, clip_duration).resize(height=1280))
            else:
                clips.append(ImageClip(img).set_duration(clip_duration).resize(lambda t: 1+0.05*t).set_fps(24))

    if clips:
        video = concatenate_videoclips(clips, method="compose").set_audio(audio_clip)
        video.write_videofile("output_short.mp4", fps=24, codec="libx264")
        print("✅ SUCCESS: output_short.mp4 created!")

if __name__ == "__main__":
    asyncio.run(main())
