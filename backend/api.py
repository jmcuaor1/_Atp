"""
Punto de entrada legacy para uvicorn: uvicorn api:app --reload
La aplicación vive en app.main.
"""

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
