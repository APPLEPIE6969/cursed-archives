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
import yt_dlp

# --- 🛠️ COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import *
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
from google.genai import types
import io

# --- CONFIGURATION ---
def get_secret(key):
    val = os.environ.get(key)
    return val.strip() if val else ""

GROQ_KEY = get_secret("GROQ_API_KEY")
YT_CLIENT_ID = get_secret("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = get_secret("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = get_secret("YOUTUBE_REFRESH_TOKEN")
HF_TOKEN = get_secret("HF_TOKEN") 
POLLINATIONS_API_KEY = get_secret("POLLINATIONS_API_KEY")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
SUBMAGIC_API_KEY = get_secret("SUBMAGIC_API_KEY")
CREATOMATE_API_KEY = get_secret("CREATOMATE_API_KEY")
FREEPIK_API_KEY = get_secret("FREEPIK_API_KEY")

# --- HELPER FUNCTIONS ---
def upload_to_temp_host(file_path):
    print("      ...Uploading to temp host (file.io / tmpfiles.org)...")
    
    # Attempt 1: file.io
    try:
        with open(file_path, 'rb') as f:
            res = requests.post('https://file.io', files={'file': f}, data={'expires': '1d'}, timeout=30)
        
        if res.status_code == 200:
            link = res.json().get('link')
            print(f"      ...file.io URL: {link}")
            return link
        else:
            print(f"⚠️ file.io upload failed: {res.text}")
    except Exception as e:
        print(f"⚠️ file.io Error: {e}")

    # Attempt 2: tmpfiles.org (Fallback)
    try:
        with open(file_path, 'rb') as f:
            # tmpfiles.org returns HTML directly sometimes, or JSON. API is https://tmpfiles.org/api/v1/upload
            res = requests.post('https://tmpfiles.org/api/v1/upload', files={'file': f}, timeout=30)
            
        if res.status_code == 200:
            data = res.json()
            if data.get('status') == 'success':
                url = data['data']['url']
                # The direct download URL needs adjustment: replace /org/ with /org/dl/
                dl_url = url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                print(f"      ...tmpfiles.org URL: {dl_url}")
                return dl_url
        print(f"⚠️ tmpfiles.org upload failed: {res.text}")
    except Exception as e:
        print(f"⚠️ tmpfiles.org Error: {e}")

    return None 

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
            "- 'music_vibe': One of [suspense, psychological, jumpscare, dark cinematic].\n"
            "- 'music_intensity': low/medium/high.\n"
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
        self.api_key = SUBMAGIC_API_KEY
        if not self.api_key:
            print("[WARN] SUBMAGIC_API_KEY not found! Captions will be skipped.")

    def process_video(self, video_path, title):
        if not self.api_key:
            return video_path

        print(f"[SUBMAGIC] Uploading {video_path}...")
        
        # 1. Upload Video
        upload_url = f"{self.BASE_URL}/projects"
        headers = {"x-api-key": self.api_key} # Content-Type is set by requests for multipart
        
        try:
            # 3: Verify Submagic Upload Payload (Debug)
            # Some APIs need the file tuple to be (filename, file_object, content_type)
            with open(video_path, 'rb') as f:
                # FIX: Send metadata as multipart fields (tuples) instead of 'data' dict
                # requests handles mixed files/data better this way for some endpoints
                # FIX: Use 'data' for metadata, 'files' for the file.
                # requests will properly format this as multipart/form-data
                files = {'file': (os.path.basename(video_path), f, 'video/mp4')}
                data = {
                    'title': title[:100],
                    'language': 'english',
                    'templateName': 'Hormozi 2'
                }
                
                res = requests.post(upload_url, headers=headers, files=files, data=data) 
            
            if res.status_code not in [200, 201]:
                print(f"[WARN] Submagic Upload Failed: {res.status_code} - {res.text}")
                # Debug print
                # print(f"Payload Debug: {files_payload}") 
                return video_path
                
            project_data = res.json().get('data', {}) # Assuming 'data' envelope or direct
            # If API returns direct object
            if 'id' in res.json(): project_data = res.json()
            
            project_id = project_data.get('id')
            if not project_id:
                print(f"[WARN] Submagic: No Project ID returned. {res.text}")
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
                            print("[WARN] Submagic Completed but no URL found.")
                            return video_path
                            
                    elif status == 'failed':
                        print("[ERR] Submagic Processing Failed.")
                        return video_path
                else:
                    print(f"   Polling Error: {status_res.status_code}")
                    
            print("[WARN] Submagic Timeout.")
            return video_path

        except Exception as e:
            print(f"[WARN] Submagic Client Error: {e}")
            return video_path

# --- 2.5. CREATOMATE CLIENT (Fallback Captions) ---
class CreatomateClient:
    BASE_URL = "https://api.creatomate.com/v2/renders"
    
    def __init__(self):
        self.api_key = CREATOMATE_API_KEY
        if not self.api_key:
            print("[WARN] CREATOMATE_API_KEY not found! Fallback will be skipped.")

    def process_video(self, video_path, text_overlay):
        if not self.api_key:
            return video_path

        print(f"[CREATOMATE] Processing {video_path}...")
        
        # 1. Host Video Temporarily (file.io)
        # Creatomate needs a public URL. GitHub Actions local files are not public.
        # We use file.io for ephemeral hosting (auto deletes after download).
        public_url = upload_to_temp_host(video_path)
        if not public_url:
            return video_path
            
        # 2. Trigger Render
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Template from user request
        data = {
          "template_id": "3ec2bf1b-7151-4b5d-a4d3-cb819cfb78ec",
          "modifications": {
            "Video.source": public_url,
            "Text-1.text": text_overlay, # "Your Text And Video Here"
            "Text-2.text": "Create & Automate\n[size 150%]Video[/size]" # Static or dynamic? User snippet had this.
            # Ideally we might want to just caption the audio? 
            # The user snippet seems to be a specific visual template.
            # We will use the caption text provided in args or just the hook text?
            # User said "use this as fallback for some".
            # If this is for captions, Creatomate usually needs a transcription.
            # If this template just adds text overlay, we'll use header text.
            # Let's trust the user wants this specific template applied.
          }
        }
        
        try:
            print("      ...Triggering Render...")
            res = requests.post(self.BASE_URL, headers=headers, json=data)
            
            if res.status_code not in [200, 201, 202]:
                print(f"[WARN] Creatomate Render Req Failed: {res.status_code} - {res.text}")
                return video_path
                
            resp_json = res.json()
            # Handle list or single dict
            if isinstance(resp_json, list):
                render_data = resp_json[0]
            else:
                render_data = resp_json
            render_id = render_data.get('id')
            status = render_data.get('status')
            
            # 3. Poll
            for _ in range(60): # 10 min
                if status == 'succeeded':
                    url = render_data.get('url')
                    print(f"   [OK] Creatomate Success! Downloading...")
                    final_res = requests.get(url)
                    out_path = video_path.replace(".mp4", "_creatomate.mp4")
                    with open(out_path, "wb") as f:
                        f.write(final_res.content)
                    return out_path
                    
                elif status == 'failed':
                    print(f"[ERR] Creatomate Failed: {render_data.get('errorMessage')}")
                    return video_path
                    
                time.sleep(5)
                # Refresh status
                check_res = requests.get(f"{self.BASE_URL}/{render_id}", headers=headers)
                if check_res.status_code == 200:
                    render_data = check_res.json()
                    status = render_data.get('status')
                else:
                    print("pwning polling...")
                    
            return video_path
            
        except Exception as e:
            print(f"[WARN] Creatomate Error: {e}")
            return video_path



# --- 3. IMAGE GENERATOR (Gemini Fallback) ---
def generate_image_gemini(prompt, filename):
    print(f"[IMG] Generating Image (Gemini/Imagen): {filename}...")
    if not GEMINI_API_KEY:
        print("[WARN] GEMINI_API_KEY not found.")
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)
    # User specified priority order
    models = [
        "gemini-3-pro-image-preview",
        "imagen-4-ultra-generate",
        "imagen-4-generate",
        "imagen-4-fast-generate",
        "gemini-2.5-flash-image"
    ]
    
    for model in models:
        try:
            print(f"   Trying model: {model}...")
            # Attempt generation
            # Note: '9:16' is standard for Shorts/Reels in Imagen config
            response = client.models.generate_image(
                model=model,
                prompt=prompt,
                config=types.GenerateImageConfig(
                    aspect_ratio="9:16",
                    person_generation="allow_adult", 
                    safety_filter_level="block_only_high"
                )
            )
            
            if response.generated_images:
                image = response.generated_images[0].image
                image.save(filename)
                print(f"   [OK] Gemini Success ({model})")
                return filename
                
        except Exception as e:
            print(f"   [WARN] Model {model} failed: {e}")
            continue
            
    print("[ERR] All Gemini models failed.")
    return None

