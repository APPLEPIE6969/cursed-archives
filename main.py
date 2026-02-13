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
# --- 1. VIRAL BRAIN ---
class ViralBrain:
    REACTIONS = ["WTF", "SHOCK", "GLITCH", "UNSETTLING", "CURSED"] # Optimized for Cursed Archives
    FORMATS = [
        "POV: You found this tape", "Don't watch this at 3AM", "Glitch in the simulation",
        "Found Footage: The Backrooms", "Cursed Tutorial", "Screamer Prank (Fakeout)"
    ]

    def __init__(self, groq_key):
        self.client = Groq(api_key=groq_key)

    def generate_viral_concept(self):
        reaction = random.choice(self.REACTIONS)
        fmt = random.choice(self.FORMATS)
        print(f"🧠 Brain Active: Target Reaction={reaction} | Format={fmt}")

        sys_prompt = (
            "You are a VIRAL SHORTS ENGINEER. Your goal is to generate a script that escapes 'Swipe Jail'.\n"
            "MANDATORY RULES:\n"
            "1. TRIPLE HOOK (0-3s): Visual (weird/scary), Verbal (provocative statement), Text (amplified curiosity).\n"
            "2. PACING: Fast cuts, no filler. Every sentence must build tension.\n"
            "3. ENDING: Twist or jump scare or unsettling realization.\n"
            f"4. TARGET EMOTION: {reaction}.\n"
            f"5. FORMAT: {fmt}.\n"
            "6. DURATION: 20-30 seconds max.\n\n"
            "Return JSON with:\n"
            "- 'title': Viral clickbait title.\n"
            "- 'target_reaction': The chosen reaction.\n"
            "- 'hook_visual': Detailed prompt for the FIRST 3 seconds (The Hook Image).\n"
            "- 'hook_audio': The first sentence spoken (The Verbal Hook).\n"
            "- 'hook_text': The text overlay for the hook (The Text Hook).\n"
            "- 'script_body': The rest of the script (excluding the hook).\n"
            "- 'visual_prompts': A list of 3-5 highly detailed image prompts for the rest of the video. strictly visual descriptions.\n"
            "- 'description': Video description.\n"
            "- 'hashtags': String of hashtags."
        )

        completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Generate a Cursed Archive viral short concept."}
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)

def get_concept():
    # Legacy wrapper or replacement
    brain = ViralBrain(GROQ_KEY)
    return brain.generate_viral_concept()

# --- 2. SUBMAGIC CLIENT (Auto-Captions) ---
class SubmagicClient:
    BASE_URL = "https://api.submagic.co/v1"

    def __init__(self):
        self.api_key = os.environ.get("SUBMAGIC_API_KEY")
        if not self.api_key:
            print("⚠️ SUBMAGIC_API_KEY not found! Captions will be skipped.")

    def process_video(self, video_path, title):
        if not self.api_key:
            return video_path

        print(f"✨ Submagic: Uploading {video_path}...")
        
        # 1. Upload Video
        upload_url = f"{self.BASE_URL}/projects"
        headers = {"x-api-key": self.api_key} # Content-Type is set by requests for multipart
        
        try:
            with open(video_path, 'rb') as f:
                # Based on search results: 'file', 'title', 'language', 'templateName'
                files = {'file': f}
                data = {
                    'title': title[:100],
                    'language': 'en',
                    'templateName': 'Hormozi 2' # User requested template
                }
                res = requests.post(upload_url, headers=headers, files=files, data=data)
            
            if res.status_code not in [200, 201]:
                print(f"⚠️ Submagic Upload Failed: {res.status_code} - {res.text}")
                return video_path
                
            project_data = res.json().get('data', {}) # Assuming 'data' envelope or direct
            # If API returns direct object
            if 'id' in res.json(): project_data = res.json()
            
            project_id = project_data.get('id')
            if not project_id:
                print(f"⚠️ Submagic: No Project ID returned. {res.text}")
                return video_path
                
            print(f"   Submagic Project ID: {project_id}. Waiting for processing...")
            
            # 2. Poll for Completion
            # Rate limit check: "Standard operations... 500/hour". 
            # We poll every 10s.
            for attempt in range(60): # 10 minutes timeout
                time.sleep(10)
                status_url = f"{self.BASE_URL}/projects/{project_id}"
                status_res = requests.get(status_url, headers=headers)
                
                if status_res.status_code == 200:
                    status_data = status_res.json()
                    # Flatten if inside 'data'
                    if 'data' in status_data: status_data = status_data['data']
                    
                    status = status_data.get('status')
                    print(f"      ...Status: {status}")
                    
                    if status == 'completed':
                        # Look for download URL. 
                        # Sometimes it's 'videoUrl', 'downloadUrl', or we need to hit /export.
                        # User mentioned "Export operations". Let's try export if no URL found.
                        download_url = status_data.get('videoUrl') or status_data.get('downloadUrl')
                        
                        if not download_url:
                            # Try explicit export (blind attempt based on user prompt hint)
                            print("      ...Triggering Export...")
                            export_url = f"{self.BASE_URL}/projects/{project_id}/export"
                            # Export might be blocking or return a url
                            export_res = requests.post(export_url, headers=headers)
                            if export_res.status_code == 200:
                                export_data = export_res.json()
                                if 'data' in export_data: export_data = export_data['data']
                                download_url = export_data.get('url')
                        
                        if download_url:
                            print(f"   ✅ Submagic Success! Downloading captions...")
                            # Download
                            final_res = requests.get(download_url)
                            captioned_path = video_path.replace(".mp4", "_submagic.mp4")
                            with open(captioned_path, "wb") as f_out:
                                f_out.write(final_res.content)
                            return captioned_path
                        else:
                            print("⚠️ Submagic Completed but no URL found.")
                            return video_path
                            
                    elif status == 'failed':
                        print("❌ Submagic Processing Failed.")
                        return video_path
                else:
                    print(f"   Polling Error: {status_res.status_code}")
                    
            print("⚠️ Submagic Timeout.")
            return video_path

        except Exception as e:
            print(f"⚠️ Submagic Client Error: {e}")
            return video_path

