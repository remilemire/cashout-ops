# backend/main.py

from dotenv import load_dotenv

from app.core.config import settings

load_dotenv()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG
    )
