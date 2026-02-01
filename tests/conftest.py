"""pytest 설정."""

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-for-ci")

from dotenv import load_dotenv

load_dotenv()
