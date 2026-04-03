"""MLX Optimization Configuration for Mac M4.

Provides optimized model loading and inference configuration for Apple Silicon.
Auto-detects M4 chip capabilities and configures models accordingly.
"""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("qtrader.ml.mlx_config")


@dataclass(slots=True)
class M4ChipInfo:
    """Detected M4 chip information."""

    chip: str  # "M4", "M4 Pro", "M4 Max", "M4 Ultra"
    cpu_cores: int
    gpu_cores: int
    neural_engine_cores: int
    unified_memory_gb: int
    memory_bandwidth_gbps: int
    is_apple_silicon: bool


@dataclass(slots=True)
class MLXConfig:
    """MLX optimization configuration."""

    # Model precision
    default_dtype: str = "float16"  # float16 for M4, bfloat16 for M4 Pro+
    quantization: str | None = None  # "4bit", "8bit", or None

    # Inference settings
    max_tokens: int = 256
    temperature: float = 0.3
    top_p: float = 0.9

    # Memory management
    memory_limit_gb: float = 0.0  # 0 = auto
    cache_size_mb: int = 512

    # Parallelism
    num_threads: int = 0  # 0 = auto (uses all performance cores)

    # Model-specific settings
    chronos_batch_size: int = 1
    tabpfn_n_estimators: int = 4
    phi2_max_context: int = 2048


def detect_m4_chip() -> M4ChipInfo:
    """Detect M4 chip capabilities."""
    is_apple_silicon = platform.machine() == "arm64"

    if not is_apple_silicon:
        return M4ChipInfo(
            chip="Unknown",
            cpu_cores=0,
            gpu_cores=0,
            neural_engine_cores=0,
            unified_memory_gb=0,
            memory_bandwidth_gbps=0,
            is_apple_silicon=False,
        )

    # Try to get chip info from system_profiler
    import subprocess

    try:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout.lower()

        # Detect chip type
        if "m4 ultra" in output:
            chip = "M4 Ultra"
            cpu_cores = 32
            gpu_cores = 80
            neural_engine_cores = 32
            memory_bandwidth_gbps = 800
        elif "m4 max" in output:
            chip = "M4 Max"
            cpu_cores = 16
            gpu_cores = 40
            neural_engine_cores = 16
            memory_bandwidth_gbps = 546
        elif "m4 pro" in output:
            chip = "M4 Pro"
            cpu_cores = 14
            gpu_cores = 20
            neural_engine_cores = 16
            memory_bandwidth_gbps = 273
        elif "m4" in output:
            chip = "M4"
            cpu_cores = 10
            gpu_cores = 10
            neural_engine_cores = 16
            memory_bandwidth_gbps = 120
        else:
            chip = "Apple Silicon (unknown)"
            cpu_cores = 0
            gpu_cores = 0
            neural_engine_cores = 0
            memory_bandwidth_gbps = 0

        # Detect memory (approximate)
        mem_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        mem_bytes = int(mem_result.stdout.strip())
        unified_memory_gb = mem_bytes // (1024**3)

    except Exception:
        chip = "Apple Silicon (detection failed)"
        cpu_cores = 0
        gpu_cores = 0
        neural_engine_cores = 0
        unified_memory_gb = 0
        memory_bandwidth_gbps = 0

    return M4ChipInfo(
        chip=chip,
        cpu_cores=cpu_cores,
        gpu_cores=gpu_cores,
        neural_engine_cores=neural_engine_cores,
        unified_memory_gb=unified_memory_gb,
        memory_bandwidth_gbps=memory_bandwidth_gbps,
        is_apple_silicon=True,
    )


def get_optimized_config(chip: M4ChipInfo | None = None) -> MLXConfig:
    """Get optimized MLX configuration for the detected chip."""
    if chip is None:
        chip = detect_m4_chip()

    config = MLXConfig()

    if not chip.is_apple_silicon:
        logger.warning("[MLX] Not running on Apple Silicon, using fallback config")
        config.default_dtype = "float32"
        config.num_threads = 4
        return config

    # Configure based on chip tier
    if "Ultra" in chip.chip:
        config.default_dtype = "bfloat16"
        config.num_threads = 24
        config.memory_limit_gb = min(chip.unified_memory_gb * 0.7, 128)
        config.chronos_batch_size = 8
        config.phi2_max_context = 4096
    elif "Max" in chip.chip:
        config.default_dtype = "bfloat16"
        config.num_threads = 12
        config.memory_limit_gb = min(chip.unified_memory_gb * 0.6, 64)
        config.chronos_batch_size = 4
        config.phi2_max_context = 4096
    elif "Pro" in chip.chip:
        config.default_dtype = "float16"
        config.num_threads = 10
        config.memory_limit_gb = min(chip.unified_memory_gb * 0.5, 36)
        config.chronos_batch_size = 2
        config.phi2_max_context = 2048
    else:  # Base M4
        config.default_dtype = "float16"
        config.num_threads = 8
        config.memory_limit_gb = min(chip.unified_memory_gb * 0.5, 16)
        config.chronos_batch_size = 1
        config.phi2_max_context = 2048

    # Quantization for memory-constrained setups
    if chip.unified_memory_gb <= 16:
        config.quantization = "4bit"
    elif chip.unified_memory_gb <= 32:
        config.quantization = "8bit"

    logger.info(
        f"[MLX] Optimized config for {chip.chip}: "
        f"dtype={config.default_dtype}, "
        f"quantization={config.quantization}, "
        f"threads={config.num_threads}, "
        f"memory_limit={config.memory_limit_gb:.0f}GB"
    )

    return config


def get_model_recommendations(chip: M4ChipInfo | None = None) -> dict[str, Any]:
    """Get model size recommendations for the detected chip."""
    if chip is None:
        chip = detect_m4_chip()

    if not chip.is_apple_silicon:
        return {
            "chronos": "small (9M params, ~20MB)",
            "tabpfn": "standard (~1.5GB)",
            "phi2": "not recommended (use rule-based fallback)",
            "total_memory_mb": 1700,
            "warning": "Not running on Apple Silicon. MLX optimization unavailable.",
        }

    if "Ultra" in chip.chip:
        return {
            "chronos": "large (710M params, ~1.4GB)",
            "tabpfn": "standard (~1.5GB)",
            "phi2": "full FP16 (5.4GB)",
            "total_memory_mb": 8300,
            "note": "All models can run simultaneously with room for trading engine.",
        }
    elif "Max" in chip.chip:
        return {
            "chronos": "large (710M params, ~1.4GB)",
            "tabpfn": "standard (~1.5GB)",
            "phi2": "FP16 (5.4GB) or 8-bit quantized (2.7GB)",
            "total_memory_mb": 8300,
            "note": "All models fit comfortably. Consider 8-bit Phi-2 for more headroom.",
        }
    elif "Pro" in chip.chip:
        return {
            "chronos": "base (200M params, ~400MB)",
            "tabpfn": "standard (~1.5GB)",
            "phi2": "8-bit quantized (2.7GB)",
            "total_memory_mb": 4600,
            "note": "Good balance. All three models fit within 32GB RAM.",
        }
    else:  # Base M4
        return {
            "chronos": "small (9M params, ~20MB)",
            "tabpfn": "standard (~1.5GB)",
            "phi2": "4-bit quantized (1.4GB) or rule-based fallback",
            "total_memory_mb": 2920,
            "note": "Tight on memory with 16GB. Use small Chronos and quantized Phi-2.",
        }
