"""
inspire/ — Qt-free VLM + Unsplash moodboard pipeline and profile-chat helper.

This logic was previously embedded in sensi_pyqt.py (wrapped in QThread workers).
It is pure Python (langchain + httpx + stdlib), so it lives here now and can be
called from either the FastAPI backend or the legacy PyQt shell. The PyQt app
keeps its own copies during the migration as the parity reference; once the web
frontend reaches parity and PyQt is removed, this becomes the single source.
"""

from inspire.pipeline import run_inspire_round, profile_chat_reply

__all__ = ["run_inspire_round", "profile_chat_reply"]
