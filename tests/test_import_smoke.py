"""Import-time smoke test for the FastAPI app.

This sandbox has no network access to install fastapi/sqlmodel/apscheduler/
apprise, so - same approach as test_rules.py - we stub just enough of
their surface for app.main to import cleanly and every route decorator to
apply without error. This catches typos, missing imports, and wiring
mistakes (e.g. calling a function that doesn't exist, wrong arg names)
that py_compile's syntax-only check can't. Real dependencies are used
wherever this app actually runs (Docker image / a normal dev env) - these
stubs are sandbox-only scaffolding.
"""
import os
import sys
import types
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PRICEWATCH_DATA_DIR", "/tmp/pricewatch_smoke_test_data")


def _install_stubs():
    # ---------------------------------------------------------- sqlmodel
    if "sqlmodel" not in sys.modules:
        sqlmodel_stub = types.ModuleType("sqlmodel")

        def Field(*a, **kw):
            return kw.get("default")

        class SQLModel:
            def __init_subclass__(cls, **kwargs):
                pass

            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        def create_engine(*a, **kw):
            return object()

        class _Result(list):
            def all(self):
                return list(self)

            def first(self):
                return self[0] if self else None

        class _Select:
            def where(self, *a, **kw):
                return self

            def order_by(self, *a, **kw):
                return self

            def limit(self, *a, **kw):
                return self

        class Session:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def exec(self, *a, **kw):
                return _Result()

            def add(self, *a, **kw):
                pass

            def commit(self):
                pass

            def refresh(self, *a, **kw):
                pass

            def get(self, *a, **kw):
                return None

            def delete(self, *a, **kw):
                pass

        def select(*a, **kw):
            return _Select()

        sqlmodel_stub.Field = Field
        sqlmodel_stub.SQLModel = SQLModel
        sqlmodel_stub.create_engine = create_engine
        sqlmodel_stub.Session = Session
        sqlmodel_stub.select = select
        sys.modules["sqlmodel"] = sqlmodel_stub

    # ---------------------------------------------------------- apprise
    if "apprise" not in sys.modules:
        apprise_stub = types.ModuleType("apprise")

        class Apprise:
            def add(self, *a, **kw):
                pass

            def notify(self, *a, **kw):
                return True

        apprise_stub.Apprise = Apprise
        sys.modules["apprise"] = apprise_stub

    # ---------------------------------------------------------- fastapi
    if "fastapi" not in sys.modules:
        fastapi_stub = types.ModuleType("fastapi")

        def _decorator(*dargs, **dkwargs):
            def wrap(fn):
                return fn
            return wrap

        class FastAPI:
            def __init__(self, *a, **kw):
                pass

            def get(self, *a, **kw):
                return _decorator()

            def post(self, *a, **kw):
                return _decorator()

            def delete(self, *a, **kw):
                return _decorator()

            def put(self, *a, **kw):
                return _decorator()

            def on_event(self, *a, **kw):
                return _decorator()

            def mount(self, *a, **kw):
                pass

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=None):
                self.status_code = status_code
                self.detail = detail

        class Form:
            def __init__(self, *a, **kw):
                pass

        class Request:
            pass

        fastapi_stub.FastAPI = FastAPI
        fastapi_stub.Form = Form
        fastapi_stub.HTTPException = HTTPException
        fastapi_stub.Request = Request
        sys.modules["fastapi"] = fastapi_stub

        responses_stub = types.ModuleType("fastapi.responses")
        for name in ["HTMLResponse", "RedirectResponse", "JSONResponse", "FileResponse"]:
            setattr(responses_stub, name, type(name, (), {"__init__": lambda self, *a, **kw: None}))
        sys.modules["fastapi.responses"] = responses_stub

        staticfiles_stub = types.ModuleType("fastapi.staticfiles")

        class StaticFiles:
            def __init__(self, *a, **kw):
                pass

        staticfiles_stub.StaticFiles = StaticFiles
        sys.modules["fastapi.staticfiles"] = staticfiles_stub

        templating_stub = types.ModuleType("fastapi.templating")

        class Jinja2Templates:
            def __init__(self, *a, **kw):
                pass

            def TemplateResponse(self, *a, **kw):
                return None

        templating_stub.Jinja2Templates = Jinja2Templates
        sys.modules["fastapi.templating"] = templating_stub

    # ---------------------------------------------------------- apscheduler
    if "apscheduler" not in sys.modules:
        apscheduler_stub = types.ModuleType("apscheduler")
        sys.modules["apscheduler"] = apscheduler_stub

        schedulers_stub = types.ModuleType("apscheduler.schedulers")
        sys.modules["apscheduler.schedulers"] = schedulers_stub

        background_stub = types.ModuleType("apscheduler.schedulers.background")

        class BackgroundScheduler:
            def __init__(self, *a, **kw):
                self.running = False
                self._jobs = {}

            def start(self):
                self.running = True

            def add_job(self, func, trigger=None, id=None, **kw):
                self._jobs[id] = func
                return object()

            def get_job(self, job_id):
                return self._jobs.get(job_id)

            def remove_job(self, job_id):
                self._jobs.pop(job_id, None)

            def get_jobs(self):
                return list(self._jobs.values())

        background_stub.BackgroundScheduler = BackgroundScheduler
        sys.modules["apscheduler.schedulers.background"] = background_stub

        triggers_stub = types.ModuleType("apscheduler.triggers")
        sys.modules["apscheduler.triggers"] = triggers_stub

        interval_stub = types.ModuleType("apscheduler.triggers.interval")

        class IntervalTrigger:
            def __init__(self, *a, **kw):
                pass

        interval_stub.IntervalTrigger = IntervalTrigger
        sys.modules["apscheduler.triggers.interval"] = interval_stub


_install_stubs()

import app.main  # noqa: E402  (import success = the smoke test)


def test_app_object_exists():
    assert app.main.app is not None


def test_expected_routes_are_defined_as_module_functions():
    # With decorators stubbed to no-ops, every @app.get/@app.post handler
    # is still just a plain function on the module - confirms the routes
    # we added actually got defined (would fail loudly on a typo'd name,
    # bad indentation moving a function out of module scope, etc).
    expected = [
        "deals_list",
        "deals_mark_all_read",
        "deal_detail",
        "deal_mark_read",
        "deal_toggle_favourite",
        "deal_refresh",
        "api_list_deals",
        "api_get_deal",
        "api_poll_deals",
    ]
    for name in expected:
        assert hasattr(app.main, name), f"missing route function: {name}"
        assert callable(getattr(app.main, name))


def test_rfd_jobs_wired_into_startup():
    import inspect
    src = inspect.getsource(app.main.on_startup)
    assert "rfd_jobs.run_feed_poll_job" in src
    assert "rfd_jobs.run_summary_refresh_job" in src


if __name__ == "__main__":
    test_app_object_exists()
    print("PASS test_app_object_exists")
    test_expected_routes_are_defined_as_module_functions()
    print("PASS test_expected_routes_are_defined_as_module_functions")
    test_rfd_jobs_wired_into_startup()
    print("PASS test_rfd_jobs_wired_into_startup")
    print("\n3 passed, 0 failed")
