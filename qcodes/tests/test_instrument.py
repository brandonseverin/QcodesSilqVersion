from unittest import TestCase
from datetime import datetime, timedelta
import time

from qcodes.instrument.base import Instrument
from qcodes.instrument.mock import MockInstrument
from qcodes.instrument.parameter import Parameter, ManualParameter
from qcodes.instrument.sweep_values import SweepValues
from qcodes.instrument.function import Function
from qcodes.instrument.server import get_instrument_server

from qcodes.utils.validators import Numbers, Ints, Strings, MultiType, Enum
from qcodes.utils.sync_async import NoCommandError
from qcodes.utils.helpers import LogCapture, killprocesses

from .instrument_mocks import (AMockModel, MockInstTester,
                               MockGates, MockSource, MockMeter)


class TestParamConstructor(TestCase):
    def test_name_s(self):
        p = Parameter('simple')
        self.assertEqual(p.name, 'simple')

        with self.assertRaises(ValueError):
            # you need a name of some sort
            Parameter()

        # or names
        names = ['H1', 'L1']
        p = Parameter(names=names)
        self.assertEqual(p.names, names)
        self.assertFalse(hasattr(p, 'name'))

        # or both, that's OK too.
        names = ['Peter', 'Paul', 'Mary']
        p = Parameter(name='complex', names=names)
        self.assertEqual(p.names, names)
        # TODO: below seems wrong actually - we should let a parameter have
        # a simple name even if it has a names array. But then we need to
        # check everywhere this is used, and make sure everyone who cares
        # about it looks for names first.
        self.assertFalse(hasattr(p, 'name'))

        size = 10
        setpoints = 'we dont check the form of this until later'
        setpoint_names = 'we dont check this either'
        setpoint_labels = 'nor this'
        p = Parameter('makes_array', size=size, setpoints=setpoints,
                      setpoint_names=setpoint_names,
                      setpoint_labels=setpoint_labels)
        self.assertEqual(p.size, size)
        self.assertFalse(hasattr(p, 'sizes'))
        self.assertEqual(p.setpoints, setpoints)
        self.assertEqual(p.setpoint_names, setpoint_names)
        self.assertEqual(p.setpoint_labels, setpoint_labels)

        sizes = [2, 3]
        p = Parameter('makes arrays', sizes=sizes, setpoints=setpoints,
                      setpoint_names=setpoint_names,
                      setpoint_labels=setpoint_labels)
        self.assertEqual(p.sizes, sizes)
        self.assertFalse(hasattr(p, 'size'))
        self.assertEqual(p.setpoints, setpoints)
        self.assertEqual(p.setpoint_names, setpoint_names)
        self.assertEqual(p.setpoint_labels, setpoint_labels)


class GatesBadDelayType(MockGates):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_parameter('chan0bad', get_cmd='c0?',
                           set_cmd=self.slow_neg_set,
                           get_parser=float,
                           vals=Numbers(-10, 10), sweep_step=0.2,
                           sweep_delay=0.01,
                           max_sweep_delay='forever')


class GatesBadDelayValue(MockGates):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_parameter('chan0bad', get_cmd='c0?',
                           set_cmd=self.slow_neg_set,
                           get_parser=float,
                           vals=Numbers(-10, 10), sweep_step=0.2,
                           sweep_delay=0.05,
                           max_sweep_delay=0.03)


