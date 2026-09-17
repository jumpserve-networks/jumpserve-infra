import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


class BenchmarkToolTest(unittest.TestCase):
    def test_multi_bottleneck_arguments_reach_the_launch_api(self):
        httpx = types.ModuleType('httpx')
        httpx.post = Mock(return_value=Mock(json=lambda: {'jobId': 'test-job'}))
        strands = types.ModuleType('strands')
        strands.tool = lambda fn: fn
        path = pathlib.Path(__file__).parents[1] / 'agent/tools/benchmark.py'
        spec = importlib.util.spec_from_file_location('benchmark_tool_test_target', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'httpx': httpx, 'strands': strands}):
            spec.loader.exec_module(module)
        module.run_benchmark(
            num_clients=2, client_ccas=['cubic', 'cubic'], client_delays_ms=[10, 20],
            client_file_sizes_mbytes=[5, 5], bottleneck_rate_mbit=100, buffer_size_kbytes=125,
            script='netem_multi_bottleneck.py', topology='dumbbell',
            bottleneck_rates_mbit=[100, 50], bottleneck_buffers_kbytes=[125, 64], client_groups=[1, 1],
        )
        config = httpx.post.call_args.kwargs['json']['config']
        self.assertEqual(config['topology'], 'dumbbell')
        self.assertEqual(config['bottleneck_rates_mbit'], [100, 50])
        self.assertEqual(config['bottleneck_buffers_kbytes'], [125, 64])
        self.assertEqual(config['client_groups'], [1, 1])
