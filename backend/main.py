# backend/main.py

from dotenv import load_dotenv

from app.core.config import settings

load_dotenv()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5001, reload=settings.DEBUG)