class TestParameters(TestCase):
    def setUp(self):
        self.model = AMockModel()
        self.read_response = 'I am the walrus!'

        self.gates = MockGates(model=self.model,
                               read_response=self.read_response)
        self.source = MockSource(model=self.model)
        self.meter = MockMeter(model=self.model,
                               read_response=self.read_response)

        self.init_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def tearDown(self):
        try:
            self.model.close()
            for instrument in [self.gates, self.source, self.meter]:
                instrument.close()
        except:
            pass

    def test_unpicklable(self):
        self.assertEqual(self.gates.add5(6), 11)
        # compare docstrings to make sure we're really calling add5
        # on the server, and seeing its docstring
        self.assertIn('The class copy of this should not get run',
                      MockInstTester.add5.__doc__)
        self.assertIn('not the same function as the original method',
                      self.gates.add5.__doc__)

    def test_slow_set(self):
        # at least for now, need a local instrument to test logging
        gatesLocal = MockGates(model=self.model, server_name=None)
        for param, logcount in (('chan0slow', 2), ('chan0slow2', 2),
                                ('chan0slow3', 0)):
            gatesLocal.chan0.set(-0.5)

            with LogCapture() as s:
                gatesLocal.set(param, 0.5)

            logs = s.getvalue().split('\n')[:-1]
            s.close()

            # TODO: occasional extra negative delays here
            self.assertEqual(len(logs), logcount, (param, logs))
            for line in logs:
                self.assertTrue(line.startswith('negative delay'), line)

    def test_max_sweep_delay_errors(self):
        with self.assertRaises(TypeError):
            # add_parameter works remotely with string commands, but
            # function commands are not going to be picklable, since they
            # need to talk to the hardware, so these need to be included
            # from the beginning when the instrument is created on the
            # server.
            GatesBadDelayType(model=self.model)

        with self.assertRaises(ValueError):
            GatesBadDelayValue(model=self.model)

    def check_ts(self, ts_str):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.assertTrue(self.init_ts <= ts_str <= now)

    def test_instances(self):
        instruments = [self.gates, self.source, self.meter]
        for instrument in instruments:
            for other_instrument in instruments:
                instances = instrument.instances()
                if other_instrument is instrument:
                    self.assertIn(instrument, instances)
                else:
                    self.assertNotIn(other_instrument, instances)

        # somehow instances never go away... there are always 3
        # extra references to every instrument object, so del doesn't
        # work. For this reason, instrument tests should take
        # the *last* instance to test.
        # so we can't test that the list of defined instruments is actually
        # *only* what we want to see defined.

    def test_mock_instrument(self):
        gates, source, meter = self.gates, self.source, self.meter

        # initial state
        # short form of getter
        self.assertEqual(meter.get('amplitude'), 0)
        # shortcut to the parameter, longer form of get
        self.assertEqual(meter['amplitude'].get(), 0)
        # explicit long form of getter
        self.assertEqual(meter.parameters['amplitude'].get(), 0)
        # both should produce the same history entry
        hist = meter.getattr('history')
        self.assertEqual(len(hist), 3)
        self.assertEqual(hist[0][1:], ('ask', 'ampl'))
        self.assertEqual(hist[0][1:], ('ask', 'ampl'))

        # errors trying to set (or validate) invalid param values
        # put here so we ensure that these errors don't make it to
        # the history (ie they don't result in hardware commands)
        with self.assertRaises(TypeError):
            gates.set('chan1', '1')
        with self.assertRaises(TypeError):
            gates.parameters['chan1'].validate('1')

        # change one param at a time
        gates.set('chan0', 0.5)
        self.assertEqual(gates.get('chan0'), 0.5)
        self.assertEqual(meter.get('amplitude'), 0.05)

        gates.set('chan1', 2)
        self.assertEqual(gates.get('chan1'), 2)
        self.assertEqual(meter.get('amplitude'), 0.45)

        gates.set('chan2', -3.2)
        self.assertEqual(gates.get('chan2'), -3.2)
        self.assertEqual(meter.get('amplitude'), -2.827)

        source.set('amplitude', 0.6)
        self.assertEqual(source.get('amplitude'), 0.6)
        self.assertEqual(meter.get('amplitude'), -16.961)

        gatehist = gates.getattr('history')
        sourcehist = source.getattr('history')
        meterhist = meter.getattr('history')
        # check just the size and timestamps of histories
        for entry in gatehist + sourcehist + meterhist:
            self.check_ts(entry[0])
        self.assertEqual(len(gatehist), 6)
        self.assertEqual(len(sourcehist), 5)
        self.assertEqual(len(meterhist), 7)

        # plus enough setters to check the parameter sweep
        # first source has to get the starting value
        self.assertEqual(sourcehist[0][1:], ('ask', 'ampl'))
        # then it writes each
        self.assertEqual(sourcehist[1][1:], ('write', 'ampl', '0.3000'))
        self.assertEqual(sourcehist[2][1:], ('write', 'ampl', '0.5000'))
        self.assertEqual(sourcehist[3][1:], ('write', 'ampl', '0.6000'))

        source.set('amplitude', 0.8)
        self.assertEqual(source.get('amplitude'), 0.8)
        gates.set('chan1', -2)
        self.assertEqual(gates.get('chan1'), -2)

        # test functions
        self.assertEqual(meter.call('echo', 1.2345), 1.23)  # model returns .2f
        # too many ways to do this...
        self.assertEqual(meter.echo.call(1.2345), 1.23)
        self.assertEqual(meter.echo(1.2345), 1.23)
        self.assertEqual(meter['echo'].call(1.2345), 1.23)
        self.assertEqual(meter['echo'](1.2345), 1.23)
        with self.assertRaises(TypeError):
            meter.call('echo', 1, 2)
        with self.assertRaises(TypeError):
            meter.call('echo', '1')

        # validating before actually trying to call
        with self.assertRaises(TypeError):
            meter.functions['echo'].validate(1, 2)
        with self.assertRaises(TypeError):
            meter.functions['echo'].validate('1')
        gates.call('reset')
        self.assertEqual(gates.get('chan0'), 0)

        self.assertEqual(meter.call('echo', 4.567), 4.57)
        gates.set('chan0', 1)
        self.assertEqual(gates.get('chan0'), 1)
        gates.call('reset')
        self.assertEqual(gates.get('chan0'), 0)

    def test_mock_set_sweep(self):
        gates = self.gates
        gates.set('chan0step', 0.5)
        gatehist = gates.getattr('history')
        self.assertEqual(len(gatehist), 6)
        self.assertEqual(
            [float(h[3]) for h in gatehist if h[1] == 'write'],
            [0.1, 0.2, 0.3, 0.4, 0.5])

    def test_mock_instrument_errors(self):
        gates, meter = self.gates, self.meter
        with self.assertRaises(ValueError):
            gates.ask('no question')
        with self.assertRaises(ValueError):
            gates.ask('question?yes but more after')

        with self.assertRaises(ValueError):
            gates.write('ampl 1')
            self.meter.echo(9.99)  # known good call, just to read the error
        with self.assertRaises(ValueError):
            gates.ask('ampl?')

        with self.assertRaises(TypeError):
            MockInstrument('', delay='forever')
        with self.assertRaises(TypeError):
            MockInstrument('', delay=-1)

        # TODO: when an error occurs during constructing an instrument,
        # we don't have the instrument but its server doesn't know to stop.
        # should figure out a way to remove it. (I thought I had but it
        # doesn't seem to have worked...)
        get_instrument_server('MockInstruments').close()
        time.sleep(0.5)

        with self.assertRaises(AttributeError):
            MockInstrument('', model=None)

        with self.assertRaises(KeyError):
            gates.add_parameter('chan0', get_cmd='boo')
        with self.assertRaises(KeyError):
            gates.add_function('reset', call_cmd='hoo')

        with self.assertRaises(NotImplementedError):
            meter.set('amplitude', 0.5)
        meter.add_parameter('gain', set_cmd='gain {:.3f}')
        with self.assertRaises(NotImplementedError):
            meter.get('gain')

        with self.assertRaises(TypeError):
            gates.add_parameter('fugacity', set_cmd='f {:.4f}', vals=[1, 2, 3])

        # TODO: when an error occurs during constructing an instrument,
        # we don't have the instrument but its server doesn't know to stop.
        # should figure out a way to remove it. (I thought I had but it
        # doesn't seem to have worked...)
        killprocesses()

    def check_set_amplitude2(self, val, log_count, history_count):
        source = self.sourceLocal
        with LogCapture() as s:
            source.amplitude2.set(val)

        logs = s.getvalue().split('\n')[:-1]
        s.close()

        self.assertEqual(len(logs), log_count, logs)
        for line in logs:
            self.assertIn('cannot sweep', line.lower())
        hist = source.getattr('history')
        self.assertEqual(len(hist), history_count)

    def test_sweep_steps_edge_case(self):
        # MultiType with sweeping is weird - not sure why one would do this,
        # but we should handle it
        # at least for now, need a local instrument to check logging
        source = self.sourceLocal = MockSource(model=self.model,
                                               server_name=None)
        source.add_parameter('amplitude2', get_cmd='ampl?',
                             set_cmd='ampl:{}', get_parser=float,
                             vals=MultiType(Numbers(0, 1), Strings()),
                             sweep_step=0.2, sweep_delay=0.02)
        self.assertEqual(len(source.getattr('history')), 0)

        # 2 history items - get then set, and one warning (cannot sweep
        # number to string value)
        self.check_set_amplitude2('Off', log_count=1, history_count=2)

        # one more history item - single set, and one warning (cannot sweep
        # string to number)
        self.check_set_amplitude2(0.2, log_count=1, history_count=3)

        # the only real sweep (0.2 to 0.8) adds 3 set's to history and no logs
        self.check_set_amplitude2(0.8, log_count=0, history_count=6)

        # single set added to history, and another sweep warning num->string
        self.check_set_amplitude2('Off', log_count=1, history_count=7)

    def test_set_sweep_errors(self):
        gates = self.gates

        # for reference, some add_parameter's that should work
        gates.add_parameter('t0', set_cmd='{}', vals=Numbers(),
                            sweep_step=0.1, sweep_delay=0.01)
        gates.add_parameter('t2', set_cmd='{}', vals=Ints(),
                            sweep_step=1, sweep_delay=0.01,
                            max_val_age=0)

        with self.assertRaises(TypeError):
            # can't sweep non-numerics
            gates.add_parameter('t1', set_cmd='{}', vals=Strings(),
                                sweep_step=1, sweep_delay=0.01)
        with self.assertRaises(TypeError):
            # need a numeric step too
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step='a skosh', sweep_delay=0.01)
        with self.assertRaises(TypeError):
            # Ints requires and int step
            gates.add_parameter('t1', set_cmd='{}', vals=Ints(),
                                sweep_step=0.1, sweep_delay=0.01)
        with self.assertRaises(ValueError):
            # need a positive step
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step=0, sweep_delay=0.01)
        with self.assertRaises(ValueError):
            # need a positive step
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step=-0.1, sweep_delay=0.01)
        with self.assertRaises(TypeError):
            # need a numeric delay
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step=0.1, sweep_delay='a tad')
        with self.assertRaises(ValueError):
            # need a positive delay
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step=0.1, sweep_delay=-0.01)
        with self.assertRaises(ValueError):
            # need a positive delay
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step=0.1, sweep_delay=0)
        with self.assertRaises(TypeError):
            # need a numeric max_val_age
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step=0.1, sweep_delay=0.01,
                                max_val_age='an hour')
        with self.assertRaises(ValueError):
            # need a non-negative max_val_age
            gates.add_parameter('t1', set_cmd='{}', vals=Numbers(),
                                sweep_step=0.1, sweep_delay=0.01,
                                max_val_age=-1)

    def getmem(self, key):
        return self.source.ask('mem{}?'.format(key))

    def test_val_mapping(self):
        gates = self.gates

        # memraw has no mappings - it just sets and gets what the instrument
        # uses to encode this parameter
        gates.add_parameter('memraw', set_cmd='mem0:{}', get_cmd='mem0?',
                            vals=Enum('zero', 'one'))

        # memcoded maps the instrument codes ('zero' and 'one') into nicer
        # user values 0 and 1
        gates.add_parameter('memcoded', set_cmd='mem0:{}', get_cmd='mem0?',
                            val_mapping={0: 'zero', 1: 'one'})

        gates.memcoded.set(0)
        self.assertEqual(gates.memraw.get(), 'zero')
        self.assertEqual(gates.memcoded.get(), 0)
        self.assertEqual(self.getmem(0), 'zero')

        gates.memraw.set('one')
        self.assertEqual(gates.memcoded.get(), 1)
        self.assertEqual(gates.memraw.get(), 'one')
        self.assertEqual(self.getmem(0), 'one')

        with self.assertRaises(ValueError):
            gates.memraw.set(0)

        with self.assertRaises(ValueError):
            gates.memcoded.set('zero')

    def test_bare_function(self):
        # not a use case we want to promote, but it's there...
        p = ManualParameter('test')

        def doubler(x):
            p.set(x * 2)

        f = Function('f', call_cmd=doubler, args=[Numbers(-10, 10)])

        f(4)
        self.assertEqual(p.get(), 8)
        with self.assertRaises(ValueError):
            f(20)

    def test_standard_snapshot(self):
        self.assertEqual(self.meter.snapshot(), {
            'parameters': {'amplitude': {'value': None, 'ts': None}},
            'functions': {'echo': {}}
        })

        ampsnap = self.meter.snapshot(update=True)['parameters']['amplitude']
        amp = self.meter.get('amplitude')
        self.assertEqual(ampsnap['value'], amp)
        amp_ts = datetime.strptime(ampsnap['ts'], '%Y-%m-%d %H:%M:%S')
        self.assertLessEqual(amp_ts, datetime.now())
        self.assertGreater(amp_ts, datetime.now() - timedelta(seconds=1.1))

    def test_manual_snapshot(self):
        self.source.add_parameter('noise', parameter_class=ManualParameter)
        noise = self.source.noise

        self.assertEqual(self.source.snapshot()['parameters']['noise'],
                         {'value': None, 'ts': None})

        noise.set(100)
        noisesnap = self.source.snapshot()['parameters']['noise']
        self.assertEqual(noisesnap['value'], 100)

        noise_ts = datetime.strptime(noisesnap['ts'], '%Y-%m-%d %H:%M:%S')
        self.assertLessEqual(noise_ts, datetime.now())
        self.assertGreater(noise_ts, datetime.now() - timedelta(seconds=1.1))

    def tests_get_latest(self):
        self.source.add_parameter('noise', parameter_class=ManualParameter)
        noise = self.source.noise

        self.assertIsNone(noise.get_latest())

        noise.set(100)

        mock_ts = datetime(2000, 3, 4)
        ts_str = mock_ts.strftime('%Y-%m-%d %H:%M:%S')
        noise.setattr('_latest_ts', mock_ts)
        self.assertEqual(noise.snapshot()['ts'], ts_str)

        self.assertEqual(noise.get_latest(), 100)
        self.assertEqual(noise.get_latest.get(), 100)

        # get_latest should not update ts
        self.assertEqual(noise.snapshot()['ts'], ts_str)

        # get_latest is not settable
        with self.assertRaises(AttributeError):
            noise.get_latest.set(50)

    def test_mock_read(self):
        gates, meter = self.gates, self.meter
        self.assertEqual(meter.read(), self.read_response)
        self.assertEqual(gates.read(), self.read_response)

    def test_base_instrument_errors(self):
        b = Instrument('silent', server_name=None)

        with self.assertRaises(NotImplementedError):
            b.read()
        with self.assertRaises(NotImplementedError):
            b.write('hello!')
        with self.assertRaises(NotImplementedError):
            b.ask('how are you?')

        with self.assertRaises(TypeError):
            b.add_function('skip', call_cmd='skip {}',
                           args=['not a validator'])
        with self.assertRaises(NoCommandError):
            b.add_function('jump')
        with self.assertRaises(NoCommandError):
            b.add_parameter('height')

    def test_sweep_values_errors(self):
        gates, source, meter = self.gates, self.source, self.meter
        c0 = gates.parameters['chan0']
        source_amp = source.parameters['amplitude']
        meter_amp = meter.parameters['amplitude']

        # only complete 3-part slices are valid
        with self.assertRaises(TypeError):
            c0[1:2]  # For Int params this could be defined as step=1
        with self.assertRaises(TypeError):
            c0[:2:3]
        with self.assertRaises(TypeError):
            c0[1::3]
        with self.assertRaises(TypeError):
            c0[:]  # For Enum params we *could* define this one too...

        # fails if the parameter has no setter
        # with self.assertRaises(AttributeError):
        meter_amp[0]

        # validates every step value against the parameter's Validator
        with self.assertRaises(ValueError):
            c0[5:15:1]
        with self.assertRaises(ValueError):
            c0[5.0:15.0:1.0]
        with self.assertRaises(ValueError):
            c0[-12]
        with self.assertRaises(ValueError):
            c0[-5, 12, 5]
        with self.assertRaises(ValueError):
            c0[-5, 12:8:1, 5]

        # cannot combine SweepValues for different parameters
        with self.assertRaises(TypeError):
            c0[0.1] + source_amp[0.2]

        # improper use of extend
        with self.assertRaises(TypeError):
            c0[0.1].extend(5)

        # SweepValue object has no getter, even if the parameter does
        with self.assertRaises(AttributeError):
            c0[0.1].get

    def test_sweep_values_valid(self):
        gates = self.gates
        c0 = gates.parameters['chan0']

        c0_sv = c0[1]
        # setter gets mapped
        self.assertEqual(c0_sv.set, c0.set)
        # normal sequence operations access values
        self.assertEqual(list(c0_sv), [1])
        self.assertEqual(c0_sv[0], 1)
        self.assertTrue(1 in c0_sv)
        self.assertFalse(2 in c0_sv)

        # in-place and copying addition
        c0_sv += c0[1.5:1.8:0.1]
        c0_sv2 = c0_sv + c0[2]
        self.assertEqual(list(c0_sv), [1, 1.5, 1.6, 1.7])
        self.assertEqual(list(c0_sv2), [1, 1.5, 1.6, 1.7, 2])

        # append and extend
        c0_sv3 = c0[2]
        # append only works with straight values
        c0_sv3.append(2.1)
        # extend can use another SweepValue, (even if it only has one value)
        c0_sv3.extend(c0[2.2])
        # extend can also take a sequence
        c0_sv3.extend([2.3])
        # as can addition
        c0_sv3 += [2.4]
        c0_sv4 = c0_sv3 + [2.5, 2.6]
        self.assertEqual(list(c0_sv3), [2, 2.1, 2.2, 2.3, 2.4])
        self.assertEqual(list(c0_sv4), [2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6])

        # len
        self.assertEqual(len(c0_sv3), 5)

        # in-place and copying reverse
        c0_sv.reverse()
        c0_sv5 = reversed(c0_sv)
        self.assertEqual(list(c0_sv), [1.7, 1.6, 1.5, 1])
        self.assertEqual(list(c0_sv5), [1, 1.5, 1.6, 1.7])

        # multi-key init, where first key is itself a list
        c0_sv6 = c0[[1, 3], 4]
        # copying
        c0_sv7 = c0_sv6.copy()
        self.assertEqual(list(c0_sv6), [1, 3, 4])
        self.assertEqual(list(c0_sv7), [1, 3, 4])
        self.assertFalse(c0_sv6 is c0_sv7)

    def test_sweep_values_base(self):
        p = self.gates.chan0
        with self.assertRaises(NotImplementedError):
            iter(SweepValues(p))

    def test_manual_parameter(self):
        self.source.add_parameter('bias_resistor',
                                  parameter_class=ManualParameter,
                                  initial_value=1000)
        res = self.source.bias_resistor
        self.assertEqual(res.get(), 1000)

        res.set(1e9)
        self.assertEqual(res.get(), 1e9)
        # default vals is all numbers
        res.set(-1)
        self.assertEqual(res.get(), -1)

        self.source.add_parameter('alignment',
                                  parameter_class=ManualParameter,
                                  vals=Enum('lawful', 'neutral', 'chaotic'))
        alignment = self.source.alignment

        # a ManualParameter can have initial_value=None (default) even if
        # that's not a valid value to set later
        self.assertIsNone(alignment.get())
        with self.assertRaises(ValueError):
            alignment.set(None)

        alignment.set('lawful')
        self.assertEqual(alignment.get(), 'lawful')

        # None is the only invalid initial_value you can use
        with self.assertRaises(TypeError):
            self.source.add_parameter('alignment2',
                                      parameter_class=ManualParameter,
                                      initial_value='nearsighted')


