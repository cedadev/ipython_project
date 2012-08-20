"""A module to compute the seasonal mean over a variable in a dataset.

See the run function.  time_bounds may also be useful.

"""

from IPython.parallel import Client, interactive
import numpy
from netCDF4 import MFDataset, num2date


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


def run (files, var_name, start_year, start_month, end_year, parallel = True,
         season_length = 3, engines = None, var_path = '/', time_path = '/',
         time_name = 'time'):
    """Run a seasonal mean on a dataset.

run(files, var_name, start_year, end_year, start_month, parallel = True,
    season_length = 3, engines = None, var_path = '/', time_path = '/',
    time_name = 'time') -> results

files: as taken by netCDF4.MFDataset.
var_name: the name of the variable to compute the mean of.
start_year: the year to start at (this year is included).
end_year: the year to end at (this year is included).
start_month: the month to start at (this month is included).
parallel: whether to run the computation in parallel (using IPython.parallel).
season_length: the length of a season in months.
engines: a list of engines to use if running in parallel.  The default is to
         use all available engines.
var_path, time_path: the path of the groups these variables are in within the
                     dataset.
time_name: the name of the time variable.  This can actually be any
           one-dimensional variable - it doesn't need to represent time.

results: the array for the var variable, with time now in seasons.

"""
    if parallel:
        c = Client()
        dv = c[:]
        if engines is not None:
            dv.targets = engines
        dv.block = True
        dv.execute('import numpy')

    with MFDataset(files) as d:
        # find variables
        vs = []
        for path, v_name in ((time_path, time_name), (var_path, var_name)):
            g = d
            for g_name in path.strip('/').split('/'):
                if g_name:
                    g = g.groups[g_name]
            vs.append(g.variables[v_name])
        time, var = vs
        time_index = var.dimensions.index(time.dimensions[0])
        # get time indices
        times = time[:]
        dates = num2date(times, time.units, time.calendar)
        started = False
        in_season = False
        time_indices = []
        n = len(times)
        i = 0
        while i < n:
            t = times[i]
            date = dates[i]
            if started:
                if in_season:
                    if date.year >= season_end_year and \
                       date.month >= season_end_month:
                        # season ended; (i0, i) is used as [i0:i], skipping i,
                        # as we want
                        in_season = False
                        time_indices.append((i0, i))
                        # next season might start here: don't increment counter
                        continue
                elif date.year > end_year:
                    # found end year (and no seasons are in progress)
                    break
                elif date.month >= start_month:
                    # found new season
                    in_season = True
                    # get end year/month (might be longer than a year)
                    season_end_month = start_month + season_length
                    season_end_year = date.year + season_end_month / 12
                    season_end_month %= 12
                    i0 = i
            elif date.year >= start_year:
                # found start year
                started = True
                # first season might start here: don't increment counter
                continue
            i += 1

        if parallel:
            results = get_mean_parallel(dv, var, time_index, time_indices)
        else:
            results = get_mean_serial(var, time_index, time_indices)
    return results