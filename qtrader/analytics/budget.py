import logging


class CloudBudgetGuard:
    """
    Prevents 'Cloud Cost Explosion' (v4).
    Monitors Ray/K8s resource usage and kills jobs if budget is exceeded.
    """
    
    def __init__(self, monthly_budget: float = 1000.0) -> None:
        self.monthly_budget = monthly_budget
        self.current_spend = 0.0
        self.is_throttled = False

    def update_spend(self, spend: float) -> None:
        """Updates current cloud spend (e.g., from AWS/GCP API)."""
        self.current_spend = spend
        if self.current_spend >= self.monthly_budget:
            self.trigger_budget_circuit_breaker()

    def trigger_budget_circuit_breaker(self) -> None:
        """Kills expensive training jobs."""
        logging.critical(
            "BUDGET | Monthly budget of $%s reached! Throttling all non-critical compute.",
            self.monthly_budget,
        )
        self.is_throttled = True
        # Future: Call ray.shutdown() or kubectl delete jobs

    def check_job_eligibility(self, estimated_cost: float) -> bool:
        """Validates if a new training job can start."""
        if self.is_throttled:
            return False
        if (self.current_spend + estimated_cost) > (self.monthly_budget * 1.1):
            logging.warning("BUDGET | Job rejected: would exceed 110% of monthly budget info.")
            return False
        return True

class ResourceGuardrail:
    """Enforces execution limits on Ray tasks."""
    
    @staticmethod
    def get_job_config():
        return {
            "num_cpus": 2,
            "num_gpus": 0,
            "memory": 4 * 1024 * 1024 * 1024,  # 4GB
            "timeout": 3600,  # 1 hour Max TTL
        }
