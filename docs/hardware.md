# Hardware reference

Rev 0.1.0. The schematic is the authority, and this page is the short version for wiring and firmware.

## Power

- 2S LiPo (6–8.4 V) or USB powers an AP63203 buck converter, which makes 3.3 V. Each input goes through a Schottky diode, so you can plug in both at once and a reversed battery is blocked.
- The middle pin of every servo header is `SERVO_V`. This rail is **not** connected to the board's supply. Your ESC's BEC powers it, and a servo-only setup needs a separate 5 V source on it.
- The battery voltage reaches the ADC through a 10 k / 3.3 k divider, so `VBAT = ADC × 4.03`.

## GPIO map

| Function | GPIO | Notes |
|---|---|---|
| GPS TX/RX | 0 / 1 | UART0 (GPIO0 = MCU TX → GPS RX) |
| OUT1–OUT8 | 4–11 | PWM slices 2–5. OUT1/2, 3/4, 5/6 and 7/8 share a frequency |
| IMU MISO / CS / SCK / MOSI | 16 / 17 / 18 / 19 | SPI0 |
| IMU INT1 | 20 | |
| LED | 25 | Active high |
| VBAT sense | 26 | ADC0 |

## Connectors

| Connector | Pin 1 | Pin 2 | Pin 3 | Pin 4 |
|---|---|---|---|---|
| GPS (JST-GH 4) | 3.3 V | MCU TX → GPS RX | MCU RX ← GPS TX | GND |
| SWD (JST-SH 3, Raspberry Pi debug probe pinout) | SWCLK | GND | SWDIO | |
| 2S+ (JST-XH 2) | VBAT + | GND | | |
| OUT1–8 (2.54 mm) | Signal | SERVO_V (BEC) | GND | |

The GPS connector gives out 3.3 V. GY-NEO6MV2 boards accept that, but their on-board LDO then drops it to about 3.2 V.

To load firmware, hold BOOTSEL while plugging in USB. There's no reset button, so power-cycle the board instead.

## Ordering (JLCPCB)

- For the bare board, upload `fc-gerbers.zip` with 2 layers, 1.6 mm thickness and black solder mask with white silkscreen. The board uses JLCPCB's 2-layer minimum of 0.1 mm track and space, which the RP2350 QFN needs. The smallest via is a 0.25 mm hole in a 0.6 mm pad.
- For assembly, also upload `fc-bom.csv` and `fc-cpl.csv`. They list the 54 SMD parts. The servo headers and the battery connector are through-hole and soldered by hand.
- Check every part's position and rotation in JLCPCB's placement preview before you pay, because the CPL has KiCad's rotations and JLCPCB's differ for some packages.
- The silkscreen has no reference designators. descent's PCB view shows them.
- The ICM-42688-P is an extended part at JLCPCB and has been out of stock at LCSC. Check its stock before ordering.
