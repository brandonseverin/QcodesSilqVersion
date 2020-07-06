from qcodes import VisaInstrument
from qcodes.instrument.parameter import Parameter
from qcodes.utils.validators import Bool, Enum, Ints, MultiType, Numbers
from typing import Union
from functools import wraps
import logging

logger = logging.getLogger(__name__)


def str_to_bool(s):
    if type(s) != str:
        raise ValueError("Argument must be a string.")
    if s == '0':
        return False
    elif s == '1':
        return True
    else:
        raise ValueError("String data not valid, string must be "
                         "either '0' or '1'")


def with_error_check(fun):
    @wraps(fun)
    def error_check_wrapper(*args, **kwargs):
        value = fun(*args, **kwargs)
        error_check(value, f'{fun.__name__} with args {args}, {kwargs}.')
        return value

    return error_check_wrapper


def error_check(self, last_method=''):
    """Check if an error occurred while setting/getting a value.

    :param self: Keithley_2450 instance.
    :param last_method: A string representation of the last called method
    with arguments

    Raises:
        RuntimeError if an error occurred during instrument command.

    """
    if self.log_message_count(eventType='ERR') > 0:
        raise RuntimeError(last_method + '\n' + self.next_log_message('ERR'))
    elif self.log_message_count(eventType='WARN') > 0:
        logger.warning(last_method + '\n' + self.next_log_message('WARN'))
    elif self.log_message_count(eventType='INFO') > 0:
        logger.info(last_method + '\n' + self.next_log_message('INFO'))


class SMUParameter(Parameter):
    def __init__(self,
                 name: str,
                 parent: Union[VisaInstrument] = None,
                 cmd: str = None,
                 get_cmd: str = None,
                 set_cmd: Union[str, bool] = None,
                 **kwargs):

        if cmd is not None:
            if not (get_cmd is None and set_cmd is None):
                raise ValueError("If cmd is provided, get_cmd and set_cmd "
                                 "should be None.")
            self.get_cmd = cmd + '?'
            self.set_cmd = cmd + '{}'
        else:
            self.get_cmd = get_cmd
            self.set_cmd = set_cmd

        super().__init__(name=name, parent=parent, **kwargs)

    @with_error_check
    def get_raw(self):
        if 'sour' in self.get_cmd.lower():
            mode = self.parent.source_mode()
        elif 'sens' in self.get_cmd.lower():
            mode = self.parent.sense_mode()
        else:
            mode = ''

        if self.get_cmd is not None:
            retVal = self.parent.ask(self.get_cmd.format(mode=mode))
        else:
            raise RuntimeError(f"get_cmd not defined for SMU parameter "
                               f"{self.name}")
        # Process boolean return values
        if type(self.vals) == Bool:
            retVal = str_to_bool(retVal)
        return retVal

    @with_error_check
    def set_raw(self, value):
        if 'sour' in self.set_cmd.lower():
            mode = self.parent.source_mode()
        elif 'sens' in self.set_cmd.lower():
            mode = self.parent.sense_mode()
        else:
            mode = ''

        if self.set_cmd is not None:
            self.parent.write(self.set_cmd.format(value, mode=mode))
        else:
            raise RuntimeError(f"set_cmd not defined for SMU oarameter "
                               f"{self.name}")


