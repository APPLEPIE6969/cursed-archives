import os, random, requests, asyncio, time, urllib.parse, shutil, re, json
import PIL.Image
import numpy as np
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# --- MOVIEPY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- CONFIG ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client_gemini = genai.Client(api_key=GEMINI_KEY)

# --- 1. CHATTERBOX (Fixed Parameter Mapping) ---
def generate_voice(text, lang_code="en", filename="voice.wav"):
    # Clean brackets just in case
    clean_text = re.sub(r'\[.*?\]', '', text).strip()
    print(f"🎙️ Chatterbox Attempt: Text='{clean_text[:30]}...', Lang='{lang_code}'")
    
    try:
        client = Client("ResembleAI/Chatterbox-Multilingual-TTS")
        
        # We use a list for arguments. 
        # BASED ON THE ERROR: 
        # Slot 0 = Text
        # Slot 1 = Language Choice (This is where your script was accidentally going)
        # Slot 2 = Speed
        # Slot 3 = Exaggeration
        result = client.predict(
            clean_text,     # arg 0
            lang_code,      # arg 1 (This MUST be 'en')
            0.5,            # arg 2
            0.8,            # arg 3
            fn_index=0      
        )
        
        if result and os.path.exists(result):
            shutil.copy(result, filename)
            return os.path.abspath(filename)
        return None
    except Exception as e:
        print(f"❌ Voice Error: {e}")
        return None

# --- 2. IMAGE & ANIMATION (Standard logic) ---
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
    # Strict Prompt to Gemini
    prompt_text = (
        "Choose 2 random characters from Disney or Nintendo. "
        "Write a 20-word scary found footage script. Do NOT use brackets []. "
        "Return JSON: {'lang': 'en', 'script': '...', 'prompts': ['...', '...']}"
    )
    
    try:
        response = client_gemini.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt_text,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
    except:
        # Emergency Fallback if Gemini fails
        data = {"lang": "en", "script": "He is watching from the shadows.", "prompts": ["horror monster"]}

    # Generate Voice with the verified 'en' code
    audio_path = generate_voice(data['script'], data.get('lang', 'en'))
    
    if not audio_path:
        print("🛑 STOPPING: Voice failed again. Check the 'en' parameter.")
        return 

    audio_clip = AudioFileClip(audio_path)
    clip_duration = audio_clip.duration / len(data['prompts'])

    clips = []
    for i, p in enumerate(data['prompts']):
        img = generate_horror_image(p, f"img_{i}.jpg")
        if img:
            vid = animate_horror(img, i)
            if vid: clips.append(VideoFileClip(vid).subclip(0, clip_duration).resize(height=1280))
            else: clips.append(ImageClip(img).set_duration(clip_duration).resize(lambda t: 1+0.05*t).set_fps(24))

    if clips:
        video = concatenate_videoclips(clips, method="compose").set_audio(audio_clip)
        video.write_videofile("output_short.mp4", fps=24, codec="libx264")
        print("✅ SUCCESS!")

if __name__ == "__main__":
    asyncio.run(main())
