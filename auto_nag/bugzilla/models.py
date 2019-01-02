import urlparse

from remoteobjects import RemoteObject as RemoteObject_, fields

from .fields import StringBoolean, Datetime
from utils import getVersions

# The datetime format is inconsistent.
DATETIME_FORMAT_WITH_SECONDS = '%Y-%m-%d %H:%M:%S %z'
DATETIME_FORMAT = '%Y-%m-%d %H:%M %Z'


class RemoteObject(RemoteObject_):

    def post_to(self, url):
        self._location = url
        self.post(self)
        return self.api_data['ref']

    def put_to(self, url):
        self._location = url
        self.put()

    def _get_location(self):
        if self.__location is not None:
            return self.__location
        else:
            return self.api_data.get('ref', None)

    def _set_location(self, url):
        self.__location = url

    _location = property(_get_location, _set_location)


class Comments(fields.List):
    """This is a bit of a mix between Link and List, retrieving the comments
    from an API call and then turning the returned data into a list of Comment
    objets"""
    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.attrname not in instance.__dict__:
            if instance._location is None:
                raise AttributeError('Cannot find URL of %s relative to URL-less %s'
                                     % (self.fld.cls.__name__, owner.__name__))
            newurl = urlparse.urljoin(instance._location + '/', self.api_name)
            value = RemoteObject.get(newurl, http=instance._http)
            value = value.api_data['bugs'][str(instance.id)]['comments']
            value = self.decode(value)
            instance.__dict__[self.attrname] = value
        return instance.__dict__[self.attrname]


class Bug(RemoteObject):
    id = fields.Field()
    summary = fields.Field()
    assigned_to = fields.Object('User', api_name='assigned_to_detail')
    creator = fields.Object('User', api_name='creator_detail')
    target_milestone = fields.Field()
    attachments = fields.List(fields.Object('Attachment'))
    comments = Comments(fields.Object('Comment'), api_name='comment')
    history = fields.List(fields.Object('Changeset'))
    keywords = fields.List(fields.Object('Keyword'))
    status = fields.Field()
    resolution = fields.Field()

    # TODO: These are Mozilla specific and should be generalized
    cf_blocking_20 = fields.Field()
    cf_blocking_fennec = fields.Field()
    cf_crash_signature = fields.Field()

    creation_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    flags = fields.List(fields.Object('Flag'))
    blocks = fields.List(fields.Field())
    depends_on = fields.List(fields.Field())
    url = fields.Field()
    cc = fields.List(fields.Object('User'), api_name='cc_detail')
    keywords = fields.List(fields.Field())
    whiteboard = fields.Field()

    op_sys = fields.Field()
    platform = fields.Field()
    priority = fields.Field()
    product = fields.Field()
    qa_contact = fields.Object('User', api_name='qa_contact_detail')
    severity = fields.Field()
    see_also = fields.List(fields.Field())
    version = fields.Field()

    alias = fields.Field()
    classification = fields.Field()
    component = fields.Field()
    is_cc_accessible = StringBoolean()
    is_everconfirmed = StringBoolean()
    is_creator_accessible = StringBoolean()
    last_change_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    ref = fields.Field()

    # Needed for submitting changes.
    token = fields.Field(api_name='update_token')

    # Time tracking.
    actual_time = fields.Field()
    deadline = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    estimated_time = fields.Field()
    groups = fields.List(fields.Field())
    percentage_complete = fields.Field()
    remaining_time = fields.Field()
    work_time = fields.Field()

    def __repr__(self):
        return '<Bug %s: "%s">' % (self.id, self.summary)

    def __str__(self):
        return "[Bug %s] - %s" % (self.id, self.summary)

    def __hash__(self):
        return self.id

    def get_fx_affected_versions(self):
        affected = []
        for version in getVersions():
            if "esr" in version:
                version = "_" + version
            if ('cf_status_firefox' + version in self.api_data and
               self.api_data['cf_status_firefox' + version] == 'affected'):
                affected.append(version)

        return affected


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
    creator = fields.Field()
    creation_time = Datetime(DATETIME_FORMAT_WITH_SECONDS)
    text = fields.Field()
    is_private = StringBoolean()

    def __repr__(self):
        return '<Comment by %s on %s>' % (
            self.creator, self.creation_time.strftime(DATETIME_FORMAT))

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
            self.changer, self.change_time.strftime(DATETIME_FORMAT))


class Flag(RemoteObject):

    id = fields.Field()
    name = fields.Field()
    setter = fields.Field()
    status = fields.Field()
    requestee = fields.Field()
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


class BugList(fields.List):
    def __get__(self, obj, cls):
        ret = super(BugList, self).__get__(obj, cls)
        for bug in ret:
            bug._location = urlparse.urljoin(obj._location, str(bug.id))
            bug._http = obj._http
        return ret


class BugSearch(RemoteObject):

    bugs = BugList(fields.Object('Bug'))
