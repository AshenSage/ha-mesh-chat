# Experimental Serial/JTAG USB handoff

The pinned external selector configuration enables `CONFIG_ESP_CONSOLE_USB_CDC`.
On ESP32-S3 this is the USB-OTG console, whereas our companion uses hardware
USB Serial/JTAG (`ARDUINO_USB_MODE=1`, CDC on boot). Both share the internal PHY.

The pinned Arduino 2.0.17 `HWCDC::begin()` sets the Serial/JTAG pad controls
but does not restore the RTC PHY mux. ESP-IDF 4.4.7's
`usb_phy_ll_int_jtag_enable()` additionally sets `sw_hw_usb_phy_sel=1` and
`sw_usb_phy_sel=0`. This is a source-level handoff defect when entering with
the OTG selection still active; it is not proof of the cause of a particular
board's failed boot. Source configuration is not full provenance for the
external prebuilt bootloader/selector.

The bench patch resets/disables the OTG module, explicitly claims the internal
PHY for Serial/JTAG, disconnects its USB pads for 30 ms, and reconnects before
`Serial.begin()`. A target/mode compile guard confines the hook to the pinned
ESP32-S3 hardware CDC environment. These are volatile peripheral operations;
the hook contains no eFuse, flash, NVS, OTA selection, profile or radio writes.

Sources used for the pinned implementation:

- [Arduino 2.0.17 HWCDC.cpp](https://github.com/espressif/arduino-esp32/blob/2.0.17/cores/esp32/HWCDC.cpp)
- [ESP-IDF 4.4.7 USB PHY HAL](https://github.com/espressif/esp-idf/blob/v4.4.7/components/hal/esp32s3/include/hal/usb_phy_ll.h)
- [ESP-IDF 4.4.7 bootloader console](https://github.com/espressif/esp-idf/blob/v4.4.7/components/bootloader_support/src/bootloader_console.c)
- [ESP-IDF USB controller handoff discussion](https://github.com/espressif/esp-idf/issues/9826)

The register-model regression uses the unmodified pinned Espressif HAL with
minimal synthetic register declarations. It checks the OTG-to-JTAG mux and
pad detach transition; it does not emulate a host, interrupts or USB traffic.
The Actions build checks the actual pinned compiler/framework integration.

## Required hardware validation

Hardware validation of the correction remains pending. Do not infer success
from a passing build or test. Independently verify the USB companion protocol
after a cold boot, entry through the selector, ROM flashing and software reset.
Then verify profile persistence and repeat in both directions with Meshtastic.
The A5 manual OTA-selection proof and all existing lab write gates still apply.
Do not publish device identifiers, keys, namespace contents or raw flash dumps.
