# config.py
import os

# --- API Keys ---
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
SCRAPECREATORS_API_KEY = os.environ.get("SCRAPECREATORS_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

# --- AI Model ---
# This is the variable you can easily swap
# e.g., "gemini-2.5-pro", "gemini-1.5-flash", etc.
GEMINI_MODEL_NAME = "gemini-2.0-flash-exp"

# --- Backend Settings ---
FLASK_PORT = 5000
