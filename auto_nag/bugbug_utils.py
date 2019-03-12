import lzma
import os
import shutil
from urllib.request import urlretrieve
import requests
from libmozdata.bugzilla import Bugzilla
from auto_nag.bzcleaner import BzCleaner


class BugbugScript(BzCleaner):
    def retrieve_model(self, name):
        os.makedirs('models', exist_ok=True)

        file_name = f'{name}model'  # noqa: E999
        file_path = os.path.join('models', file_name)

        model_url = f'https://index.taskcluster.net/v1/task/project.releng.services.project.testing.bugbug_train.latest/artifacts/public/{file_name}.xz'  # noqa
        r = requests.head(model_url, allow_redirects=True)
        new_etag = r.headers['ETag']

        try:
            with open(f'{file_path}.etag', 'r') as f:  # noqa
                old_etag = f.read()
        except IOError:
            old_etag = None

        if old_etag != new_etag:
            urlretrieve(model_url, f'{file_path}.xz')

            with lzma.open(f'{file_path}.xz', 'rb') as input_f:  # noqa
                with open(file_path, 'wb') as output_f:
                    shutil.copyfileobj(input_f, output_f)

            with open(f'{file_path}.etag', 'w') as f:  # noqa
                f.write(new_etag)

        return file_path

    def ignore_bug_summary(self):
        return False

    def all_include_fields(self):
        return True

    def get_data(self):
        return {'bugs': {}}

    def bughandler(self, bug, data):
        data['bugs'][bug['id']] = bug

    def retrieve_history(self, bugs):
        """Retrieve bug history"""

        def history_handler(bug):
            bugs[int(bug['id'])]['history'] = bug['history']

        Bugzilla(
            bugids=[bug_id for bug_id in bugs.keys()], historyhandler=history_handler
        ).get_data().wait()

    def retrieve_comments_and_attachments(self, bugs):
        """Retrieve bug comments and attachments"""

        def comment_handler(bug, bug_id):
            bugs[int(bug_id)]['comments'] = bug['comments']

        def attachment_handler(bug, bug_id):
            bugs[int(bug_id)]['attachments'] = bug

        Bugzilla(
            bugids=[bug_id for bug_id in bugs.keys()],
            commenthandler=comment_handler,
            attachmenthandler=attachment_handler,
            comment_include_fields=['text', 'creation_time', 'count'],
            attachment_include_fields=[
                'id',
                'is_obsolete',
                'flags',
                'is_patch',
                'creator',
                'content_type',
                'creation_time',
            ],
        ).get_data().wait()
