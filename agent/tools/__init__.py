from tools.benchmark import run_benchmark, cancel_benchmark, get_benchmark_logs
from tools.query import list_jobs, get_job_status, get_run_results, compare_runs, search_runs
from tools.config import list_configs, save_config, delete_config, run_saved_config
from tools.real_world import search_real_world_tests, get_real_world_results, get_real_world_trace, compare_real_world_tests
from modules import EMULATED_MODULE, REAL_WORLD_MODULE

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

MODULE_TOOLS = {
    EMULATED_MODULE: ALL_TOOLS,
    REAL_WORLD_MODULE: [search_real_world_tests, get_real_world_results, get_real_world_trace, compare_real_world_tests],
}
