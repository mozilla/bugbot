# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import sys

from . import config

config.load()

# We can remove this hack and load utils in the same line as config when we fix
# the libmozdata bug that doesn't allow to reset the configuration.
try:
    from . import utils
except ModuleNotFoundError:
    raise


VERSION = (0, 0, 1)
__version__ = ".".join(map(str, VERSION))


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
