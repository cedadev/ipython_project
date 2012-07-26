"""A wrapper around netCDF4 to make its objects serialisable.

Objects in this module should work the same as the corresponding ones in
in netCDF4.  The only differences are (should be):

 * Objects have some extra attributes which can't then be used as netCDF4
   attributes (these are all '_'-prefixed).
 * Some returned objects are replaced with wrappers from this module (for
   example, Dataset.variables contains Variable instead of netCDF4.Variable
   instances).
 * CompoundType and VLType instances have a group attribute

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

class CompoundType (object):
    """A netCDF4.CompoundType wrapper that can be serialised.

Takes a Dataset instance, a netCDF4.CompoundType instance to wrap and the
type's name.

Like with netCDF4.CompoundType, you shouldn't create one of these directly.

A CompoundType doesn't provide a way of retrieving its Dataset to close it (see
Dataset documentation for why this is necessary).  For this reason, this
wrapper provides a `group' attribute, which contains the Group instance it was
created through.

"""

    _private_attrs = ('group', '_wrapped', '_name')

    def __init__ (self, group, cmptype, name):
        self.group = group
        self._wrapped = cmptype
        self._name = name

    # magic wrappers

    def __str__ (self):
        return '{0}({1})'.format(self.__class__.__name__, str(self._wrapped))

    def __unicode__ (self):
        return u'{0}({1})'.format(self.__class__.__name__,
                                  unicode(self._wrapped))

    # serialisation

    def __getstate__ (self):
        return (self.group, self._name)

    def __setstate__ (self, state):
        group, name = state
        cmptype = group._want_wrapped('cmptypes', name, self)
        self.__init__(group, cmptype, name)


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

Diskless operation is not supported.

"""

    _private_attrs = (
        '_args', '_kwargs', '_wrapped', '_want_wrappeds'
    )
    _public_attrs = (
        'parent',
    )
    _dataset_type = netCDF4.Dataset

    def __init__ (self, *args, **kwargs):
        # if diskless, throw an exception
        if args[4] if len(args) >= 5 else kwargs.get('diskless', False):
            raise ValueError('diskless operation is not supported')
        self.parent = None
        self._init_dataset(args, kwargs)

    def _init_dataset (self, args, kwargs, reopen = False):
        self._args = args
        self._kwargs = kwargs
        if reopen:
            # if mode is write, don't allow reclobbering or raising an
            # exception: switch to append
            mode = args[1] if len(args) >= 2 else kwargs.get('mode', 'r')
            if mode in ('w', 'ws'):
                mode = mode.replace('w', 'a')
                if len(args) >= 2:
                    args = list(args)
                    args[1] = mode
                else:
                    kwargs['mode'] = mode
        self._wrapped = d = self._dataset_type(*args, **kwargs)

    # magic wrappers

    def __enter__ (self):
        return self

    def __exit__ (self, *args):
        self.close()

    def __str__ (self):
        return '{0}({1})'.format(self.__class__.__name__, str(self._wrapped))

    def __unicode__ (self):
        return u'{0}({1})'.format(self.__class__.__name__,
                                  unicode(self._wrapped))

    def __delattr__ (self, attr):
        if attr in self._private_attrs:
            del self.__dict__[attr]
        else:
            delattr(self._wrapped, attr)

    def __getattr__ (self, attr):
        val = getattr(self._wrapped, attr)
        # replace object dicts with dicts of wrappers
        cls = {
            'cmptypes': CompoundType,
            'dimensions': Dimension,
            'groups': Group,
            'vltypes': VLType,
            'variables': Variable
        }.get(attr, None)
        if cls is not None:
            return OrderedDict((k, cls(self, v, k)) \
                               for k, v in val.iteritems())

    def __setattr__ (self, attr, val):
        if attr in self._private_attrs + self._public_attrs:
            self.__dict__[attr] = val
        else:
            setattr(self._wrapped, attr, val)

    # serialisation

    def __getstate__ (self):
        # everything can be reconstructed from args to netCDF4.Dataset, plus
        # some public attributes we want to preserve
        attrs = dict((k, getattr(self, k)) for k in self._public_attrs)
        return (self._args, self._kwargs, attrs)

    def _want_wrapped (self, attr, key, instance, dataset = None):
        """Signal the Dataset that a netCDF4 object to wrap is needed.

This is used in unserialising objects.  This instance may be initialised after
some other objects, and if so, this method stores a request for the desired
object.

_want_wrapped (attr, key, instance[, dataset]) -> wrapped

attr, key: wrapped is obtained through getattr(ndataset, attr)[key], where
           ndataset is the netCDF4.Dataset instance.
instance: the object calling this function.
dataset: the Dataset instance to obtain ndataset from; defaults to this
         instance.  If given, this must be guaranteed to be unserialised before
         this instance (and so realistically, only dataset itself should pass
         this argument).

wrapped: the object, if it can be obtained now.  If this instance has not yet
         been initialised, this is None, and instance._wrapped will be done
         later (before this instance's unserialisation finishes).

"""
        if dataset is None:
            dataset = self
        if hasattr(dataset, '_wrapped'):
            # obtain and return the object now
            try:
                return getattr(dataset._wrapped, attr)[key]
            except KeyError:
                err = 'tried to unpickle a {0} that no longer exists ' \
                      '(\'{0}\' at \'{1}\')'
                raise UnpicklingError(err.format(attr[:-1], key, dataset.path))
        else:
            # not initialised yet: store a request
            if not hasattr(self, '_want_wrappeds'):
                self._want_wrappeds = {}
            if (dataset, attr) in self._want_wrappeds:
                self._want_wrappeds[(dataset, attr)].append((key, instance))
            else:
                self._want_wrappeds[(dataset, attr)] = [(key, instance)]

    def __setstate__ (self, state):
        args, kwargs, attrs = state
        self._init_dataset(args, kwargs, True)
        self.__dict__.update(attrs)
        # handle wrapped requests (see _want_wrapped)
        if hasattr(self, '_want_wrappeds'):
            for (dataset, attr), wanting in self._want_wrappeds.iteritems():
                wrappeds = getattr(dataset, attr)
                for key, instance in wanting:
                    try:
                        instance._wrapped = wrappeds[key]
                    except KeyError:
                        err = 'tried to unpickle a {0} that no longer ' \
                              'exists (\'{0}\' at \'{1}\')'
                        err = err.format(attr[:-1], key, dataset.path)
                        raise UnpicklingError(err)
            del self._want_wrappeds

    # method wrappers

    def close (self):
        self._wrapped.close()

    def createCompoundType (self, datatype, datatype_name):
        c = self._wrapped.createCompoundType(datatype, datatype_name)
        return CompoundType(self, c, datatype_name)

    def createDimension (self, dimname, size = None):
        d = self._wrapped.createDimension(dimname, size)
        return Dimension(self, d, dimname)

    def createGroup (self, groupname):
        g = self._wrapped.createGroup(groupname)
        return Group(self, g, groupname)

    def createVLType (self, datatype, datatype_name):
        v = self._wrapped.createVLType(datatype, datatype_name)
        return VLType(self, v, datatype_name)

    def createVariable (self, varname, datatype, *args, **kwargs):
        if isinstance(datatype, (CompoundType, VLType)):
            # netCDF4.Variable constructor expects a netCDF4.CompoundType or
            # netCDF4.VLType subclass, not CompoundType or VLType
            datatype = datatype._wrapped
        v = self._wrapped.createVariable(varname, datatype, *args, **kwargs)
        return Variable(self, v, varname)


class MFDataset (Dataset):
    """A netCDF4.MFDataset wrapper that can be serialised; Dataset subclass.

Takes the same arguments as netCDF4.MFDataset.

See Dataset for serialisation details.

"""

    _dataset_type = netCDF4.MFDataset


class Dimension (object):
    """A netCDF4.Dimension wrapper that can be serialised.

Takes a Dataset instance, a netCDF4.Dimension instance to wrap and the
dimension's name.

Like with netCDF4.Dimension, you shouldn't create one of these directly.

"""

    _private_attrs = ('_group', '_wrapped', '_name')

    def __init__ (self, group, dimension, name):
        self._group = group
        self._wrapped = dimension
        self._name = name

    # magic wrappers

    def __str__ (self):
        return '{0}({1})'.format(self.__class__.__name__, str(self._wrapped))

    def __unicode__ (self):
        return u'{0}({1})'.format(self.__class__.__name__,
                                  unicode(self._wrapped))

    def __len__ (self):
        return len(self._wrapped)

    # serialisation

    def __getstate__ (self):
        return (self._group, self._name)

    def __setstate__ (self, state):
        group, name = state
        dimension = group._want_wrapped('dimensions', name, self)
        self.__init__(group, dimension, name)

    # method wrappers

    def group (self):
        return self._group


class Group (Dataset):
    """A netCDF4.Group wrapper that can be serialised.

Takes a Dataset instance, a netCDF4.Group instance to wrap and the group's
name.

Like with netCDF4.Group, you shouldn't create one of these directly.

"""

    _private_attrs = Dataset._private_attrs + ('_name',)

    def __init__ (self, parent, group, name):
        self.parent = parent
        self._wrapped = group
        self._name = name

    # serialisation

    def _want_wrapped (self, attr, key, instance, group = None):
        if group is None:
            group = self
        return self.parent._want_wrapped(attr, key, instance, group)

    def __getstate__ (self):
        return (self.parent, self._name)

    def __setstate__ (self, state):
        parent, name = state
        group = parent._want_wrapped('groups', name, self)
        self.__init__(parent, group, name)


class VLType (object):
    """A netCDF4.VLType wrapper that can be serialised.

Takes a Dataset instance, a netCDF4.VLType instance to wrap and the
type's name.

Like with netCDF4.VLType, you shouldn't create one of these directly.

A VLType doesn't provide a way of retrieving its Dataset to close it (see
Dataset documentation for why this is necessary).  For this reason, this
wrapper provides a `group' attribute, which contains the Group instance it was
created through.

"""

    _private_attrs = ('group', '_wrapped', '_name')

    def __init__ (self, group, cmptype, name):
        self.group = group
        self._wrapped = cmptype
        self._name = name

    # magic wrappers

    def __str__ (self):
        return '{0}({1})'.format(self.__class__.__name__, str(self._wrapped))

    def __unicode__ (self):
        return u'{0}({1})'.format(self.__class__.__name__,
                                  unicode(self._wrapped))

    # serialisation

    def __getstate__ (self):
        return (self.group, self._name)

    def __setstate__ (self, state):
        group, name = state
        vltype = group._want_wrapped('vltypes', name, self)
        self.__init__(group, vltype, name)


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
        if attr in self._private_attrs:
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