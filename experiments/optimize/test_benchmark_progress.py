"""Process containment checks using short Python fixtures; never solver timings."""

from contextlib import closing
import importlib.util
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    'benchmark_progress', Path(__file__).with_name('benchmark_progress.py')
)
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


@unittest.skipUnless(os.name == 'posix', 'POSIX benchmark containment')
class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def capture(self, source, timeout=1, **kwargs):
        return BENCH.capture_command(
            [sys.executable, '-u', '-c', source],
            self.directory,
            os.environ.copy(),
            timeout,
            **kwargs,
        )

    def assert_gone(self, pid):
        # An adopted, killed grandchild may briefly remain a zombie before init
        # reaps it. It has no running code and cannot retain the output files.
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            state = subprocess.run(
                ['ps', '-p', str(pid), '-o', 'stat='],
                capture_output=True,
                text=True,
                timeout=0.2,
            )
            if not state.stdout.strip() or state.stdout.strip().startswith('Z'):
                return
            time.sleep(0.01)
        self.fail(f'fixture process {pid} survived cleanup')

    def descendant_source(self, parent_wait):
        return (
            'import pathlib,subprocess,sys,time\n'
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
            "pathlib.Path('descendant.pid').write_text(str(p.pid))\n"
            "pathlib.Path('leader.pid').write_text(str(__import__('os').getpid()))\n"
            f'time.sleep({parent_wait})\n'
        )

    def assert_fixture_gone(self):
        for name in ('leader.pid', 'descendant.pid'):
            self.assert_gone(int((self.directory / name).read_text()))

    def test_success_and_nonzero_exit_preserve_both_streams(self):
        result = self.capture(
            "import sys;print('answer');print('diagnostic',file=sys.stderr)"
        )
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['stdout'], b'answer\n')
        self.assertEqual(result['stderr'], b'diagnostic\n')
        self.assertFalse(result['hard_timeout'])
        self.assertFalse(result['output_limit'])
        result = self.capture("import sys;print('bad');sys.exit(7)")
        self.assertEqual(result['returncode'], 7)
        self.assertEqual(result['stdout'], b'bad\n')

    def test_output_allowance_during_execution_and_after_exit(self):
        for stream in (1, 2):
            for after in ('', ';time.sleep(30)'):
                with self.subTest(stream=stream, stays_alive=bool(after)):
                    result = self.capture(
                        f"import os,time;os.write({stream},b'x'*131072){after}",
                        max_output=4096,
                    )
                    self.assertTrue(result['output_limit'])
                    self.assertFalse(result['hard_timeout'])
                    self.assertLess(result['external_seconds'], 1)
                    self.assertLessEqual(len(result['stdout']), 4096)
                    self.assertLessEqual(len(result['stderr']), 4096)
                    self.assertGreaterEqual(
                        result['stdout_bytes_observed']
                        + result['stderr_bytes_observed'],
                        131072,
                    )

    def test_timeout_kills_leader_and_descendant(self):
        result = self.capture(self.descendant_source(30), timeout=0.2)
        self.assertTrue(result['hard_timeout'])
        self.assertLess(result['external_seconds'], 1)
        self.assert_fixture_gone()

    def test_successful_leader_does_not_leave_descendant(self):
        result = self.capture(self.descendant_source(0))
        self.assertEqual(result['returncode'], 0)
        self.assertFalse(result['hard_timeout'])
        self.assert_fixture_gone()

    def interrupted_capture(self, failure):
        real_popen = subprocess.Popen
        launched = []

        def start(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            launched.append(proc)
            end = time.monotonic() + 0.5
            while not (self.directory / 'descendant.pid').exists():
                if time.monotonic() >= end:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=0.5)
                    self.fail('fixture did not register its descendant')
                time.sleep(0.005)
            proc.poll = mock.Mock(side_effect=failure)
            return proc

        with mock.patch.object(BENCH.subprocess, 'Popen', side_effect=start):
            with self.assertRaises(type(failure)):
                self.capture(self.descendant_source(30))
        self.assertIsNotNone(launched[0].returncode)
        self.assert_fixture_gone()

    def test_keyboard_interrupt_cleans_process_group(self):
        self.interrupted_capture(KeyboardInterrupt())

    def test_unexpected_exception_cleans_process_group(self):
        self.interrupted_capture(RuntimeError('injected poll failure'))

    def test_invalid_allowances_and_launch_failure(self):
        for timeout in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.capture('pass', timeout=timeout)
        for maximum in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                self.capture('pass', max_output=maximum)
        with self.assertRaises(FileNotFoundError):
            BENCH.capture_command(
                ['/definitely/not/a/program'], self.directory, os.environ.copy(), 0.1
            )

    @unittest.skipUnless(sys.platform == 'darwin', 'Darwin zombie-only group behavior')
    def test_unreaped_zombie_output_limit_reaps_and_retries_group(self):
        real_popen, real_killpg = subprocess.Popen, os.killpg
        launched, outcomes = [], []

        def start(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            launched.append(proc)
            # Observe process exit without wait/poll reaping it. The child gate
            # makes NOTE_EXIT registration deterministic even on a fast host.
            with closing(select.kqueue()) as queue:
                event = select.kevent(
                    proc.pid, filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                    fflags=select.KQ_NOTE_EXIT,
                )
                queue.control([event], 0, 0)
                (self.directory / 'run').touch()
                events = queue.control(None, 1, 0.5)
                self.assertTrue(events and events[0].fflags & select.KQ_NOTE_EXIT)
            self.assertIsNone(proc.returncode)
            return proc

        def kill_group(pid, sig):
            try:
                real_killpg(pid, sig)
                outcomes.append('success')
            except OSError as error:
                outcomes.append(type(error).__name__)
                raise

        source = (
            'import os,pathlib,time\n'
            'deadline=time.monotonic()+0.5\n'
            "while not pathlib.Path('run').exists():\n"
            ' if time.monotonic()>deadline: raise SystemExit(9)\n'
            ' time.sleep(0.001)\n'
            "os.write(1,b'x'*131072)\n"
        )
        try:
            with mock.patch.object(BENCH.subprocess, 'Popen', side_effect=start), \
                 mock.patch.object(BENCH.os, 'killpg', side_effect=kill_group):
                result = self.capture(source, max_output=4096)
            self.assertEqual(outcomes, ['PermissionError', 'ProcessLookupError'])
            self.assertEqual(result['returncode'], 0)
            self.assertTrue(result['output_limit'])
            self.assertFalse(result['hard_timeout'])
            self.assertEqual(result['stdout'], b'x'*4096)
        finally:
            for proc in launched:
                proc.kill()
                proc.wait(timeout=0.5)

    def test_permission_retry_still_kills_live_descendant(self):
        real_popen, real_killpg = subprocess.Popen, os.killpg
        launched, attempts = [], []

        def start(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            launched.append(proc)
            proc.wait(timeout=0.5)  # The fixture's ordinary descendant stays live.
            return proc

        def kill_group(pid, sig):
            attempts.append((pid, sig))
            if len(attempts) == 1:
                raise PermissionError(1, 'injected initial group denial')
            real_killpg(pid, sig)

        try:
            with mock.patch.object(BENCH.subprocess, 'Popen', side_effect=start), \
                 mock.patch.object(BENCH.os, 'killpg', side_effect=kill_group):
                result = self.capture(self.descendant_source(0))
            self.assertEqual(result['returncode'], 0)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(attempts[0], attempts[1])
            self.assert_fixture_gone()
        finally:
            for proc in launched:
                try:
                    real_killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    # A killed, adopted descendant can briefly be a zombie.
                    pass
                proc.wait(timeout=0.5)

    def test_persistent_permission_denial_is_not_swallowed_after_reap(self):
        real_popen = subprocess.Popen

        def start(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            proc.wait(timeout=0.5)
            return proc

        denial = PermissionError(1, 'injected persistent group denial')
        with mock.patch.object(BENCH.subprocess, 'Popen', side_effect=start), \
             mock.patch.object(BENCH.os, 'killpg', side_effect=denial) as kill_group:
            with self.assertRaisesRegex(PermissionError, 'persistent group denial'):
                self.capture('pass')
        self.assertEqual(kill_group.call_count, 2)

    def test_reap_permission_denial_propagates_without_group_retry(self):
        real_popen, real_killpg = subprocess.Popen, os.killpg
        launched = []

        def start(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            real_wait = proc.wait
            launched.append((proc, real_wait))
            proc.wait = mock.Mock(side_effect=PermissionError(1, 'injected reap denial'))
            return proc

        try:
            with mock.patch.object(BENCH.subprocess, 'Popen', side_effect=start), \
                 mock.patch.object(BENCH.os, 'killpg', wraps=real_killpg) as kill_group:
                with self.assertRaisesRegex(PermissionError, 'reap denial'):
                    self.capture('import time;time.sleep(30)', timeout=0.005)
            self.assertEqual(kill_group.call_count, 1)
        finally:
            for proc, real_wait in launched:
                proc.kill()
                real_wait(timeout=0.5)

    def test_exit_transition_waits_once_then_retries_group(self):
        real_killpg = os.killpg
        attempts = []

        def kill_group(pid, sig):
            attempts.append((pid, sig))
            if len(attempts) == 1:
                raise PermissionError(1, 'injected exit-transition denial')
            real_killpg(pid, sig)

        with mock.patch.object(BENCH.os, 'killpg', side_effect=kill_group):
            result = self.capture('import time;time.sleep(0.08)', timeout=0.005)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual(result['returncode'], 0)
        self.assertTrue(result['hard_timeout'])
        self.assertLess(result['external_seconds'], 1)

    def test_live_leader_permission_denial_exceeds_cleanup_allowance(self):
        # The error path must stay bounded even when the group cannot be
        # signalled. Remove the denial before the fixture's own final cleanup.
        real_popen = subprocess.Popen
        launched = []

        def start(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            launched.append(proc)
            return proc

        denial = PermissionError(1, 'injected live group denial')
        started = time.monotonic()
        try:
            with mock.patch.object(BENCH.subprocess, 'Popen', side_effect=start), \
                 mock.patch.object(BENCH.os, 'killpg', side_effect=denial) as kill_group:
                with self.assertRaisesRegex(RuntimeError, 'cleanup deadline exceeded'):
                    self.capture('import time;time.sleep(30)', timeout=0.005)
            self.assertEqual(kill_group.call_count, 1)
            self.assertLess(time.monotonic()-started, 1)
            self.assertIsNone(launched[0].poll())
        finally:
            for proc in launched:
                proc.kill()
                proc.wait(timeout=0.5)


if __name__ == '__main__':
    unittest.main()
