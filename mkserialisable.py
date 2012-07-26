"""Routines to make objects serialisable.

Each of the functions in this module makes a specific type of object
serialisable.  Here's a summary (see function documentation for details):

mk_ellipsis: Ellipsis.
mk_slots: classes with __slots__ but not __dict__.
mk_netcdf: netCDF4.
mk_cf: cf.

"""

import copy_reg

_done = []

# ellipsis

def mk_ellipsis ():
    """Make the Ellipsis builtin serialisable."""
    if 'ellipsis' in _done:
        return

    copy_reg.pickle(type(Ellipsis), lambda e: 'Ellipsis')

# slots

def _construct_slots (cls, attrs):
    o = object.__new__(cls)
    for k, v in attrs.iteritems():
        setattr(o, k, v)
    return o

def _reduce_slots (o):
    attrs = dict((k, getattr(o, k)) for k in o.__slots__ if hasattr(o, k))
    return _construct_slots, (type(o), attrs,)

def mk_slots (*objs):
    """Make the classes that have __slots__ but not __dict__ serialisable.

Takes a number of types (new-style classes) to make serialisable.

"""
    for cls in objs:
        copy_reg.pickle(cls, _reduce_slots)

# netcdf

def mk_netcdf ():
    """Make objects in the netCDF4 module serialisable.

Depends on ncserialisable; see that module's documentation for details.  This
replaces the netCDF4 module with ncserialisable directly through sys.modules;
to access netCDF4 directly, use ncserialisable.netCDF4.

Call this before importing any module that uses netCDF4.

"""
    if 'netcdf' in _done:
        return

    import sys
    import ncserialisable

    sys.modules['netCDF4'] = ncserialisable

# cf

def _construct_cf_units (attrs):
    u = object.__new__(cf.Units)
    for k, v in attrs.iteritems():
        setattr(u, k, v)
    if hasattr(u, 'units'):
        u.units = u.units
    return u

def _reduce_cf_units (u):
    attrs = dict((k, getattr(u, k)) for k in u.__slots__ if hasattr(u, k))
    return _construct_cf_units, (attrs,)

def mk_cf ():
    """Make objects in the cf module serialisable.

Calls mk_netcdf, and so depends on ncserialisable.

Call this before importing cf.

"""
    if 'cf' in _done:
        return

    mk_netcdf()

    global cf
    import cf

    mk_slots(
        cf.data.ElementProperties,
        cf.Data,
        cf.data.SliceData,
        #cf.Units,
        cf.pp.Variable,
        cf.pp.VariableCalc,
        cf.pp.VariableCalcBounds,
        cf.pp.VariableBounds,
        #cf.org_field.SliceVariable,
        #cf.org_field.SliceCoordinate,
        #cf.org_field.SliceField,
        #cf.org_field.SliceVariableList,
        #cf.org_field.SliceFieldList,
        #cf.org_field.Flags,
        cf.field.SliceField,
        cf.field.SliceFieldList,
        cf.Flags,
        cf.coordinate.SliceCoordinate,
        cf.variable.SliceVariable,
        cf.variable.SliceVariableList
    )

    copy_reg.pickle(cf.Units, _reduce_cf_units)