#!/usr/bin/env python3
"""Run the unchanged official evaluator and record resource measurements separately.

Usage: python experiments/measure.py --package /path/to/MP3_SQL_student_package
The agent never receives the scorer's files. No official file is modified.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
MEMORY_BYTES = 2 * 1024**3


def linux_process_tree(pid):
    """Sample the complete process tree, including children of worker threads."""
    pending, visited = [pid], set()
    rss = virtual = 0
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        proc = Path('/proc') / str(current)
        try:
            pages = [int(x) for x in (proc / 'statm').read_text().split()[:2]]
            virtual += pages[0] * os.sysconf('SC_PAGE_SIZE')
            rss += pages[1] * os.sysconf('SC_PAGE_SIZE')
            for task in (proc / 'task').iterdir():
                try:
                    pending.extend(int(x) for x in (task / 'children').read_text().split())
                except (OSError, ValueError):
                    pass
        except (OSError, ValueError, ProcessLookupError):
            pass
    return rss, virtual


def windows_process_usage(process):
    """Windows standard-library fallback: root process only, explicitly labelled."""
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage',
                'PrivateUsage')]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    handle = wintypes.HANDLE(int(process._handle))
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    memory_ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    creation, end, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
    cpu_ok = kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(end),
                                  ctypes.byref(kernel_time), ctypes.byref(user_time))
    cpu = None
    if cpu_ok:
        cpu = sum((x.dwHighDateTime << 32) + x.dwLowDateTime
                  for x in (kernel_time, user_time)) / 10_000_000
    return (int(counters.PeakWorkingSetSize) if memory_ok else None,
            int(counters.PeakPagefileUsage) if memory_ok else None, cpu)


def linux_limits():
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    if hasattr(os, 'sched_getaffinity'):
        cpus = sorted(os.sched_getaffinity(0))[:4]
        os.sched_setaffinity(0, cpus)


def stop_process(process):
    if process.poll() is None:
        if sys.platform.startswith('linux'):
            os.killpg(process.pid, signal.SIGKILL)
        elif os.name == 'nt':
            # PID comes from Popen, not untrusted text. /T closes SQL workers too.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
        else:
            process.kill()
        process.wait()


def run_command(command, package, environment, log_path, deadline):
    linux = sys.platform.startswith('linux')
    resource = __import__('resource') if linux else None
    before = resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None
    time_path = log_path.with_suffix('.time.txt')
    actual_command = command
    if linux and Path('/usr/bin/time').exists():
        actual_command = ['/usr/bin/time', '-v', '-o', str(time_path), *command]
    usage = {'command': command, 'stdout_log': log_path.name,
             'scope': 'process_tree' if linux else 'controller_process_only',
             'sample_interval_seconds': 0.02}
    if linux:
        usage.update({'rlimit_as_bytes_per_process': MEMORY_BYTES,
                      'sampled_process_tree_vms_limit_bytes': MEMORY_BYTES,
                      'cpu_affinity_limit': 4})
    started = time.perf_counter()
    failure = None
    peak_rss = peak_virtual = 0
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(
            actual_command, cwd=package, env=environment, stdout=log,
            stderr=subprocess.STDOUT, start_new_session=linux,
            preexec_fn=linux_limits if linux else None)
        try:
            while process.poll() is None:
                if time.perf_counter() >= deadline:
                    failure = 'Combined prediction and scoring deadline exceeded'
                    break
                if linux:
                    rss, virtual = linux_process_tree(process.pid)
                    peak_rss = max(peak_rss, rss)
                    peak_virtual = max(peak_virtual, virtual)
                    if virtual > MEMORY_BYTES:
                        failure = 'Sampled process-tree virtual memory exceeds 2 GiB'
                        break
                elif os.name == 'nt':
                    rss, virtual, _ = windows_process_usage(process)
                    peak_rss = max(peak_rss, rss or 0)
                    peak_virtual = max(peak_virtual, virtual or 0)
                time.sleep(0.02)
        finally:
            if failure is not None or process.poll() is None:
                stop_process(process)
            usage['wall_seconds'] = time.perf_counter() - started
            usage['exit_code'] = process.returncode
            if linux:
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                usage['cpu_user_seconds'] = after.ru_utime - before.ru_utime
                usage['cpu_system_seconds'] = after.ru_stime - before.ru_stime
                usage['cpu_seconds'] = usage['cpu_user_seconds'] + usage['cpu_system_seconds']
                usage['sampled_peak_tree_rss_bytes'] = peak_rss
                usage['sampled_peak_tree_virtual_bytes'] = peak_virtual
                if time_path.exists():
                    usage['gnu_time_report'] = time_path.name
            elif os.name == 'nt':
                rss, private, cpu = windows_process_usage(process)
                usage['cpu_seconds'] = cpu
                usage['root_peak_rss_bytes'] = max(peak_rss, rss or 0)
                usage['root_peak_private_bytes'] = max(peak_virtual, private or 0)
                usage['limitation'] = ('Windows measurements exclude SQL worker CPU/memory; '
                                       'Linux limits are not enforced on Windows.')
    print(log_path.read_text(encoding='utf-8'), end='')
    if failure:
        usage['failure'] = failure
    elif process.returncode:
        usage['failure'] = f'Official command exited {process.returncode}'
    return usage


def run_pair(package, output, split, name, config, baseline, timeout):
    stem = split if name == 'full' else f'{split}-{name}'
    predictions = output / f'{stem}.json'
    score = output / f'{stem}-score.json'
    environment = os.environ.copy()
    environment['PYTHONUTF8'] = '1'
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, [
        str(ROOT / 'v2'), environment.get('PYTHONPATH', '')]))
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'NUMEXPR_NUM_THREADS'):
        environment[key] = '1'
    predict = [sys.executable, '-m', 'mp3_sql.predict', '--split', split,
               '--workers', '4', '--output', str(predictions)]
    if not baseline:
        predict.extend(['--method', str(ROOT / 'v2' / 'submission.py'),
                        '--checkpoint', str(config)])
    grade = [sys.executable, '-m', 'mp3_sql.score', '--split', split,
             '--workers', '4', '--predictions', str(predictions), '--output', str(score)]
    started = time.perf_counter()
    deadline = started + timeout
    metrics = {'split': split, 'variant': name, 'python': sys.version,
               'platform': platform.platform(), 'workers': 4,
               'combined_wall_limit_seconds': timeout,
               'official_package': str(package),
               'config': str(config) if not baseline else None,
               'measurements': []}
    for label, command in (('predict', predict), ('score', grade)):
        measured = run_command(command, package, environment,
                               output / f'{stem}-{label}.log', deadline)
        measured['phase'] = label
        metrics['measurements'].append(measured)
        if 'failure' in measured:
            metrics['failure'] = measured['failure']
            break
    metrics['combined_wall_seconds'] = time.perf_counter() - started
    metrics['combined_cpu_seconds'] = sum(
        item.get('cpu_seconds') or 0 for item in metrics['measurements'])
    metrics['completed'] = 'failure' not in metrics
    (output / f'{stem}-runtime.json').write_text(
        json.dumps(metrics, indent=2) + '\n', encoding='utf-8')
    if not metrics['completed']:
        raise RuntimeError(metrics['failure'])
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results' / 'measured')
    parser.add_argument('--split', choices=('validation', 'test'), default='test')
    parser.add_argument('--config', type=Path, default=ROOT / 'v2' / 'config.json')
    
    parser.add_argument('--timeout', type=float, default=180,
                        help='Combined prediction/scoring wall limit; at most 180 seconds')
    args = parser.parse_args()
    if sys.version_info[:2] not in ((3, 11), (3, 12)):
        parser.error('Official specification requires Python 3.11 or 3.12')
    if not 0 < args.timeout <= 180:
        parser.error('--timeout must be positive and no greater than 180')
    package, output, config = (args.package.resolve(), args.output_dir.resolve(),
                               args.config.resolve())
    if not (package / 'mp3_sql' / 'predict.py').is_file():
        parser.error('--package must be the extracted official package root')
    if not config.is_file():
        parser.error('--config does not exist')
    output.mkdir(parents=True, exist_ok=True)
    variants = [('full', config, False)]
    for name, variant_config, baseline in variants:
        print(f'Running {args.split}: {name}', flush=True)
        run_pair(package, output, args.split, name, variant_config, baseline, args.timeout)


if __name__ == '__main__':
    main()
