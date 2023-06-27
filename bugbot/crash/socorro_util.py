# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

"""The code in this module was borrowed from Socorro (some parts were adjusted).
Each function, class, or dictionary is documented with a link to the original
source.
"""


import re
from functools import cached_property
from itertools import islice


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/crashstats/templatetags/jinja_helpers.py#L182-L203
def generate_bug_description_data(report) -> dict:
    crashing_thread = get_crashing_thread(report)
    parsed_dump = get_parsed_dump(report) or {}

    frames = None
    threads = parsed_dump.get("threads")
    if threads:
        thread_index = crashing_thread or 0
        frames = bugzilla_thread_frames(parsed_dump["threads"][thread_index])

    return {
        "uuid": report["uuid"],
        # NOTE(willkg): this is the redacted stack trace--not the raw one that can
        # have PII in it
        "java_stack_trace": report.get("java_stack_trace", None),
        # NOTE(willkg): this is the redacted mozcrashreason--not the raw one that
        # can have PII in it
        "moz_crash_reason": report.get("moz_crash_reason", None),
        "reason": report.get("reason", None),
        "frames": frames,
        "crashing_thread": crashing_thread,
    }


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/crashstats/templatetags/jinja_helpers.py#L227-L278
def bugzilla_thread_frames(thread):
    """Build frame information for bug creation link

    Extract frame info for the top frames of a crashing thread to be included in the
    Bugzilla summary when reporting the crash.

    :arg thread: dict of thread information including "frames" list

    :returns: list of frame information dicts

    """

    def frame_generator(thread):
        """Yield frames in a thread factoring in inlines"""
        for frame in thread["frames"]:
            for inline in frame.get("inlines") or []:
                yield {
                    "frame": frame.get("frame", "?"),
                    "module": frame.get("module", ""),
                    "signature": inline["function"],
                    "file": inline["file"],
                    "line": inline["line"],
                }

            yield frame

    # We only want to include 10 frames in the link
    MAX_FRAMES = 10

    frames = []
    for frame in islice(frame_generator(thread), MAX_FRAMES):
        # Source is an empty string if data isn't available
        source = frame.get("file") or ""
        if frame.get("line"):
            source += ":{}".format(frame["line"])

        signature = frame.get("signature") or ""

        # Remove function arguments
        if not signature.startswith("(unloaded"):
            signature = re.sub(r"\(.*\)", "", signature)

        frames.append(
            {
                "frame": frame.get("frame", "?"),
                "module": frame.get("module") or "?",
                "signature": signature,
                "source": source,
            }
        )

    return frames


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/crashstats/utils.py#L343-L359
def enhance_json_dump(dump, vcs_mappings):
    """
    Add some information to the stackwalker's json_dump output
    for display. Mostly applying vcs_mappings to stack frames.
    """
    for thread_index, thread in enumerate(dump.get("threads", [])):
        if "thread" not in thread:
            thread["thread"] = thread_index

        frames = thread["frames"]
        for frame in frames:
            enhance_frame(frame, vcs_mappings)
            for inline in frame.get("inlines") or []:
                enhance_frame(inline, vcs_mappings)

        thread["frames"] = frames
    return dump


