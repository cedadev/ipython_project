"""A module to compute the seasonal mean over a variable in a dataset.

See the run function.

"""

from IPython.parallel import Client, interactive
import numpy
from netCDF4 import MFDataset

@interactive
def _get_mean_worker (times):
    """Used by get_mean_parallel."""
    results = []
    index = [slice(None)] * time_index + [None, Ellipsis]
    for t0, t1 in times:
        index[time_index] = slice(t0, t1)
        arr = var[index]
        results.append(arr.mean(time_index))
    return numpy.array(results)

def get_mean_serial (var, time_index, times):
    """Compute the seasonal mean.

get_mean_serial(var, time_index, times) -> results

var: netCDF4 variable to average over.
time_index: the index of the time variable's dimension in var's dimensions.
times: a list of (a, b) indices indicating sets of times to take the mean over
       (var[a:b]).

results: the var array with time now in seasons.

"""
    results = []
    index = [slice(None)] * time_index + [None, Ellipsis]
    for t0, t1 in times:
        index[time_index] = slice(t0, t1)
        arr = var[index]
        results.append(arr.mean(time_index))
    return numpy.array(results)

def get_mean_parallel (dv, var, time_index, times):
    """Compute the seasonal mean in parallel.

get_mean_serial(dv, var, time_index, times) -> results

dv: IPython DirectView to use.
var: netCDF4 variable to average over.
time_index: the index of the time variable's dimension in var's dimensions.
times: a list of (a, b) indices indicating sets of times to take the mean over
       (var[a:b]).

results: the var array with time now in seasons.

"""
    # transfer var to the engines
    dv.push({'var': var, 'time_index': time_index})
    # do the calculation
    results = dv.parallel(block = True)(_get_mean_worker)(times)
    # close datasets
    dv.execute('var.group().close()')
    # clean up variables
    dv.execute('del var, time_index')
    return results

def run (files, var_name, parallel = True, season_length = 90, engines = None,
         var_path = '/', time_path = '/', time_name = 'time'):
    """Run a seasonal mean on a dataset.

run(files, var_name, parallel = True, season_length = 90, engines = None,
    var_path = '/', time_path = '/', time_name = 'time') -> results

files: a list of the netCDF data files to use, or just one.
var_name: the name of the variable to compute the mean of.
parallel: whether to run the computation in parallel (using IPython.parallel).
season_length: the length of a 'season' in whatever units the time variable has
               (the default makes sense for days).
engines: a list of engines to use if running in parallel.  The default is to
         use all available engines.
var_path, time_path: the path of the groups the temperature and time variables
                     are in within the dataset.
time_name: the name of the time variable.  This can actually be any
           one-dimensional variable - it doesn't need to represent time.

results: the array for the var variable, with time now in seasons.

"""
    if isinstance(files, basestring):
        files = [files]
    if parallel:
        c = Client()
        dv = c[:]
        if engines is not None:
            dv.targets = engines
        dv.block = True
        dv.execute('import numpy')
        dv.execute('from ncserialisable import MFDataset')

    d = MFDataset(files)
    try:
        # find variables
        vs = []
        for path, v_name in ((time_path, time_name), (var_path, var_name)):
            g = d
            for g_name in path.strip('/').split(' /'):
                if g_name:
                    g = g.groups[g_name]
            vs.append(g.variables[v_name])
        time, var = vs
        time_index = var.dimensions.index(time.dimensions[0])
        # get time indices
        time_indices = []
        i0 = 0
        t0 = time[0]
        for i, t in enumerate(time[:]):
            if t - t0 >= season_length:
                time_indices.append((i0, i))
                i0 = i
                t0 = t
        # add on remainder
        i = len(time)
        if i - 1 > i0:
            time_indices.append((i0, i))

        if parallel:
            results = get_mean_parallel(dv, var, time_index, time_indices)
        else:
            results = get_mean_serial(var, time_index, time_indices)
    finally:
        d.close()
    return results