class Keithley_2450(VisaInstrument):
    """
    qcodes driver for the Keithley 2450 SMU.

    NOTE: Not full list of parameters, however basic functions are implemented.
          Needs further testing, but is ready for usage.
    """

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, terminator='\n', **kwargs)

        # Convenient parameters
        self.voltage = Parameter('voltage',
                                 get_cmd=self.get_voltage,
                                 set_cmd=self.set_voltage,
                                 unit='V',
                                 label='Voltage',
                                 docstring='A parameter to get and set a '
                                           'voltage. '
                                           'Equivalent to sense_value ('
                                           'source_level) if the '
                                           'sense_mode (source_mode) is set '
                                           'to "VOLT"'
                                 )

        self.current = Parameter('current',
                                 get_cmd=self.get_current,
                                 set_cmd=self.set_current,
                                 unit='A',
                                 label='Current',
                                 docstring='A parameter to get and set a '
                                           'current. '
                                           'Equivalent to sense_value ('
                                           'source_level) if the '
                                           'sense_mode (source_mode) is set '
                                           'to "CURR"'
                                 )

        self.resistance = Parameter('resistance',
                                    get_cmd=self.get_resistance,
                                    unit='Ohm',
                                    label='Sensed resistance',
                                    docstring='A parameter to return a sensed '
                                              'resistance. '
                                              'Equivalent to sense_value if '
                                              'the '
                                              'sense_mode is set to "RES"'
                                    )

        # Sense parameters

        self.sense_mode = Parameter('sense_mode',
                                    vals=Enum('VOLT', 'CURR', 'RES'),
                                    get_cmd=':SENS:FUNC?',
                                    get_parser=lambda s: s[:4],
                                    # Truncate to 4 chars
                                    set_cmd=self._set_sense_mode,
                                    label='Sense mode',
                                    docstring='Sets the sensing to a voltage, '
                                              'current '
                                              'or resistance.')

        self.sense_value = SMUParameter('sense_value',
                                        get_cmd=':READ?',
                                        get_parser=float,
                                        set_cmd=False,
                                        label='Sense value',
                                        docstring='Reading the sensing value '
                                                  'of the active sense mode.')

        self.count = SMUParameter('count',
                                  vals=Numbers(min_value=1, max_value=300000),
                                  cmd=':SENS:COUNT',
                                  get_parser=int,
                                  set_parser=int,
                                  label='Count',
                                  docstring='The number of measurements to '
                                            'perform upon request.')

        self.average_count = SMUParameter('average_count',
                                          vals=MultiType(
                                              Ints(min_value=1, max_value=100),
                                              Enum('MIN', 'DEF', 'MAX')),
                                          cmd=':SENS:{mode}:AVER:COUNT',
                                          get_parser=int,
                                          label='Average count',
                                          docstring='The number of '
                                                    'measurements to average '
                                                    'over.')

        self.average_mode = SMUParameter('average_mode',
                                         vals=Enum('MOV', 'REP'),
                                         cmd=':SENS:{mode}:AVER:TCON',
                                         label='Average mode',
                                         docstring='A moving filter will '
                                                   'average data from sample '
                                                   'to sample, \
                           but a true average will not be generated until the '
                                                   'chosen count is reached. \
                           A repeating filter will only output an average '
                                                   'once all measurement '
                                                   'counts \
                           are collected and is hence slower.')

        self.average_enabled = SMUParameter('average_enabled',
                                            vals=Bool(),
                                            cmd=':SENS:{mode}:AVER',
                                            label='Average enabled',
                                            docstring='If averaging is '
                                                      'enabled, each read will '
                                                      'be averaged using '
                                                      'either a moving or '
                                                      'repeated average (see '
                                                      'average_mode) for a '
                                                      'number of counts (see '
                                                      'average_count)')

        self.sense_range_auto = SMUParameter('sense_range_auto',
                                             vals=Bool(),
                                             cmd=':SENS:{mode}:RANG:AUTO',
                                             label='Sense range auto mode',
                                             docstring='This determines if '
                                                       'the range for '
                                                       'measurements is '
                                                       'selected automatically '
                                                       '(True) or manually ('
                                                       'False).')

        self.sense_range_auto_lower_limit = SMUParameter(
            'sense_range_auto_lower_limit',
            vals=Numbers(),
            cmd=':SENS:{mode}:RANG:AUTO:LLIM',
            label='Auto range lower limit',
            docstring='This sets the lower limit used when in auto-ranging '
                      'mode. \
                           The lower this limit requires a longer settling '
                      'time, and so you can \
                           speed up measurements by choosing a suitably high '
                      'lower limit.')

        self.sense_range_auto_upper_limit = SMUParameter(
            'sense_range_auto_upper_limit',
            vals=Numbers(),
            cmd=':SENS:{mode}:RANG:AUTO:ULIM',
            label='Auto range upper limit',
            docstring='This sets the upper limit used when in auto-ranging '
                      'mode. \
                           This is only used when measuring a resistance.')

        # TODO: needs connection with source range setting
        self.sense_range_manual = SMUParameter('sense_range_manual',
                                               vals=Numbers(),
                                               cmd=':SENS:{mode}:RANG',
                                               label='Manual range upper limit',
                                               docstring='The upper limit of '
                                                         'what is being '
                                                         'measured when in '
                                                         'manual mode')

        self.nplc = SMUParameter('nplc',
                                 vals=Numbers(min_value=0.01, max_value=10),
                                 cmd=':SENS:{mode}:NPLC',
                                 label='Sensed input integration time',
                                 docstring='This command sets the amount of '
                                           'time that the input signal is '
                                           'measured. \
                                      The amount of time is specified in '
                                           'parameters that are based on the \
                                      number of power line cycles (NPLCs). '
                                           'Each PLC for 60 Hz is 16.67 ms \
                                      (1/60) and each PLC for 50 Hz is 20 ms '
                                           '(1/50).')

        self.relative_offset = SMUParameter('relative_offset',
                                            vals=Numbers(),
                                            cmd=':SENS:{mode}:REL',
                                            label='Relative offset value for '
                                                  'a measurement.',
                                            docstring='This specifies an '
                                                      'internal offset that '
                                                      'can be applied to '
                                                      'measured data')

        self.relative_offset_enabled = SMUParameter('relative_offset_enabled',
                                                    vals=Bool(),
                                                    cmd=':SENS:{mode}:REL:STAT',
                                                    label='Relative offset '
                                                          'enabled',
                                                    docstring='This '
                                                              'determines if '
                                                              'the relative '
                                                              'offset is to '
                                                              'be applied to '
                                                              'measurements.')

        self.four_wire_mode = SMUParameter('four_wire_mode',
                                           vals=Bool(),
                                           cmd=':SENS:{mode}:RSEN',
                                           label='Four-wire sensing state',
                                           docstring='This determines whether '
                                                     'you sense in '
                                                     'four-wire (True) or '
                                                     'two-wire (False) mode')

        # Source parameters

        self.source_mode = Parameter('source_mode',
                                     vals=Enum('VOLT', 'CURR'),
                                     get_cmd=':SOUR:FUNC?',
                                     set_cmd=self._set_source_mode,
                                     label='Source mode',
                                     docstring='This determines whether a '
                                               'voltage or current is being '
                                               'sourced.')

        self.source_level = SMUParameter('source_level',
                                         vals=Numbers(),
                                         cmd=':SOUR:{mode}',
                                         label='Source level',
                                         docstring='This sets/reads the '
                                                   'output voltage or current '
                                                   'level of the source.')

        self.output_on = SMUParameter('output_on',
                                      vals=Bool(),
                                      cmd=':OUTP:STAT',
                                      label='Output on',
                                      docstring='Determines whether output is '
                                                'on (True) '
                                                'or off (False)')

        self.source_limit = SMUParameter('source_limit',
                                         vals=Numbers(),
                                         cmd=':SOUR:VOLT:{"I" if mode == '
                                             '"VOLT" else "V"}LIM',
                                         label='Source limit',
                                         docstring='The current (voltage) '
                                                   'limit when sourcing '
                                                   'voltage (current).')

        self.source_limit_tripped = SMUParameter(
            'source_limit_tripped',
            get_cmd=':SOUR:VOLT:{"I" if mode == "VOLT" else "V"}LIM:TRIP?',
            get_parser=str_to_bool,
            set_cmd=False,
            label='Source limit reached',
            docstring='Returns True if the source limit has '
                      'been reached and False otherwise.')

        self.source_range = SMUParameter('source_range',
                                         vals=Numbers(),
                                         cmd=':SOUR:{mode}:RANG',
                                         label='Source range',
                                         docstring='The voltage (current) '
                                                   'output range when '
                                                   'sourcing a voltage ('
                                                   'current).')

        self.source_range_auto = SMUParameter('source_range_auto',
                                              vals=Bool(),
                                              cmd=':SOUR:{mode}:RANG:AUTO',
                                              label='Source range auto mode',
                                              docstring='Determines if the '
                                                        'range for sourcing '
                                                        'is selected '
                                                        'automatically (True) '
                                                        'or manually (False)')

        self.source_read_back = SMUParameter('source_read_back',
                                             vals=Bool(),
                                             cmd=':SOUR:{mode}:READ:BACK',
                                             label='Source read-back',
                                             docstring='Determines whether '
                                                       'the recorded output '
                                                       'is the measured '
                                                       'source value \
                           or the configured source value. The former '
                                                       'increases the '
                                                       'precision, \
                           but slows down the measurements.')

        # Note: delay value for 'MAX' is 10 000 instead of 4.
        self.source_delay = SMUParameter(
            'source_delay',
            vals=MultiType(Numbers(min_value=0.0, max_value=4.0),
                           Enum('MIN', 'DEF', 'MAX')),
            cmd=':SOUR:{mode}:DEL',
            unit='s',
            label='Source measurement delay',
            docstring='This determines the delay between the source changing '
                      'and a measurement \
                           being recorded.')

        # TODO: Is this even needed?
        self.source_delay_auto = SMUParameter(
            'source_delay_auto',
            vals=Bool(),
            cmd=':SOUR:{mode}:DEL:AUTO',
            label='Source measurement delay auto state',
            docstring='This determines the autodelay between '
                      'the source changing and a measurement '
                      'being recorded set to state ON/OFF.')

        self.source_protection = SMUParameter(
            'source_protection',
            vals=Enum('PROT2', 'PROT5', 'PROT10', 'PROT20', 'PROT40', 'PROT60',
                      'PROT80', 'PROT100',
                      'PROT120', 'PROT140', 'PROT160', 'PROT180', 'NONE'),
            get_cmd='SOUR:VOLT:PROT?',
            set_cmd='SOUR:VOLT:PROT {:s}',
            label='Source overvoltage protection',
            docstring='This sets the overvoltage protection setting of the '
                      'source output. \
                           Overvoltage protection restricts the maximum '
                      'voltage level that the instrument can source. \
                           It is in effect when either current or voltage is '
                      'sourced.')

        self.source_protection_tripped = SMUParameter(
            'source_protection_tripped',
            get_cmd='SOUR:VOLT:PROT:TRIP?',
            get_parser=str_to_bool,
            set_cmd=False,
            label='Source overvoltage protection tripped status',
            docstring='True if the voltage source exceeded '
                      'the protection limits, False otherwise.')

    # Functions

    def reset(self):
        """
        Resets the instrument. During reset, it cancels all pending commands
        and all previously sent `*OPC` and `*OPC?`
        """
        self.write(':*RST')

    def clear_log(self):
        self.write(f":SYSTem:CLEar")

    def log_message_count(self, event_type="ALL"):
        """

        :param event_type: filter by event type, allowed types:
            ERRor, WARNing, INFormation, ALL
        :return: The number of messages in the event log.
        """
        return self.ask(f":SYSTem:EVENtlog:COUNt? {event_type}")

    def next_log_message(self, event_type="ALL"):
        return self.ask(f":SYSTem:EVENtlog:NEXT? {event_type}")

    def get_voltage(self):
        """A handy function to return the voltage if in the correct mode
            :return:
                The sensed voltage

            :raise:
                RunTimeError
        """
        if self.sense_mode() == 'VOLT':
            return self.sense_value()
        else:
            raise RuntimeError(f"{self.name} is not configured to sense a "
                               f"voltage.")

    def get_current(self):
        """A handy function to return the current if in the correct mode
            :return:
                The sensed current

            :raise:
                RunTimeError
        """
        if self.sense_mode() == 'CURR':
            return self.sense_value()
        else:
            raise RuntimeError(f"{self.name} is not configured to sense a "
                               f"current.")

    def get_resistance(self):
        """A handy function to return the resistance if in the correct mode
            :return:
                The sensed resistance

            :raise:
                RunTimeError
        """
        if self.sense_mode() == 'RES':
            return self.sense_value()
        else:
            raise RuntimeError(f"{self.name} is not configured to sense a "
                               f"resistance.")

    def set_voltage(self, value):
        """A handy function to set the voltage if in the correct mode
            :raise:
                RunTimeError
        """
        if self.source_mode() == 'VOLT':
            return self.source_level(value)
        else:
            raise RuntimeError(f"{self.name} is not configured to source a "
                               f"voltage.")

    def set_current(self, value):
        """A handy function to set the current if in the correct mode
            :raise:
                RunTimeError
        """
        if self.source_mode() == 'CURR':
            return self.source_level(value)
        else:
            raise RuntimeError(f"{self.name} is not configured to source a "
                               f"current.")

    @with_error_check
    def _set_source_mode(self, mode):
        # Set the appropriate unit for the source parameter
        if mode == 'VOLT':
            self.source_level.unit = 'V'
            self.source_range.unit = 'V'
            self.source_limit.unit = 'A'
        elif mode == 'CURR':
            self.source_level.unit = 'A'
            self.source_range.unit = 'A'
            self.source_limit.unit = 'V'
        self.write(f':SOUR:FUNC {mode}')

    @with_error_check
    def _set_sense_mode(self, mode):
        if mode == 'VOLT':
            self.sense_value.unit = 'V'
            self.sense_range_manual.unit = 'V'
        elif mode == 'CURR':
            self.sense_value.unit = 'A'
            self.sense_range_manual.unit = 'A'
        elif mode == 'RES':
            self.sense_value.unit = 'Ohm'  # unicode upper-case omega is \u03A9
            self.sense_range_manual.unit = 'Ohm'
        self.write(f':SENS:FUNC "{mode}"')

    # Other deprecated functions

    # deprecated
    def make_buffer(self, buffer_name, buffer_size):
        self.write('TRACe:MAKE {:s}, {:d}'.format(buffer_name, buffer_size))

    # deprecated
    def clear_buffer(self, buffer_name):
        self.write(':TRACe:CLEar {:s}'.format(buffer_name))
