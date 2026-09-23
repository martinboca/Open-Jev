import importlib.util
import unittest
from unittest import mock

HAS_TORCH = importlib.util.find_spec("torch") is not None
if HAS_TORCH:
    import torch
    from jev.model import parameter_dtype, resolve_device


@unittest.skipUnless(HAS_TORCH, "requires optional torch runtime")
class DeviceSelectionTest(unittest.TestCase):
    def test_auto_prefers_cuda_then_mps_then_cpu(self):
        for cuda, mps, expected in [(True, True, "cuda:0"), (True, False, "cuda:0"),
                                    (False, True, "mps"), (False, False, "cpu")]:
            with mock.patch("torch.cuda.is_available", return_value=cuda), \
                 mock.patch("torch.backends.mps.is_available", return_value=mps):
                self.assertEqual(resolve_device("auto"), expected)

    def test_explicit_device_is_never_downgraded(self):
        # A silent fallback would change measured latency without saying so.
        with mock.patch("torch.cuda.is_available", return_value=False), \
             mock.patch("torch.backends.mps.is_available", return_value=False):
            for device in ("cuda:0", "cuda:3", "mps", "cpu"):
                self.assertEqual(resolve_device(device), device)

    def test_only_cpu_drops_bfloat16(self):
        self.assertEqual(parameter_dtype("cpu"), torch.float32)
        for device in ("cuda:0", "mps"):
            self.assertEqual(parameter_dtype(device), torch.bfloat16)


if __name__ == "__main__":
    unittest.main()
