"""Release metadata checks that mirror the release workflow's validation."""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_version_matches_changelog_and_limits():
    version = _read("VERSION").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    log = _read("CHANGELOG.md")
    m = re.search(r"^## v%s - .*\n\*\*Short:\*\* (.+)\n\*\*Long:\*\* (.+)$" % re.escape(version), log, re.M)
    assert m, "CHANGELOG.md needs an entry for the current VERSION"
    short, long_ = m.group(1), m.group(2)
    assert 0 < len(short) <= 50, len(short)
    assert 0 < len(long_) <= 250, len(long_)


def test_deploy_compose_pins_current_version():
    version = _read("VERSION").strip()
    assert "mybadreligon/pricewatch:%s" % version in _read("deploy/compose.yaml")
    assert ("# Release v%s" % version) in _read("deploy/RELEASE.md")


def test_dockerfile_follows_port_and_runs_non_root():
    d = _read("Dockerfile")
    assert "${PORT}" in d and "127.0.0.1" in d
    assert "USER 1000:100" in d and "tini" in d
    assert "# syntax" not in d


def test_healthz_returns_version():
    main = _read("app/main.py")
    assert '"version": __version__' in main


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
