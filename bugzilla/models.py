from remoteobjects import RemoteObject as RemoteObject_, fields

from .fields import StringBoolean, Datetime
import urlparse


# The datetime format is inconsistent.
DATETIME_FORMAT_WITH_SECONDS = '%Y-%m-%d %H:%M:%S %z'
DATETIME_FORMAT = '%Y-%m-%d %H:%M %Z'


class RemoteObject(RemoteObject_):

    def post_to(self, url):
        self._location = url
        self.post(self)
        return self.api_data['ref']

    def _get_location(self):
        if self.__location is not None:
            return self.__location
        else:
            return self.api_data.get('ref', None)

    def _set_location(self, url):
        self.__location = url

    _location = property(_get_location, _set_location)

'''
class BugLink(fields.Link):

    def install(self, attrname, cls):
        print cls
        print attrname
        self.of_cls = cls
        self.attrname = attrname
        if self.api_name is None:
            self.api_name = attrname

    def __decode__(self, foo):
        print foo

    def __get__(self, instance, owner):
        print "HERE"
        if instance._location is None:
            raise AttributeError('Cannot find URL of %s relative to URL-less %s' % (self.cls.__name__, owner.__name__))
        newurl = urlparse.urljoin(instance._location, self.api_name)
        print instance._location
        print newurl
        return self.cls.get(newurl)
'''


class Bug(RemoteObject):

    id = fields.Field()
    summary = fields.Field()
    assigned_to = fields.Object('User')
    reporter = fields.Object('User')
    target_milestone = fields.Field()
    attachments = fields.List(fields.Object('Attachment'))
    comments = fields.List(fields.Object('Comment'))
    history = fields.List(fields.Object('Changeset'))
    keywords = fields.List(fields.Object('Keyword'))
    status = fields.Field()
    resolution = fields.Field()

    creation_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    flags = fields.List(fields.Object('Flag'))
    blocks = fields.List(fields.Field())
    #depends_on = fields.List(BugLink(fields.Object('Bug')))
    #depends_on = BugLink(fields.List(fields.Object('Bug')))
    url = fields.Field()
    cc = fields.List(fields.Object('User'))
    keywords = fields.List(fields.Field())
    whiteboard = fields.Field()

    op_sys = fields.Field()
    platform = fields.Field()
    priority = fields.Field()
    product = fields.Field()
    qa_contact = fields.Object('User')
    severity = fields.Field()
    see_also = fields.List(fields.Field())
    version = fields.Field()

    alias = fields.Field()
    classification = fields.Field()
    component = fields.Field()
    is_cc_accessible = StringBoolean()
    is_everconfirmed = StringBoolean()
    is_reporter_accessible = StringBoolean()
    last_change_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    ref = fields.Field()

    # Needed for submitting changes.
    token = fields.Field()

    # Time tracking.
    actual_time = fields.Field()
    deadline = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    estimated_time = fields.Field()
    # groups = fields.Field() # unimplemented
    percentage_complete = fields.Field()
    remaining_time = fields.Field()
    work_time = fields.Field()

    def __repr__(self):
        return '<Bug %s: "%s">' % (self.id, self.summary)

    def __str__(self):
        return "[%s] - %s" % (self.id, self.summary)

    def __hash__(self):
        return self.id


class User(RemoteObject):

    name = fields.Field()
    real_name = fields.Field()
    ref = fields.Field()

    def __repr__(self):
        return '<User "%s">' % self.real_name

    def __str__(self):
        return self.real_name or self.name

    def __hash__(self):
        if not self or not self.name:
            return 0
        return self.name.__hash__()


class Attachment(RemoteObject):

    # Attachment data.
    id = fields.Field()
    attacher = fields.Object('User')
    creation_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    last_change_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    description = fields.Field()
    bug_id = fields.Field()
    bug_ref = fields.Field()

    # File data.
    file_name = fields.Field()
    size = fields.Field()
    content_type = fields.Field()

    # Attachment metadata.
    flags = fields.List(fields.Object('Flag'))
    is_obsolete = StringBoolean()
    is_private = StringBoolean()
    is_patch = StringBoolean()

    # Used for submitting changes.
    token = fields.Field()
    ref = fields.Field()

    # Only with attachmentdata=1
    data = fields.Field()
    encoding = fields.Field()

    def __repr__(self):
        return '<Attachment %s: "%s">' % (self.id, self.description)

    def __hash__(self):
        return self.id


class Comment(RemoteObject):

    id = fields.Field()
    author = creator = fields.Object('User')
    creation_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    text = fields.Field()
    is_private = StringBoolean()

    def __repr__(self):
        return '<Comment by %s on %s>' % (
            self.author, self.creation_time.strftime(DATETIME_FORMAT))

    def __str__(self):
        return self.text

    def __hash__(self):
        return self.id


class Change(RemoteObject):

    field_name = fields.Field()
    added = fields.Field()
    removed = fields.Field()

    def __repr__(self):
        return '<Change "%s": "%s" -> "%s">' % (self.field_name, self.removed,
                                                self.added)


class Changeset(RemoteObject):

    changer = fields.Object('User')
    changes = fields.List(fields.Object('Change'))
    change_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)

    def __repr__(self):
        return '<Changeset by %s on %s>' % (
            self.changer, self.change_time.strptime(DATETIME_FORMAT))


class Flag(RemoteObject):

    id = fields.Field()
    name = fields.Field()
    setter = fields.Object('User')
    status = fields.Field()
    requestee = fields.Object('User')
    type_id = fields.Field()

    def __repr__(self):
        return '<Flag "%s">' % self.name

    def __str__(self):
        return self.name

    def __hash__(self):
        return self.id


class Keyword(RemoteObject):

    name = fields.Field()

    def __repr__(self):
        return '<Keyword "%s">' % self.name

    def __str__(self):
        return self.name

    def __hash__(self):
        if not self or not self.name:
            return 0
        return self.name.__hash__()


class BugSearch(RemoteObject):
    
    bugs = fields.List(fields.Object('Bug'))
