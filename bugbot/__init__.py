# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import os
import sys
from subprocess import check_output

import sentry_sdk

from . import config

__version__ = (
    check_output(["git", "tag", "--sort=-version:refname"])
    .decode("utf-8")
    .splitlines()[0]
)


sentry_sdk.init(
    dsn="https://866f146f649d6ffcac86175a1e2513f2@o1069899.ingest.us.sentry.io/4510268495101953",
    release=__version__,
    environment=os.getenv("ENVIRONMENT", "development"),
    dist=check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").rstrip(),
    server_name=check_output("hostname").decode("utf-8").rstrip(),
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
    # Enable sending logs to Sentry
    enable_logs=True,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    # Set profile_session_sample_rate to 1.0 to profile 100%
    # of profile sessions.
    profile_session_sample_rate=1.0,
)

sentry_sdk.profiler.start_profiler()

config.load()

# We can remove this hack and load utils in the same line as config when we fix
# the libmozdata bug that doesn't allow to reset the configuration.
try:
    from . import utils
except ModuleNotFoundError:
    raise


path = utils.get_config("common", "log")

logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

error = logging.FileHandler(path)
error.setLevel(logging.ERROR)
error.setFormatter(formatter)
logger.addHandler(error)


def _handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else:
        logger.critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )


sys.excepthook = _handle_uncaught_exception
