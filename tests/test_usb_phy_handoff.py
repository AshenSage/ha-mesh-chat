"""Exercise the actual pinned Espressif HAL against synthetic registers.

No USB device, host, interrupts, hardware, flash operation or firmware tool runs.
"""
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HAL = Path(__file__).parent / "fixtures/esp_idf_4_4_7/usb_phy_ll.h"


def added_header():
    patch = (ROOT / "firmware/meshcore-usb-lab.patch").read_text()
    section = patch.split("+++ b/examples/companion_radio/LabUSBPhy.h\n", 1)[1]
    return "".join(line[1:] for line in section.splitlines(True)
                   if line.startswith("+") and not line.startswith("+++"))


def make_fixture(tmp_path):
    includes = tmp_path / "include"
    files = {
        "Arduino.h": "#pragma once\nvoid delay(unsigned long);\n",
        "driver/periph_ctrl.h": "#pragma once\nvoid periph_module_reset(int);\nvoid periph_module_disable(int);\n",
        "esp_attr.h": "#pragma once\n#define FORCE_INLINE_ATTR inline\n",
        "soc/periph_defs.h": "#pragma once\n#define PERIPH_USB_MODULE 7\n",
        "soc/soc.h": "#pragma once\n#include <stdint.h>\n",
        "soc/system_struct.h": """#pragma once
struct system_dev_t {
  struct { int usb_clk_en; } perip_clk_en0;
  struct { int usb_rst; } perip_rst_en0;
};
extern system_dev_t SYSTEM;
""",
        "soc/usb_wrap_struct.h": """#pragma once
struct usb_wrap_otg_conf_reg_t {
  int phy_sel, pad_pull_override, dp_pullup, dp_pulldown, dm_pullup, dm_pulldown, pad_enable;
};
struct usb_wrap_dev_t {
  usb_wrap_otg_conf_reg_t otg_conf;
  struct { unsigned val; int test_usb_wrap_oe, test_enable; } test_conf;
};
extern usb_wrap_dev_t USB_WRAP;
""",
        "soc/rtc_cntl_struct.h": """#pragma once
struct rtc_cntl_dev_t { struct { int sw_hw_usb_phy_sel, sw_usb_phy_sel; } usb_conf; };
extern rtc_cntl_dev_t RTCCNTL;
""",
        "soc/usb_serial_jtag_struct.h": """#pragma once
struct usb_serial_jtag_dev_t {
  struct { int phy_sel, pad_pull_override, dp_pullup, usb_pad_enable; } conf0;
};
extern usb_serial_jtag_dev_t USB_SERIAL_JTAG;
""",
        "LabUSBPhy.h": added_header(),
    }
    for name, text in files.items():
        target = includes / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    target = includes / "hal/usb_phy_ll.h"
    target.parent.mkdir(parents=True)
    shutil.copyfile(HAL, target)
    return includes


def test_hal_fixture_matches_unmodified_pinned_upstream():
    # ESP-IDF v4.4.7 components/hal/esp32s3/include/hal/usb_phy_ll.h
    assert hashlib.sha256(HAL.read_bytes()).hexdigest() == "07f869755299e96fc73fb913bb0b9fed2ade580f12a22c058bbb07247f5c959c"


@pytest.mark.parametrize("initial_otg", [False, True])
def test_handoff_reclaims_phy_and_exposes_real_detach_interval(tmp_path, initial_otg):
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("C++ compiler required for register-model test")
    includes = make_fixture(tmp_path)
    source = tmp_path / "main.cpp"
    source.write_text("""#include <cassert>
#include "LabUSBPhy.h"
system_dev_t SYSTEM = {};
usb_wrap_dev_t USB_WRAP = {};
rtc_cntl_dev_t RTCCNTL = {};
usb_serial_jtag_dev_t USB_SERIAL_JTAG = {};
bool module_reset = false, module_disabled = false, detached = false;
void periph_module_reset(int p) { assert(p == PERIPH_USB_MODULE); module_reset = true; }
void periph_module_disable(int p) { assert(p == PERIPH_USB_MODULE); module_disabled = true; }
void delay(unsigned long ms) {
  assert(module_reset && module_disabled);
  assert(USB_SERIAL_JTAG.conf0.usb_pad_enable == 0);
  assert(RTCCNTL.usb_conf.sw_usb_phy_sel == 0);
  assert(ms >= 10 && ms <= 100);
  detached = true;
}
int main() {
  RTCCNTL.usb_conf.sw_hw_usb_phy_sel = 1;
  RTCCNTL.usb_conf.sw_usb_phy_sel = INITIAL_OTG;
  USB_SERIAL_JTAG.conf0.phy_sel = 1;
  USB_SERIAL_JTAG.conf0.pad_pull_override = 1;
  meshchat_lab_prepare_usb_phy();
  assert(detached && module_reset && module_disabled);
  assert(RTCCNTL.usb_conf.sw_hw_usb_phy_sel == 1);
  assert(RTCCNTL.usb_conf.sw_usb_phy_sel == 0);
  assert(USB_SERIAL_JTAG.conf0.phy_sel == 0);
  assert(USB_SERIAL_JTAG.conf0.pad_pull_override == 0);
  assert(USB_SERIAL_JTAG.conf0.dp_pullup == 1);
  assert(USB_SERIAL_JTAG.conf0.usb_pad_enable == 1);
}
""")
    executable = tmp_path / "register-test"
    result = subprocess.run([compiler, "-std=c++17", "-DCONFIG_IDF_TARGET_ESP32S3=1",
                             "-DARDUINO_USB_MODE=1", "-DARDUINO_USB_CDC_ON_BOOT=1",
                             "-DINITIAL_OTG=" + str(int(initial_otg)), "-I", str(includes),
                             str(source), "-o", str(executable)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(executable)], check=True)


def test_handoff_rejects_otg_usb_build_at_compile_time(tmp_path):
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("C++ compiler required for compile guard test")
    includes = make_fixture(tmp_path)
    source = tmp_path / "main.cpp"
    source.write_text('#include "LabUSBPhy.h"\n')
    result = subprocess.run([compiler, "-fsyntax-only", "-DCONFIG_IDF_TARGET_ESP32S3=1",
                             "-DARDUINO_USB_MODE=0", "-DARDUINO_USB_CDC_ON_BOOT=1",
                             "-I", str(includes), str(source)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "requires ESP32-S3 hardware USB CDC" in result.stderr