# --- 3. IMAGE GENERATOR (Freepik Mystic) ---
def generate_image_freepik(prompt, filename):
    print(f"[IMG] Generating Image (Freepik): {filename}...")
    api_key = FREEPIK_API_KEY
    if not api_key:
        print("[WARN] FREEPIK_API_KEY not found. Using fallback placeholder.")
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
            print(f"[ERR] Freepik Request Failed: {res.text}")
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
                    print("[ERR] Freepik Task Failed.")
                    break
            else:
                print(f"   Polling Error: {check_res.status_code}")

    except Exception as e:
        print(f"[WARN] Image Generation Error: {e}")

    # Fallback
    print("   [WARN] Freepik failed/skipped. Trying Gemini Fallback...")
    gemini_result = generate_image_gemini(prompt, filename)
    if gemini_result:
        return gemini_result
        
    print("   [WARN] Gemini Fallback failed. Using placeholder.")
    PIL.Image.new('RGB', (720, 1280), (50, 50, 50)).save(filename)
    return filename



# --- 3.5 POLLINATIONS AI (Fallback) ---
def animate_pollinations_i2v(image_path, prompt):
    print(f"[POLLINATIONS] Connecting to Pollinations AI (Wan 2.6 Fallback)...")
    
    if not POLLINATIONS_API_KEY:
        print("[WARN] POLLINATIONS_API_KEY not found! Fallback skipped.")
        return None

    # 1. Upload Image to get URL
    image_url = upload_to_temp_host(image_path)
    if not image_url:
        print("[WARN] Failed to upload image for Pollinations.")
        return None

    # 2. Construct URL
    # https://gen.pollinations.ai/video/{prompt}?model=wan&image={image_url}
    # Encode prompt
    enhanced_prompt = f"found footage horror style, {prompt}, cinematic motion, smooth animation"
    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    api_url = f"https://gen.pollinations.ai/video/{encoded_prompt}?model=wan&image={image_url}"
    
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_API_KEY}"
    }

    try:
        print(f"   Requesting video generation...")
        # 3. GET Request (It returns the video content directly or redirects?)
        # User says "Video generation is computationally heavy...".
        # curl -o output.mp4. So it likely streams the response.
        # Timeout needs to be high.
        
        res = requests.get(api_url, headers=headers, stream=True, timeout=300)
        
        if res.status_code == 200:
            final_name = "pollinations_wan.mp4"
            with open(final_name, 'wb') as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"   [OK] Pollinations Success! Saved to {final_name}")
            return final_name
        else:
            print(f"[ERR] Pollinations Failed: {res.status_code} - {res.text}")
            return None

    except Exception as e:
        print(f"[WARN] Pollinations Error: {e}")
        return None

