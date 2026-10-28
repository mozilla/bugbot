# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import fnmatch
import json
import os

with open(os.path.join(os.path.dirname(__file__), "modules.json")) as f:
    data = json.load(f)
    MODULES = [module["name"] for module in data]


def __match(path, pattern):
    pattern = os.path.normpath(pattern)
    path = os.path.normpath(path)

    # If the pattern contains a '*', assume the pattern is correct and we don't have to modify it.
    if "*" in pattern:
        return fnmatch.fnmatch(path, pattern)
    # If the pattern contains a '.', assume it is a specific file.
    elif "." in pattern:
        return path == pattern
    # Otherwise, assume the pattern is a directory and add a '*' to match all its children.
    else:
        return fnmatch.fnmatch(path, pattern + "*")


def module_from_path(path):
    maxCommon = dict(module=None, directory="")

    for module in data:
        for directory in module["sourceDirs"]:
            if (
                len(os.path.commonprefix([path, directory]))
                > len(os.path.commonprefix([path, maxCommon["directory"]]))
            ) and __match(path, directory):
                maxCommon["module"] = module
                maxCommon["directory"] = directory

    # If we couldn't pinpoint the module, use some heuristics.
    if maxCommon["module"] is None:
        if (
            path.endswith("configure.in")
            or path.endswith("moz.build")
            or path.endswith("client.mk")
            or path.endswith("moz.configure")
            or path.endswith("aclocal.m4")
            or path.endswith("Makefile.in")
            or path.startswith("python/mach")
        ):
            return module_info("Build Config")

        if path.startswith("js/"):
            return module_info("JavaScript")

        if path.startswith("security/"):
            return module_info("security")

        if path.startswith("tools/profiler/"):
            return module_info("Code Analysis and Debugging Tools")

    return maxCommon["module"]


def module_info(moduleName):
    for module in data:
        if module["name"].lower() == moduleName.lower():
            return module


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mozilla Modules")
    parser.add_argument("-p", "--path", action="store", help="the path to the file")
    parser.add_argument("-m", "--module", action="store", help="the module name")

    args = parser.parse_args()

    if args.path:
        print(module_from_path(args.path))
    elif args.module:
        print(module_info(args.module))
    else:
        parser.print_help()
