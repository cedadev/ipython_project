import types
import copy_reg
from pickle import UnpicklingError

import netCDF4
from ordereddict import OrderedDict # provided by netCDF4

copy_reg.pickle(types.EllipsisType, lambda e: 'Ellipsis')

class Dataset (object):
    """A netCDF4.Dataset wrapper that can be serialised.

Takes the same arguments as a netCDF4.Dataset, and all methods and attributes
should work the same.

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

(those not provided by netCDF4.Dataset)

filename: the path of the opened file; don't change this.
closed: whether this instance is closed; don't change this.
close_on_serialise: whether to close this instance when serialised.

"""

    _private_attrs = ('_args', '_kwargs', '_dataset')
    _public_attrs = (
        'filename', 'closed', 'close_on_serialise',
        'variables'
    )

    def __init__ (self, *args, **kwargs):
        self._init(args, kwargs)
        self.filename = args[0] if args else kwargs['filename']
        self.closed = False
        self.close_on_serialise = True

    def _init (self, args, kwargs):
        self._args = args
        self._kwargs = kwargs
        self._dataset = d = netCDF4.Dataset(*args, **kwargs)
        self.variables = OrderedDict((k, Variable(self, v, k)) \
                                     for k, v in d.variables.iteritems())

    # magic wrappers
    # TODO: __enter__, __exit__

    def __str__ (self):
        return '{0}({1})'.format(Dataset.__name__, str(self._dataset))

    def __unicode__ (self):
        return u'{0}({1})'.format(Dataset.__name__, unicode(self._dataset))

    def __delattr__ (self, attr):
        delattr(self._variable, attr)

    def __getattr__ (self, attr):
        return getattr(self._dataset, attr)

    def __setattr__ (self, attr, val):
        if attr in Dataset._private_attrs + Dataset._public_attrs:
            self.__dict__[attr] = val
        else:
            setattr(self._dataset, attr, val)

    # serialisation

    def __getstate__ (self):
        if self.close_on_serialise:
            self.close()
        attrs = dict((k, getattr(self, k)) for k in Dataset._public_attrs)
        return (self._args, self._kwargs, attrs)

    def __setstate__ (self, state):
        args, kwargs, attrs = state
        self._init(args, kwargs)
        self.__dict__.update(attrs)

    # method wrappers

    def close (self):
        if not self.closed:
            self._dataset.close()
            self.closed = True

    def createVariable (self, *args, **kwargs):
        v = self._dataset.createVariable(*args, **kwargs)
        name = args[0] if args else kwargs['varname']
        v = Variable(self, v, name)
        self.variables[name] = v
        return v

    def renameVariable (self, oldname, newname):
        self._dataset.renameVariable(oldname, newname)
        vs = self.variables
        v = vs[oldname]
        del vs[oldname]
        v._name = newname
        vs[newname] = v

class Variable (object):
    """A netCDF4.Variable wrapper that can be serialised.

Takes a Dataset instance, a netCDF4.Variable instance to wrap and the
variable's name.

Like with netCDF4.Variable, you shouldn't create one of these directly.

"""

    _private_attrs = ('_dataset', '_variable', '_name')

    def __init__ (self, dataset, variable, name):
        self._dataset = dataset
        self._variable = variable
        self._name = name

    # magic wrappers

    def __str__ (self):
        return '{0}({1})'.format(Variable.__name__, str(self._variable))

    def __unicode__ (self):
        return u'{0}({1})'.format(Variable.__name__, unicode(self._variable))

    def __delattr__ (self, attr):
        delattr(self._variable, attr)

    def __getattr__ (self, attr):
        return getattr(self._variable, attr)

    def __setattr__ (self, attr, val):
        if attr in Variable._private_attrs:
            self.__dict__[attr] = val
        else:
            setattr(self._variable, attr, val)

    def __getitem__ (self, index):
        return self._variable[index]

    def __setitem__ (self, index, val):
        self._variable[index] = val

    def __len__ (self):
        return len(self._variable)

    # serialisation

    def __getstate__ (self):
        return (self._dataset, self._name)

    def __setstate__ (self, state):
        dataset, name = state
        try:
            variable = dataset._dataset.variables[name]
        except KeyError:
            err = 'tried to unpickle a variable that no longer exists ' \
                  '(\'{0}\' in \'{1}\' at \'{2}\')'
            raise UnpicklingError(err.format(self._name, self._dataset.filename,
                                             self._dataset.path))
        self.__init__(dataset, variable, name)

    # method wrappers

    def group (self):
        return self._dataset