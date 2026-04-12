import os
import tempfile
import pytest
from agent.app.core.security import generate_ca, generate_agent_cert, load_ssl_context


@pytest.fixture
def cert_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_generate_ca_creates_files(cert_dir):
    ca_key, ca_cert = generate_ca(cert_dir)
    assert os.path.exists(ca_key)
    assert os.path.exists(ca_cert)


def test_generate_agent_cert_creates_files(cert_dir):
    ca_key, ca_cert = generate_ca(cert_dir)
    agent_key, agent_cert = generate_agent_cert(cert_dir, ca_key, ca_cert, "test-agent")
    assert os.path.exists(agent_key)
    assert os.path.exists(agent_cert)


def test_load_ssl_context(cert_dir):
    ca_key, ca_cert = generate_ca(cert_dir)
    agent_key, agent_cert = generate_agent_cert(cert_dir, ca_key, ca_cert, "test-agent")
    ctx = load_ssl_context(agent_cert, agent_key, ca_cert)
    assert ctx is not None
