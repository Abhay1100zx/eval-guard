import os

# Hermetic tests: never read the real provider from .env (load_dotenv doesn't override existing env vars).
os.environ["LLM_PROVIDER"] = "mock"
