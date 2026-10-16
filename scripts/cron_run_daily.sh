#!/bin/bash

source ./scripts/cron_common_start.sh

# Update the people.json file
python -m bugbot.iam


# Detect accessibility-related bugs using accessibility model from bugbug
python -m bugbot.rules.accessibilitybug --production

# Try to detect potential performance-related bugs using bugbug
python -m bugbot.rules.performancebug --production

# Try to detect potential performance alerts that have been inactive for too long
python -m bugbot.rules.perfalert_inactive_regression --production

# Send an email about all performance alerts who were recently resolved
python -m bugbot.rules.perfalert_resolved_regression --production

# Try to detect potential telemetry alerts that have been inactive for too long
python -m bugbot.rules.telemetryalert_inactive_regression --production

# Update the webcompat score fields
python -m bugbot.rules.webcompat_score --production

# Update the links in bugs associated with web features
python -m bugbot.rules.web_platform_features --production

# Clear needinfos on bugs that have been closed or moved to a graveyard product
python -m bugbot.rules.closed_bug_ni_cleanup --production

# Clear uplift needinfos on closed bugs no longer affecting any Firefox version
python -m bugbot.rules.uplift_ni_cleanup --production

# Clear needinfos requested from accounts that cannot answer
python -m bugbot.rules.unanswerable_ni_cleanup --production

# Send a mail if the logs are not empty
# MUST ALWAYS BE THE LAST COMMAND
python -m bugbot.log --send

# Set nightly status to affected on newly filed regressions
python -m bugbot.rules.regression_new_set_nightly_affected --production

source ./scripts/cron_common_end.sh
