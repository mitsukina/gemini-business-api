import os
import uvicorn
from auth import accounts
from main import app
from config import HOST, PORT, PROXY

if __name__ == "__main__":
    if not accounts:
        print("Error: No accounts loaded.")
        exit(1)
    
    # 设置代理环境变量
    if PROXY:
        os.environ['HTTP_PROXY'] = PROXY
        os.environ['HTTPS_PROXY'] = PROXY
        print(f"Using proxy: {PROXY}")
    
    print(f"Starting server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)