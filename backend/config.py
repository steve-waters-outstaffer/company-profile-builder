# config.py
import os
from google.cloud import firestore

# --- API Keys ---
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
SCRAPECREATORS_API_KEY = os.environ.get("SCRAPECREATORS_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

# --- AI Model (Load from Firestore, fallback to env/default) ---
def get_gemini_model():
    """Load Gemini model from Firestore config. Fallback to env var or default."""
    try:
        db = firestore.Client()
        config_doc = db.collection("config").document("ai_models").get()
        if config_doc.exists:
            model = config_doc.get("ai_model")
            if model:
                return model
    except Exception as e:
        print(f"[CONFIG] Warning: Could not load model from Firestore: {e}")
    
    # Fallback: env var or hardcoded default
    return os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")

GEMINI_MODEL_NAME = get_gemini_model()

# --- Backend Settings ---
FLASK_PORT = 5000
