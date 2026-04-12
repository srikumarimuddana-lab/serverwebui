import pytest
from unittest.mock import MagicMock, patch
from agent.app.services.terminal import TerminalManager, TerminalSession


@pytest.fixture
def config():
    c = MagicMock()
    c.max_terminal_sessions = 5
    c.terminal_idle_timeout = 1800
    return c


@pytest.fixture
def platform():
    p = MagicMock()
    p.get_shell_command.return_value = ["/bin/bash"]
    return p


def _make_mock_session(session_id=None):
    """Return a MagicMock that behaves like a live TerminalSession."""
    s = MagicMock(spec=TerminalSession)
    s.id = session_id or "mock-session-id"
    s.is_alive.return_value = True
    return s


def test_terminal_manager_creates_session(config, platform):
    with patch("agent.app.services.terminal.TerminalSession") as MockSession:
        mock = _make_mock_session("test-sid")
        MockSession.return_value = mock

        tm = TerminalManager(config, platform)
        session_id = tm.create_session()

        assert session_id is not None
        assert session_id in tm.sessions


def test_terminal_manager_respects_max_sessions(config, platform):
    config.max_terminal_sessions = 2

    with patch("agent.app.services.terminal.TerminalSession") as MockSession:
        counter = [0]

        def make_session(*args, **kwargs):
            counter[0] += 1
            s = MagicMock(spec=TerminalSession)
            s.id = f"session-{counter[0]}"
            s.is_alive.return_value = True
            return s

        MockSession.side_effect = make_session

        tm = TerminalManager(config, platform)
        tm.create_session()
        tm.create_session()

        with pytest.raises(RuntimeError, match="Max sessions"):
            tm.create_session()


def test_terminal_manager_destroys_session(config, platform):
    with patch("agent.app.services.terminal.TerminalSession") as MockSession:
        mock = _make_mock_session("del-sid")
        MockSession.return_value = mock

        tm = TerminalManager(config, platform)
        sid = tm.create_session()
        tm.destroy_session(sid)

        assert sid not in tm.sessions
