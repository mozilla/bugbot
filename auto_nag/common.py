import json
from urllib2 import urlopen


def loadJSON(url):
    return json.load(urlopen(url))


def get_current_versions(jsonVersion, key):
    # In X.Y, we just need X
    version = jsonVersion[key].split(".")
    return version[0]


def getCurrentVersion():
    jsonContent = loadJSON("https://product-details.mozilla.org/1.0/firefox_versions.json")
    esr_next_version = get_current_versions(jsonContent, "FIREFOX_ESR_NEXT")
    if esr_next_version:
        esr_version = esr_next_version
    else:
        # We are in a cycle where we don't have esr_next
        # For example, with 52.6, esr_next doesn't exist
        # But it will exist, once 60 is released
        # esr_next will be 60
        esr_version = get_current_versions(jsonContent, "FIREFOX_ESR")

    return {"central": get_current_versions(jsonContent, "FIREFOX_NIGHTLY"),
            "beta": get_current_versions(jsonContent, "LATEST_FIREFOX_DEVEL_VERSION"),
            "esr": esr_version,
            "release": get_current_versions(jsonContent, "LATEST_FIREFOX_VERSION"),
            }
