"""A wrapper around netCDF4 to make its objects serialisable.

Objects in this module should work the same as the corresponding ones in
in netCDF4.  The only differences are (should be):

 * Objects have some extra attributes which can't then be used as netCDF4
   attributes (public ones are documented, others are '_'-prefixed).
 * Dataset.close doesn't raise an exception when the Dataset is already closed.
 * Some returned objects are replaced with wrappers from this module (for
   example, Dataset.variables contains Variable instead of netCDF4.Variable
   instances).
 * Objects obtained from a Dataset are the same instance every time, and
   Variable instances may still affect the data after being renamed (unlike in
   netCDF4).

    CLASSES

Dataset
MFDataset
Group
[Dimension]
Variable
[CompoundType, VLType, MFTime]

"""

import types
import copy_reg
from pickle import UnpicklingError

import netCDF4
from ordereddict import OrderedDict # provided by netCDF4

copy_reg.pickle(types.EllipsisType, lambda e: 'Ellipsis')

class Dataset (object):
    """A netCDF4.Dataset wrapper that can be serialised.

Takes the same arguments as netCDF4.Dataset.

An instance passed for serialisation becomes closed; to disable this behaviour,
set the instance's `close_on_serialise' attribute to False.  Each time the
serialised data is unserialised, it yields an open Dataset pointing to the same
file as the original Dataset.

It is possible to pass a closed instance for serialisation, and the unserialised
instance will still be open.

Note that, for example, serialising and retrieving a Dataset and one of its
Variable instances will yield a Dataset and Variable that are no longer
connected.  Instead, do this with only one object in the hierarchy and retrieve
the other objects through that one once retrieved.

    ATTRIBUTES

closed: whether this instance is closed; don't change this.
close_on_serialise: whether to close this instance when serialised.

"""

    _private_attrs = (
        '_dataset_type', '_args', '_kwargs', '_wrapped'
    )
    _public_attrs = (
        'closed', 'close_on_serialise',
        'groups', 'variables', 'parent'
    )
    _dataset_type = netCDF4.Dataset

    def __init__ (self, *args, **kwargs):
        self._init_dataset(args, kwargs)
        self._init_public_attrs()

    def _init_dataset (self, args, kwargs):
        self._args = args
        self._kwargs = kwargs
        self._wrapped = d = self._dataset_type(*args, **kwargs)
        # keeping lists of things around means they don't 'get detached'
        for attr, cls in (
            ('groups', Group),
            ('variables', Variable)
        ):
            val = OrderedDict((k, cls(self, v, k)) \
                              for k, v in getattr(d, attr).iteritems())
            setattr(self, attr, val)

    def _init_public_attrs (self):
        self.closed = False
        self.close_on_serialise = True
        self.parent = None

    # magic wrappers
    # TODO: __enter__, __exit__

    def __str__ (self):
        return '{0}({1})'.format(self.__class__.__name__, str(self._wrapped))

    def __unicode__ (self):
        return u'{0}({1})'.format(self.__class__.__name__,
                                  unicode(self._wrapped))

    def __delattr__ (self, attr):
        delattr(self._wrapped, attr)

    def __getattr__ (self, attr):
        return getattr(self._wrapped, attr)

    def __setattr__ (self, attr, val):
        if attr in self._private_attrs + self._public_attrs:
            self.__dict__[attr] = val
        else:
            setattr(self._wrapped, attr, val)

    # serialisation

    def __getstate__ (self):
        if self.close_on_serialise:
            self.close()
        # everything can be reconstructed from args to netCDF4.Dataset, plus
        # some public attributes we want to preserve
        attrs = dict((k, getattr(self, k)) for k in self._public_attrs)
        return (self._args, self._kwargs, attrs)

    def __setstate__ (self, state):
        args, kwargs, attrs = state
        self._init(args, kwargs)
        self.__dict__.update(attrs)

    # method wrappers

    def close (self):
        if not self.closed:
            self._wrapped.close()
            # set closed after so it doesn't get set on Group instances (which
            # will raise IOError in the above call)
            self.closed = True

    # TODO: createCompoundType, createDimension

    def createGroup (self, groupname):
        g = self._wrapped.createGroup(groupname)
        return g

    # TODO: createVLType

    def createVariable (self, *args, **kwargs):
        v = self._wrapped.createVariable(*args, **kwargs)
        name = args[0] if args else kwargs['varname']
        v = Variable(self, v, name)
        self.variables[name] = v
        return v

    # TODO: renameDimension

    def renameVariable (self, oldname, newname):
        self._wrapped.renameVariable(oldname, newname)
        vs = self.variables
        v = vs[oldname]
        del vs[oldname]
        v._name = newname
        vs[newname] = v

class MFDataset (Dataset):
    """A netCDF4.MFDataset wrapper that can be serialised; Dataset subclass.

Takes the same arguments as netCDF4.MFDataset.

See Dataset for serialisation details.

"""

    _dataset_type = netCDF4.MFDataset

class Group (Dataset):
    """A netCDF4.Group wrapper that can be serialised.

Takes a Dataset instance, a netCDF4.Group instance to wrap and the group's
name.

Like with netCDF4.Group, you shouldn't create one of these directly.

"""

    _private_attrs = Dataset._private_attrs + ('_name',)

    def __init__ (self, parent, group, name):
        self._wrapped = group
        self._name = name
        self._init_public_attrs()
        self.parent = parent

    # serialisation

    def __getstate__ (self):
        return (self.parent, self._name)

    def __setstate__ (self, state):
        parent, name = state
        try:
            group = parent._wrapped.groups[name]
        except KeyError:
            err = 'tried to unpickle a group that no longer exists (\'{0}\')'
            raise UnpicklingError(err.format(parent.path + name))
        self.__init__(parent, group, name)

class Variable (object):
    """A netCDF4.Variable wrapper that can be serialised.

Takes a Dataset instance, a netCDF4.Variable instance to wrap and the
variable's name.

Like with netCDF4.Variable, you shouldn't create one of these directly.

"""

    _private_attrs = ('_group', '_wrapped', '_name')

    def __init__ (self, group, variable, name):
        self._group = group
        self._wrapped = variable
        self._name = name

    # magic wrappers

    def __str__ (self):
        return '{0}({1})'.format(self.__class__.__name__, str(self._wrapped))

    def __unicode__ (self):
        return u'{0}({1})'.format(self.__class__.__name__,
                                  unicode(self._wrapped))

    def __delattr__ (self, attr):
        delattr(self._wrapped, attr)

    def __getattr__ (self, attr):
        return getattr(self._wrapped, attr)

    def __setattr__ (self, attr, val):
        if attr in Variable._private_attrs:
            self.__dict__[attr] = val
        else:
            setattr(self._wrapped, attr, val)

    def __getitem__ (self, index):
        return self._wrapped[index]

    def __setitem__ (self, index, val):
        self._wrapped[index] = val

    def __len__ (self):
        return len(self._wrapped)

    # serialisation

    def __getstate__ (self):
        return (self._group, self._name)

    def __setstate__ (self, state):
        group, name = state
        try:
            variable = group._wrapped.variables[name]
        except KeyError:
            err = 'tried to unpickle a variable that no longer exists ' \
                  '(\'{0}\' at \'{1}\')'.format(name, group.path)
            raise UnpicklingError(err)
        self.__init__(group, variable, name)

    # method wrappers

    def group (self):
        return self._group