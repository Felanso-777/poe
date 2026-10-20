"""
collector/ebpf_collector.py — Linux eBPF/BCC process-execution collector.

Tracepoint used
---------------
    sched:sched_process_exec

This tracepoint fires in the kernel immediately after execve() successfully
substitutes a new program image.  It is available on Linux ≥ 4.7 with BPF
support compiled in (virtually all modern distros).

Privacy guarantees
------------------
* Only `comm` (≤ 15-char process name, no argv) is captured.
* PID and a kernel-monotonic timestamp are captured.
* argv, env, cwd, file paths, and parent process details are NEVER recorded.
* Events are immediately mapped to the existing PoEEvent/EventType schema
  with event_type=PROCESS_START so they are subject to the same schema-level
  privacy filter as mock events.

Linux dependencies
------------------
    1. Linux kernel ≥ 4.7 with CONFIG_BPF=y
    2. BCC Python bindings:
           sudo apt install python3-bcc          # Debian/Ubuntu
           sudo dnf install bcc-tools            # Fedora/RHEL
           pip install bcc                       # some distributions
    3. Root privileges OR CAP_BCC + CAP_PERFMON:
           sudo python main.py run               # simplest approach
           # or grant capabilities once:
           sudo setcap cap_bcc,cap_perfmon+ep $(which python3)

How to test without BCC / without a Linux machine
--------------------------------------------------
    EBPF_AVAILABLE is False when BCC is not installed or the platform is not
    Linux.  In that case eBPFCollector transparently falls back to
    MockCollector and prints a clear banner — no silent substitution.

    The full test suite (tests/) runs on any platform using purely mock data.

Fallback behaviour
------------------
    If BCC is unavailable or privileges are insufficient:
        - A WARNING banner is printed to stderr.
        - If fallback_to_mock=True (default), MockCollector is used instead
          and every event gets a metadata key "source" = "MOCK" to make the
          substitution explicit.
        - If fallback_to_mock=False, start() raises the original exception.
"""

from __future__ import annotations

import platform
import sys
import threading
import time
from typing import Optional

from .batcher import EventBatcher
from .mock_collector import MockCollector
from .schema import EventType, PoEEvent
from .interfaces import CollectorMetadata

# ---------------------------------------------------------------------------
# Detect BCC availability once at import time
# ---------------------------------------------------------------------------

EBPF_AVAILABLE: bool = False
_BCC_IMPORT_ERROR: Optional[Exception] = None

if platform.system() == "Linux":
    try:
        from bcc import BPF as _BPF  # type: ignore[import]  # noqa: F401 — availability probe
        EBPF_AVAILABLE = True
    except ImportError as _e:
        _BCC_IMPORT_ERROR = _e
    except Exception as _e:                  # pragma: no cover — platform-specific
        _BCC_IMPORT_ERROR = _e
else:
    _BCC_IMPORT_ERROR = OSError(
        "eBPF/BCC is only supported on Linux. "
        f"Current platform: {platform.system()}"
    )

# ---------------------------------------------------------------------------
# BPF program — C code loaded by BCC at runtime
# ---------------------------------------------------------------------------

# Only the comm field (process name, max 15 chars + NUL) is extracted.
# No argv, no environment, no file path.
_BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

struct exec_event_t {
    u32  pid;
    u64  ts_ns;          /* kernel monotonic nanoseconds */
    char comm[TASK_COMM_LEN];
};

BPF_PERF_OUTPUT(exec_events);

