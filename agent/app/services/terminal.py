import os
import sys
import uuid
import time
import subprocess
import threading
from typing import Callable


class TerminalSession:
    def __init__(self, shell_cmd: list[str], idle_timeout: int):
        self.id = str(uuid.uuid4())
        self.created_at = time.time()
        self.last_activity = time.time()
        self.idle_timeout = idle_timeout
        self._process = None
        self._master_fd = None
        self._alive = False
        # Windows pipe reading uses a background thread + buffer
        self._read_buffer: bytes = b""
        self._read_lock = threading.Lock()
        self._read_thread: threading.Thread | None = None

        if sys.platform != "win32":
            self._start_unix(shell_cmd)
        else:
            self._start_windows(shell_cmd)

    def _start_unix(self, shell_cmd: list[str]):
        import pty  # Unix-only
        master_fd, slave_fd = pty.openpty()
        self._process = subprocess.Popen(
            shell_cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
        )
        os.close(slave_fd)
        self._master_fd = master_fd
        self._alive = True

    def _start_windows(self, shell_cmd: list[str]):
        self._process = subprocess.Popen(
            shell_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self._alive = True
        # Start a background thread to drain stdout into our buffer
        # because Windows pipes can't be used with select()
        self._read_thread = threading.Thread(
            target=self._windows_reader_thread, daemon=True
        )
        self._read_thread.start()

    def _windows_reader_thread(self):
        """Background thread that continuously reads stdout into _read_buffer."""
        stdout = self._process.stdout
        if stdout is None:
            return
        try:
            while self._alive:
                chunk = stdout.read(4096)
                if not chunk:
                    break
                with self._read_lock:
                    self._read_buffer += chunk
        except OSError:
            pass
        finally:
            self._alive = False

    def write(self, data: bytes):
        self.last_activity = time.time()
        if self._master_fd is not None:
            os.write(self._master_fd, data)
        elif self._process and self._process.stdin:
            try:
                self._process.stdin.write(data)
                self._process.stdin.flush()
            except OSError:
                self._alive = False

    def read(self, size: int = 4096) -> bytes | None:
        self.last_activity = time.time()
        if self._master_fd is not None:
            # Unix: use select to check if data is available without blocking
            import select  # Unix-only; safe here since _master_fd is only set on Unix
            if select.select([self._master_fd], [], [], 0.05)[0]:
                try:
                    return os.read(self._master_fd, size)
                except OSError:
                    self._alive = False
                    return None
        elif self._process and self._process.stdout:
            # Windows: drain from the thread-populated buffer
            with self._read_lock:
                if self._read_buffer:
                    chunk = self._read_buffer[:size]
                    self._read_buffer = self._read_buffer[size:]
                    return chunk
        return None

    def resize(self, rows: int, cols: int):
        """Resize the PTY window (Unix only)."""
        if self._master_fd is not None and sys.platform != "win32":
            import fcntl    # Unix-only
            import struct
            import termios  # Unix-only
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def is_alive(self) -> bool:
        if not self._alive:
            return False
        if self._process and self._process.poll() is not None:
            self._alive = False
            return False
        if time.time() - self.last_activity > self.idle_timeout:
            self.destroy()
            return False
        return True

    def destroy(self):
        self._alive = False
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass


class TerminalManager:
    def __init__(self, config, platform):
        self.config = config
        self.platform = platform
        self.sessions: dict[str, TerminalSession] = {}

    def create_session(self) -> str:
        self._cleanup_dead()
        if len(self.sessions) >= self.config.max_terminal_sessions:
            raise RuntimeError(
                f"Max sessions ({self.config.max_terminal_sessions}) reached"
            )
        shell = self.platform.get_shell_command()
        session = TerminalSession(shell, self.config.terminal_idle_timeout)
        self.sessions[session.id] = session
        return session.id

    def get_session(self, session_id: str) -> TerminalSession | None:
        session = self.sessions.get(session_id)
        if session and not session.is_alive():
            del self.sessions[session_id]
            return None
        return session

    def destroy_session(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if session:
            session.destroy()

    def _cleanup_dead(self):
        dead = [sid for sid, s in self.sessions.items() if not s.is_alive()]
        for sid in dead:
            self.sessions.pop(sid, None)