# --- 3. VIDEO GENERATOR (Wan 2.2 I2V) ---
from gradio_client import handle_file

def animate_wan_i2v(image_path, prompt, max_retries=3):
    print(f"[WAN] Connecting to Wan-AI/Wan2.2 (I2V)...")
    
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
            print(f"[WARN] Video Attempt {attempt+1} failed: {e}")
            time.sleep(10)
    
    print("[WARN] All Wan 2.2 attempts failed. Trying Pollinations Fallback...")
    return animate_pollinations_i2v(image_path, prompt)

# --- 4. EDITOR (Viral Engine) ---
def create_viral_short(hook_video_path, body_image_paths, hook_audio_path, body_audio_path, hook_text, output_filename, music_path=None):
    print("[EDIT] Editing Viral Short (Smart Sync)...")
    
    # Load Audios
    hook_audio = AudioFileClip(hook_audio_path)
    body_audio = AudioFileClip(body_audio_path)
    total_audio_duration = hook_audio.duration + body_audio.duration
    
    clips = []
    
    # --- 1. THE HOOK (Synced to Audio) ---
    hook_duration = hook_audio.duration
    
    # Visual Hook: Wan 2.2 generated video OR fallback image
    if os.path.exists(hook_video_path):
        # Determine if video or image
        if hook_video_path.lower().endswith(('.mp4', '.mov', '.avi')):
            video_clip = VideoFileClip(hook_video_path).resize(height=1280)
            # Center crop to 720x1280
            if video_clip.w > 720:
                 video_clip = video_clip.crop(x1=video_clip.w/2 - 360, width=720)
            
            # Logic: If Audio > Video, freeze the last frame. If Audio < Video, cut video.
            if hook_duration > video_clip.duration:
                # Freeze frame extension
                freeze_duration = hook_duration - video_clip.duration
                frozen_frame = video_clip.to_ImageClip(t=video_clip.duration - 0.1).set_duration(freeze_duration)
                hook_clip = concatenate_videoclips([video_clip, frozen_frame])
            else:
                hook_clip = video_clip.subclip(0, hook_duration)
                
        else:
            # Fallback to ImageClip if it's a jpg/png
            hook_clip = ImageClip(hook_video_path).set_duration(hook_duration).resize(height=1280)
            if hook_clip.w > 720:
                 hook_clip = hook_clip.crop(x1=hook_clip.w/2 - 360, width=720)
            # Apply subtle zoom to static hook
            hook_clip = hook_clip.resize(lambda t: 1 + 0.05*t)
        
        # Text Hook: Overlay
        try:
            txt_clip = TextClip(hook_text, fontsize=70, color='white', font='Arial-Bold', stroke_color='black', stroke_width=2, size=(600, None), method='caption')
            txt_clip = txt_clip.set_position('center').set_duration(hook_duration)
            hook_clip = CompositeVideoClip([hook_clip, txt_clip])
        except Exception:
            pass # Silent fail
            
        # Bind audio
        hook_clip = hook_clip.set_audio(hook_audio)
        clips.append(hook_clip)
    else:
        # Emergency fallback if no hook media?
        # Just use black screen? Or skip.
        pass

    # --- 2. THE BODY (Synced to Body Audio) ---
    body_duration = body_audio.duration
    
    if body_duration > 0 and body_image_paths:
        # Calculate duration per image based on BODY audio
        # Logic: Remaining Audio = Total Audio - Hook Duration
        # We want images to fill this exact duration.
        remaining_audio = max(body_duration, 0.1) # Default to body audio clip duration
        num_images = len(body_image_paths)
        duration_per_image = remaining_audio / num_images
        
        for i, img_path in enumerate(body_image_paths):
            if not os.path.exists(img_path): continue
            
            # Create Clip
            img_clip = ImageClip(img_path).set_duration(duration_per_image)
            img_clip = img_clip.resize(height=1280)
            if img_clip.w > 720:
                img_clip = img_clip.crop(x1=img_clip.w/2 - 360, width=720)
            
            # Apply "Ken Burns" (Zoom/Pan)
            effect = random.choice(['zoom_in', 'zoom_out', 'pan'])
            if effect == 'zoom_in':
                img_clip = img_clip.resize(lambda t: 1 + 0.05*t)
            elif effect == 'zoom_out':
                img_clip = img_clip.resize(lambda t: 1.2 - 0.05*t) 
            
            clips.append(img_clip)
        
        # Create body composite (sequence of images)
        # Verify timestamps... concatenate_videoclips handles basic sequencing
        # But we need to set the collective audio for the body part?
        # No, easier to just concat the visual clips first, then set audio? 
        # Actually, let's keep them as a list and concat all at the end.
        pass
    
    # --- 3. DURATION MATCHING ---
    # We now calculate image duration dynamically so no looping is needed.
    # Just validation check.
    current_video_duration = sum([c.duration for c in clips])
    print(f"   [INFO] Video Duration: {current_video_duration:.2f}s | Audio Duration: {total_audio_duration:.2f}s")

    # Concatenate all visual clips (Hook + Body Images + Loops)
    final_video = concatenate_videoclips(clips, method="compose")
    
    # Trim to exact audio duration
    final_video = final_video.subclip(0, total_audio_duration)
    
    # Composite Audio (Hook Audio + Body Audio)
    # Note: concatenate_videoclips might preserve audio if clips have it. 
    # Hook has audio. Body images don't.
    # We need to explicitly set the Body Audio to start after Hook.
    # Safest: Create a composite audio clip.
    # Composite Audio with Music?
    # Logic: script audio is primary. Music is background.
    # If music_path is provided, we mix it here.
    
    primary_audio = concatenate_audioclips([hook_audio, body_audio])
    
    if music_path and os.path.exists(music_path):
        print(f"   [MUSIC] Mixing background music: {music_path}")
        try:
             bg_music = AudioFileClip(music_path)
             # Loop if too short
             if bg_music.duration < final_duration:
                 # Calculate loops needed
                 n_loops = int(final_duration / bg_music.duration) + 1
                 bg_music = concatenate_audioclips([bg_music] * n_loops)
             
             bg_music = bg_music.subclip(0, final_duration)
             bg_music = bg_music.volumex(0.35) # Increased volume (was 0.25)
             
             final_audio = CompositeAudioClip([primary_audio, bg_music])
        except Exception as e:
             print(f"[WARN] Music Mix Error: {e}")
             final_audio = primary_audio
    else:
        final_audio = primary_audio

    final_video = final_video.set_audio(final_audio)
    
    # Ensure exact duration match
    # STRICT SHORTS LIMIT: 59 seconds max to be safe.
    final_duration = min(final_video.duration, 59.0)
    final_video = final_video.set_duration(final_duration)
    
    final_video.write_videofile(output_filename, fps=24, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
    return output_filename

def generate_audio_kokoro(text, filename):
    print("   [TTS] Generating audio (Kokoro TTS)...")
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
        print(f"   [WARN] Kokoro Init Error: {e}")
        raise e

async def make_audio(text, filename):
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, generate_audio_kokoro, text, filename)
        print("   [OK] Kokoro TTS success.")
    except Exception as e:
        print(f"   [WARN] Kokoro TTS failed: {e}. Switching to EdgeTTS fallback...")
        try:
            await edge_tts.Communicate(text, "en-US-ChristopherNeural").save(filename)
            print("   ✅ EdgeTTS success.")
        except Exception as e2:
             print(f"   [ERR] All TTS failed: {e2}")
             raise e2

