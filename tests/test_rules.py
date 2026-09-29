"""Tests for the alert-rule logic in checker._should_notify.

This sandbox doesn't have network access to install sqlmodel/apprise,
so we stub just enough of their surface for app.checker to import
cleanly. This file (and its stubs) are not needed when the real
dependencies are installed (e.g. inside the Docker image / a normal
dev environment) - real sqlmodel/apprise are used there instead.
"""
import os
import sys
import types
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _install_stubs():
    if "sqlmodel" not in sys.modules:
        sqlmodel_stub = types.ModuleType("sqlmodel")

        def Field(*a, **kw):
            return kw.get("default")

        class SQLModel:
            def __init_subclass__(cls, **kwargs):
                pass

        def create_engine(*a, **kw):
            return None

        class Session:
            def __init__(self, *a, **kw):
                pass

        def select(*a, **kw):
            return None

        sqlmodel_stub.Field = Field
        sqlmodel_stub.SQLModel = SQLModel
        sqlmodel_stub.create_engine = create_engine
        sqlmodel_stub.Session = Session
        sqlmodel_stub.select = select
        sys.modules["sqlmodel"] = sqlmodel_stub

    if "apprise" not in sys.modules:
        apprise_stub = types.ModuleType("apprise")

        class Apprise:
            def add(self, *a, **kw):
                pass

            def notify(self, *a, **kw):
                return True

        apprise_stub.Apprise = Apprise
        sys.modules["apprise"] = apprise_stub


_install_stubs()

from app.checker import _should_notify  # noqa: E402


def _monitor(**overrides):
    defaults = dict(
        notify_on_any_change=True,
        notify_on_price_drop=True,
        notify_on_price_rise=False,
        min_change_percent=0.0,
        min_change_absolute=0.0,
        target_price=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_notifies_on_price_drop_by_default():
    m = _monitor()
    should, reason = _should_notify(m, 100.0, 90.0, content_changed=True)
    assert should is True
    assert "dropped" in reason


def test_does_not_notify_on_rise_by_default():
    m = _monitor()
    should, reason = _should_notify(m, 100.0, 110.0, content_changed=True)
    assert should is False


def test_notifies_on_rise_when_enabled():
    m = _monitor(notify_on_price_rise=True)
    should, reason = _should_notify(m, 100.0, 110.0, content_changed=True)
    assert should is True
    assert "rose" in reason


def test_respects_min_change_percent_threshold():
    m = _monitor(min_change_percent=5.0)
    # 1% drop, below threshold
    should, _ = _should_notify(m, 100.0, 99.0, content_changed=True)
    assert should is False
    # 10% drop, above threshold
    should, _ = _should_notify(m, 100.0, 90.0, content_changed=True)
    assert should is True


def test_respects_min_change_absolute_threshold():
    m = _monitor(min_change_absolute=10.0)
    should, _ = _should_notify(m, 100.0, 95.0, content_changed=True)  # $5 drop
    assert should is False
    should, _ = _should_notify(m, 100.0, 85.0, content_changed=True)  # $15 drop
    assert should is True


def test_target_price_fires_even_with_small_change_below_threshold():
    # Regression test: a target-price alert must still fire even when
    # the price move is too small to clear min_change_percent/absolute.
    m = _monitor(min_change_percent=50.0, min_change_absolute=50.0, target_price=95.0)
    should, reason = _should_notify(m, 100.0, 94.0, content_changed=True)
    assert should is True
    assert "target" in reason


def test_target_price_fires_with_no_prior_price():
    m = _monitor(target_price=50.0)
    should, reason = _should_notify(m, None, 45.0, content_changed=True)
    assert should is True


def test_no_notification_when_price_unchanged_and_no_target():
    m = _monitor()
    should, _ = _should_notify(m, 100.0, 100.0, content_changed=False)
    assert should is False


def test_content_change_alert_when_no_price_detected():
    m = _monitor()
    should, reason = _should_notify(m, None, None, content_changed=True)
    assert should is True
    assert "content changed" in reason


def test_no_content_change_alert_when_disabled():
    m = _monitor(notify_on_any_change=False)
    should, _ = _should_notify(m, None, None, content_changed=True)
    assert should is False


if __name__ == "__main__":
    import inspect
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_") and inspect.isfunction(obj)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