class TestAttrAccess(TestCase):
    def tearDown(self):
        self.instrument.close()
        # do it twice - should not error, though the second is irrelevant
        self.instrument.close()

    def test_simple_noserver(self):
        instrument = Instrument(name='test_simple_local', server_name=None)
        self.instrument = instrument

        # before setting attr1
        self.assertEqual(instrument.getattr('attr1', 99), 99)
        with self.assertRaises(AttributeError):
            instrument.getattr('attr1')

        with self.assertRaises(TypeError):
            instrument.setattr('attr1')

        self.assertFalse(hasattr(instrument, 'attr1'))

        # set it to a value
        instrument.setattr('attr1', 98)
        self.assertTrue(hasattr(instrument, 'attr1'))

        self.assertEqual(instrument.getattr('attr1', 99), 98)
        self.assertEqual(instrument.getattr('attr1'), 98)

        # then delete it
        instrument.delattr('attr1')

        with self.assertRaises(AttributeError):
            instrument.delattr('attr1')

        with self.assertRaises(AttributeError):
            instrument.getattr('attr1')

    def test_nested_noserver(self):
        instrument = Instrument(name='test_nested_local', server_name=None)
        self.instrument = instrument

        self.assertFalse(hasattr(instrument, 'd1'))

        with self.assertRaises(TypeError):
            instrument.setattr(('d1', 'a', 1))

        # set one attribute that requires creating nested levels
        instrument.setattr(('d1', 'a', 1), 2)

        # can't nest inside a non-container
        with self.assertRaises(TypeError):
            instrument.setattr(('d1', 'a', 1, 'secret'), 42)

        # get the whole dict with simple getattr style
        self.assertEqual(instrument.getattr('d1'), {'a': {1: 2}})

        # get the whole or parts with nested style
        self.assertEqual(instrument.getattr(('d1',)), {'a': {1: 2}})
        self.assertEqual(instrument.getattr(('d1',), 55), {'a': {1: 2}})
        self.assertEqual(instrument.getattr(('d1', 'a')), {1: 2})
        self.assertEqual(instrument.getattr(('d1', 'a', 1)), 2)
        self.assertEqual(instrument.getattr(('d1', 'a', 1), 3), 2)

        # add an attribute inside, then delete it again
        instrument.setattr(('d1', 'a', 2, 3), 4)
        self.assertEqual(instrument.getattr('d1'), {'a': {1: 2, 2: {3: 4}}})
        instrument.delattr(('d1', 'a', 2, 3))
        self.assertEqual(instrument.getattr('d1'), {'a': {1: 2}})

        # deleting it without pruning should leave empty containers
        instrument.delattr(('d1', 'a', 1), prune=False)
        self.assertEqual(instrument.getattr('d1'), {'a': {}})

        with self.assertRaises(KeyError):
            instrument.delattr(('d1', 'a', 1))

        # now prune
        instrument.delattr(('d1', 'a'))
        self.assertIsNone(instrument.getattr('d1', None))

        # a little more with top-level attrs as tuples
        instrument.setattr(('d2',), 'potato')
        self.assertEqual(instrument.getattr('d2'), 'potato')
        instrument.delattr(('d2',))
        self.assertIsNone(instrument.getattr('d2', None))

    def test_server(self):
        instrument = Instrument(name='test_server', server_name='attr_test')
        self.instrument = instrument

        with self.assertRaises(TypeError):
            instrument.setattr(('d1', 'a', 1))
            instrument.getattr('name')

        # set one attribute that requires creating nested levels
        instrument.setattr(('d1', 'a', 1), 2)

        # can't nest inside a non-container
        with self.assertRaises(TypeError):
            instrument.setattr(('d1', 'a', 1, 'secret'), 42)
            instrument.getattr('name')

        # get the whole dict with simple getattr style
        # TODO: twice (out of maybe 50 runs) I saw the below fail,
        # it returned "test_server" which should have been the response
        # above if it didn't raise an error.
        # I guess this is catching the error before receiving the
        # next response somehow. I've added a bit of a wait in there
        # that may have fixed this but lets leave the comment for a
        # while to see if it recurs.
        self.assertEqual(instrument.getattr('d1'), {'a': {1: 2}})

        # get the whole or parts with nested style
        self.assertEqual(instrument.getattr(('d1',)), {'a': {1: 2}})
        self.assertEqual(instrument.getattr(('d1',), 55), {'a': {1: 2}})
        self.assertEqual(instrument.getattr(('d1', 'a')), {1: 2})
        self.assertEqual(instrument.getattr(('d1', 'a', 1)), 2)
        self.assertEqual(instrument.getattr(('d1', 'a', 1), 3), 2)

        # add an attribute inside, then delete it again
        instrument.setattr(('d1', 'a', 2), 23)
        self.assertEqual(instrument.getattr('d1'), {'a': {1: 2, 2: 23}})
        instrument.delattr(('d1', 'a', 2))
        self.assertEqual(instrument.getattr('d1'), {'a': {1: 2}})

        # deleting it without pruning should leave empty containers
        instrument.delattr(('d1', 'a', 1), prune=False)
        self.assertEqual(instrument.getattr('d1'), {'a': {}})

        with self.assertRaises(KeyError):
            instrument.delattr(('d1', 'a', 1))
            instrument.getattr('name')

        # now prune
        instrument.delattr(('d1', 'a'))
        self.assertIsNone(instrument.getattr('d1', None))

        # test restarting the InstrumentServer - this clears these attrs
        instrument.setattr('answer', 42)
        self.assertEqual(instrument.getattr('answer', None), 42)
        instrument.connection.manager.restart()
        self.assertIsNone(instrument.getattr('answer', None))


class TestLocalMock(TestCase):
    def setUp(self):
        self.model = AMockModel()

        self.gates = MockGates(self.model, server_name=None)
        self.source = MockSource(self.model, server_name=None)
        self.meter = MockMeter(self.model, server_name=None)

    def tearDown(self):
        self.model.close()
        for instrument in [self.gates, self.source, self.meter]:
            instrument.close()

    def test_local(self):
        self.gates.chan1.set(3.33)
        self.assertEqual(self.gates.chan1.get(), 3.33)

        self.gates.reset()
        self.assertEqual(self.gates.chan1.get(), 0)

        with self.assertRaises(ValueError):
            self.gates.ask('knock knock? Oh never mind.')