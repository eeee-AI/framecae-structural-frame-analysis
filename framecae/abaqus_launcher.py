"""Optional local Abaqus discovery; explicit user configuration takes priority."""
import os,shutil
from pathlib import Path

def find_launcher():
    configured=os.environ.get('ABAQUS_LAUNCHER')
    if configured:return Path(configured)
    candidates=[shutil.which('abaqus'),r'D:\abaqus\2025\Commands\abaqus.bat',r'D:\SIMULIA\Commands\abq2022.bat',r'C:\SIMULIA\Commands\abaqus.bat']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():return Path(candidate)
    return Path(r'D:\SIMULIA\Commands\abaqus.bat')
