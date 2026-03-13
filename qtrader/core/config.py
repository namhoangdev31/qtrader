import os
from dotenv import load_dotenv
from typing import Optional

# Load .env file from the root directory
load_dotenv()

class Config:
    """
    Centralized configuration management for QTrader.
    Access variables from .env with fallbacks.
    """
    
    # Binance
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    
    # Coinbase
    COINBASE_API_KEY = os.getenv("COINBASE_API_KEY", "")
    COINBASE_API_SECRET = os.getenv("COINBASE_API_SECRET", "")
    
    # Data Lake
    DATALAKE_URI = os.getenv("DATALAKE_URI", "./data_lake")
    S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
    S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
    
    # ML & Simulation
    MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5050")
    MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "qtrader_v4_autonomous")
    SIMULATE_MODE = os.getenv("SIMULATE_MODE", "True").lower() == "true"
    
    # Ray Resources
    RAY_ADDRESS = os.getenv("RAY_ADDRESS", "auto")
    RAY_MEMORY = os.getenv("RAY_MEMORY", "4G")
    RAY_CPUS = int(os.getenv("RAY_CPUS", "2"))
    
    # Operational
    MONTHLY_BUDGET = float(os.getenv("MONTHLY_CLOUD_BUDGET", "1000.0"))
    DB_PATH = os.getenv("DB_PATH", "./qtrader.db")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # PostgreSQL Persistence
    DB_DRIVER = os.getenv("DATABASE_DRIVER", "org.postgresql.Driver")
    DB_TYPE = os.getenv("DATABASE_TYPE", "postgres")
    DB_HOST = os.getenv("DATABASE_HOST", "host.docker.internal")
    DB_PORT = os.getenv("DATABASE_PORT", "5432")
    DB_USER = os.getenv("DATABASE_USERNAME", "sanauto")
    DB_PASS = os.getenv("DATABASE_PASSWORD", "secret")
    DB_NAME = os.getenv("DATABASE_NAME", "qtrader")
    raw_url = os.getenv("DATABASE_URL", "")
    if raw_url.startswith("jdbc:"):
        raw_url = raw_url.replace("jdbc:", "")
    
    DB_URL = raw_url or f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    DB_MAX_CONN = int(os.getenv("DATABASE_MAX_CONNECTIONS", "100"))
    DB_SSL = os.getenv("DATABASE_SSL_ENABLED", "false").lower() == "true"
    DB_SYNC = os.getenv("DATABASE_SYNCHRONIZE", "false").lower() == "true"

    @classmethod
    def validate(cls):
        """Basic validation to ensure critical keys are present in production."""
        if not cls.SIMULATE_MODE:
            if not cls.BINANCE_API_KEY or not cls.COINBASE_API_KEY:
                print("WARNING: Live mode enabled but API keys are missing!")
