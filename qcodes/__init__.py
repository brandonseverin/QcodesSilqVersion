"""Set up the main qcodes namespace."""

# flake8: noqa (we don't need the "<...> imported but unused" error)

# config

from qcodes.config import Config

config = Config()

from qcodes.version import __version__

plotlib = config.gui.plotlib
if plotlib in {'QT', 'all'}:
    try:
        from qcodes.plots.pyqtgraph import QtPlot
    except Exception:
        print('pyqtgraph plotting not supported, '
              'try "from qcodes.plots.pyqtgraph import QtPlot" '
              'to see the full error')

if plotlib in {'matplotlib', 'all'}:
    try:
        from qcodes.plots.qcmatplotlib import MatPlot
    except Exception:
        print('matplotlib plotting not supported, '
              'try "from qcodes.plots.qcmatplotlib import MatPlot" '
              'to see the full error')


from qcodes.station import Station
from qcodes.loops import Loop, active_loop, active_data_set, stop
from qcodes.measure import Measure
from qcodes.actions import Task, Wait, BreakIf
haswebsockets = True
try:
    import websockets
except ImportError:
    haswebsockets = False
if haswebsockets:
    from qcodes.monitor.monitor import Monitor

from qcodes.data.data_set import DataSet, new_data, load_data
from qcodes.data.location import FormatLocation
from qcodes.data.data_array import DataArray
from qcodes.data.format import Formatter
from qcodes.data.gnuplot_format import GNUPlotFormat
from qcodes.data.hdf5_format import HDF5Format
from qcodes.data.io import DiskIO

from qcodes.instrument.base import Instrument
from qcodes.instrument.ip import IPInstrument
from qcodes.instrument.visa import VisaInstrument
from qcodes.instrument.channel import InstrumentChannel, ChannelList

from qcodes.instrument.function import Function
from qcodes.instrument.parameter import (
    Parameter,
    ArrayParameter,
    MultiParameter,
    StandardParameter,
    ManualParameter,
    combine,
    CombinedParameter)
from qcodes.instrument.sweep_values import SweepFixedValues, SweepValues

from qcodes.utils import validators

from qcodes.instrument_drivers.test import test_instruments, test_instrument

try:
    get_ipython() # Check if we are in iPython
    from qcodes.utils.magic import register_magic_class
    register_magic = config.core.get('register_magic', False)
    if register_magic is not False:
        register_magic_class(magic_commands=register_magic)
except RuntimeError as e:
    print(e)

# Close all instruments when exiting QCoDeS
import atexit
atexit.register(Instrument.close_all)

# Patch matplotlib webagg backend to add delay when refreshing.
# Otherwise, any event (such as moving mouse over plot) can temporarily create
# a blank figure. Adding a small sleep fixes this
from matplotlib.backends.backend_webagg_core import FigureManagerWebAgg as _FigureManagerWebAgg
_original_refresh_all = _FigureManagerWebAgg.refresh_all
_FigureManagerWebAgg._sleep_duration = 0.1
def _new_refresh_all(self):
    from time import sleep
    sleep(self._sleep_duration)
    _original_refresh_all(self)
_FigureManagerWebAgg.refresh_all = _new_refresh_all