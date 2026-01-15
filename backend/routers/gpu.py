"""
GPU monitoring router.

Provides /api/gpu endpoint.
"""

from fastapi import APIRouter

from services.gpu_monitor import get_gpu

router = APIRouter(prefix="/api", tags=["gpu"])


@router.get("/gpu")
def gpu():
    """
    Get GPU statistics for all available GPUs.

    Returns:
        list: List of GPU info dicts with load, memory, temperature, etc.
    """
    return get_gpu()
