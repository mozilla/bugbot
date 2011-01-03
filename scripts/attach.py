#!/usr/bin/env python

import base64
import itertools
import os
import argparse

from bugzilla.models import Bug, Attachment, Flag, User, Comment
from bugzilla.agents import BugzillaAgent
from bugzilla.utils import urljoin, qs, get_credentials, FILE_TYPES

REVIEW = 4

class AttachmentAgent(BugzillaAgent):
    """Stores credentials, navigates the site."""

    def attach(self, bug_id, filename, description, patch=False,
               reviewer=None, comment='', content_type='text/plain'):
        """Create an attachment, add a comment, obsolete other attachments."""

        print 'Adding "%s" to %s' % (filename, bug_id)
        self._attach(bug_id, filename, description, patch,
                     reviewer, content_type)

        bug = self.get_bug(bug_id)

        if comment:
            print 'Adding the comment'
            self._comment(bug_id, comment)

        print 'Finding attachments to make obsolete...'
        self.obsolete(bug)

    def _attach(self, bug_id, filename, description, is_patch=False,
               reviewer=None, content_type='text/plain'):
        """Create a new attachment."""
        fields = {
            'data':         base64.b64encode(open(filename).read()),
            'encoding':     'base64',
            'file_name':    filename,
            'content_type': content_type,
            'description':  description,
            'is_patch':     is_patch,
        }

        if reviewer is not None:
            fields['flags'] = [Flag(type_id=REVIEW, status='?',
                                    requestee=User(name=reviewer))]

        url = urljoin(self.API_ROOT, 'bug/%s/attachment?%s' % (bug_id, self.qs()))
        return Attachment(**fields).post_to(url)

    def _comment(self, bug_id, comment):
        """Create a new comment."""
        url = urljoin(self.API_ROOT, 'bug/%s/comment?%s' % (bug_id, self.qs()))
        return Comment(text=comment).post_to(url)

    def obsolete(self, bug):
        """Ask what attachments should be obsoleted."""
        attachments = [a for a in bug.attachments
                       if not bool(int(a.is_obsolete))]

        if not attachments:
            return

        print "What attachments do you want to obsolete?"
        msg = '[{index}] {a.id}: "{a.description}" ({a.file_name})'
        for index, a in enumerate(attachments):
            print msg.format(index=index, a=a)

        numbers = raw_input('Enter the numbers (space-separated) of '
                            'attachments to make obsolete:\n').split()

        if not numbers:
            return

        map_ = dict((str(index), a) for index, a in enumerate(attachments))
        for num, _ in itertools.groupby(sorted(numbers)):
            try:
                self._obsolete(map_[num])
            except KeyError:
                pass

    def _obsolete(self, attachment):
        """Mark an attachment obsolete."""
        print "Obsoleting", attachment
        attachment.is_obsolete = True
        attachment._location += '?%s' % self.qs()
        attachment.put()

def main():

    # Script options
    parser = argparse.ArgumentParser(description='Submit Bugzilla attachments')

    parser.add_argument('bug_id',
                        type=int,
                        metavar='BUG',
                        help='Bug number')

    parser.add_argument('filename',
                        metavar='FILE',
                        help='File to upload')

    parser.add_argument('--description',
                        help='Attachment description',
                        required=True)

    parser.add_argument('--patch',
                        action='store_true',
                        help='Is this a patch?')

    parser.add_argument('--reviewer',
                        help='Bugzilla name of someone to r?')

    parser.add_argument('--comment',
                        help='Comment for the attachment')

    parser.add_argument('--content_type',
                        choices=FILE_TYPES,
                        help="File's content_type")

    args = parser.parse_args()

    if args.content_type:
        args.content_type = FILE_TYPES[args.content_type]

    # Get the API root, default to bugzilla.mozilla.org
    API_ROOT = os.environ.get('BZ_API_ROOT',
                              'https://api-dev.bugzilla.mozilla.org/latest/')

    # Authenticate
    username, password = get_credentials()

    # Load the agent
    bz = AttachmentAgent(API_ROOT, username, password)

    # Attach the file
    bz.attach(**dict(args._get_kwargs()))


if __name__ == '__main__':
    main()
