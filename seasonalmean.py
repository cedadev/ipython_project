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
        arr = tas[index]
        results.append(arr.mean(time_index))
    return numpy.array(results)

def get_mean_serial (tas, time_index, times):
    """Compute the seasonal mean.

get_mean_serial(tas, time_index, times) -> results

tas: temperature netCDF4 variable.
time_index: the index of the time variable's dimension in tas's dimensions.
times: a list of (a, b) indices indicating sets of times to take the mean over
       (tas[a:b]).

results: the tas array with time now in seasons.

"""
    results = []
    index = [slice(None)] * time_index + [None, Ellipsis]
    for t0, t1 in times:
        index[time_index] = slice(t0, t1)
        arr = tas[index]
        results.append(arr.mean(time_index))
    return numpy.array(results)

def get_mean_parallel (dv, tas, times):
    """Compute the seasonal mean in parallel.

get_mean_serial(dv, tas, time_index times) -> results

dv: IPython DirectView to use.
tas: temperature netCDF4 variable.
time_index: the index of the time variable's dimension in tas's dimensions.
times: a list of (a, b) indices indicating sets of times to take the mean over
       (tas[a:b]).

results: the tas array with time now in seasons.

"""
    # transfer tas to the engines
    dv.push({'tas': tas, 'time_index': time_index})
    # do the calculation
    results = dv.parallel(block = True)(_get_mean_worker)(times)
    # close datasets
    dv.execute('tas.group().close()')
    # clean up variables
    dv.execute('del tas, time_index')
    return results

def run (files, parallel = True, season_length = 90, engines = None,
         time_var = ('/', 'time'), tas_var = ('/', 'tas')):
    """Run a seasonal mean on a dataset.

run(files, parallel = True, season_length = 90, engines = None,
    time_var = ('/', 'time'), tas_var = ('/', 'tas')) -> results

files: a list of the netCDF data files to use, or just one.
parallel: whether to run the computation in parallel (using IPython.parallel).
season_length: the length of a 'season' in whatever units the time variable has
               (the default makes sense for days).
engines: a list of engines to use if running in parallel.  The default is to
         use all available engines.
time_var, tas_var: the locations of the temperature and time variables within
                   the dataset.  Each is (path, name), the path of the group
                   the variable is in and its name within that group.

results: the array for the tas variable, with time now in seasons.

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
        for path, v_name in (time_var, tas_var):
            g = d
            for g_name in path.strip('/').split(' /'):
                if g_name:
                    g = g.groups[g_name]
            vs.append(g.variables[v_name])
        time, tas = vs
        time_index = tas.dimensions.index(time.dimensions[0])
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
            results = get_mean_parallel(dv, tas, time_index, time_indices)
        else:
            results = get_mean_serial(tas, time_index, time_indices)
    finally:
        d.close()
    return results