# https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/crashstats/utils.py#L259-L340
def enhance_frame(frame, vcs_mappings):
    """Add additional info to a stack frame

    This adds signature and source links from vcs_mappings.

    """
    # If this is a truncation frame, then we don't need to enhance it in any way
    if frame.get("truncated") is not None:
        return

    if frame.get("function"):
        # Remove spaces before all stars, ampersands, and commas
        function = re.sub(r" (?=[\*&,])", "", frame["function"])
        # Ensure a space after commas
        function = re.sub(r",(?! )", ", ", function)
        frame["function"] = function
        signature = function
    elif frame.get("file") and frame.get("line"):
        signature = "%s#%d" % (frame["file"], frame["line"])
    elif frame.get("module") and frame.get("module_offset"):
        signature = "%s@%s" % (
            frame["module"],
            strip_leading_zeros(frame["module_offset"]),
        )
    elif frame.get("unloaded_modules"):
        first_module = frame["unloaded_modules"][0]
        if first_module.get("offsets"):
            signature = "(unloaded %s@%s)" % (
                first_module.get("module") or "",
                strip_leading_zeros(first_module.get("offsets")[0]),
            )
        else:
            signature = "(unloaded %s)" % first_module
    else:
        signature = "@%s" % frame["offset"]

    frame["signature"] = signature
    if signature.startswith("(unloaded"):
        # If the signature is based on an unloaded module, leave the string as is
        frame["short_signature"] = signature
    else:
        # Remove arguments which are enclosed in parens
        frame["short_signature"] = re.sub(r"\(.*\)", "", signature)

    if frame.get("file"):
        vcsinfo = frame["file"].split(":")
        if len(vcsinfo) == 4:
            vcstype, root, vcs_source_file, revision = vcsinfo
            if "/" in root:
                # The root is something like 'hg.mozilla.org/mozilla-central'
                server, repo = root.split("/", 1)
            else:
                # E.g. 'gecko-generated-sources' or something without a '/'
                repo = server = root

            if (
                vcs_source_file.count("/") > 1
                and len(vcs_source_file.split("/")[0]) == 128
            ):
                # In this case, the 'vcs_source_file' will be something like
                # '{SHA-512 hex}/ipc/ipdl/PCompositorBridgeChild.cpp'
                # So drop the sha part for the sake of the 'file' because
                # we don't want to display a 128 character hex code in the
                # hyperlink text.
                vcs_source_file_display = "/".join(vcs_source_file.split("/")[1:])
            else:
                # Leave it as is if it's not unwieldy long.
                vcs_source_file_display = vcs_source_file

            if vcstype in vcs_mappings:
                if server in vcs_mappings[vcstype]:
                    link = vcs_mappings[vcstype][server]
                    frame["file"] = vcs_source_file_display
                    frame["source_link"] = link % {
                        "repo": repo,
                        "file": vcs_source_file,
                        "revision": revision,
                        "line": frame["line"],
                    }
            else:
                path_parts = vcs_source_file.split("/")
                frame["file"] = path_parts.pop()


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/socorro/signature/utils.py#L405-L422
def strip_leading_zeros(text):
    """Strips leading zeros from a hex string.

    Example:

    >>> strip_leading_zeros("0x0000000000032ec0")
    "0x32ec0"

    :param text: the text to strip leading zeros from

    :returns: stripped text

    """
    try:
        return hex(int(text, base=16))
    except (ValueError, TypeError):
        return text


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/settings/base.py#L268-L293
# Link to source if possible
VCS_MAPPINGS = {
    "cvs": {
        "cvs.mozilla.org": (
            "http://bonsai.mozilla.org/cvsblame.cgi?file=%(file)s&rev=%(revision)s&mark=%(line)s#%(line)s"
        )
    },
    "hg": {
        "hg.mozilla.org": (
            "https://hg.mozilla.org/%(repo)s/file/%(revision)s/%(file)s#l%(line)s"
        )
    },
    "git": {
        "git.mozilla.org": (
            "http://git.mozilla.org/?p=%(repo)s;a=blob;f=%(file)s;h=%(revision)s#l%(line)s"
        ),
        "github.com": (
            "https://github.com/%(repo)s/blob/%(revision)s/%(file)s#L%(line)s"
        ),
    },
    "s3": {
        "gecko-generated-sources": (
            "/sources/highlight/?url=https://gecko-generated-sources.s3.amazonaws.com/%(file)s&line=%(line)s#L-%(line)s"
        )
    },
}


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/crashstats/views.py#L141-L153
def get_parsed_dump(report):
    # For C++/Rust crashes
    if "json_dump" in report:
        json_dump = report["json_dump"]

        # This is for displaying on the "Details" tab
        enhance_json_dump(json_dump, VCS_MAPPINGS)
        parsed_dump = json_dump
    else:
        parsed_dump = {}

    return parsed_dump


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/crashstats/views.py#L155-L160
def get_crashing_thread(report):
    if report["signature"].startswith("shutdownhang"):
        # For shutdownhang signatures, we want to use thread 0 as the crashing thread,
        # because that's the thread that actually contains the useful data about what
        # happened.
        return 0

    return report.get("crashing_thread")


