"""Compatibility shim. M3 implementation now lives in app.supportpilot.m3."""
from .m3 import create_m3_router, init_m3_schema, start_m3_worker, stop_m3_worker

__all__ = ["create_m3_router", "init_m3_schema", "start_m3_worker", "stop_m3_worker"]
