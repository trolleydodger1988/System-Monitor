"""
Profiling script to identify performance bottlenecks in SystemMonitor.

Run this to see where the application spends most of its time.
"""

import cProfile
import pstats
from pathlib import Path
from pstats import SortKey

from services.system_monitor import get_overview, get_cpu, get_mem, get_swap, get_info
from services.network_service import get_net, get_conns
from services.disk_monitor import get_disk_io, get_disks
from services.gpu_monitor import get_gpu
from config import GPU_AVAILABLE


def profile_system_overview() -> None:
    """Profile the main system overview function."""
    print("Profiling system overview (called by WebSocket)...")
    for _ in range(10):
        get_overview()


def profile_individual_functions() -> None:
    """Profile each monitoring function separately."""
    print("Profiling individual functions...")

    # Run fast functions multiple times
    print("  - Testing fast functions (20 iterations)...")
    for _ in range(20):
        get_cpu()
        get_mem()
        get_swap()
        get_info()
        get_net()
        get_disk_io()
        get_disks()

        if GPU_AVAILABLE:
            get_gpu()

    # Run slow function only a few times
    print("  - Testing slow functions (2 iterations)...")
    for _ in range(2):
        get_conns()  # This is SLOW on Windows!


def run_profiling() -> None:
    """Run profiling and generate reports."""
    profile_output = Path(__file__).parent / "profile_results.prof"

    print("=" * 60)
    print("Starting profiling...")
    print("=" * 60)

    # Profile the code
    profiler = cProfile.Profile()
    profiler.enable()

    profile_system_overview()
    profile_individual_functions()

    profiler.disable()

    # Save to file
    profiler.dump_stats(str(profile_output))
    print(f"\nProfile data saved to: {profile_output}")

    # Print stats
    print("\n" + "=" * 60)
    print("TOP 30 SLOWEST FUNCTIONS (by cumulative time)")
    print("=" * 60)
    stats = pstats.Stats(profiler)
    stats.strip_dirs()
    stats.sort_stats(SortKey.CUMULATIVE)
    stats.print_stats(30)

    print("\n" + "=" * 60)
    print("TOP 30 SLOWEST FUNCTIONS (by total time)")
    print("=" * 60)
    stats.sort_stats(SortKey.TIME)
    stats.print_stats(30)

    print("\n" + "=" * 60)
    print("FUNCTIONS CALLED MOST FREQUENTLY")
    print("=" * 60)
    stats.sort_stats(SortKey.CALLS)
    stats.print_stats(30)

    print("\n" + "=" * 60)
    print("Profiling complete!")
    print("=" * 60)
    print(f"\nAnalyze further with: python -m pstats {profile_output}")


if __name__ == "__main__":
    run_profiling()
