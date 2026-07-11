"""Render/Gunicorn 生产启动入口。"""
from app import app, monitor, trading_engine


monitor.start()
trading_engine.start_if_enabled()
