"""Install the declared dependencies with visible, resumable package steps."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import subprocess
import sys
import time
import tomllib
from pathlib import Path


def requirements(root: Path, formats: bool = True) -> list[str]:
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    result = list(project['dependencies'])
    if formats:
        result.extend(project.get('optional-dependencies', {}).get('formats', []))
    return result


def install(root: Path, formats: bool = True) -> int:
    packages = requirements(root, formats)
    pip_version = tuple(int(part) for part in importlib.metadata.version('pip').split('.')[:2])
    resume_options = ['--resume-retries', '30'] if pip_version >= (25, 2) else []
    for index, package in enumerate(packages, 1):
        print(f'[{index}/{len(packages)}] Installing package: {package}', flush=True)
        for attempt in range(1, 4):
            command = [sys.executable, '-m', 'pip', 'install',
                       '--disable-pip-version-check', '--timeout', '300',
                       '--retries', '10', *resume_options,
                       '--prefer-binary', '--progress-bar', 'on', package]
            result = subprocess.run(command, check=False)
            if result.returncode == 0:
                break
            if attempt == 3:
                print(f'ERROR: could not install {package}. See the network errors above.', flush=True)
                return result.returncode
            print(f'Retrying {package}: attempt {attempt + 1}/3 in 15 seconds', flush=True)
            time.sleep(15)
    print('Registering IR/Raman Phase Finder...', flush=True)
    result = subprocess.run([sys.executable, '-m', 'pip', 'install',
                             '--disable-pip-version-check', '--no-deps',
                             '--no-build-isolation', '-e', str(root)], check=False)
    if result.returncode:
        return result.returncode
    print('Testing installed scientific packages...', flush=True)
    for name in ('numpy', 'scipy', 'pybaselines', 'pyqtgraph', 'PySide6.QtWidgets',
                 'certifi', 'pyreadr', 'rdata', 'ijson'):
        importlib.import_module(name)
        print(f'OK: {name}', flush=True)
    import numpy as np
    from scipy.signal import find_peaks
    assert find_peaks(np.array([0., 1., 0.]))[0].tolist() == [1]
    print('Runtime self-test passed.', flush=True)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    if args.list:
        print('\n'.join(requirements(args.root)))
    else:
        raise SystemExit(install(args.root))
