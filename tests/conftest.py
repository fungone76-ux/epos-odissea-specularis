"""Shared test bootstrap.

The production package root is deliberately side-effect free.  The existing
suite exercises the Resort runtime, so it opts into the headless Resort
extensions explicitly here.  GUI extensions are never loaded during test
collection.
"""

from epos.resort_bootstrap import bootstrap_resort_runtime

bootstrap_resort_runtime()
