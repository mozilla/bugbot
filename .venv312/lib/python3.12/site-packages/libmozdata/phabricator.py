# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import collections
import enum
import json
import logging
import math
import time
from functools import cached_property
from urllib.parse import urlencode, urlparse

import hglib
import requests

from . import config

HGMO_JSON_REV_URL_TEMPLATE = "https://hg.mozilla.org/mozilla-central/json-rev/{}"
MOZILLA_PHABRICATOR_PROD = "https://phabricator.services.mozilla.com/api/"

PhabricatorPatch = collections.namedtuple(
    "PhabricatorPatch", "id, phid, patch, base_revision, commits, merged"
)

logger = logging.getLogger(__name__)


class BuildState(enum.Enum):
    Work = "work"
    Pass = "pass"
    Fail = "fail"


class UnitResultState(enum.Enum):
    Pass = "pass"
    Fail = "fail"
    Skip = "skip"
    Broken = "broken"
    Unsound = "unsound"


class ArtifactType(enum.Enum):
    Host = "host"
    WorkingCopy = "working-copy"
    File = "file"
    Uri = "uri"


def revision_available(repo, revision):
    """
    Check if a revision is available on a Mercurial repo
    """
    try:
        repo.identify(revision)
        return True
    except hglib.error.CommandError:
        return False


def as_list(name, value, value_type):
    """
    Helper to convert Phabricator inputs to list
    Supports unique and multiple values, checking their type
    """
    if isinstance(value, value_type):
        return [value]
    elif isinstance(value, list):
        assert all(
            map(lambda v: isinstance(v, value_type), value)
        ), "All values in {} should be of type {}".format(name, value_type)
        return value
    else:
        raise Exception("{0} must be a {1} or a list of {1}".format(name, value_type))


# Descriptions of the fields are available at
# https://phabricator.services.mozilla.com/conduit/method/harbormaster.sendmessage/,
# in the "Lint Results" paragraph.
class LintResult(dict):
    def __init__(
        self, name, code, severity, path, line=None, char=None, description=None
    ):
        self["name"] = name
        self["code"] = code
        self["severity"] = severity
        self["path"] = path
        if line is not None:
            self["line"] = line
        if char is not None:
            self["char"] = char
        if description is not None:
            self["description"] = description
        self.validates()

    def validates(self):
        """
        Check the input is a lint issue compatible with Phabricator
        """

        # Check required strings
        for key in ("name", "code", "severity", "path"):
            assert isinstance(self[key], str), "{} should be a string".format(key)

        # Check the severity is a valid value
        assert self["severity"] in (
            "advice",
            "autofix",
            "warning",
            "error",
            "disabled",
        ), "Invalid severity value: {}".format(self["severity"])

        # Check optional integers
        for key in ("line", "char"):
            value = self.get(key)
            if value:
                assert isinstance(value, int), "{} should be an int".format(key)

        return True


class UnitResult(dict):
    def __init__(self, name, result, **kwargs):
        self["name"] = name
        assert isinstance(result, UnitResultState), "result must be a UnitResultState"
        self["result"] = result.value

        for key in (
            "namespace",
            "engine",
            "duration",
            "path",
            "coverage",
            "details",
            "format",
        ):
            value = kwargs.get(key)
            if value is not None:
                self[key] = value

        self.validates()

    def validates(self):
        """
        Check the input is a unit result compatible with Phabricator
        """
        # Check name
        assert isinstance(self["name"], str), "name should be a string"

        # Check special optional types
        if "duration" in self:
            assert isinstance(
                self["duration"], (float, int)
            ), "Duration should be an int or float"
        if "coverage" in self:
            assert isinstance(self["coverage"], dict), "Coverage should be a dict"
        if "format" in self:
            assert self["format"] in ("text", "remarkup"), "Invalid format value"

        # Check optional strings
        for key in ("namespace", "engine", "path", "details"):
            if key in self:
                assert isinstance(self[key], str), "{} should be a string".format(key)


class PhabricatorRevisionNotFoundException(Exception):
    pass


class PhabricatorUserNotFoundException(Exception):
    pass


class PhabricatorBzNotFoundException(Exception):
    pass


