import os
import socket

import pytest


def test_credentials_and_local_discovery_disabled():
    assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
    assert os.environ["TAGEBUCH_CONFIG"] == ""
    assert "GEMINI_API_KEY" not in os.environ
    assert "GOOGLE_API_KEY" not in os.environ
    assert "GOOGLE_GENAI_DEBUG" not in os.environ


@pytest.mark.parametrize("method", ["connect", "connect_ex", "sendto"])
def test_internet_sockets_blocked(method):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        args = (b"synthetic", ("127.0.0.1", 9)) if method == "sendto" else (("127.0.0.1", 9),)
        with pytest.raises(AssertionError, match="Network access"):
            getattr(sock, method)(*args)
