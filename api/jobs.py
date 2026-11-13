import os
import signal
import threading

_LOCK = threading.Lock()
_PROCS = {}


def register(job_id, proc):
    with _LOCK:
        _PROCS[job_id] = proc


def unregister(job_id):
    with _LOCK:
        _PROCS.pop(job_id, None)


def stop(job_id):
    with _LOCK:
        proc = _PROCS.get(job_id)
    if proc is None or proc.poll() is not None:
        return False
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except Exception:
            return False

    def _kill():
        try:
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass

    t = threading.Timer(2.0, _kill)
    t.daemon = True
    t.start()
    return True
