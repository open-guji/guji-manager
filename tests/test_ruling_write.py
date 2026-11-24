import pytest

from guji_manager.ruling_write import append_rulings


class BadRequest(Exception):
    pass


class _Log:
    def __init__(self, exc=None):
        self.exc = exc

    def append(self, evs):
        if self.exc:
            raise self.exc
        return len(evs)


def test_ok():
    assert append_rulings(_Log(), [1, 2]) == 2


def test_badrequest_exits_with_message():
    with pytest.raises(SystemExit) as ei:
        append_rulings(_Log(BadRequest("prompt_ver 'x' 不认识")), [1])
    assert "prompt_ver 'x' 不认识" in str(ei.value)


def test_other_errors_propagate():
    with pytest.raises(ValueError):
        append_rulings(_Log(ValueError("boom")), [1])
