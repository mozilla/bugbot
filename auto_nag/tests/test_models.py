
from auto_nag.bugzilla.agents import BMOAgent

bug_number = 656222
# Load our agent for BMO
bmo = BMOAgent()
bug = bmo.get_bug(bug_number)

class TestModels:
    # Test bugzilla agent methods
    def test_BugSearch(self):
        # Set whatever REST API options we want
        options = {
            'changed_after':    ['2012-12-24'],
            'changed_before':   ['2012-12-27'],
            'changed_field':    ['status'],
            'changed_field_to': ['RESOLVED'],
            'product':          ['Firefox'],
            'resolution':       ['FIXED'],
            'include_fields':   ['attachments'],
        }
        # Load our agent for BMO
        bmo = BMOAgent()
        # Get the bugs from the api
        buglist = bmo.get_bug_list(options)
        assert buglist != []

    def test_BugAttributes(self):
        attrs = ['summary', 'id', 'assigned_to', 'creator', 'target_milestone',
                 'attachments', 'comments', 'history', 'keywords', 'status',
                 'resolution', 'cf_blocking_20', 'cf_blocking_fennec',
                 'cf_crash_signature', 'creation_time', 'flags', 'blocks',
                 'depends_on', 'url', 'cc', 'keywords', 'whiteboard', 'op_sys',
                 'platform', 'priority', 'product', 'qa_contact', 'severity',
                 'see_also', 'version', 'alias', 'classification', 'component',
                 'is_cc_accessible', 'is_everconfirmed',
                 'is_creator_accessible', 'last_change_time', 'ref', 'token',
                 'actual_time', 'deadline', 'estimated_time',
                 'percentage_complete', 'remaining_time', 'work_time']

        for attr in attrs:
            assert hasattr(bug, attr)

    def test_Bugrepr(self):
        assert '<Bug ' in repr(bug)

    def test_Bugstr(self):
        assert '[Bug ' in str(bug)

    def test_Bughash(self):
        assert hash(bug) == bug_number

    def test_UserAttributes(self):
        attrs = ['name', 'real_name', 'ref']

        for attr in attrs:
            assert hasattr(bug.creator, attr)

    def test_Userrepr(self):
        creator = bug.creator
        assert '<User ' in repr(creator)

    def test_Userstr(self):
        creator = bug.creator
        assert str(creator) in repr(creator) and 'instance at' not in \
                                                 str(creator)

    def test_Userhash(self):
        creator = bug.creator
        assert isinstance(hash(creator), (int, long))

    def test_AttachmentAttributes(self):
        attrs = ['id', 'attacher', 'creation_time', 'last_change_time',
                 'last_change_time', 'description', 'bug_id', 'bug_ref',
                 'file_name', 'size', 'content_type', 'flags', 'is_obsolete',
                 'is_private', 'is_patch', 'token', 'ref', 'data', 'encoding']

        if bug.attachments:
            for attr in attrs:
                assert hasattr(bug.attachments[0], attr)

    def test_Attachmentrepr(self):
        if bug.attachments:
            attachment = bug.attachments[0]
            assert '<Attachment ' in repr(attachment)

    def test_Attachmenthash(self):
        if bug.attachments:
            assert isinstance(hash(bug.attachments[0]), (int, long))

    def test_CommentAttributes(self):
        attrs = ['id', 'creator', 'creation_time', 'text', 'is_private']
        if bug.comments:
            for attr in attrs:
                assert hasattr(bug.comments[0], attr)

    def test_Commentrepr(self):
        if bug.comments:
            assert '<Comment by' in repr(bug.comments[0])

    def test_Commentstr(self):
        if bug.comments:
            assert isinstance(str(bug.comments[0]), (str))

    def test_Commenthash(self):
        if bug.comments:
            assert isinstance(hash(bug.comments[0]), (int, long))

    def test_ChangeAttributes(self):
        attrs = ['field_name', 'added', 'removed']
        if bug.history:
            for attr in attrs:
                assert hasattr(bug.history[0].changes[0], attr)
    def test_Changerepr(self):
        if bug.history:
            assert '<Change ' in repr(bug.history[0].changes[0])

    def test_ChangesetAttributes(self):
        attrs = ['changer', 'changes', 'change_time']

        if bug.history:
            for attr in attrs:
                assert hasattr(bug.history[0], attr)

    def test_Changesetrepr(self):
        if bug.history:
            assert '<Changeset ' in repr(bug.history[0])

    def test_FlagAttributes(self):
        attrs = ['id', 'name', 'setter', 'status', 'requestee', 'type_id']
        if bug.flags:
            for attr in attrs:
                assert hasattr(bug.flags[0], attr)

    def test_Flagrepr(self):
        if bug.flags:
            assert '<Flag ' in repr(bug.flags[0])

    def test_Flagstr(self):
        if bug.flags:
            assert isinstance(str(bug.flags[0]), (str))

    def test_Flaghash(self):
        if bug.flags:
            assert isinstance(hash(bug.flags[0]), (int))

    def test_KeywordAttributes(self):
        attrs = ['name']

        if bug.keywords:
            for attr in attrs:
                assert hasattr(bug.keywords[0], attr)

    def test_Keywordrepr(self):
        if bug.keywords:
            if bug.keywords:
                assert '<Keyword ' in repr(bug.keywords[0])

    def test_Keywordstr(self):
        if bug.keywords:
            if bug.keywords:
                assert isinstance(str(bug.keywords[0]), (str))

    def test_Keywordhash(self):
        if bug.keywords:
            assert isinstance(hash(bug.keywords[0]), (int, long))
