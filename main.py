import os, random, requests, asyncio, time, urllib.parse, shutil
import PIL.Image
from moviepy.editor import *
from google import genai
from google.genai import types
from gradio_client import Client, handle_file

# --- MOVIEPY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- KEYS ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
YT_REFRESH = os.environ.get("YOUTUBE_REFRESH_TOKEN")

gemini = genai.Client(api_key=GEMINI_KEY)

# --- CHATTERBOX VOICE GENERATOR ---
def generate_chatterbox_voice(text, filename="voice.wav"):
    print(f"🎙️ Chatterbox is speaking: {text[:30]}...")
    try:
        # Using the official ResembleAI Space (or a reliable mirror)
        client = Client("ResembleAI/Chatterbox") 
        
        # Chatterbox Parameters: Text, Language, Speed, Exaggeration
        result = client.predict(
            text,           # Input text
            "English",      # Language
            0.5,            # Speed (lower is slower)
            0.7,            # Exaggeration (higher is more emotional)
            api_name="/predict"
        )
        shutil.copy(result, filename)
        return filename
    except Exception as e:
        print(f"❌ Chatterbox Error: {e}")
        return None

# --- IMAGE GENERATOR ---
def generate_image(prompt, filename):
    seed = random.randint(0, 999999)
    clean_p = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{clean_p}?width=720&height=1280&seed={seed}&nologo=true"
    res = requests.get(url)
    with open(filename, "wb") as f: f.write(res.content)
    return filename

# --- ANIMATOR ---
def animate_frame(image_path, index):
    try:
        client = Client("linoyts/FramePack-F1")
        result = client.predict(handle_file(image_path), "horror movement, subtle", api_name="/predict")
        out = f"vid_{index}.mp4"
        shutil.copy(result, out)
        return out
    except: return None

# --- MAIN WORKFLOW ---
async def run_bot():
    # 1. BRAIN: Pick 4 characters & write script
    # (Simplified for brevity, use your full list prompt here)
    data = {
        "chars": ["Mickey Mouse", "Pikachu", "SpongeBob", "Link"],
        "script": "The archives hold secrets [sigh]. Mickey isn't smiling anymore [laugh]. Pikachu's spark is... gone.",
        "prompts": ["horror mickey", "horror pikachu", "horror spongebob", "horror link"]
    }

    # 2. VOICE: Generate first to get duration
    audio_file = generate_chatterbox_voice(data['script'])
    audio_clip = AudioFileClip(audio_file)
    
    # 3. VISUALS: Generate and Animate 4 segments
    clips = []
    for i in range(4):
        img = generate_image(data['prompts'][i], f"img_{i}.jpg")
        vid = animate_frame(img, i)
        if vid: 
            clips.append(VideoFileClip(vid))
        else:
            clips.append(ImageClip(img).set_duration(audio_clip.duration/4).resize(lambda t: 1+0.02*t))

    # 4. MERGE
    final_video = concatenate_videoclips(clips, method="compose")
    final_video = final_video.set_audio(audio_clip).set_duration(audio_clip.duration)
    final_video.write_videofile("output.mp4", fps=24, codec="libx264")
    
    print("🚀 Video Ready for YouTube!")

if __name__ == "__main__":
    asyncio.run(run_bot())
