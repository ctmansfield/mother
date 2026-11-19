import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import native_science as n


class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((n.HERE / "retrieval_fixture.json").read_text())

    def cache(self, base, revision="a" * 40):
        repo = Path(base) / "model-cache"
        snapshot = repo / "snapshots" / revision
        snapshot.mkdir(parents=True)
        (snapshot / "config.json").write_text('{"model_type":"bert"}')
        (snapshot / "tokenizer.json").write_text('{}')
        (snapshot / "model.safetensors").write_bytes(b"fixture-only-not-real-weights")
        return repo, snapshot

    def test_snapshot_is_pinned_from_cached_main(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, snapshot = self.cache(temporary)
            (repo / "refs").mkdir()
            (repo / "refs/main").write_text("a" * 40)
            self.assertEqual(n.resolve_snapshot(repo), snapshot)

    def test_multiple_unpinned_snapshots_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, _ = self.cache(temporary)
            (repo / "snapshots" / ("b" * 40)).mkdir()
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                n.resolve_snapshot(repo)

    def test_missing_shard_refused_before_runtime_load(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, snapshot = self.cache(temporary)
            (snapshot / "model.safetensors.index.json").write_text(json.dumps({
                "weight_map": {"layer": "model-00001-of-00002.safetensors"}}))
            with self.assertRaises(FileNotFoundError):
                n.asset_layout(snapshot)

    def test_model_file_symlink_to_cache_blob_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, snapshot = self.cache(temporary)
            (repo / "blobs").mkdir()
            blob = repo / "blobs/123"
            blob.write_bytes((snapshot / "model.safetensors").read_bytes())
            (snapshot / "model.safetensors").unlink()
            (snapshot / "model.safetensors").symlink_to(blob)
            layout = n.freeze_assets(n.asset_layout(snapshot))
            n.assets_unchanged(layout)
            self.assertEqual(len(layout["manifest_sha256"]), 64)

    def test_out_of_cache_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, snapshot = self.cache(temporary)
            external = Path(temporary) / "outside"
            external.write_bytes(b"untrusted")
            (snapshot / "model.safetensors").unlink()
            (snapshot / "model.safetensors").symlink_to(external)
            with self.assertRaisesRegex(ValueError, "out-of-cache"):
                n.asset_layout(snapshot)

    def test_weight_index_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, snapshot = self.cache(temporary)
            (snapshot / "model.safetensors.index.json").write_text(json.dumps({
                "weight_map": {"layer": "../../other.safetensors"}}))
            with self.assertRaisesRegex(ValueError, "unsafe weight shard"):
                n.asset_layout(snapshot)

    def test_changed_model_asset_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, snapshot = self.cache(temporary)
            layout = n.freeze_assets(n.asset_layout(snapshot))
            (snapshot / "model.safetensors").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "assets changed"):
                n.assets_unchanged(layout)

    def test_retargeted_snapshot_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, snapshot = self.cache(temporary)
            (repo / "blobs").mkdir()
            old_blob, new_blob = repo / "blobs/old", repo / "blobs/new"
            old_blob.write_bytes(b"old model")
            new_blob.write_bytes(b"new model")
            pointer = snapshot / "model.safetensors"
            pointer.unlink()
            pointer.symlink_to(old_blob)
            layout = n.freeze_assets(n.asset_layout(snapshot))
            pointer.unlink()
            pointer.symlink_to(new_blob)
            with self.assertRaisesRegex(ValueError, "symlink target changed"):
                n.assets_unchanged(layout)

    def test_retrieval_labels_are_not_encoder_inputs(self):
        altered = copy.deepcopy(self.fixture)
        altered["queries"][0].update(relevant_article="A7", hard_negative="A8")
        self.assertEqual(n.fixture_inputs(self.fixture), n.fixture_inputs(altered))
        query_inputs, article_inputs = n.fixture_inputs(self.fixture)
        self.assertEqual(len(query_inputs), 4)
        self.assertEqual(len(article_inputs), 8)

    def test_retrieval_scores_preserve_ties_and_hard_negatives(self):
        scores = [[0.0] * 8 for _ in range(4)]
        scores[0][0] = scores[0][1] = 1.0
        result = n.retrieval_scores(self.fixture, scores)
        self.assertEqual(result["queries"][0]["relevant_rank"], 1)
        self.assertFalse(result["queries"][0]["positive_over_hard_negative"])
        self.assertEqual(result["queries"][0]["hard_negative_margin"], 0)
        self.assertEqual(result["positive_over_hard_negative_count"], 0)
        scores[0][0] = 2.0
        result = n.retrieval_scores(self.fixture, scores)
        self.assertEqual(result["positive_over_hard_negative_count"], 1)
        self.assertNotIn("hard_negative_wins", result)

    def test_nonfinite_retrieval_score_refused(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            n.retrieval_scores(self.fixture, [[float("nan")] * 8] * 4)

    def test_cuda_evidence_rejects_cpu_parameters(self):
        tensor = lambda device: types.SimpleNamespace(device=device)
        cuda = types.SimpleNamespace(synchronize=lambda _: None, max_memory_allocated=lambda _: 50,
                                     max_memory_reserved=lambda _: 100)
        torch = types.SimpleNamespace(cuda=cuda)
        model = types.SimpleNamespace(parameters=lambda: [tensor("cpu")], buffers=lambda: [])
        with self.assertRaisesRegex(ValueError, "CUDA tensor placement"):
            n.cuda_evidence(torch, model, {"input_ids": tensor("cuda:0")}, tensor("cuda:0"))
        model.parameters = lambda: [tensor("cuda:0")]
        result = n.cuda_evidence(torch, model, {"input_ids": tensor("cuda:0")}, tensor("cuda:0"))
        self.assertEqual(result["evidence"], "CUDA_PARAMETERS_INPUTS_OUTPUTS_OBSERVED")

    def test_unknown_gpu_process_output_is_not_treated_as_idle(self):
        with patch.object(n, "command", return_value="[Not Supported]\n"):
            with self.assertRaisesRegex(ValueError, "unreadable"):
                n.gpu_processes()

    def test_inspection_performs_no_cuda_or_model_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = types.SimpleNamespace(hf_cache=Path(temporary), boltz_cache=Path(temporary) / "boltz")
            with patch.object(n, "gpu_snapshot", side_effect=AssertionError("must not touch CUDA")):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    n.inspect_local(args)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "READINESS_ONLY_NO_MODEL_LOAD_NO_CUDA_INFERENCE")
            self.assertEqual(result["boltz2"]["readiness"], "NOT_VALIDATED")

    def test_native_source_pin_not_substitutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(n, "command", return_value="0" * 40):
                with self.assertRaisesRegex(ValueError, "exact source pin"):
                    n.verify_source(Path(temporary))

    def test_same_head_with_modified_checkout_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(n, "command", side_effect=[n.SOURCE_PIN, " M packages/fw00412/broker.py"]):
                with self.assertRaisesRegex(ValueError, "checkout must be clean"):
                    n.verify_source(Path(temporary))

    def test_explicit_offline_loader_parameters(self):
        self.assertEqual(n.load_kwargs({"weight_format": "safetensors"}), {
            "local_files_only": True, "trust_remote_code": False, "use_safetensors": True})
        with patch.object(n.importlib.metadata, "version", return_value="2.5.1"):
            with self.assertRaisesRegex(ValueError, "torch >= 2.6"):
                n.load_kwargs({"weight_format": "bin"})

    def test_owned_worker_exit_race_is_already_stopped(self):
        process = types.SimpleNamespace(pid=12345, poll=lambda: None, wait=lambda timeout: 0)
        with patch.object(n.os, "killpg", side_effect=ProcessLookupError):
            n.stop_owned(process)

    def test_idle_check_refuses_redirects(self):
        with self.assertRaisesRegex(ValueError, "redirects are refused"):
            n.RejectRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.invalid")


if __name__ == "__main__":
    unittest.main()
