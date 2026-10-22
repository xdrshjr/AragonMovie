import os
import shutil
import subprocess

import imageio_ffmpeg

root = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "AragonMovie", "resources")
expected = os.path.join(root, "app", "bin", "ffmpeg.exe")
os.environ["IMAGEIO_FFMPEG_EXE"] = expected
os.environ["PATH"] = os.path.join(root, "app", "bin") + os.pathsep + os.environ.get("PATH", "")

exe = imageio_ffmpeg.get_ffmpeg_exe()
print("expected exists:", os.path.exists(expected))
print("imageio exe:", exe, "exists:", os.path.exists(exe))
print("which ffmpeg:", shutil.which("ffmpeg"))
print("which ffprobe:", shutil.which("ffprobe"))
print(subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0])

import moviepy  # noqa: E402
from moviepy import VideoFileClip  # noqa: E402,F401

print("moviepy import ok")
