"""A module to compute the seasonal mean over a variable in a dataset.

Depends on IPython, netCDF4 and cdms2.

See the run function.  time_bounds may also be useful.

"""

from glob import glob

from IPython.parallel import Client, interactive
import numpy
from netCDF4 import MFDataset, num2date
import cdms2


def split_range (start, end, n_pieces):
    """Split a range into the given number of pieces.

split_range(start, end, n_pieces) -> list_of_ranges

list_of_ranges is a list of (start, end) tuples, and the end and start of
consecutive ranges are equal.

"""
    n = end - start
    per_piece = float(n) / n_pieces
    pieces = [start + int(round(per_piece * i)) for i in xrange(n_pieces + 1)]
    return [(pieces[i], pieces[i + 1])
            for i in xrange(n_pieces) if pieces[i] < pieces[i + 1]]


def time_bounds (files, time_name = 'time'):
    """Get first and last times, and length of time variable.

time_bounds(files, time_name = 'time') -> (first, last, length)

files: as taken by netCDF4.MFDataset.
time_name: the name of the time variable; can actually be any one-dimensional
           variable.

Times are netCDF4.netcdftime.datetime objects.  If length is 0, times are None.

"""
    with MFDataset(files) as d:
        t = d.variables[time_name]
        l = len(t)
        if l == 0:
            times = (None, None)
        else:
            times = tuple(num2date((t[0], t[-1]), t.units, t.calendar))
    return times + (l,)


def get_mean_serial (files, start, end, var_names, times_at_once, wt):
    """Compute the global mean.

get_mean_serial(files, start, end, var_names, wt) -> results

files: as taken by netCDF4.MFDataset.
start, end: as taken by run.
var_names: (time, lat, lon, var) variable names.
wt: latitude/longitude weights for var.

results: the var array along time with each subarray its mean.

"""
    with MFDataset(files) as d:
        # get variables
        time, lat, lon, var = [d.variables[name] for name in var_names]
        # create slice
        time_index, lat_index, lon_index = [
            var.dimensions.index(v.dimensions[0])
            for v in (time, lat, lon)
        ]
        index = [0] * len(var.dimensions)
        index[lat_index] = slice(None)
        index[lon_index] = slice(None)
        data = []
        # read times
        time = time[start:end]
        # do in time chunks
        n = end - start
        n_pieces = n / times_at_once + bool(n % times_at_once)
        times = split_range(start, end, n_pieces)
        for start, end in times:
            index[time_index] = slice(start, end)
            # get and transform data
            this_data = var[index] * wt
            # sum over data: get new indices: should be 3D, in the same order
            indices = [ident for i, ident in
                       sorted(((time_index, 'time'), (lat_index, 'lat'),
                               (lon_index, 'lon')))]
            for name in ('lat', 'lon'):
                i = indices.index(name)
                this_data = this_data.sum(i)
                indices.pop(i)
            data.append(this_data)
    return (time, numpy.hstack(data))


def get_mean_parallel (dv, files, start, end, var_names, times_at_once, wt):
    """Compute the seasonal mean in parallel.

get_mean_serial(dv, files, start, end, var_names, wt) -> results

dv: IPython DirectView to use.
files: as taken by netCDF4.MFDataset.
start, end: as taken by run.
var_names: (time, lat, lon, var) variable names.
wt: latitude/longitude weights for var.

results: the var array along time with each subarray its mean.

"""
    # split between engines
    times = split_range(start, end, len(dv.targets))
    dv.push({'get_mean_serial': get_mean_serial, 'split_range': split_range})
    args = [(files, start, end, var_names, times_at_once, wt)
            for start, end in times]
    times, data = zip(*dv.map(lambda args: get_mean_serial(*args), args))
    # join results
    return (numpy.hstack(times), numpy.hstack(data))


def run (files, var_name, start = 0, end = None, parallel = True,
         engines = None, time_name = 'time', lat_name = 'lat',
         lon_name = 'lon', times_at_once = 1000):
    """Run a global mean on a dataset.

run(files, var_name, start = 0, end = None, parallel = True, engines = None,
    time_name = 'time', lat_name = 'lat', lon_name = 'lon',
    time_at_once = 1000) -> (times, mean)

files: as taken by netCDF4.MFDataset.
var_name: the name of the variable to compute the mean of.
start: the index in the time variable to start at (this index is included).
end: the index in the time variable to end at (this index is not included);
     defaults to the variable's length.
parallel: whether to run the computation in parallel (using IPython.parallel).
engines: a list of engines to use if running in parallel.  The default is to
         use all available engines.
time_name, lat_name, lon_name: the names of these variables.  time can actually
                               be any one-dimensional variable, but longitude
                               and latitude must be 'the' longitude and
                               latitude for var, in standard format.
times at once: the number of times to retrieve data for before processing it.
               Note that this much may be in memory at any time on every
               engine, for parallel runs.

times: an array of times from the time variable, for the given time range.
mean: a corresponding array of means over the var variable for each time.  Each
      mean is taken over lat and lon for the 0th index of any other dimensions.

"""
    if parallel:
        c = Client()
        dv = c[:]
        if engines is not None:
            dv.targets = engines
        dv.block = True
        dv.execute('import numpy')
        dv.execute('from netCDF4 import MFDataset')
    # get weightings
    fs = files
    if isinstance(fs, basestring):
        fs = glob(fs)
    f = cdms2.open(fs[0])
    try:
        wt = numpy.outer(*f[var_name].getGrid().getWeights())
    finally:
        f.close()
    with MFDataset(files) as d:
        # get end time
        time = d.variables[time_name]
        n = len(time)
        if end is None or end > n:
            end = n
    # run
    var_names = (time_name, lat_name, lon_name, var_name)
    if parallel:
        results = get_mean_parallel(dv, files, start, end, var_names,
                                    times_at_once, wt)
    else:
        results = get_mean_serial(files, start, end, var_names, times_at_once,
                                  wt)
    return results