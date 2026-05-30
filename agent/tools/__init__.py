from tools.benchmark import run_benchmark, cancel_benchmark, get_benchmark_logs
from tools.query import list_jobs, get_job_status, get_run_results, compare_runs, search_runs
from tools.config import list_configs, save_config, delete_config, run_saved_config

ALL_TOOLS = [
    run_benchmark,
    cancel_benchmark,
    get_benchmark_logs,
    list_jobs,
    get_job_status,
    get_run_results,
    compare_runs,
    search_runs,
    list_configs,
    save_config,
    delete_config,
    run_saved_config,
]
