"""FastAPI dependencies. The AiCore is built once at startup and stored on
app.state; routes read it from there so every request shares one pipeline,
chat store, retriever, and LLM client.
"""
from fastapi import Request

from app.runtime.analyze import AiCore


def get_core(request: Request) -> AiCore:
    return request.app.state.core
