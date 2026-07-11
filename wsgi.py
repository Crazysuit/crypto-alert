"""Render/Gunicorn 生产启动入口。"""
from app import app, monitor


monitor.start()

