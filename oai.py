import os
from dotenv import load_dotenv
from openai import OpenAI

# Load your API key from .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Noisy OCR song title examples
noisy_titles = [

     "ArethaFranklin&Eurythulcs | SistersAre Doin lForhgmselve | Che sZoomin Whoz QrethaFtanklin & Eurythmits | GistersAre Doin ItF0/Themselve | Whoszoomin; Who? ArethaFtankling Eurythmics | SistersAreDoin lrFo/Themselve | WhogzoominiWhoz arel_ | Sisters | Doin' | emse | Who5zo | Arel"
]

# System prompt to guide the model
system_prompt = (
    "You are a music expert. Normalize the following noisy OCR input into a clean "
    "song title in the format: 'Artist - Song Title'."
)

# Normalize each OCR title
for title in noisy_titles:
    response = client.chat.completions.create(
        model="gpt-4o",  # or "gpt-4o-mini" for cheaper inference
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": title}
        ],
        temperature=0.2,
        max_tokens=50
    )
    
    normalized = response.choices[0].message.content.strip()
    print(f"\n🧪 OCR: {title}\n✅ Normalized: {normalized}")
