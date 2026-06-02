from __future__ import annotations

from types import SimpleNamespace

import pytest

import tb_credentials as cred


class DummyLogger:
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password


class BrokenKeyring:
    def get_password(self, *args):
        raise RuntimeError("backend down")

    def set_password(self, *args):
        raise RuntimeError("backend down")


def make_args(username=None, password=None):
    return SimpleNamespace(username=username, password=password)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # load_dotenv writes os.environ directly (not tracked by monkeypatch),
    # so every test starts by clearing both variables.
    monkeypatch.delenv("TIMEBUTLER_USERNAME", raising=False)
    monkeypatch.delenv("TIMEBUTLER_PASSWORD", raising=False)


def test_cli_password_wins(tmp_path, monkeypatch):
    fake = FakeKeyring()
    fake.set_password("timebutler", "user@example.com", "from-keyring")
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(
        make_args("user@example.com", "from-cli"), tmp_path, DummyLogger()
    )
    assert (user, pw) == ("user@example.com", "from-cli")


def test_keyring_password_used(tmp_path, monkeypatch):
    fake = FakeKeyring()
    fake.set_password("timebutler", "user@example.com", "from-keyring")
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(
        make_args("user@example.com"), tmp_path, DummyLogger()
    )
    assert (user, pw) == ("user@example.com", "from-keyring")


def test_env_password_migrates_to_keyring(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "TIMEBUTLER_USERNAME=user@example.com\nTIMEBUTLER_PASSWORD=secret\nOTHER=keep\n",
        encoding="utf-8",
    )
    fake = FakeKeyring()
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == ("user@example.com", "secret")
    assert fake.store[("timebutler", "user@example.com")] == "secret"
    content = env.read_text(encoding="utf-8")
    assert "TIMEBUTLER_PASSWORD" not in content
    assert "OTHER=keep" in content
    assert "TIMEBUTLER_USERNAME=user@example.com" in content


def test_env_fallback_without_keyring(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TIMEBUTLER_USERNAME=u\nTIMEBUTLER_PASSWORD=p\n", encoding="utf-8")
    monkeypatch.setattr(cred, "keyring", None)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == ("u", "p")
    # no migration possible -> .env stays untouched
    assert "TIMEBUTLER_PASSWORD" in env.read_text(encoding="utf-8")


def test_broken_keyring_falls_back_to_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TIMEBUTLER_USERNAME=u\nTIMEBUTLER_PASSWORD=p\n", encoding="utf-8")
    monkeypatch.setattr(cred, "keyring", BrokenKeyring())
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == ("u", "p")
    assert "TIMEBUTLER_PASSWORD" in env.read_text(encoding="utf-8")


def test_missing_credentials_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cred, "keyring", None)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == (None, None)


def test_env_password_updates_differing_keyring_entry(tmp_path, monkeypatch):
    # user rotated the password in .env after an earlier migration
    env = tmp_path / ".env"
    env.write_text("TIMEBUTLER_USERNAME=u\nTIMEBUTLER_PASSWORD=new\n", encoding="utf-8")
    fake = FakeKeyring()
    fake.set_password("timebutler", "u", "old")
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert pw == "new"
    assert fake.store[("timebutler", "u")] == "new"
    assert "TIMEBUTLER_PASSWORD" not in env.read_text(encoding="utf-8")


def test_migration_handles_spaced_assignment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TIMEBUTLER_USERNAME=u\nTIMEBUTLER_PASSWORD = spaced\n", encoding="utf-8")
    fake = FakeKeyring()
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert pw == "spaced"
    assert "TIMEBUTLER_PASSWORD" not in env.read_text(encoding="utf-8")
