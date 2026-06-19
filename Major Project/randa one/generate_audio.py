import pyttsx3, os

os.makedirs("static/audio", exist_ok=True)

tts_texts = {
    "positive": "This is a positive review. You can buy this product.",
    "neutral": "This review is neutral. Check more details before deciding.",
    "negative": "This is a negative review. Better to avoid this product."
}

for label, text in tts_texts.items():
    engine = pyttsx3.init()  

    try:
        voices = engine.getProperty("voices")
        female_id = None
        for v in voices:
            name = (getattr(v, "name", "") or "").lower()
            if "female" in name or "zira" in name or "susan" in name:
                female_id = v.id
                break
        if female_id:
            engine.setProperty("voice", female_id)
    except Exception:
        pass

    engine.setProperty("rate", 160)

    out_path = f"static/audio/{label}.wav"
    print(f"Generating: {out_path}")
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    engine.stop()

print("✅ Done. Files are in static/audio/")

