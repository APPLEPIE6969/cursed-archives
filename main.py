import os, random, requests, asyncio, time, urllib.parse, shutil, io
import PIL.Image
import numpy as np
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# --- CRITICAL FIXES ---
# 1. Restore the removed ANTIALIAS attribute for MoviePy
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- CONFIG ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
gemini = genai.Client(api_key=GEMINI_KEY)

# --- 1. CHATTERBOX (Emotional Voice) ---
def generate_voice(text, filename="voice.wav"):
    print(f"🎙️ Chatterbox is narrating...")
    try:
        # Using the Multilingual space (most stable in 2026)
        client = Client("ResembleAI/Chatterbox-Multilingual-TTS")
        # Use fn_index=0 to bypass named endpoint errors
        result = client.predict(
            text,           # text
            "English",      # language
            0.5,            # speed
            0.8,            # exaggeration (higher for horror)
            fn_index=0      
        )
        shutil.copy(result, filename)
        return str(os.path.abspath(filename))
    except Exception as e:
        print(f"❌ Voice Error: {e}")
        return None

# --- 2. IMAGE GEN (Pollinations Flux) ---
def generate_horror_image(prompt, filename):
    print(f"🎨 Creating: {filename}")
    clean_p = urllib.parse.quote(prompt)
    seed = random.randint(0, 999999)
    # Using 'flux' model for high-end horror detail
    url = f"https://image.pollinations.ai/prompt/{clean_p}?width=720&height=1280&seed={seed}&model=flux&nologo=true"
    res = requests.get(url, timeout=30)
    if res.status_code == 200:
        with open(filename, "wb") as f: f.write(res.content)
        return str(os.path.abspath(filename))
    return None

# --- 3. ANIMATION (FramePack-F1) ---
def animate_horror(image_path, index):
    print(f"🎬 Animating segment {index}...")
    try:
        client = Client("linoyts/FramePack-F1")
        # FramePack usually takes image + motion prompt
        result = client.predict(
            handle_file(image_path), 
            "slow eerie movement, breathing", 
            fn_index=0
        )
        out_vid = f"vid_{index}.mp4"
        shutil.copy(result, out_vid)
        return str(os.path.abspath(out_vid))
    except Exception as e:
        print(f"⚠️ Animation failed: {e}")
        return None

# --- 4. MAIN PIPELINE ---
async def main():
    # A. Get Content from Gemini
    # (Insert your full character list prompt here)
    data = {
        "script": "The basement was never empty [gasp]. Mickey's eyes followed me. They weren't plastic. They were wet [laugh].",
        "prompts": ["Horror Mickey Mouse in dark basement, found footage", "Scary Pikachu with glowing eyes"]
    }

    # B. Generate Voice
    audio_path = generate_voice(data['script'])
    audio_clip = AudioFileClip(audio_path)
    clip_duration = audio_clip.duration / len(data['prompts'])

    # C. Generate & Animate Clips
    final_clips = []
    for i, p in enumerate(data['prompts']):
        img = generate_horror_image(p, f"img_{i}.jpg")
        vid = animate_horror(img, i)
        
        if vid and os.path.exists(vid):
            c = VideoFileClip(vid).subclip(0, clip_duration).resize(height=1280)
        else:
            # Fallback to static zoom if animation fails
            c = (ImageClip(img).set_duration(clip_duration)
                 .resize(lambda t: 1 + 0.04*t).set_fps(24))
        final_clips.append(c)

    # D. Final Merge
    video = concatenate_videoclips(final_clips, method="compose")
    video = video.set_audio(audio_clip)
    video.write_videofile("output_short.mp4", fps=24, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    asyncio.run(main())
