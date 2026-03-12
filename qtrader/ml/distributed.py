import ray
from typing import Callable, Any, List

class RayCompute:
    """Helper for distributed task execution using Ray (Local Mode)."""
    
    def __init__(self) -> None:
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)

    @staticmethod
    def run_parallel(func: Callable[..., Any], tasks_args: List[tuple]) -> List[Any]:
        """Runs a function in parallel over a list of arguments."""
        remote_func = ray.remote(func)
        futures = [remote_func.remote(*args) for args in tasks_args]
        return ray.get(futures)

    def shutdown(self) -> None:
        ray.shutdown()
