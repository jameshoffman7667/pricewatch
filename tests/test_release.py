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


def test_health_start_period_is_30s_in_image_and_compose():
    assert "--start-period=30s" in _read("Dockerfile")
    assert "start_period: 30s" in _read("deploy/compose.yaml")
    assert "/healthz" in _read("deploy/compose.yaml") and "$${PORT}" in _read("deploy/compose.yaml")


def test_release_workflow_triggers_on_main_version_push_without_tag_push():
    w = _read(".github/workflows/release.yml")
    assert 'branches: ["main"]' in w and '- "VERSION"' in w and '- "package.json"' in w
    assert 'tags: ["v*.*.*"]' in w  # manual fallback only
    assert "contents: write" in w
    assert 'gh release create "v$VERSION" --target "$GITHUB_SHA"' in w
    assert "group: release" in w and "cancel-in-progress: false" in w
    assert "refs/tags/v$VERSION" in w  # fails when the tag already exists


def test_healthz_returns_version():
    main = _read("app/main.py")
    assert '"version": __version__' in main


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
