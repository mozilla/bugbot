from typing import Iterable, Optional

from google.cloud import bigquery
from google.oauth2 import service_account

from bugbot import utils

SCOPES = {
    "cloud-platform": "https://www.googleapis.com/auth/cloud-platform",
    "drive": "https://www.googleapis.com/auth/drive",
}


def get_bq_client(
    project: str, scopes: Optional[Iterable[str]] = None
) -> bigquery.Client:
    """Get a bigquery.Client for a given project

    :param project: Name of the project.
    :param scopes: Optional iterable containing the scopes the client should have.
                   By default this will be the cloud-platform scopes required to
                   run queries.
    :returns: bigquery.Client
    """
    scope_urls = []
    if scopes is None:
        scope_urls.append(SCOPES["cloud-platform"])
    else:
        for item in scopes:
            scope_urls.append(SCOPES[item] if item in SCOPES else item)

    credentials = service_account.Credentials.from_service_account_info(
        utils.get_gcp_service_account_info()
    ).with_scopes(scope_urls)

    return bigquery.Client(project=project, credentials=credentials)