# --- 4.5 MUSIC ENGINE ---
class MusicEngine:
    TAG_MAP = {
        "suspense": "dark ambient horror music no copyright",
        "psychological": "psychological thriller background music no copyright",
        "jumpscare": "horror chase music phonk no copyright",
        "dark cinematic": "dark cinematic horror soundtrack no copyright"
    }

    def __init__(self):
        pass

    def select_song(self, vibe, intensity):
        search_query = self.TAG_MAP.get(vibe, "horror ambient music no copyright")
        if intensity == "high":
            search_query += " intense"
        
        print(f"[MUSIC] MusicEngine: Search Query = '{search_query}'")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'default_search': 'ytsearch1',
            'noplaylist': True,
            'quiet': True,
            'extract_flat': True # Just get metadata first
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                if 'entries' in info and info['entries']:
                    video_info = info['entries'][0]
                    return video_info['url'], video_info['title']
        except Exception as e:
            print(f"[WARN] Music Search Failed: {e}")
            
        return None, None

    def download_song(self, url, filename="music.mp3"):
        print(f"[DL] Downloading Music: {url}...")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': filename,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'overwrites': True
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            # yt-dlp appends extension to outtmpl if not present in some cases,
            # but FFmpegExtractAudio usually ensures it ends in .mp3
            # We check if file exists, else try appending .mp3
            final_path = filename
            if not os.path.exists(final_path):
                 if os.path.exists(final_path + ".mp3"):
                     final_path += ".mp3"
            
            return final_path
        except Exception as e:
            print(f"[WARN] Music Download Failed: {e}")
            return None

