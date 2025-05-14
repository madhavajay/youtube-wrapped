# main.py
import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([
        sys.executable,
        "-m", "uvicorn",
        "app:syftbox.app",
        "--reload",
    ])
