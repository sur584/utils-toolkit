"""临时文件管理"""
import shutil
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager


@asynccontextmanager
async def temp_workspace(prefix: str = "transcript_"):
    """Create a temporary directory and auto-cleanup."""
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