# Original Socorro code: https://github.com/mozilla-services/socorro/blob/ff8f5d6b41689e34a6b800577d8ffe383e1e62eb/webapp/crashstats/crashstats/utils.py#L73-L195
class SignatureStats:
    def __init__(
        self,
        signature,
        num_total_crashes,
        rank=0,
        platforms=None,
        previous_signature=None,
    ):
        self.signature = signature
        self.num_total_crashes = num_total_crashes
        self.rank = rank
        self.platforms = platforms
        self.previous_signature = previous_signature

    @cached_property
    def platform_codes(self):
        return [x["short_name"] for x in self.platforms if x["short_name"] != "unknown"]

    @cached_property
    def signature_term(self):
        return self.signature["term"]

    @cached_property
    def percent_of_total_crashes(self):
        return 100.0 * self.signature["count"] / self.num_total_crashes

    @cached_property
    def num_crashes(self):
        return self.signature["count"]

    @cached_property
    def num_crashes_per_platform(self):
        num_crashes_per_platform = {
            platform + "_count": 0 for platform in self.platform_codes
        }
        for platform in self.signature["facets"]["platform"]:
            code = platform["term"][:3].lower()
            if code in self.platform_codes:
                num_crashes_per_platform[code + "_count"] = platform["count"]
        return num_crashes_per_platform

    @cached_property
    def num_crashes_in_garbage_collection(self):
        num_crashes_in_garbage_collection = 0
        for row in self.signature["facets"]["is_garbage_collecting"]:
            if row["term"].lower() == "t":
                num_crashes_in_garbage_collection = row["count"]
        return num_crashes_in_garbage_collection

    @cached_property
    def num_installs(self):
        return self.signature["facets"]["cardinality_install_time"]["value"]

    @cached_property
    def percent_of_total_crashes_diff(self):
        if self.previous_signature:
            # The number should go "up" when moving towards 100 and "down" when moving
            # towards 0
            return (
                self.percent_of_total_crashes
                - self.previous_signature.percent_of_total_crashes
            )
        return "new"

    @cached_property
    def rank_diff(self):
        if self.previous_signature:
            # The number should go "up" when moving towards 1 and "down" when moving
            # towards infinity
            return self.previous_signature.rank - self.rank
        return 0

    @cached_property
    def previous_percent_of_total_crashes(self):
        if self.previous_signature:
            return self.previous_signature.percent_of_total_crashes
        return 0

    @cached_property
    def num_startup_crashes(self):
        return sum(
            row["count"]
            for row in self.signature["facets"]["startup_crash"]
            if row["term"] in ("T", "1")
        )

    @cached_property
    def is_startup_crash(self):
        return self.num_startup_crashes == self.num_crashes

    @cached_property
    def is_potential_startup_crash(self):
        return (
            self.num_startup_crashes > 0 and self.num_startup_crashes < self.num_crashes
        )

    @cached_property
    def is_startup_window_crash(self):
        is_startup_window_crash = False
        for row in self.signature["facets"]["histogram_uptime"]:
            # Aggregation buckets use the lowest value of the bucket as
            # term. So for everything between 0 and 60 excluded, the
            # term will be `0`.
            if row["term"] < 60:
                ratio = 1.0 * row["count"] / self.num_crashes
                is_startup_window_crash = ratio > 0.5
        return is_startup_window_crash

    @cached_property
    def is_plugin_crash(self):
        for row in self.signature["facets"]["process_type"]:
            if row["term"].lower() == "plugin":
                return row["count"] > 0
        return False

    @cached_property
    def is_startup_related_crash(self):
        return (
            self.is_startup_crash
            or self.is_potential_startup_crash
            or self.is_startup_window_crash
        )
