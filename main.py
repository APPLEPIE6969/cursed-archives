import os
import random
import requests
import asyncio
import edge_tts
import time
import json
import shutil
import urllib.parse
from gradio_client import Client
from groq import Groq
import PIL.Image

# --- 🛠️ COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import *
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURATION ---
def get_secret(key):
    val = os.environ.get(key)
    return val.strip() if val else ""

GROQ_KEY = get_secret("GROQ_API_KEY")
YT_CLIENT_ID = get_secret("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = get_secret("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = get_secret("YOUTUBE_REFRESH_TOKEN")
HF_TOKEN = get_secret("HF_TOKEN") 

# --- 1. BRAIN ---
HORROR_STYLES = [
    "Found Footage", "Analog Horror", "Liminal Space", "Uncanny Valley",
    "Body Horror", "Cosmic Horror", "Folk Horror", "Slasher", 
    "Paranormal/Ghost", "Psychological Thriller", "Cryptid Encounter",
    "Cursed Internet Mystery", "VHS Glitch Horror"
]

def get_concept():
    client = Groq(api_key=GROQ_KEY)
    style = random.choice(HORROR_STYLES)
    print(f"👻 Selected Horror Style: {style}")
    
    prompt = (
        f"Generate a '{style}' YouTube Short script (approx 30-60s). "
        "Return a JSON object with:\n"
        "- 'script': The narrator's voiceover text.\n"
        "- 'prompt_1_normal': A highly detailed visual description of the opening scene (setting the mood).\n"
        "- 'prompt_2_uncanny': A visual description of the middle scene where something is wrong.\n"
        "- 'prompt_3_horror': A visual description of the terrifying climax/reveal.\n"
        "- 'title': A viral clickbait title.\n"
        "- 'description': Short video description.\n"
        "- 'hashtags': Relevant hashtags as a single string.\n"
        "IMPORTANT: The image prompts MUST strictly match the events described in the 'script'. "
        "Describe the lighting, environment, and entities visible at that specific moment."
    )
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- 2. IMAGE GENERATOR (Freepik Mystic) ---
def generate_image_freepik(prompt, filename):
    print(f"🎨 Generating Image (Freepik): {filename}...")
    api_key = os.environ.get("FREEPIK_API_KEY")
    if not api_key:
        print("⚠️ FREEPIK_API_KEY not found. Using fallback placeholder.")
        PIL.Image.new('RGB', (720, 1280), (20, 20, 20)).save(filename)
        return filename

    url = "https://api.freepik.com/v1/ai/mystic"
    headers = {
        "x-freepik-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Using 'realism' model and vertical aspect ratio for Shorts
    payload = {
        "prompt": prompt,
        "aspect_ratio": "social_story_9_16", 
        "model": "realism",
        "filter_nsfw": False # CAUTION: Requires permission, otherwise ignored/true
    }

    try:
        # 1. Start Generation
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code != 200:
            print(f"❌ Freepik Request Failed: {res.text}")
            raise Exception(f"Freepik API Error: {res.status_code}")
        
        task_data = res.json().get("data", {})
        task_id = task_data.get("task_id")
        print(f"   Task Started: {task_id}")

        # 2. Poll for Completion
        for _ in range(30): # Timeout ~60s
            time.sleep(2)
            check_url = f"{url}/{task_id}"
            check_res = requests.get(check_url, headers=headers)
            if check_res.status_code == 200:
                status_data = check_res.json().get("data", {})
                status = status_data.get("status")
                
                if status == "COMPLETED":
                    img_url = status_data.get("generated", [])[0]
                    print(f"   Image Function Success: {img_url}")
                    
                    # Download Image
                    img_res = requests.get(img_url)
                    with open(filename, "wb") as f:
                        f.write(img_res.content)
                    return filename
                elif status == "FAILED":
                    print("❌ Freepik Task Failed.")
                    break
            else:
                print(f"   Polling Error: {check_res.status_code}")

    except Exception as e:
        print(f"⚠️ Image Generation Error: {e}")

    # Fallback
    print("   Using fallback image.")
    PIL.Image.new('RGB', (720, 1280), (50, 50, 50)).save(filename)
    return filename

# --- 3. VIDEO GENERATOR (Wan 2.2 I2V) ---
from gradio_client import handle_file

def animate_wan_i2v(image_path, prompt, max_retries=3):
    print(f"🎬 Connecting to Wan-AI/Wan2.2 (I2V)...")
    
    for attempt in range(max_retries):
        try:
            client = Client("r3gm/wan2-2-fp8da-aoti-preview2")
            
            print(f"   Requesting animation for {image_path} (Attempt {attempt+1})...")
            
            # Based on user-provided API docs for /generate_video
            result = client.predict(
                input_image=handle_file(image_path),
                last_image=None,
                prompt=f"found footage horror style, {prompt}, cinematic motion, smooth animation",
                steps=6,
                negative_prompt="bright, cartoon, static, low quality, watermark, text",
                duration_seconds=5,
                guidance_scale=1,
                guidance_scale_2=1,
                seed=42,
                randomize_seed=True,
                quality=6,
                scheduler="UniPCMultistep",
                flow_shift=3,
                frame_multiplier=16,
                video_component=True,
                api_name="/generate_video"
            )
            
            # Result is tuple: (filepath, filepath, seed)
            # We want the video path [0]
            video_path = result[0]
            print(f"   Generation complete! Video at: {video_path}")
            
            final_name = "wan_climax.mp4"
            shutil.copy(video_path, final_name)
            return final_name

        except Exception as e:
            print(f"⚠️ Video Attempt {attempt+1} failed: {e}")
            time.sleep(10)
            
    return None

# --- 4. EDITOR ---
def create_story_video(img1, img2, video_clip, audio_path, output_filename):
    audio = AudioFileClip(audio_path)
    d = audio.duration
    
    # img1: Normal (Intro)
    c1 = ImageClip(img1).set_duration(d*0.3 + 1).resize(lambda t: 1+0.04*t).set_position('center')
    
    # img2: Uncanny (Middle -> Will be animated)
    c2 = ImageClip(img2).set_duration(d*0.3 + 1).resize(lambda t: 1+0.06*t).set_position('center').set_start(d*0.3).crossfadein(1)
    
    # video_clip: Horror (Climax) - animated from img2 (Uncanny) or separate prompt? 
    # Logic: "Generate Image (Freepik) -> Animate that same Image (Wan I2V)"
    # We will animate img2 (Uncanny) to become the Horror Climax.
    
    if video_clip and os.path.exists(video_clip):
        c3 = VideoFileClip(video_clip).resize(height=1280).set_start(d*0.6).crossfadein(0.5)
        # Adjust timing to finish with audio
        remaining_time = d - (d * 0.6)
        if c3.duration > remaining_time:
             c3 = c3.subclip(0, remaining_time + 1) # small buffer
        
        # Center crop if needed (Wan2.2 usually follows aspect ratio but lets be safe)
        if c3.w > 720:
             c3 = c3.crop(x1=c3.w/2 - 360, width=720)
    else:
        # Fallback if video gen failed
        c3 = ImageClip(img2).set_duration(d*0.4 + 1).resize(lambda t: 1+0.15*t).set_start(d*0.6).crossfadein(0.5)

    final = CompositeVideoClip([c1, c2, c3], size=(720, 1280)).set_duration(d).set_audio(audio)
    final.write_videofile(output_filename, fps=24, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
    return output_filename

def generate_audio_kokoro(text, filename):
    print("   🎙️ Generating audio (Kokoro TTS)...")
    try:
        client = Client("https://yakhyo-kokoro-onnx.hf.space/")
        result = client.predict(
            text=text,
            model_path="kokoro-quant.onnx",
            style_vector="am_adam.pt", # Male voice
            output_file_format="mp3",
            speed=1,
            api_name="/local_tts"
        )
        shutil.copy(result, filename)
        return filename
    except Exception as e:
        print(f"   ⚠️ Kokoro Init Error: {e}")
        raise e

async def make_audio(text, filename):
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, generate_audio_kokoro, text, filename)
        print("   ✅ Kokoro TTS success.")
    except Exception as e:
        print(f"   ⚠️ Kokoro TTS failed: {e}. Switching to EdgeTTS fallback...")
        try:
            await edge_tts.Communicate(text, "en-US-ChristopherNeural").save(filename)
            print("   ✅ EdgeTTS success.")
        except Exception as e2:
             print(f"   ❌ All TTS failed: {e2}")
             raise e2

# --- 5. UPLOADER (Fixed Split Error) ---
def upload_to_youtube(video_path, title, description, tags):
    # Fix for the 'list' has no attribute 'split' error
    if isinstance(tags, list):
        tag_list = tags
        tag_str = " ".join(tags)
    else:
        tag_list = tags.split(',')
        tag_str = tags

    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    service = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title[:100], 
            "description": f"{description}\n\n{tag_str}", 
            "tags": tag_list, 
            "categoryId": "1"
        }, 
        "status": {"privacyStatus": "public"}
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    res = service.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return res['id']

if __name__ == "__main__":
    try:
        data = get_concept()
        print(f"📝 Concept: {data['title']}")
        
        # 1. Generate Images (Freepik)
        # Normal (Intro)
        generate_image_freepik(data['prompt_1_normal'], "n.jpg")
        # Uncanny (Middle -> Will be animated)
        generate_image_freepik(data['prompt_2_uncanny'], "u.jpg")
        
        # 2. Audio
        asyncio.run(make_audio(data['script'], "v.mp3"))
        
        # 3. Video (Wan 2.2 I2V)
        # Animate the Uncanny image ("u.jpg") to create the horror climax
        video_clip = animate_wan_i2v("u.jpg", data['prompt_3_horror'])
        
        # 4. Edit
        final_path = create_story_video("n.jpg", "u.jpg", video_clip, "v.mp3", "final.mp4")
        
        # 5. Upload
        vid_id = upload_to_youtube(final_path, data['title'], data['description'], data['hashtags'])
        print(f"🚀 Success! https://youtube.com/shorts/{vid_id}")
    except Exception as e:
        print(f"❌ Critical Failure: {e}")
