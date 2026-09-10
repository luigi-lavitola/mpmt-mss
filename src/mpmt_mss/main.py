
import logging

from mpmt_mss.rpc import RPCRuntime, create_app
from mpmt_mss.runcontrol.fpga import FPGA
from mpmt_mss.feb import FEBManager, ModbusConfig
from mpmt_mss.sensors import HouseKeeping
from mpmt_mss.monitoring import Monitoring

# No logging was configured before, so module-level `logging.getLogger(...)`
# calls (e.g. progress logging in FEBManager.alignModbusAddresses) went
# nowhere. This puts them on stderr, which systemd (Type=simple, no
# StandardOutput= override) already captures into the journal, visible via
# `journalctl -u mpmt-mss -f`.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

febmgr = FEBManager(ModbusConfig(mode="rtu", port="/dev/ttyPS1"))

# core objects
fpga = FPGA('/dev/uio0')
hk = HouseKeeping(fpga)
monitoring = Monitoring(febmgr, fpga, hk)

runtime = RPCRuntime()

# core layer
runtime.register_service("fpga", fpga)
runtime.register_service("sensors", hk)
runtime.register_service("febmgr", febmgr)
runtime.register_service("monitoring", monitoring)

app = create_app(runtime)

def start():
    import uvicorn
    uvicorn.run("mpmt_mss.main:app", host="0.0.0.0", port=8000)
