"""A wrapper around netCDF4 to make its objects serialisable.

Objects in this module should work the same as the corresponding ones in
in netCDF4.  The only differences are (should be):

 * Objects have some extra attributes which can't then be used as netCDF4
   attributes (these are all '_'-prefixed).
 * Some returned objects are replaced with wrappers from this module (for
   example, Dataset.variables contains Variable instead of netCDF4.Variable
   instances).

For notes on serialisation, see the documentation for Dataset.

If you want to replace netCDF4 with this module, so that libraries that use it
don't need to change their imports, then before importing them, do:

    import sys
    sys.modules['netCDF4'] = sys.modules['ncserialisable']

"""

import types
import copy_reg
from pickle import UnpicklingError

import netCDF4
from netCDF4 import * # provides OrderedDict

copy_reg.pickle(types.EllipsisType, lambda e: 'Ellipsis')


class Dataset (object):
    """A netCDF4.Dataset wrapper that can be serialised.

Takes the same arguments as netCDF4.Dataset.

An instance passed for serialisation remains open itself, and each time the
serialised data is unserialised, it yields an open Dataset pointing to the same
file as the original Dataset.  Make sure to close all of these.

It is possible to pass a closed instance for serialisation, and the
unserialised instance will still be open.

Note that, for example, serialising and retrieving a Dataset and one of its
Variable instances will yield a Dataset and Variable that are no longer
connected.  Instead, do this with only one object in the hierarchy and retrieve
the other objects through that one once retrieved.  Serialising and retrieving
a list containing the same object twice, however, will return the same object
twice.

This means that serialising and retrieving, for example, a Variable instance
will create an open Dataset.  This should be accessed through the unserialised
instance and closed when finished.

"""

    _private_attrs = (
        '_dataset_type', '_args', '_kwargs', '_wrapped', '_want_wrappeds'
    )
    _public_attrs = (
        'parent',
    )
    _dataset_type = netCDF4.Dataset

    def __init__ (self, *args, **kwargs):
        self._init_dataset(args, kwargs)
        self._init_public_attrs()

    def _init_dataset (self, args, kwargs):
        self._args = args
        self._kwargs = kwargs
        self._wrapped = d = self._dataset_type(*args, **kwargs)

    def _init_public_attrs (self):
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

    def _get_wrapped (self, attr, cls):
        return OrderedDict((k, cls(self, v, k)) \
                           for k, v in getattr(self._wrapped, attr).iteritems())

    @property
    def variables (self):
        return self._get_wrapped('variables', Variable)

    @property
    def groups (self):
        return self._get_wrapped('groups', Group)

    # serialisation

    def __getstate__ (self):
        # everything can be reconstructed from args to netCDF4.Dataset, plus
        # some public attributes we want to preserve
        attrs = dict((k, getattr(self, k)) for k in self._public_attrs)
        return (self._args, self._kwargs, attrs)

    def _want_wrapped (self, attr, key, instance):
        if hasattr(self, '_wrapped'):
            try:
                return getattr(self._wrapped, attr)[key]
            except KeyError:
                err = 'tried to unpickle a {0} that no longer exists (\'{0}\')'
                raise UnpicklingError(err.format(attr[:-1], key))
        else:
            if not hasattr(self, '_want_wrappeds'):
                self._want_wrappeds = {}
            self._want_wrappeds[attr] = (key, instance)

    def __setstate__ (self, state):
        args, kwargs, attrs = state
        self._init_dataset(args, kwargs)
        self.__dict__.update(attrs)
        if hasattr(self, '_want_wrappeds'):
            for attr, wanting in self._want_wrappeds.iteritems():
                wrappeds = getattr(self, attr)
                for key, instance in wanting:
                    try:
                        instance._wrapped = wrappeds[key]
                    except KeyError:
                        err = 'tried to unpickle a {0} that no longer ' \
                              'exists (\'{0}\' at \'{1}\')'
                        err = err.format(attr[:-1], key, self.path)
                        raise UnpicklingError(err)
            del self._want_wrappeds

    # method wrappers

    def close (self):
        self._wrapped.close()

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
        parent._want_wrappeds('groups', name, self)
        self.__init__(parent, None, name)


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
        variable = group._want_wrapped('variables', name, self)
        self.__init__(group, variable, name)

    # method wrappers

    def group (self):
        return self._group