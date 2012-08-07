from distutils.core import setup

setup(
    name = 'nc_ipython',
    version = '0.1.0',
    description = 'Tools for using NetCDF with IPython',
    long_description = 'Contains the ncserialisable module as a ' \
                       'serialisable wrapper of NetCDF objects.',
    author = 'Joseph Lansdowne',
    author_email = 'j.lansdowne@warwick.ac.uk',
    url = 'http://proj.badc.rl.ac.uk/cedaservices/browser/ipython_project/' \
          'nc_ipython',
    packages = ['nc_ipython'],
    license = 'BSD New',
    requires = ['netCDF4']
)