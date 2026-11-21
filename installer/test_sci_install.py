import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

spec = importlib.util.spec_from_file_location('sci_install', Path(__file__).resolve().parents[1] / 'toolkit/install_sci_requirements.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InstallationTests(unittest.TestCase):
    def test_requirements_include_all_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'pyproject.toml').write_text('[project]\ndependencies=["numpy"]\n[project.optional-dependencies]\nformats=["ramanchada2"]\n')
            self.assertEqual(module.requirements(root), ['numpy', 'ramanchada2'])

    def test_network_failure_stops_before_registration(self):
        with patch.object(module, 'requirements', return_value=['pyreadr']), patch.object(module.subprocess, 'run', return_value=CompletedProcess([], 1)) as run, patch.object(module.time, 'sleep'):
            self.assertEqual(module.install(Path('.')), 1)
            self.assertEqual(run.call_count, 3)
            self.assertTrue(all(call.args[0][-1] == 'pyreadr' for call in run.call_args_list))

    def test_transient_failure_retries_same_package(self):
        with patch.object(module, 'requirements', return_value=['pyreadr']), patch.object(module.subprocess, 'run', side_effect=[CompletedProcess([], 1), CompletedProcess([], 0), CompletedProcess([], 5)]) as run, patch.object(module.time, 'sleep'):
            self.assertEqual(module.install(Path('.')), 5)
            self.assertEqual(run.call_args_list[0].args[0], run.call_args_list[1].args[0])
            self.assertIn('--no-deps', run.call_args_list[2].args[0])


if __name__ == '__main__':
    unittest.main()
