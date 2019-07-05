# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from urllib.error import HTTPError
from urllib.request import urlretrieve

import hglib
import requests
import zstandard
from bugbug import db, repository
from bugbug.models.regressor import RegressorModel

from auto_nag import logger
from auto_nag.bugbug_utils import BugbugScript
from auto_nag.utils import get_login_info, nice_round


class Regressor(BugbugScript):
    def __init__(self):
        self.model_class = RegressorModel

        self.repo_dir = get_login_info()["repo_dir"]

        if not os.path.exists(self.repo_dir):
            cmd = hglib.util.cmdbuilder(
                "robustcheckout",
                "https://hg.mozilla.org/mozilla-central",
                self.repo_dir,
                purge=True,
                sharebase=self.repo_dir + "-shared",
                networkattempts=7,
                branch=b"tip",
            )

            cmd.insert(0, hglib.HGPATH)

            proc = hglib.util.popen(cmd)
            out, err = proc.communicate()
            if proc.returncode:
                raise hglib.error.CommandError(cmd, proc.returncode, out, err)

            logger.info("mozilla-central cloned")

            # Remove pushlog DB to make sure it's regenerated.
            try:
                os.remove(os.path.join(self.repo_dir, ".hg", "pushlog2.db"))
            except FileNotFoundError:
                logger.info("pushlog database doesn't exist")

        logger.info("Pulling and updating mozilla-central")
        with hglib.open(self.repo_dir) as hg:
            hg.pull(update=True)
        logger.info("mozilla-central pulled and updated")

        db.download_version(repository.COMMITS_DB)
        if db.is_old_version(repository.COMMITS_DB) or not os.path.exists(
            repository.COMMITS_DB
        ):
            db.download(repository.COMMITS_DB, force=True, support_files_too=True)

        super().__init__()
        self.model = self.model_class.load(self.retrieve_model())

    def retrieve_model(self):
        os.makedirs("models", exist_ok=True)

        file_name = f"{self.name()}model"
        file_path = os.path.join("models", file_name)

        model_url = f"https://index.taskcluster.net/v1/task/project.relman.bugbug.train_{self.name()}.latest/artifacts/public/{file_name}.zst"
        r = requests.head(model_url, allow_redirects=True)
        new_etag = r.headers["ETag"]

        try:
            with open(f"{file_path}.etag", "r") as f:
                old_etag = f.read()
        except IOError:
            old_etag = None

        if old_etag != new_etag:
            try:
                urlretrieve(model_url, f"{file_path}.zst")
            except HTTPError:
                logger.exception("Tool {}".format(self.name()))
                return file_path

            dctx = zstandard.ZstdDecompressor()
            with open(f"{file_path}.zst", "rb") as input_f:
                with open(file_path, "wb") as output_f:
                    dctx.copy_stream(input_f, output_f)

            with open(f"{file_path}.etag", "w") as f:
                f.write(new_etag)

        return file_path

    def description(self):
        return "[Using ML] Recently landed risky patches"

    def columns(self):
        return ["id", "summary", "result", "confidence"]

    def sort_columns(self):
        return lambda p: -p[3]

    def get_bugs(self, date="today", bug_ids=[]):
        self.query_url = ""

        # Ignore already analyzed commits.
        for commit in repository.get_commits():
            pass

        rev_start = f"children({commit['node']})"

        commits = repository.download_commits(self.repo_dir, rev_start, ret=True)

        commits = [commit for commit in commits if not commit["ever_backedout"]]

        probs = self.model.classify(commits, True)
        indexes = probs.argmax(axis=-1)

        result = {}
        for commit, prob, index in zip(commits, probs, indexes):
            result[commit["node"]] = {
                "id": commit["node"],
                "summary": commit["desc"].split("\n", 1)[0],
                "result": "Risky" if prob[1] > 0.5 else "Not risky",
                "confidence": nice_round(prob[index]),
            }

        return result


if __name__ == "__main__":
    Regressor().run()
