import os, random, requests, asyncio, time, urllib.parse, shutil, re, json
import PIL.Image
import numpy as np
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# --- CRITICAL MOVIEPY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- CONFIG ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client_gemini = genai.Client(api_key=GEMINI_KEY)

# --- 1. CHATTERBOX (Multilingual Emotional Voice) ---
def generate_voice(text, lang_code, filename="voice.wav"):
    # CLEANUP: Remove any [laugh], [cry], [gasp] etc. using Regex
    # This ensures the API only gets pure text.
    clean_text = re.sub(r'\[.*?\]', '', text).strip()
    
    print(f"🎙️ Chatterbox is narrating: \"{clean_text[:50]}...\"")
    try:
        client = Client("ResembleAI/Chatterbox-Multilingual-TTS")
        
        # API expects: (text, language, speed, exaggeration)
        result = client.predict(
            clean_text,     # 1. PURE text only (No brackets!)
            lang_code,      # 2. Language Code ('en')
            0.5,            # 3. Speed
            0.8,            # 4. Exaggeration
            fn_index=0      
        )
        
        if result and os.path.exists(result):
            shutil.copy(result, filename)
            return os.path.abspath(filename)
        return None
    except Exception as e:
        print(f"❌ Voice Error: {e}")
        return None

# --- 2. IMAGE GEN ---
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

# --- 3. ANIMATION ---
def animate_horror(image_path, index):
    print(f"🎬 Animating segment {index}...")
    try:
        client = Client("linoyts/FramePack-F1")
        result = client.predict(handle_file(image_path), "eerie movement", fn_index=0)
        out_vid = f"vid_{index}.mp4"
        shutil.copy(result, out_vid)
        return os.path.abspath(out_vid)
    except: return None

# --- 4. MAIN PIPELINE ---
async def main():
    # A. Content Generation Call
    # We strictly forbid brackets in the prompt.
    prompt_text = (
        "Pick 2 Disney characters and write a 20-word scary found footage script. "
        "DO NOT use brackets like [laugh] or [cry]. DO NOT use any text inside [] brackets. "
        "Return JSON with keys: 'lang' (set to 'en'), 'script', and 'prompts' (list of 2 image prompts)."
    )
    
    response = client_gemini.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt_text,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    
    # Parse the AI response
    data = json.loads(response.text)
    print(f"🧠 Gemini Script: {data['script']}")

    # B. Generate Voice (Backwards compatible logic)
    audio_path = generate_voice(data['script'], data.get('lang', 'en'))
    
    if not audio_path:
        print("🛑 Voice generation failed.")
        return 

    audio_clip = AudioFileClip(audio_path)
    clip_duration = audio_clip.duration / len(data['prompts'])

    # C. Video Segments
    final_clips = []
    for i, p in enumerate(data['prompts']):
        img = generate_horror_image(p, f"img_{i}.jpg")
        if not img: continue
        
        vid = animate_horror(img, i)
        if vid and os.path.exists(vid):
            c = VideoFileClip(vid).subclip(0, clip_duration).resize(height=1280)
        else:
            c = (ImageClip(img).set_duration(clip_duration)
                 .resize(lambda t: 1 + 0.05*t).set_fps(24))
        final_clips.append(c)

    # D. Render
    if final_clips:
        video = concatenate_videoclips(final_clips, method="compose")
        video = video.set_audio(audio_clip)
        video.write_videofile("output_short.mp4", fps=24, codec="libx264", audio_codec="aac")
        print("✅ Finished: output_short.mp4")

if __name__ == "__main__":
    asyncio.run(main())
