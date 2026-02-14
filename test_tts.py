import asyncio
from main import make_audio

async def test_tts():
    print("Testing TTS fallback logic...")
    try:
        await make_audio("This is a test of the Kokoro TTS system.", "test_tts.mp3")
        print("[OK] TTS Test Completed.")
    except Exception as e:
        print(f"[ERR] TTS Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_tts())