TRACEPOINT_PROBE(sched, sched_process_exec) {
    struct exec_event_t data = {};
    data.pid    = bpf_get_current_pid_tgid() >> 32;
    data.ts_ns  = bpf_ktime_get_ns();
    bpf_get_current_comm(&data.comm, sizeof(data.comm));
    exec_events.perf_submit(args, &data, sizeof(data));
    return 0;
}
"""


# ---------------------------------------------------------------------------
# eBPFCollector
# ---------------------------------------------------------------------------

class eBPFCollector:
    """
    Collects process-execution events from the Linux kernel via eBPF/BCC.

    Parameters
    ----------
    session_id : str
        Session UUID embedded in every emitted PoEEvent.
    batcher : EventBatcher
        Receives each event via batcher.add().
    fallback_to_mock : bool
        If True (default) and BCC is unavailable / permissions are denied,
        fall back to MockCollector transparently with a visible warning.
        If False, start() raises immediately on failure.
    seed : int, optional
        RNG seed forwarded to MockCollector when falling back.
    """

    def __init__(
        self,
        session_id: str,
        batcher: EventBatcher,
        fallback_to_mock: bool = True,
        seed: Optional[int] = None,
    ) -> None:
        self._session_id      = session_id
        self._batcher         = batcher
        self._fallback_to_mock = fallback_to_mock
        self._seed             = seed

        self._using_mock      = False
        self._mock: Optional[MockCollector] = None
        self._bpf             = None          # type: ignore[assignment]
        self._running         = False
        self._thread: Optional[threading.Thread] = None
        self.metadata = CollectorMetadata(
            name="eBPFCollector", platform="Linux", synthetic=False, authorized=True
        )

    # ------------------------------------------------------------------
    # Public API  (mirrors MockCollector interface)
    # ------------------------------------------------------------------

    def start(self, interval_seconds: float = 0.1) -> None:
        """
        Begin event collection.

        On Linux with BCC/root, attaches the eBPF tracepoint.
        Otherwise, falls back to MockCollector (or raises if fallback is off).
        """
        if self._running:
            return

        if not EBPF_AVAILABLE:
            self._handle_unavailable()
            return

        try:
            self._start_ebpf()
        except PermissionError as exc:
            self._handle_permission_error(exc)
        except Exception as exc:              # pragma: no cover
            self._handle_unavailable(exc)

    def stop(self) -> list[PoEEvent]:
        """
        Stop collection and drain any remaining buffered events.

        Returns the final flushed batch.
        """
        self._running = False

        if self._using_mock and self._mock is not None:
            return self._mock.stop()

        if self._thread is not None:
            self._thread.join(timeout=5.0)

        return self._batcher.force_flush()

    @property
    def is_mock(self) -> bool:
        """True when falling back to MockCollector."""
        return self._using_mock

    # ------------------------------------------------------------------
    # Internal — eBPF path
    # ------------------------------------------------------------------

    def _start_ebpf(self) -> None:
        """Load the BPF program and start the perf-buffer poll thread."""
        from bcc import BPF  # type: ignore[import]  # Linux only; guarded by EBPF_AVAILABLE

        self._bpf = BPF(text=_BPF_PROGRAM)
        self._bpf["exec_events"].open_perf_buffer(self._handle_event)

        self._running = True
        self._thread  = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="eBPFCollector",
        )
        self._thread.start()
        print(
            f"[eBPF] Collector started. Tracepoint: sched:sched_process_exec",
            file=sys.stderr,
        )

    def _poll_loop(self) -> None:
        """Continuously poll the BPF perf buffer."""
        while self._running:
            try:
                self._bpf.perf_buffer_poll(timeout=100)
            except Exception:               # pragma: no cover
                break

    def _handle_event(self, cpu, data, size) -> None:  # type: ignore[no-untyped-def]
        """BCC callback: convert a kernel exec_event_t into a PoEEvent."""
        event = self._bpf["exec_events"].event(data)
        process_name = event.comm.decode("utf-8", errors="replace").strip("\x00")
        poe = PoEEvent(
            event_type=EventType.PROCESS_START,
            session_id=self._session_id,
            metadata={"process_name": process_name},
        )
        self._batcher.add(poe)

    # ------------------------------------------------------------------
    # Internal — fallback / error handling
    # ------------------------------------------------------------------

    def _handle_permission_error(self, exc: Exception) -> None:
        msg = (
            "\n[eBPF] Permission denied. eBPF requires root or CAP_BCC+CAP_PERFMON.\n"
            "       Run with: sudo python main.py run\n"
            "       Or grant once: sudo setcap cap_bcc,cap_perfmon+ep $(which python3)\n"
        )
        self._emit_fallback_or_raise(exc, msg)

    def _handle_unavailable(self, exc: Optional[Exception] = None) -> None:
        err = exc or _BCC_IMPORT_ERROR
        if platform.system() != "Linux":
            msg = (
                "\n[eBPF] Not available: eBPF/BCC requires Linux.\n"
                f"       Current platform: {platform.system()}\n"
            )
        else:
            msg = (
                "\n[eBPF] BCC Python bindings not found.\n"
                "       Install with: sudo apt install python3-bcc\n"
                f"       Error: {err}\n"
            )
        self._emit_fallback_or_raise(err, msg)

    def _emit_fallback_or_raise(
        self, exc: Optional[Exception], message: str
    ) -> None:
        print(message, file=sys.stderr)
        if not self._fallback_to_mock:
            raise exc or RuntimeError("eBPF unavailable")

        print(
            "[eBPF] Falling back to MockCollector. "
            "Events are SYNTHETIC — NOT real kernel events.\n",
            file=sys.stderr,
        )
        self._using_mock = True
        self.metadata = CollectorMetadata(
            name="MockCollector (eBPF fallback)",
            platform=platform.system(),
            synthetic=True,
            authorized=False,
        )
        self._mock = MockCollector(
            session_id=self._session_id,
            batcher=self._batcher,
            seed=self._seed,
        )
        self._mock.start()
        self._running = True
