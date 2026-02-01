import os, random, requests, asyncio, time, urllib.parse, shutil
import PIL.Image
import numpy as np
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# --- CRITICAL FIXES ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- CONFIG ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client_gemini = genai.Client(api_key=GEMINI_KEY)

# --- 1. CHATTERBOX (Emotional Voice) ---
def generate_voice(text, filename="voice.wav"):
    print(f"🎙️ Chatterbox is narrating...")
    try:
        # 2026 Multilingual endpoint
        client = Client("ResembleAI/Chatterbox-Multilingual-TTS")
        
        # API expects: (text, language, speed, exaggeration)
        # Your previous error was because the script was in the 'language' slot.
        result = client.predict(
            text,           # text_input
            "en",           # language (MUST be 2-letter code)
            0.5,            # speed
            0.8,            # exaggeration
            fn_index=0      
        )
        
        if result and os.path.exists(result):
            shutil.copy(result, filename)
            return os.path.abspath(filename)
        return None
    except Exception as e:
        print(f"❌ Voice Error: {e}")
        return None

# --- 2. IMAGE GEN (Pollinations Flux) ---
def generate_horror_image(prompt, filename):
    print(f"🎨 Creating: {filename}")
    try:
        clean_p = urllib.parse.quote(prompt)
        seed = random.randint(0, 999999)
        url = f"https://image.pollinations.ai/prompt/{clean_p}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
        res = requests.get(url, timeout=60)
        if res.status_code == 200:
            with open(filename, "wb") as f: f.write(res.content)
            return os.path.abspath(filename)
    except: pass
    return None

# --- 3. ANIMATION (FramePack-F1) ---
def animate_horror(image_path, index):
    print(f"🎬 Animating segment {index}...")
    try:
        client = Client("linoyts/FramePack-F1")
        result = client.predict(
            handle_file(image_path), 
            "slow eerie movement", 
            fn_index=0
        )
        out_vid = f"vid_{index}.mp4"
        shutil.copy(result, out_vid)
        return os.path.abspath(out_vid)
    except Exception as e:
        print(f"⚠️ Animation failed: {e}")
        return None

# --- 4. MAIN PIPELINE ---
async def main():
    # A. Get Content from Gemini 3
    # Note: Use ThinkingConfig for better horror writing
    response = client_gemini.models.generate_content(
        model="gemini-3-flash-preview",
        contents="Choose 2 Disney characters and write a 20-word scary found footage script. Give me 2 separate image prompts for them.",
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(include_thoughts=False),
            thinking_level="high"
        )
    )
    
    # Mocking structure for logic - in real use, parse the JSON from response.text
    data = {
        "script": "The archives hold a truth we were never meant to see. Mickey is waiting... in the dark.",
        "prompts": ["Horror Mickey Mouse found footage", "Scary Minnie Mouse dark eyes"]
    }

    # B. Generate Voice
    audio_path = generate_voice(data['script'])
    if not audio_path:
        print("🛑 Voice generation failed. Stopping to prevent MoviePy crash.")
        return

    audio_clip = AudioFileClip(audio_path)
    clip_duration = audio_clip.duration / len(data['prompts'])

    # C. Generate & Animate Clips
    final_clips = []
    for i, p in enumerate(data['prompts']):
        img = generate_horror_image(p, f"img_{i}.jpg")
        if not img: continue
        
        vid = animate_horror(img, i)
        
        if vid and os.path.exists(vid):
            c = VideoFileClip(vid).subclip(0, clip_duration).resize(height=1280)
        else:
            c = (ImageClip(img).set_duration(clip_duration)
                 .resize(lambda t: 1 + 0.04*t).set_fps(24))
        final_clips.append(c)

    # D. Final Merge
    if final_clips:
        video = concatenate_videoclips(final_clips, method="compose")
        video = video.set_audio(audio_clip)
        video.write_videofile("output_short.mp4", fps=24, codec="libx264", audio_codec="aac")
        print("✅ Success: output_short.mp4 created.")
    else:
        print("❌ Failed to create any video clips.")

if __name__ == "__main__":
    asyncio.run(main())
