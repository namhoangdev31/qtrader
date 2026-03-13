from collections.abc import Callable
from typing import Any

from qtrader.core.config import Config


class RayCompute:
    """Helper for distributed task execution using Ray (Local Mode)."""
    
    def __init__(self) -> None:
        if not ray.is_initialized():
            ray.init(
                address=Config.RAY_ADDRESS,
                _memory=Config.RAY_MEMORY if Config.RAY_ADDRESS == "auto" else None,
                num_cpus=Config.RAY_CPUS if Config.RAY_ADDRESS == "auto" else None,
                ignore_reinit_error=True
            )

    @staticmethod
    def run_parallel(func: Callable[..., Any], tasks_args: list[tuple]) -> list[Any]:
        """Runs a function in parallel over a list of arguments."""
        remote_func = ray.remote(func)
        futures = [remote_func.remote(*args) for args in tasks_args]
        return ray.get(futures)

    def shutdown(self) -> None:
        ray.shutdown()
