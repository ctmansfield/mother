import unittest
from scientific_compare import (
    completion_name_dropout,
    trusted_ollama_gpu_process,
    unattributed_processes,
)


class GuardRegressionTests(unittest.TestCase):
    def test_real_host_telemetry_allows_one_ollama_llama_server(self):
        process = {
            "gpu_uuid": "GPU-59ffe7a0-5ab9-9d95-12f1-4ba621956c85",
            "pid": "3766817",
            "process_name": "/usr/local/lib/ollama/llama-server",
            "used_gpu_memory_mib": "12514",
        }
        self.assertTrue(trusted_ollama_gpu_process(process))
        self.assertFalse(unattributed_processes([process]))

    def test_legacy_ollama_processes_still_accepted_individually(self):
        for name in ("/bin/ollama", "/bin/ollama_llama_server"):
            self.assertFalse(
                unattributed_processes([{"pid": "22", "process_name": name}])
            )

    def test_unknown_process_rejected(self):
        for name in (
            "/usr/bin/python",
            "/tmp/llama-server",
            "/usr/local/lib/other/llama-server",
            "/usr/local/lib/ollama/llama-server-trojan",
            "/bin/ollama-malicious",
        ):
            self.assertTrue(
                unattributed_processes([{"pid": "22", "process_name": name}])
            )

    def test_multiple_gpu_pids_rejected_even_both_ollama(self):
        self.assertTrue(
            unattributed_processes(
                [
                    {"pid": "22", "process_name": "/bin/ollama"},
                    {"pid": "23", "process_name": "/usr/local/lib/ollama/llama-server"},
                ]
            )
        )

    def test_malformed_process_rejected(self):
        for p in (
            {},
            {"pid": 22, "process_name": "/usr/local/lib/ollama/llama-server"},
            {"pid": "0", "process_name": "/bin/ollama"},
            {"pid": "a", "process_name": "/bin/ollama"},
            {"pid": "2", "process_name": None},
        ):
            self.assertTrue(unattributed_processes([p]))

    def test_empty_process_list_is_idle(self):
        self.assertFalse(unattributed_processes([]))


if __name__ == "__main__":
    unittest.main()


class CompletionNameDropoutTests(unittest.TestCase):
    def test_only_previously_attributed_process_on_completed_request(self):
        known = {
            "pid": "22",
            "process_name": "/usr/local/lib/ollama/llama-server",
            "gpu_uuid": "GPU-known",
        }
        unknown = {**known, "process_name": "[No data]"}
        response = {"done": True, "model": "candidate"}
        before = {"compute_processes": [known], "http_completed_at_sample_end": False}
        after = {"compute_processes": [unknown], "http_completed_at_sample_end": True}
        self.assertTrue(completion_name_dropout(before, after, response, "candidate"))
        for previous, current, reply in (
            (None, after, response),
            (before, {**after, "http_completed_at_sample_end": False}, response),
            (
                before,
                {**after, "compute_processes": [{**unknown, "pid": "23"}]},
                response,
            ),
            (
                before,
                {**after, "compute_processes": [{**unknown, "gpu_uuid": "GPU-other"}]},
                response,
            ),
            (before, {**after, "compute_processes": [unknown, known]}, response),
            (before, after, {"done": False, "model": "candidate"}),
            (before, after, {"done": True, "model": "other"}),
        ):
            with self.subTest(previous=previous, current=current, reply=reply):
                self.assertFalse(
                    completion_name_dropout(previous, current, reply, "candidate")
                )