# --- 3. IMAGE GENERATOR (Freepik Mystic) ---
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

# --- 4. EDITOR (Viral Engine) ---
def create_viral_short(hook_video_path, body_image_paths, audio_path, hook_text, output_filename):
    print("✂️ Editing Viral Short...")
    audio = AudioFileClip(audio_path)
    total_duration = audio.duration
    
    clips = []
    
    # 1. THE HOOK (0-3s)
    # Visual Hook: Wan 2.2 generated video OR fallback image
    if os.path.exists(hook_video_path):
        # Determine if video or image
        if hook_video_path.lower().endswith(('.mp4', '.mov', '.avi')):
            hook_clip = VideoFileClip(hook_video_path).resize(height=1280)
            # Center crop to 720x1280
            if hook_clip.w > 720:
                 hook_clip = hook_clip.crop(x1=hook_clip.w/2 - 360, width=720)
            # Duration: First 3 seconds or audio length if shorter?
            hook_duration = min(3, total_duration) 
            hook_clip = hook_clip.subclip(0, hook_duration)
        else:
            # Fallback to ImageClip if it's a jpg/png
            hook_duration = min(3, total_duration)
            hook_clip = ImageClip(hook_video_path).set_duration(hook_duration).resize(height=1280)
            if hook_clip.w > 720:
                 hook_clip = hook_clip.crop(x1=hook_clip.w/2 - 360, width=720)
            # Apply subtle zoom to static hook
            hook_clip = hook_clip.resize(lambda t: 1 + 0.05*t)
        
        # Text Hook: Overlay
        # Using simple TextClip for now (Submagic would replace this if active)
        # Ensure ImageMagick is installed or this might fail. 
        # Fallback: Print instruction if TextClip fails or skip.
        try:
            txt_clip = TextClip(hook_text, fontsize=70, color='white', font='Arial-Bold', stroke_color='black', stroke_width=2, size=(600, None), method='caption')
            txt_clip = txt_clip.set_position('center').set_duration(hook_duration)
            hook_clip = CompositeVideoClip([hook_clip, txt_clip])
        except Exception as e:
            print(f"⚠️ TextClip failed (ImageMagick missing?): {e}")
            
        clips.append(hook_clip)
        current_time = hook_duration
    else:
        current_time = 0

    # 2. THE BODY (Fast Pacing)
    # "Pattern interrupt every 5-15 seconds" -> We simply switch images fast.
    # "No static frames longer than 3 seconds"
    
    remaining_time = total_duration - current_time
    if remaining_time > 0 and body_image_paths:
        # Calculate duration per image
        num_images = len(body_image_paths)
        duration_per_image = remaining_time / num_images
        
        # Cap duration to max 3s to satisfy "No static frames > 3s"
        # If duration_per_image > 3, we might need to loop/duplicate or just accept (Kenneth Burns effect helps)
        
        for i, img_path in enumerate(body_image_paths):
            if not os.path.exists(img_path): continue
            
            # Create Clip
            img_clip = ImageClip(img_path).set_duration(duration_per_image)
            img_clip = img_clip.resize(height=1280)
            if img_clip.w > 720:
                img_clip = img_clip.crop(x1=img_clip.w/2 - 360, width=720)
            
            # Apply "Ken Burns" (Zoom/Pan) to avoid static frame
            # Randomize effect: Zoom In, Zoom Out, Pan Left, Pan Right
            effect = random.choice(['zoom_in', 'zoom_out', 'pan'])
            
            if effect == 'zoom_in':
                img_clip = img_clip.resize(lambda t: 1 + 0.05*t)
            elif effect == 'zoom_out':
                img_clip = img_clip.resize(lambda t: 1.2 - 0.05*t) # Start zoomed in
            
            clips.append(img_clip)
    
    # Concatenate
    final_video = concatenate_videoclips(clips, method="compose")
    final_video = final_video.set_audio(audio)
    
    # Ensure exact duration match
    # STRICT SHORTS LIMIT: 59 seconds max to be safe.
    final_duration = min(total_duration, 59.0)
    final_video = final_video.set_duration(final_duration)
    
    final_video.write_videofile(output_filename, fps=24, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
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

# --- 5. UPLOADER ---
def upload_to_youtube(video_path, title, description, tags):
    if isinstance(tags, list):
        tag_list = tags
        tag_str = " ".join(tags)
    else:
        tag_list = tags.split(',')
        tag_str = tags # Assuming it is already a string

    # FORCE SHORTS METADATA
    if "#Shorts" not in title:
        title = f"{title} #Shorts"
    if "#Shorts" not in description:
        description = f"{description}\n\n#Shorts"

    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    service = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title[:100], 
            "description": f"{description}\n\n{tag_str}", 
            "tags": tag_list, 
            "categoryId": "42" # Shorts often use 42 (Shorts) or 24 (Entertainment). 1 is Film & Animation. Let's stick to 42 if possible, or back to 22/24. 
            # Actually, standard categoryId 22 (People & Blogs) or 24 (Entertainment) is safer. 
            # YouTube auto-classifies shorts based on file, not categoryId. 
            # Let's keep categoryId as is but rely on title/desc.
            # Leaving as "1" (Film & Animation) is fine, but ensuring title has #Shorts is key.
        }, 
        "status": {"privacyStatus": "public"}
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    res = service.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return res['id']

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    try:
        # 1. BRAIN: Generate Viral Concept
        data = get_concept()
        print(f"📝 Title: {data['title']}")
        print(f"🧠 Reaction: {data.get('target_reaction')} | Hook: {data.get('hook_text')}")
        
        # 2. ASSETS: Generate Content
        # A. Hook Visual (Image -> Video)
        generate_image_freepik(data.get('hook_visual', 'scary face'), "hook_base.jpg")
        hook_video = animate_wan_i2v("hook_base.jpg", "terrifying movement, 4k", max_retries=2)
        if not hook_video: hook_video = "hook_base.jpg" # Fallback to image if anim fails
        
        # B. Body Visuals (Images)
        body_prompts = data.get('visual_prompts', [])
        body_images = []
        for i, p in enumerate(body_prompts):
            fname = f"body_{i}.jpg"
            generate_image_freepik(p, fname)
            body_images.append(fname)
            
        # C. Audio (Hook + Body)
        # Combine text
        full_script = f"{data.get('hook_audio', '')} {data.get('script_body', '')}"
        asyncio.run(make_audio(full_script, "full_audio.mp3"))
        
        # 3. EDIT: Assemble Viral Short
        final_file = "viral_short.mp4"
        create_viral_short(
            hook_video_path=hook_video, 
            body_image_paths=body_images, 
            audio_path="full_audio.mp3", 
            hook_text=data.get('hook_text', 'WAIT FOR IT'), 
            output_filename=final_file
        )
        
        # 4. CAPTIONS: Submagic (Placeholder/Optional)
        submagic = SubmagicClient()
        final_file = submagic.process_video(final_file, data['title'])
        
        # 5. UPLOAD
        vid_id = upload_to_youtube(final_file, data['title'], data['description'], data['hashtags'])
        print(f"🚀 Published: https://youtube.com/shorts/{vid_id}")
        
    except Exception as e:
        print(f"❌ Critical Failure: {e}")
