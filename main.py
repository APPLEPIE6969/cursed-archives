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
def get_concept():
    client = Groq(api_key=GROQ_KEY)
    prompt = "Generate a 'Cursed/Found Footage' YouTube Short script. Return JSON with: 'script', 'prompt_1_normal', 'prompt_2_uncanny', 'prompt_3_horror', 'title', 'description', 'hashtags' (as a single string)."
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- 2. IMAGE GENERATOR (Fixed Pollinations URL) ---
def generate_image(prompt, filename, max_retries=3):
    seed = random.randint(0, 999999)
    # The most stable 2026 Pollinations URL structure
    clean_prompt = urllib.parse.quote(prompt[:250])
    url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=720&height=1280&seed={seed}&nologo=true"
    
    for attempt in range(max_retries):
        try:
            print(f"🎨 Generating Image: {filename} (Attempt {attempt+1})...")
            res = requests.get(url, timeout=60)
            res.raise_for_status()
            with open(filename, "wb") as f: 
                f.write(res.content)
            return filename
        except Exception as e:
            print(f"⚠️ Image Error: {e}")
            time.sleep(5)
    
    # Emergency Fallback
    PIL.Image.new('RGB', (720, 1280), (20, 20, 20)).save(filename)
    return filename

# --- 3. VIDEO GENERATOR (Fixed API Name Error) ---
def animate_wan_with_retry(horror_prompt, max_retries=2):
    print(f"🎬 Connecting to Wan-AI/Wan2.1...")
    for attempt in range(max_retries):
        try:
            client = Client("Wan-AI/Wan2.1", token=HF_TOKEN)
            
            # Switch to T2V tab to ensure correct context
            client.predict(api_name="/switch_t2v_tab")
            
            # Trigger generation
            print(f"   PLEASE WAIT... Requesting generation (Attempt {attempt+1})...")
            client.predict(
                prompt=f"found footage horror, grainy, {horror_prompt}",
                size="720*1280",
                watermark_wan=False,
                seed=-1,
                api_name="/t2v_generation_async"
            )
            
            # Poll for status
            print("   Polling for result...")
            while True:
                # Returns: (video_dict, cost_time, estimated_waiting_time, slider_val)
                result = client.predict(api_name="/status_refresh")
                
                video_data = result[0]
                # video_data is likely {'video': '/path/to/video', 'subtitles': ...} or None or similar
                # Check if we have a valid video path in the dict
                if video_data and 'video' in video_data and video_data['video']:
                    temp_path = video_data['video']
                    print(f"   Generation complete! Video at: {temp_path}")
                    video_filename = "wan_climax.mp4"
                    shutil.copy(temp_path, video_filename)
                    return video_filename
                
                # Check for progress/waiting
                # result[2] is estimated waiting time, result[1] is cost time? 
                # Use a small sleep to avoid hammering the API
                time.sleep(2)
                
        except Exception as e:
            print(f"⚠️ Video Attempt {attempt+1} failed: {e}")
            time.sleep(10) # Wait a bit before retry
    return None

# --- 4. EDITOR ---
# --- 4. EDITOR ---
def create_story_video(img1, img2, video_clip, audio_path, output_filename):
    audio = AudioFileClip(audio_path)
    d = audio.duration
    
    c1 = ImageClip(img1).set_duration(d*0.3 + 1).resize(lambda t: 1+0.04*t).set_position('center')
    c2 = ImageClip(img2).set_duration(d*0.3 + 1).resize(lambda t: 1+0.06*t).set_position('center').set_start(d*0.3).crossfadein(1)
    
    if video_clip and os.path.exists(video_clip):
        # Clip the climax video to fit the remaining time
        c3 = VideoFileClip(video_clip).resize(height=1280).set_start(d*0.6).crossfadein(0.5)
        if c3.duration > (d * 0.4):
            c3 = c3.subclip(0, d * 0.4 + 1)
        if c3.w > 720: 
            c3 = c3.crop(x1=c3.w/2 - 360, width=720)
    else:
        c3 = ImageClip(img2).set_duration(d*0.4 + 1).resize(lambda t: 1+0.15*t).set_start(d*0.6).crossfadein(0.5)

    final = CompositeVideoClip([c1, c2, c3], size=(720, 1280)).set_duration(d).set_audio(audio)
    final.write_videofile(output_filename, fps=24, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
    return output_filename

def generate_audio_kokoro(text, filename):
    print("   🎙️ Generating audio (Kokoro TTS)...")
    client = Client("https://yakhyo-kokoro-onnx.hf.space/")
    result = client.predict(
        text=text,
        model_path="kokoro-quant.onnx",
        style_vector="am_adam.pt", # Male voice
        output_file_format="mp3",
        speed=1,
        api_name="/local_tts"
    )
    # result is the filepath to the generated audio
    shutil.copy(result, filename)
    return filename

async def make_audio(text, filename):
    try:
        # Run synchronous Gradio call in a separate thread to not block the event loop
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
        
        generate_image(data['prompt_1_normal'], "n.jpg")
        generate_image(data['prompt_2_uncanny'], "u.jpg")
        asyncio.run(make_audio(data['script'], "v.mp3"))
        
        video_clip = animate_wan_with_retry(data['prompt_3_horror'])
        
        final_path = create_story_video("n.jpg", "u.jpg", video_clip, "v.mp3", "final.mp4")
        
        vid_id = upload_to_youtube(final_path, data['title'], data['description'], data['hashtags'])
        print(f"🚀 Success! https://youtube.com/shorts/{vid_id}")
    except Exception as e:
        print(f"❌ Critical Failure: {e}")