def add_horror_music(video_path, script_vibe="suspense", intensity="medium"):
    """
    Modular function to add horror music to an existing video.
    """
    print(f"[MUSIC] Adding Horror Music ({script_vibe}/{intensity}) to {video_path}...")
    engine = MusicEngine()
    url, title = engine.select_song(script_vibe, intensity)
    
    if not url:
        print("[WARN] No music found.")
        return video_path
        
    music_file = "temp_music.mp3"
    downloaded_path = engine.download_song(url, music_file)
    
    if not downloaded_path or not os.path.exists(downloaded_path):
        print("[WARN] Music download failed.")
        return video_path
        
    # Mix Audio
    try:
        video = VideoFileClip(video_path)
        music = AudioFileClip(downloaded_path)
        
        # Loop music if video is longer
        if music.duration < video.duration:
            music = music.fx(vfx.loop, duration=video.duration) # vfx needed? usually afx loop
            # audio loop is different in moviepy 1.0.3
            # music = music.loop(duration=video.duration) # Try standard loop
            pass # See below for safer composition
            
        # Cut to video length
        music = music.subclip(0, video.duration)
        
        # Ducking (Volume 0.3)
        music = music.volumex(0.3)
        
        # Composite
        final_audio = CompositeAudioClip([video.audio, music])
        final_video = video.set_audio(final_audio)
        
        output_path = video_path.replace(".mp4", "_scored.mp4")
        final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', logger=None)
        
        return output_path
        
    except Exception as e:
        print(f"[WARN] Audio Mixing Failed: {e}")
        return video_path

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
            "categoryId": "24" # Entertainment (Safe default)
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
            
        # C. Audio (Split for Smart Sync)
        print("   [AUDIO] Generating Split Audio...")
        hook_audio_text = data.get('hook_audio', '')
        body_audio_text = data.get('script_body', '')
        
        async def generate_all_audio():
            await asyncio.gather(
                make_audio(hook_audio_text, "hook.mp3"),
                make_audio(body_audio_text, "body.mp3")
            )
            
        asyncio.run(generate_all_audio())
        

        
        # D. Music Selection
        print("   [MUSIC] Searching for Horror Music...")
        music_engine = MusicEngine()
        music_vibe = data.get('music_vibe', 'suspense')
        music_intensity = data.get('music_intensity', 'medium')
        
        song_url, song_title = music_engine.select_song(music_vibe, music_intensity)
        bg_music_path = None
        if song_url:
            print(f"   [MUSIC] Selected: {song_title}")
            bg_music_path = music_engine.download_song(song_url, "bg_music.mp3")

        # 3. EDIT: Assemble Viral Short
        final_file = "viral_short.mp4"
        create_viral_short(
            hook_video_path=hook_video, 
            body_image_paths=body_images, 
            hook_audio_path="hook.mp3",
            body_audio_path="body.mp3",
            hook_text=data.get('hook_text', 'WAIT FOR IT'), 
            output_filename=final_file,
            music_path=bg_music_path
        )
        
        # 4. CAPTIONS: Submagic -> Creatomate Fallback
        
        # Try Submagic first
        submagic = SubmagicClient()
        captioned_file = submagic.process_video(final_file, data['title'])
        
        if captioned_file == final_file:
             # Submagic failed or skipped. Try Creatomate.
             creatomate = CreatomateClient()
             # Use Hook text or Title for overlay? User provided template suggesting text overlay.
             # We'll use the Hook Text as the primary overlay content.
             captioned_file = creatomate.process_video(final_file, data.get('hook_text', 'WATCH THIS'))
             
        final_file = captioned_file
        
        # 5. UPLOAD
        vid_id = upload_to_youtube(final_file, data['title'], data['description'], data['hashtags'])
        print(f"[UPLOAD] Published: https://youtube.com/shorts/{vid_id}")
        
    except Exception as e:
        print(f"[CRITICAL] Failure: {e}")
