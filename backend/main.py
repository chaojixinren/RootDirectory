"""Nexus入口模块."""

import asyncio
import os

import uvicorn

from backend.api.main import app
from backend.config.settings import get_settings


def main():
    """CLI入口."""
    settings = get_settings()
    
    uvicorn.run(
        "backend.api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        workers=1 if settings.server.reload else settings.server.workers,
        log_level=settings.server.log_level,
    )


if __name__ == "__main__":
    main()
