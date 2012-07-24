"""A context manager to preserve global variables over IPython-parallel.

See the PreserveVars class.

"""

from IPython.parallel import interactive

_base_store_name = '_preservevars_store'

@interactive
def _enter (base_store_name, data):
    # get variable to store in (can't be in data)
    store_name = base_store_name
    while store_name in data:
        store_name += '_'
    # initialise store
    gl = globals()
    to_del = []
    store = {}
    if store_name in gl:
        old_store = gl[store_name]
    else:
        to_del.append(store_name)
        old_store = None
    gl[store_name] = (to_del, store, old_store)
    # store data and set new values
    for name, val in data.iteritems():
        if name in gl:
            store[name] = gl[name]
        else:
            to_del.append(name)
        gl[name] = val
    return store_name

@interactive
def _exit (store_name):
    # get store
    gl = globals()
    to_del, store, old_store = gl[store_name]
    # replace data that existed
    for name, val in store.iteritems():
        gl[name] = val
    gl[store_name] = old_store
    # delete references for data that didn't exist
    for name in to_del:
        del gl[name]


class PreserveVars:
    """A context manager to preserve global variables over IPython-parallel.

PreserveVars(dv[, data], **kwargs)

dv: the DirectView to use.
data: a dict of variables to transfer to the engines dv covers, as taken by
      dv.push.
kwargs: keyword arguments are also transferred.  That is,

    PreserveVars({'x': 5, 'y': 10})

        is equivalent to

    PreserveVars(x = 5, y = 10)

        or even

    PreserveVars({'x': 5}, y = 10)

"""

    def __init__ (self, dv, data = {}, **kwargs):
        self.dv = dv
        data.update(kwargs)
        self.data = data

    def __enter__ (self):
        self.store_names = self.dv.apply(_enter, _base_store_name, self.data)

    def __exit__ (self, *args):
        dv = self.dv
        targets = dv.targets
        for target, store_name in zip(targets, self.store_names):
            dv.targets = [target]
            dv.apply(_exit, store_name)
        dv.targets = targets