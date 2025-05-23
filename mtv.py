import cv2
import numpy as np
import easyocr
from datetime import datetime
import subprocess
import os
import time
import json
from collections import Counter
from openai import OpenAI
from dotenv import load_dotenv
import signal
# Load API key from .env
load_dotenv()
STREAM_URL = os.getenv("STREAM_URL")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Constants
W, H = 720, 576
frame_size = W * H * 3
COLLECTION_WINDOW = 20  # seconds
MAX_COLLECTION = 4
NORMALIZED_FILE = "normalized_ocr_dataset.txt"
consecutive_failures = 0
max_failures = 20  # number of allowed failures in a row before exiting
# Setup
reader = easyocr.Reader(['en'], gpu=True)
os.makedirs("debug_frames", exist_ok=True)

cmd = [
    'ffmpeg',
    '-i', STREAM_URL,
    '-f', 'image2pipe',
    '-pix_fmt', 'bgr24',
    '-vcodec', 'rawvideo',
    '-loglevel', 'quiet',
    '-'
]
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**8)

# State
last_text = ""
tmp_detections = []
detection_start_time = None
gen_timer = None
collected_data = []
collection_start = None

# Helpers

def cleanup():
    print("🧹 Cleaning up processes...")
    try:
        process.send_signal(signal.SIGINT)  # Try graceful shutdown first
        time.sleep(1)
        process.kill()  # Force kill if still alive
    except Exception as e:
        print(f"⚠️ Failed to kill ffmpeg: {e}")

    cv2.destroyAllWindows()


def check_collection_timeout():
    global collection_start, collected_data
    if collection_start is not None:
        now = time.time()
        if len(collected_data) >= 1 and (now - collection_start) >= COLLECTION_WINDOW:
            normalize_and_save(collected_data)
            collected_data = []
            collection_start = None
            print ("TIMER 0")

def is_clean(s):
    s = s.strip()
    return len(s) > 1 and s.isascii() and s.replace(" ", "").replace("-", "").isalpha()

def should_start_collection(text):
    return len(text) > 10

def collect_variant(most_common):
    print (most_common)
    global collection_start, collected_data
    now = time.time()
    if collection_start is None:
        print ("COLECT BEGIN")
        collection_start = now
        collected_data.append({"input": most_common, "artist": "", "song": "", "target": ""})
    elif (now - collection_start) <= COLLECTION_WINDOW:
        if len(collected_data) < MAX_COLLECTION:
            print ("ADD MORE")
            collected_data.append({"input": most_common, "artist": "", "song": "", "target": ""})

def normalize_and_save(data_block):
    combined_input = " | ".join([d["input"] for d in data_block])
    system_prompt = (
          "You are a strict normalizer for noisy OCR text from music videos.\n"
          "Given several noisy variants of the same song title, output ONLY the normalized music title.\n"
          "The output format must be: 'Artist | Song Title'.\n"
          "No extra words. No explanations. No commentary. Only the normalized title.\n"
          "Example: 'The Beatles | Yesterday'.\n"
          "Ignore irrelevant phrases like 'MUSIC TELEVISION'."
                    )


#    system_prompt = (
#        "You are a music expert. Given several noisy OCR text variants of the same song title, "
#        "normalize them into a single correct music title in the format: 'Artist | Song Title'. "
#        "Ignore irrelevant phrases like 'MUSIC TELEVISION'."
#                    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": combined_input}
            ],
            temperature=0.2,
            max_tokens=50
        )
        print(response.usage)

        normalized_text = response.choices[0].message.content.strip()
        if '|' in normalized_text:
            artist, song = normalized_text.split('|', 1)
            artist = artist.strip()
            song = song.strip()
            target = f"{artist} - {song}"
        else:
            artist = ""
            song = normalized_text
            target = normalized_text

        print(f"\n🎯 Normalized: {target}")

        with open(NORMALIZED_FILE, "a", encoding="utf-8") as f:
            for entry in data_block:
                entry.update({"artist": artist, "song": song, "target": target})
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("❌ GPT normalization failed:", e)

# Main loop
print("✅ Stream opened. OCR running with smart collection and normalization...")

while True:
    raw_frame = process.stdout.read(frame_size)
    if len(raw_frame) != frame_size:
        consecutive_failures += 1
        print(f"⚠️ Incomplete frame or stream loss detected ({consecutive_failures}/{max_failures})...")
        time.sleep(1)  # small delay to allow recovery
        if consecutive_failures >= max_failures:
            print("❌ Too many failures, exiting OCR...")
            break
        continue  # skip processing this bad frame
    else:
        consecutive_failures = 0  # Reset on successful frame


    frame = np.frombuffer(raw_frame, np.uint8).reshape((H, W, 3))
    cropped = frame[H//2:H, 0:W//2]

    thresh = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    check_collection_timeout()
    try:
        results = reader.readtext(thresh)
        cleaned_results = [r[1].strip() for r in results if is_clean(r[1])]
        if not cleaned_results:
            continue
        combined_text = " | ".join(cleaned_results)
        now_time = time.time()

        if detection_start_time is None:
            detection_start_time = now_time
        if gen_timer is None:
            gen_timer = now_time
            continue
        if len(combined_text) < 5:
            continue
        if "|" in combined_text and combined_text != last_text and combined_text not in tmp_detections and now_time - detection_start_time <= 1 :
            tmp_detections.append(combined_text)
            if "MUSIC " in combined_text.upper():
                    continue  # Skip this one
            last_text = combined_text
            if should_start_collection(combined_text):
                collect_variant(combined_text)
        detection_start_time = None
        if now_time - gen_timer >= 60:
                print ("CLEAR TMP DETECT")
                gen_timer = None
                tmp_detections = []
    except Exception as e:
        print(f"❌ OCR failed: {e}")
cleanup()
exit(0)
#process.terminate()
#cv2.destroyAllWindows()
