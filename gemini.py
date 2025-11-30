import uvicorn
from auth import accounts
from main import app

if __name__ == "__main__":
    if not accounts:
        print("Error: No accounts loaded.")
        exit(1)
    uvicorn.run(app, host="0.0.0.0", port=8000)