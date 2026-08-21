from mpmt_mss.feb.devices import DeviceType, DeviceConfig, DeviceChannel
from mpmt_mss.runcontrol.fpga import FPGA
from enum import Enum
from typing import Union

class TriggerSource(str, Enum):
    MB = "MB"
    MCU = "MCU"
    EXT = "EXT"

    def __int__(self):
        return list(TriggerSource).index(self)

    @classmethod
    def from_int(cls, value: int) -> "TriggerSource":
        return list(cls)[value]

class LEDChannel(DeviceChannel):
    DEVICE_TYPE = DeviceType.LED

    # helpers
    
    # used for coils
    STATUS_MAP = {
        0: "OFF",
        1: "ON",
    }
    
    REG_LED_BASE = 85

    # burst/pulser registers, one slot per led_rank (0..4)
    REG_BURST_START_S_BASE = 65
    REG_BURST_START_4NS_BASE = 70
    REG_BURST_INTERVAL_4NS_BASE = 75
    REG_BURST_COUNT_BASE = 80
    REG_BURST_KEY_OUT_BASE = 90
    REG_BURST_KEY_IN_BASE = 95
    REG_BURST_STATUS = 100    # shared, 2 bits per led_rank
    REG_BURST_CLEAR = 101     # shared, 2 bits per led_rank

    # meaning of bits 1/2 inferred from x_feb/led_feb_burst.py; 3 unconfirmed
    BURST_STATUS_MAP = {
        0: "IDLE",
        1: "WAITING_OR_RUNNING",
        2: "ERROR",
        3: "undef",
    }

    def __init__(self, modbus, channel: int, address: int, led_rank: int = 0):
        super().__init__(modbus, channel, address)
        self.led_rank = led_rank
        self.fpga = FPGA('/dev/uio0')
        self.probe()

    def probe(self):
        try:
            self.getLEDInfo()
        except Exception as e:
            self.online = False
        else:
            self.online = True

    @DeviceChannel.track_connection
    def powerLEDOn(self):
        self.modbus.write_coil(address=1, value=True, slave=self.address)

    @DeviceChannel.track_connection
    def powerLEDOff(self):
        self.modbus.write_coil(address=1, value=False, slave=self.address)

    @DeviceChannel.track_connection
    def getLEDStatus(self) -> dict:
        rr = self.modbus.read_discrete_inputs(address=10001, count=1, slave=self.address)
        return {"value": int(rr.bits[0]), "string": self.STATUS_MAP.get(rr.bits[0], "undef")}

    @DeviceChannel.track_connection
    def getLEDInfo(self) -> dict:
        rr = self.modbus.read_input_registers(address=30001, count=1, slave=self.address).registers
        fwver = f"{rr[0] >> 8}.{(rr[0] & 0xF0) >> 4}.{rr[0] & 0x0F}"
        return {"fwver": fwver}

    @DeviceChannel.track_connection
    def getLEDErrorRegisters(self) -> dict:
        rr = self.modbus.read_input_registers(address=30002, count=5, slave=self.address).registers
        return {
            "ledCurrentError": rr[0],
            "ledBiasError": rr[1],
            "trigSourceError": rr[2],
            "febMbSlaveError": rr[3],
            "febMbGlobalError": rr[4],
        }

    def getLEDBurstConfig(self) -> dict:
        return {
            "startTimeS": self.fpga.readRegister(self.REG_BURST_START_S_BASE + self.led_rank),
            "startTime4ns": self.fpga.readRegister(self.REG_BURST_START_4NS_BASE + self.led_rank),
            "flashInterval4ns": self.fpga.readRegister(self.REG_BURST_INTERVAL_4NS_BASE + self.led_rank),
            "flashCount": self.fpga.readRegister(self.REG_BURST_COUNT_BASE + self.led_rank),
        }

    def setLEDBurstConfig(self, startTimeS: int, startTime4ns: int, flashInterval4ns: int, flashCount: int):
        self.fpga.writeRegister(self.REG_BURST_START_S_BASE + self.led_rank, startTimeS)
        self.fpga.writeRegister(self.REG_BURST_START_4NS_BASE + self.led_rank, startTime4ns)
        self.fpga.writeRegister(self.REG_BURST_INTERVAL_4NS_BASE + self.led_rank, flashInterval4ns)
        self.fpga.writeRegister(self.REG_BURST_COUNT_BASE + self.led_rank, flashCount)

    # secondsFromNow is added to register 45 ("now"), not wall-clock seconds -
    # see the mpmt-mss-led-pulser-registers memory for why
    def setLEDBurstConfigIn(self, secondsFromNow: int, sub4ns: int, flashInterval4ns: int, flashCount: int):
        now = self.fpga.readRegister(self.fpga.REG_TR32_COUNT)
        self.setLEDBurstConfig(now + secondsFromNow, sub4ns, flashInterval4ns, flashCount)

    def getLEDBurstKey(self) -> int:
        return self.fpga.readRegister(self.REG_BURST_KEY_OUT_BASE + self.led_rank)

    def setLEDBurstKey(self, key: int):
        self.fpga.writeRegister(self.REG_BURST_KEY_IN_BASE + self.led_rank, key)

    def startLEDBurst(self):
        self.setLEDBurstKey(self.getLEDBurstKey())

    def getLEDBurstStatus(self) -> dict:
        value = (self.fpga.readRegister(self.REG_BURST_STATUS) >> (2 * self.led_rank)) & 0x3
        return {"value": value, "string": self.BURST_STATUS_MAP.get(value, "undef")}

    def clearLEDBurstStatus(self):
        self.fpga.writeRegister(self.REG_BURST_CLEAR, 0x2 << (2 * self.led_rank))

    @DeviceChannel.track_connection
    @DeviceChannel.validate_range(0, 1)
    def setLEDTrigger(self, value: int):
        self.modbus.write_coil(address=2, value=bool(value), slave=self.address)

    @DeviceChannel.track_connection
    def getLEDTriggerStatus(self):
        rr = self.modbus.read_coils(address=2, count=1, slave=self.address)
        return {"value": int(rr.bits[0]), "string": self.STATUS_MAP.get(rr.bits[0], "undef")}

    @DeviceChannel.track_connection
    @DeviceChannel.validate_range(0, 1)
    def setLEDBias(self, value: int):
        self.modbus.write_coil(address=3, value=bool(value), slave=self.address)

    @DeviceChannel.track_connection
    def getLEDBiasStatus(self):
        rr = self.modbus.read_coils(address=3, count=1, slave=self.address)
        return {"value": int(rr.bits[0]), "string": self.STATUS_MAP.get(rr.bits[0], "undef")}

    @DeviceChannel.track_connection
    @DeviceChannel.validate_range(2.02, 15.28)
    def setLEDBiasVoltage(self, value: float):
        dac_level = int(4711.9 - 307.97 * value)
        if dac_level > 4095:
            dac_level = 4095
        elif dac_level < 0:
            dac_level = 0
        rr = self.modbus.write_register(address=40003, value=dac_level, slave=self.address)     
        if not rr.isError():
            # update FPGA register
            regval = self.fpga.readRegister(self.REG_LED_BASE + self.led_rank) & 0x7F000
            regval |= (dac_level & 0xFFF)
            self.fpga.writeRegister(self.REG_LED_BASE + self.led_rank, regval)

    @DeviceChannel.track_connection
    def getLEDBiasVoltage(self) -> float:
        dac_level = self.modbus.read_holding_registers(address=40003, count=1, slave=self.address).registers[0]
        value = (4711.9 - dac_level) / 307.97
        return round(value, 2)
        
    @DeviceChannel.track_connection
    def readLEDBiasVoltage(self) -> float:
        adc_level = self.modbus.read_holding_registers(address=40004, 
            count=1, slave=self.address).registers[0] & 0xFFF;
        level_in_volts = adc_level / 248.242
        return round(level_in_volts, 2)

    @DeviceChannel.track_connection
    # enable list of led channels (first channel is 1)
    def setLEDChannels(self, channels: list[int], append: bool = False):
        value = 0
        for ch in channels:
            value |= (1<<(ch-1)) 
        
        if append:
            chs = self.modbus.read_holding_registers(address=40002, count=1, slave=self.address).registers[0]
            value |= chs

        rr = self.modbus.write_register(address=40002, value=value, slave=self.address)     
        if not rr.isError():
            # update FPGA register
            regval = self.fpga.readRegister(self.REG_LED_BASE + self.led_rank) & 0xFFF
            regval |= (value & 0x7F) << 12
            self.fpga.writeRegister(self.REG_LED_BASE + self.led_rank, regval)

    @DeviceChannel.track_connection
    # return list of enabled led channels
    def getLEDChannels(self) -> list[int]:
        output = []
        value = self.modbus.read_holding_registers(address=40002, count=1, slave=self.address).registers[0]
        for ch in range(0,7):
            if value & (1<<ch):
                output.append(ch+1)
        return output

    @DeviceChannel.track_connection
    def setLEDTriggerSource(self, source: Union[str, int]):
        if isinstance(source, str):
            source = TriggerSource(source)
        elif isinstance(source, int):
            source = TriggerSource.from_int(source)
        self.modbus.write_register(address=40001, value=int(source), slave=self.address)

    @DeviceChannel.track_connection
    def getLEDTriggerSource(self) -> dict:
        value = self.modbus.read_holding_registers(address=40001,
            count=1, slave=self.address).registers[0]
        return {"value": value, "string": TriggerSource.from_int(value)} 

    @DeviceChannel.track_connection
    def getLEDCurrent(self):
        adc_level = self.modbus.read_holding_registers(address=40005,
            count=1, slave=self.address).registers[0] & 0xFFF; 
        level_in_ma = adc_level / 248.242
        return round(level_in_ma, 2)

    @DeviceChannel.track_connection
    def readLEDMonRegisters(self) -> dict:
        monData = {}
    
        monData['status'] = self.getLEDStatus()
        monData['bias'] = self.getLEDBiasStatus()
        monData['biasVoltageSet'] = self.getLEDBiasVoltage()
        monData['biasVoltage'] = self.readLEDBiasVoltage()
        monData['trigger'] = self.getLEDTriggerStatus()
        monData['triggerSource'] = self.getLEDTriggerSource()
        monData['current'] = self.getLEDCurrent()
        monData['channels'] = self.getLEDChannels()
        
        return monData
    
    @DeviceChannel.validate_range(20, 40)
    def setLEDModbusAddress(self, addr: int):
        self.modbus.write_register(address=40006, value=addr, slave=self.address)

