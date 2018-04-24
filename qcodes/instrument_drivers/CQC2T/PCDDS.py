from qcodes.instrument_drivers.Keysight.M3300A import Keysight_M3300A_FPGA
from qcodes.instrument.base import Instrument
from qcodes.utils.validators import Bool, Ints

import numpy as np

try:
    import keysightSD1
except ImportError:
    raise ImportError('to use the Keysight SD drivers install the keysightSD1 module '
                      '(http://www.keysight.com/main/software.jspx?ckey=2784055)')


class PCDDS(Instrument):
    """
    This class is the driver for the Phase Coherent Pulse Generation Module implemented on the FPGA onboard a Keysight
    PXI AWG card
    """
    def __init__(self, name, **kwargs):
        """ Constructor for the pulse generation modules """
        super().__init__(name, **kwargs)
        self.fpga = Keysight_M3300A_FPGA('FPGA')
        self.port = 0
        self.n_pointer_bits = 9
        self.n_op_bits = 10
        self.n_phase_bits = 45
        self.n_accum_bits = 45
        self.n_amp_bits = 16
        self.clk = 100e6
        self.v_max = 3.0
        self.f_max = 200e6

        self.add_parameter(
            'output_enable',
            set_cmd=self._set_output_enable,
            vals=Bool(),
            docstring='Whether the system has an enabled output'
        )

        self.add_parameter(
            'load_delay',
            set_cmd=self._set_load_delay,
            vals=Ints(0, 15),
            docstring='How long the delay should be during loading a new pulse to calculate the new coefficients'
        )

    def _set_output_enable(self, output_enable):
        """
        Set the output enable state of the module
        :param output_enable: (Bool) Is the output enabled
        :return: None
        """
        operation = int('0010000000', 2)
        if output_enable:
            operation += int('0001000000', 2)
        instr = self.construct_instruction(operation, 0)
        self.fpga.set_fpga_pc_port(self.port, [instr], 0, 0, 1)

    def _set_load_delay(self, delay):
        """
        Set the delay that the system will apply to calculate all the phase and frequency coefficiences
        :param delay: (Int) Delay in clock cycles
        :return: None
        """
        operation = int('0000010000', 2) + delay
        # Construct and send instruction
        instr = self.construct_instruction(operation, 0)
        self.fpga.set_fpga_pc_port(self.port, [instr], 0, 0, 1)

    def construct_instruction(self, operation, pointer):
        """
        Function to construct the int instruction packet from the operation and pointer
        :param operation: (Int) Operation that we want to do
        :param pointer: (Int) ID of the pulse that this instruction refers to
        :return: (Int) Instruction
        """
        # Check that the pointer is in the allowed range
        if pointer >= 2**self.n_pointer_bits:
            raise ValueError(
                'Pointer with value {} is outside of bounds [{}, {}]'.format(pointer, 0, 2**self.n_pointer_bits-1))
        # Convert and return
        return (operation << 22) + pointer

    def reset(self):
        """ Sends the reset signal to the FPGA """
        self.fpga.reset(reset_mode=keysightSD1.SD_ResetMode.PULSE)

    def write_sine_pulse(self, pulse, phase, frequency, amplitude, next_pulse):
        """
        Write a normal sinusoidal pulse with the desired properties to the pulse memory.
        :param pulse: (Int) The location in pulse memory that this is to be written to
        :param phase: (Float) The phase of the signal in degrees
        :param frequency: (Float) The frequency of the signal in Hz
        :param amplitude: (Float) The desired output maximum amplitude in V
        :param next_pulse: (Int) The next pulse that the system is to go to after this one
        :return: None
        """
        if not isinstance(pulse, int):
            raise TypeError('Incorrect type for function input pulse. It should be an int')
        if not isinstance(next_pulse, int):
            raise TypeError('Incorrect type for function input next_pulse. It should be an int')
        # Convert all the pulse parameters to the correct register values
        phase_val = self.phase2val(phase)
        freq_val = self.freq2val(frequency)
        accum_val = 0
        amplitude_val = self.amp2val(amplitude)
        self.write_pulse(pulse, phase_val, freq_val, accum_val, amplitude_val, next_pulse)

    def write_dc_pulse(self, pulse, voltage, next_pulse):
        """
        Write a DC pulse to memory. This sets up a pulse with a phase offset of 90 degrees, 0 frequency
        and a certain amplitude
        :param pulse: (Int) The location in pulse memory that this is to be written to
        :param voltage: (Float) The desired DC voltage
        :param next_pulse: (Int) The next pulse that the system is to go to after this one
        :return:
        """
        # a constant phase
        if not isinstance(pulse, int):
            raise TypeError('Incorrect type for function input pulse. It should be an int')
        if not isinstance(next_pulse, int):
            raise TypeError('Incorrect type for function input next_pulse. It should be an int')
        # Convert the voltage to the correct register value
        amplitude_val = self.amp2val(np.abs(2.0*voltage))
        if (voltage < 0):
            phase_val = self.phase2val(270.0)
        else:
            phase_val = self.phase2val(90.0)
        accum_val = 0
        freq_val = 0
        self.write_pulse(pulse, phase_val, freq_val, accum_val, amplitude_val, next_pulse)

    def write_chirp_pulse(self, pulse, phase, frequency, frequency_accumulation, amplitude, next_pulse):
        """
        Write a pulse to pulse memory which contains a frequency sweep
        :param pulse: (Int) The location in pulse memory that this is to be written to
        :param phase: (Float) The phase value for this pulse in degrees
        :param frequency: (Float) The frequency value for this pulse in Hz
        :param frequency_accumulation: (Float) The frequency accumulation for this pulse in Hz/s
        :param amplitude: (Float) The amplitude for this pulse in V
        :param next_pulse: (Int) The pulse that the system is to go to after this one
        :return: None
        """
        if not isinstance(pulse, int):
            raise TypeError('Incorrect type for function input pulse. It should be an int')
        if not isinstance(next_pulse, int):
            raise TypeError('Incorrect type for function input next_pulse. It should be an int')
        phase_val = self.phase2val(phase)
        freq_val = self.freq2val(frequency)
        accum_val = self.accum2val(frequency_accumulation)
        amplitude_val = self.amp2val(amplitude)
        self.write_pulse(pulse, phase_val, freq_val, accum_val, amplitude_val, next_pulse)

    def write_pulse(self, pulse, phase, frequency, frequency_accumulation, amplitude, next_pulse):
        """
        Function to write a pulse with given register values to a given location in pulse memory
        :param pulse: (Int) The location in pulse memory that this is to be written to
        :param phase: (Int) The phase register value for this pulse
        :param frequency: (Int) The frequency register value for this pulse
        :param frequency_accumulation: (Int) The frequency accumulation register for this pulse
        :param amplitude: (Int) The amplitude register for this pulse
        :param next_pulse: (Int) The pulse that the system is to go to after this one
        :return: None
        """
        # Construct the initial instruction to write a new pulse to memory
        operation = int('0000100000', 2)
        instr = self.construct_instruction(operation, pulse)
        # Construct the pulse parameter to be written to memory
        pulse_data = phase
        pulse_data += (frequency << self.n_phase_bits)
        pulse_data += (frequency_accumulation << 2 * self.n_phase_bits)
        pulse_data += (amplitude << 2 * self.n_phase_bits + self.n_accum_bits)
        pulse_data += (next_pulse << 2 * self.n_phase_bits + self.n_accum_bits + self.n_amp_bits)
        pulse_data = self.split_value(pulse_data)
        self.fpga.set_fpga_pc_port(self.port, [instr], 0, 0, 1)
        self.fpga.set_fpga_pc_port(self.port, [pulse_data[4]], 0, 0, 1)
        self.fpga.set_fpga_pc_port(self.port, [pulse_data[3]], 0, 0, 1)
        self.fpga.set_fpga_pc_port(self.port, [pulse_data[2]], 0, 0, 1)
        self.fpga.set_fpga_pc_port(self.port, [pulse_data[1]], 0, 0, 1)
        self.fpga.set_fpga_pc_port(self.port, [pulse_data[0]], 0, 0, 1)

    @staticmethod
    def split_value(value):
        """
        Splits a 20 byte message up into 5x 32 bit messages
        :param value: (Int) The message that is to be split
        :return: (List of Ints) List of 32 bit length ints to be sent as messages
        """
        if not isinstance(value, int):
            raise TypeError('Incorrect type passed to split_value')
        return [int(value & 0xFFFFFFFF),
                int((value >> 32) & 0xFFFFFFFF),
                int((value >> 64) & 0xFFFFFFFF),
                int((value >> 96) & 0xFFFFFFFF),
                int((value >> 128) & 0xFFFFFFFF)]

    def set_next_pulse(self, pulse, update):
        """
        Function to set the next pulse to be played. It is also possible to update to this new pulse
        via this function
        :param pulse: (Int) Next pulse to be played
        :param update: (Bool) Should the system update right now
        :return: None
        """
        operation = int('0000000010', 2)
        if update:
            operation += int('1000000000', 2)
        instr = self.construct_instruction(operation, pulse)
        self.fpga.set_fpga_pc_port(self.port, [instr], 0, 0, 1)

    def send_trigger(self):
        """
        Send a trigger signal to the FPGA
        :return: None
        """
        operation = int('1000000000', 2)
        instr = self.construct_instruction(operation, 0)
        self.fpga.set_fpga_pc_port(self.port, [instr], 0, 0, 1)

    def phase2val(self, phase):
        """
        Function to calculate the correct phase register values for a given phase
        :param phase: (Float) The desired phase in degrees.
        :return: (Int) The register value for the desired phase
        """
        phase = phase % 360.0
        return int(np.round((2 ** self.n_phase_bits / 360.0) * phase))

    def freq2val(self, freq):
        """
        Function to calculate the correct frequency register values for a given frequency
        :param freq: (Float) The desired frequency in Hz
        :return: (Int) The register value for the desired frequency
        """
        if freq > self.f_max or freq < 0:
            raise ValueError('Frequency of {0} is outside of allowed values [0, {1}MHz]'.format(freq, self.f_max/1e6))
        return int(np.round((2 ** self.n_phase_bits / (5*self.clk)) * freq))

    def accum2val(self, accum):
        """
        Function to calculate the correct accumulation register values for a given accumulation
        :param accum: (Float) The desired accumulation in Hz/s
        :return: (Int) The register value for the desired accumulation
        """
        if accum < 0 or accum > (5*self.clk ** 2):
            raise ValueError('Frequency Accumulation of {0} is outside of allowed values [0,{1}Hz/s]'.format(
                accum, (5*self.clk ** 2)))
        return int(np.round(accum * 2 ** self.n_accum_bits / (5*self.clk) ** 2))

    def amp2val(self, amp):
        """
        Function to calculate the correct amplitude register values for a given amplitude
        :param amp: (Float) The desired amplitude in V
        :return: (Int) The register value for the desired amplitude
        """
        if amp < 0 or amp > self.v_max:
            raise ValueError('Amplitude of {0} is outside of allowed values [0, {1}V'.format(amp, self.v_max))
        return int(np.round((2**self.n_amp_bits-1) * amp/self.v_max))