class ConduitError(Exception):
    """
    Exception to be raised when Phabricator returns an error response.
    """

    def __init__(self, msg, error_code=None, error_info=None):
        super(ConduitError, self).__init__(msg)
        self.error_code = error_code
        self.error_info = error_info
        logger.warn(
            "Conduit API error {} : {}".format(
                self.error_code, self.error_info or "unknown"
            )
        )

    @classmethod
    def raise_if_error(cls, response_body):
        """
        Raise a ConduitError if the provided response_body was an error.
        """
        if response_body["error_code"] is not None:
            raise cls(
                response_body.get("error_info"),
                error_code=response_body.get("error_code"),
                error_info=response_body.get("error_info"),
            )


class PhabricatorAPI(object):
    """
    Phabricator Rest API client
    """

    def __init__(self, api_key, url=MOZILLA_PHABRICATOR_PROD, max_retries=5):
        self.USER_AGENT = config.get("User-Agent", "name", required=True)
        self.api_key = api_key
        self.url = url
        assert self.url.endswith("/api/"), "Phabricator API must end with /api/"

        # Number of API calls retries on 50x before raising an error
        self.max_retries = max_retries
        assert (
            isinstance(self.max_retries, int) and self.max_retries > 0
        ), "Invalid max_retries parameter"

    @cached_property
    def user(self):
        """
        Return the authenticated user details
        """
        return self.request("user.whoami")

    @property
    def hostname(self):
        parts = urlparse(self.url)
        return parts.netloc

    def get_header(self):
        """Get the header to use each query"""
        return {"User-Agent": self.USER_AGENT}

    def search_diffs(
        self,
        diff_phid=None,
        diff_id=None,
        revision_phid=None,
        output_cursor=False,
        **params,
    ):
        """
        Find details of differential diffs from a Differential diff or revision
        Multiple diffs can be returned (when using revision_phid)
        """
        constraints = {}
        if diff_phid is not None:
            constraints["phids"] = as_list("diff_phid", diff_phid, str)
        if diff_id is not None:
            constraints["ids"] = as_list("diff_id", diff_id, int)
        if revision_phid is not None:
            constraints["revisionPHIDs"] = as_list("revision_phid", revision_phid, str)
        out = self.request(
            "differential.diff.search", constraints=constraints, **params
        )

        def _clean(diff):
            # Make all fields easily accessible
            if "fields" in diff and isinstance(diff["fields"], dict):
                diff.update(diff["fields"])
                del diff["fields"]

            # Lookup base revision in refs
            diff["refs"] = {ref["type"]: ref for ref in diff["refs"]}
            try:
                diff["baseRevision"] = diff["refs"]["base"]["identifier"]
            except KeyError:
                diff["baseRevision"] = None

            return diff

        diffs = list(map(_clean, out["data"]))
        if output_cursor is True:
            return diffs, out["cursor"]
        return diffs

    def load_raw_diff(self, diff_id):
        """
        Load the raw diff content
        """
        return self.request("differential.getrawdiff", diffID=diff_id)

    def load_revision(self, rev_phid=None, rev_id=None, **params):
        """
        Find details of a differential revision
        """
        assert (rev_phid is not None) ^ (
            rev_id is not None
        ), "One and only one of rev_phid or rev_id should be passed"

        constraints = {}
        if rev_id is not None:
            constraints["ids"] = [rev_id]
        if rev_phid is not None:
            constraints["phids"] = [rev_phid]

        out = self.request(
            "differential.revision.search", constraints=constraints, **params
        )

        data = out["data"]
        if len(data) != 1:
            raise PhabricatorRevisionNotFoundException()
        return data[0]

    def edit_revision(self, revision_id, transactions):
        """
        Edit a differential revision
        """
        return self.request(
            "differential.revision.edit",
            objectIdentifier=revision_id,
            transactions=transactions,
        )

    def list_repositories(self):
        """
        List available repositories
        """
        out = self.request("diffusion.repository.search")
        return out["data"]

    def list_comments(self, revision_phid):
        """
        List and format existing inline comments for a revision
        """
        transactions = self.request(
            "transaction.search", objectIdentifier=revision_phid
        )
        return [
            {
                "diffID": transaction["fields"]["diff"]["id"],
                "filePath": transaction["fields"]["path"],
                "lineNumber": transaction["fields"]["line"],
                "lineLength": transaction["fields"]["length"],
                "content": comment["content"]["raw"],
            }
            for transaction in transactions["data"]
            for comment in transaction["comments"]
            if transaction["type"] == "inline"
            and transaction["authorPHID"] == self.user["phid"]
        ]

    def comment(self, revision_id, message):
        """
        Comment on a Differential revision
        Using a frozen method as new transactions does not
        seem to support inlines publication
        """
        return self.request(
            "differential.createcomment",
            revision_id=revision_id,
            message=message,
            attach_inlines=1,
        )

    def load_parents(self, revision_phid):
        """
        Recursively load parents from a stack of revision
        """
        parents, phids = [], [revision_phid]
        while phids:
            phid = phids.pop()
            out = self.request(
                "edge.search", types=["revision.parent"], sourcePHIDs=[phid]
            )
            for element in out["data"]:
                rev = element["destinationPHID"]
                if rev in parents:
                    break

                parents.append(rev)
                phids.append(rev)

        return parents

    def load_or_create_build_autotarget(self, object_phid, target_keys):
        """
        Retrieve or create a build autotarget.
        """
        res = self.request(
            "harbormaster.queryautotargets",
            objectPHID=object_phid,
            targetKeys=target_keys,
        )
        return res["targetMap"]

    def search_buildable(self, object_phid=None, buildable_phid=None):
        """
        Search HarborMaster buildables linked to an object (diff, revision, ...)
        """
        assert (object_phid is not None) or (
            buildable_phid is not None
        ), "Specify object_phid or buildable_phid"
        constraints = {}
        if object_phid is not None:
            constraints["objectPHIDs"] = [object_phid]
        if buildable_phid is not None:
            constraints["phids"] = [buildable_phid]
        out = self.request("harbormaster.buildable.search", constraints=constraints)
        return out["data"]

    def search_build(self, build_phid=None, buildable_phid=None, plans=[]):
        """
        Search HarborMaster build for a buildable
        Supports HarborMaster Build Plan filtering
        """
        assert (build_phid is not None) or (
            buildable_phid is not None
        ), "Specify build_phid or buildable_phid"
        constraints = {}
        if build_phid is not None:
            constraints["phids"] = [build_phid]
        if buildable_phid is not None:
            constraints["buildables"] = [buildable_phid]
        if plans:
            constraints["plans"] = plans
        out = self.request("harbormaster.build.search", constraints=constraints)
        return out["data"]

    def search_build_target(self, build_phid=None, build_target_phid=None):
        """
        Search HarborMaster build targets for a build
        """
        assert (build_phid is not None) or (
            build_target_phid is not None
        ), "Specify build_phid or build_target_phid"
        constraints = {}
        if build_phid is not None:
            constraints["buildPHIDs"] = [build_phid]
        if build_target_phid is not None:
            constraints["phids"] = [build_target_phid]

        out = self.request("harbormaster.target.search", constraints=constraints)
        return out["data"]

    def find_diff_build(self, object_phid, build_plan_phid):
        """
        Find a specific build and its targets for a Diff and an HarborMaster build plan
        """
        assert isinstance(object_phid, str)
        assert object_phid[0:10] in ("PHID-DIFF-", "PHID-DREV-")
        assert build_plan_phid.startswith("PHID-HMCP-")

        # First find the buildable for this diff
        buildables = self.search_buildable(object_phid=object_phid)
        assert len(buildables) == 1
        buildable = buildables[0]
        logger.info(
            "Found HarborMaster buildable id={id} phid={phid}".format(**buildable)
        )

        # Then find the build in that buildable & plan
        builds = self.search_build(
            buildable_phid=buildable["phid"], plans=[build_plan_phid]
        )
        assert len(buildables) == 1
        build = builds[0]
        logger.info("Found HarborMaster build id={id} phid={phid}".format(**build))

        # Finally look for the build targets
        targets = self.search_build_target(build_phid=build["phid"])
        logger.info("Found {} HarborMaster build targets".format(len(targets)))

        return build, targets

    def find_target_buildable(self, build_target_phid):
        """
        Find a Phabricator buildable from its build target
        """
        assert isinstance(build_target_phid, str)
        assert build_target_phid.startswith("PHID-HMBT-")

        # First lookup the target
        targets = self.search_build_target(build_target_phid=build_target_phid)
        assert len(targets) == 1, "Build target not found"
        build_phid = targets[0]["fields"]["buildPHID"]
        logger.info("Found HarborMaster build {}".format(build_phid))

        # Then lookup the build
        builds = self.search_build(build_phid=build_phid)
        assert len(builds) == 1
        buildable_phid = builds[0]["fields"]["buildablePHID"]
        logger.info("Found HarborMaster buildable {}".format(buildable_phid))

        # Finally load the buidable
        buildables = self.search_buildable(buildable_phid=buildable_phid)
        assert len(buildables) == 1
        return buildables[0]

    def update_build_target(self, build_target_phid, state, unit=[], lint=[]):
        """
        Update unit test / linting data for a given build target.
        """
        assert all(
            map(lambda i: isinstance(i, LintResult), lint)
        ), "Only support LintResult instances"
        assert all(
            map(lambda i: isinstance(i, UnitResult), unit)
        ), "Only support UnitResult instances"
        assert isinstance(state, BuildState)
        return self.request(
            "harbormaster.sendmessage",
            receiver=build_target_phid,
            type=state.value,
            unit=unit,
            lint=lint,
        )

    def create_harbormaster_artifact(
        self, build_target_phid, artifact_type, key, payload
    ):
        """
        Create an artifact on HarborMaster
        """
        assert isinstance(artifact_type, ArtifactType)
        assert isinstance(payload, dict)
        return self.request(
            "harbormaster.createartifact",
            buildTargetPHID=build_target_phid,
            artifactType=artifact_type.value,
            artifactKey=key,
            artifactData=payload,
        )

    def create_harbormaster_uri(
        self, build_target_phid, artifact_key, name, uri, external=True
    ):
        """
        Helper to create a URI Harbormaster Artifact
        """
        out = self.create_harbormaster_artifact(
            build_target_phid=build_target_phid,
            artifact_type=ArtifactType.Uri,
            key=artifact_key,
            payload={"uri": uri, "name": name, "ui.external": external},
        )
        logger.info(
            "Created HarborMaster link on {} : {}".format(build_target_phid, uri)
        )
        return out

    def upload_coverage_results(self, object_phid, coverage_data):
        """
        Upload code coverage results to a Phabricator object.

        `coverage_data` is an object in the format:
        {
            "this/is/a/path1": "UNCXUNCXUNCX",
            "this/is/a/path2": "UUU",
        }

        The keys of the object are paths to the source files in the mozilla-central
        repository.
        The values are strings defining the coverage for each line of the source file
        (one character per line), where:
        - U means "not covered";
        - N means "not executable";
        - C means "covered";
        - X means that no data is available about that line.
        """
        # TODO: We are temporarily using arcanist.unit, but we should switch to something
        # different after https://bugzilla.mozilla.org/show_bug.cgi?id=1487843 is resolved.
        res = self.load_or_create_build_autotarget(object_phid, ["arcanist.unit"])
        build_target_phid = res["arcanist.unit"]

        self.update_build_target(
            build_target_phid,
            BuildState.Pass,
            unit=[
                UnitResult(
                    name="Aggregate coverage information",
                    result=UnitResultState.Pass,
                    coverage=coverage_data,
                )
            ],
        )

    def upload_lint_results(self, object_phid, state, lint_data):
        """
        Upload linting/static analysis results to a Phabricator object.

        `type` is either "pass" if no errors were found, "fail" otherwise.

        `lint_data` is an array of LintResult objects.
        """
        assert isinstance(state, BuildState)

        # TODO: We are temporarily using arcanist.lint, but we should switch to something
        # different after https://bugzilla.mozilla.org/show_bug.cgi?id=1487843 is resolved.
        res = self.load_or_create_build_autotarget(object_phid, ["arcanist.lint"])
        build_target_phid = res["arcanist.lint"]

        self.update_build_target(build_target_phid, state, lint=lint_data)

    def search_projects(self, slugs=None, **params):
        """
        Search Phabricator projects descriptions
        """
        constraints = {}
        if slugs:
            constraints["slugs"] = slugs
        out = self.request("project.search", constraints=constraints, **params)
        return out["data"]

    def search_users(self, constraints={}, **params):
        """
        Search multiple users
        """
        assert isinstance(constraints, dict)
        out = self.request("user.search", constraints=constraints, **params)
        return out["data"]

    def load_user(self, user_phid=None, user_id=None, **params):
        """
        Find details of a user
        """
        assert (user_phid is not None) ^ (
            user_id is not None
        ), "One and only one of user_phid or user_id should be passed"

        constraints = {}
        if user_id is not None:
            constraints["ids"] = [user_id]
        if user_phid is not None:
            constraints["phids"] = [user_phid]

        data = self.search_users(constraints, **params)
        if len(data) != 1:
            raise PhabricatorUserNotFoundException()
        return data[0]

    def search_bz_accounts(self, **params):
        """
        Search multiple Bugzilla accounts
        """
        return self.request("bugzilla.account.search", **params)

    def load_bz_account(self, user_phids=None, user_ids=None, **params):
        """
        Find Bugzilla user ids
        """
        if user_ids is not None and "ids" not in params:
            params["ids"] = user_ids if isinstance(user_ids, list) else [user_ids]
        if user_phids is not None and "phids" not in params:
            params["phids"] = (
                user_phids if isinstance(user_phids, list) else [user_phids]
            )

        data = self.search_bz_accounts(**params)
        if not data:
            raise PhabricatorBzNotFoundException()

        if not isinstance(data, list):
            data = [data]
        return data

    def request(self, path, **payload):
        """
        Send a request to Phabricator API
        """
        # Add api token to payload
        payload["__conduit__"] = {"token": self.api_key}

        # Run POST request on api, retrying on 50x errors
        for nb_try in range(1, self.max_retries + 1):
            response = requests.post(
                self.url + path,
                headers=self.get_header(),
                data=urlencode({"params": json.dumps(payload), "output": "json"}),
            )
            if response.status_code >= 500:
                # Retry after a while on 50x using exponential backoff
                backoff = math.exp(nb_try)
                logger.info(
                    f"Phabricator failed with status code {response.status_code}, retrying in {backoff:.1f} seconds..."
                )
                time.sleep(backoff)
            else:
                # Stop retrying on the first successful try or other HTTP errors
                break

        # Raise immediate 40x errors or out-of-retries 50x
        response.raise_for_status()

        # Check response
        data = response.json()
        assert "error_code" in data
        ConduitError.raise_if_error(data)

        # Outputs result
        assert "result" in data
        return data["result"]

    def load_patches_stack(self, diff_id, diff=None):
        """
        Load a stack of patches with related commits, to reach a given Phabricator Diff
        without hitting a local mercurial repository
        If the full diff details are provided, they can be used directly in the stack
        """

        # Diff PHIDs from our patch to its base
        def add_patch(diff):
            # Build a nicer Diff instance with associated commit & patch
            assert isinstance(diff, dict)
            assert "id" in diff
            assert "phid" in diff
            assert "baseRevision" in diff

            # Load diff's revision to get its status
            revision = self.load_revision(rev_phid=diff["revisionPHID"])
            status = revision["fields"]["status"]
            merged = status["closed"] is True and status["value"] == "published"

            # Load the patch itself (raw format)
            patch = self.load_raw_diff(diff["id"])
            diffs = self.search_diffs(
                diff_phid=diff["phid"], attachments={"commits": True}
            )
            commits = diffs[0]["attachments"]["commits"].get("commits", [])
            logger.info(
                "Adding patch #{} to stack ({})".format(
                    diff["id"], "merged" if merged else "non-merged"
                )
            )
            return PhabricatorPatch(
                diff["id"], diff["phid"], patch, diff["baseRevision"], commits, merged
            )

        # Load full diff when not provided by user
        if diff is None:
            diffs = self.search_diffs(diff_id=diff_id)
            if not diffs:
                raise Exception("Diff not found")
            diff = diffs[0]
        else:
            assert isinstance(diff, dict)
            assert "revisionPHID" in diff

        # Stack always has the top diff
        stack = [add_patch(diff)]

        parents = self.load_parents(diff["revisionPHID"])
        if parents:
            # Load all parent diffs
            for parent in parents:
                logger.info("Loading parent diff {}".format(parent))

                # Sort parent diffs by their id to load the most recent patch
                parent_diffs = sorted(
                    self.search_diffs(revision_phid=parent), key=lambda x: x["id"]
                )
                last_diff = parent_diffs[-1]

                # Add most recent patch to stack
                stack.insert(0, add_patch(last_diff))

        return stack
