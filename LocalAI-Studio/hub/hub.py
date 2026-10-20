#!/usr/bin/env python3
"""로컬 AI 스튜디오 허브.

표준 라이브러리 + Pillow 만 사용합니다 (ComfyUI 포터블의 python_embeded 로 실행).
역할: Ollama / ComfyUI 실행, 웹 UI 제공, 모델 설치, 이미지 작업(마스크 크롭·합성·타일 리파인) 조율,
      이미지 메타데이터 읽기/제거(meta.py), ComfyUI 그래프 생성·사용자 워크플로 실행(flows.py).
"""
import base64, csv, hashlib, importlib, io, json, math, os, random, re, shutil, subprocess, sys, tempfile, threading, time, uuid, webbrowser, zipfile
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

# ComfyUI 포터블의 python_embeded 는 ._pth 설정 때문에 스크립트 폴더를 import 경로에 넣지 않으므로 직접 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flows
import meta
import bgremove
import modelinfo
import sam
import tts
import tts_models
import vmix

# ── 서버 코드는 기능별로 hub/server/ 에 나뉘어 있어요(01_base.py → 14_http.py).
#    모두 이 모듈과 같은 공간에서 실행되므로 예전처럼 hub.이름 으로 쓰고 바꿀 수 있어요.
_SERVER = Path(__file__).resolve().parent / "server"
for _part in sorted(_SERVER.glob("[0-9][0-9]_*.py")):
    exec(compile(_part.read_text(encoding="utf-8"), str(_part), "exec"), globals())
del _part


if __name__ == "__main__":
    main()
