import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
E2B_API_KEY = os.getenv("E2B_API_KEY", "")
MLFLOW_TRACKING_URI = "http://127.0.0.1:5000"
REDIS_URL = "redis://localhost:6379/0"
DATABASE_URL = os.getenv("DATABASE_URL", "")
