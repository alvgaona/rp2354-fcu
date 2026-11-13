# RP2354A flight controller, rev 0.1.0

A 40 × 40 mm, 2-layer board with:

- **MCU:** RP2354A (2 MB flash in package)
- **IMU:** ICM-42688-P on SPI
- **Inputs:** USB-C, a 2S LiPo through a JST-XH connector, and a GPS connector (JST-GH 4-pin, for a NEO-6M module)
- **Outputs:** 8 servo/ESC 3-pin headers, with SWD on JST-SH
- **Mounting:** M3 holes on a 30.5 mm pattern

The MCU core (regulator, crystal, decoupling, USB) is copied from the Raspberry Pi RP2350A minimal design, including its layout.

## Power

- 2S LiPo (6–8.4 V) or USB powers an AP63203 buck converter, which makes 3.3 V. Each input goes through a Schottky diode, so you can plug in both at once and a reversed battery is blocked.
- The middle pin of every servo header is `SERVO_V`. This rail is **not** connected to the board's supply. Your ESC's BEC powers it, and a servo-only setup needs a separate 5 V source on it.
- The battery voltage reaches the ADC through a 10 k / 3.3 k divider: `VBAT = ADC × 4.03`.

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

To load firmware: hold BOOTSEL while plugging in USB. There's no reset button, so power-cycle the board instead.

## Rebuild

You need KiCad 10 and pixi (Java and Python come from pixi). Place `freerouting-2.5.0.jar` in the repo root.

```sh
scripts/build.sh   # schematic, ERC, PCB, autoroute, DRC, layout check
scripts/fab.sh     # build/fab: gerbers zip, BOM, CPL, schematic PDF
```

`scripts/design.py` is the single source of truth for the circuit and `scripts/build_pcb.py` for the layout. `hw/fc.kicad_sch` and `hw/fc.kicad_pcb` are generated, so edit the scripts rather than those files. `ref/` holds the Raspberry Pi RP2350A minimal design (MIT licence) that the MCU core layout is copied from.

How the layout is made:

- **Fixed by hand in `build_pcb.py`:** the 3.3 V regulator, USB data pair, SWD, the eight servo outputs and the IMU supply. These are locked before routing.
- **Ground:** every ground pad gets its own via into the bottom ground pour. The autorouter does not route ground.
- **Everything else:** Freerouting. Its result depends on the order of items in the board file, so the build tries a fixed list of seeds and keeps the first board that passes KiCad's DRC and `scripts/check_layout.py`. The same inputs always give the same board.
- **`check_layout.py`** checks what DRC cannot: a ground via near every ground pad, the ground pour in one solid piece, no pad fed only by a thin 3.3 V track, and nothing drilled under the IMU.

## Ordering (PCBWay)

- Bare board: upload `fc-gerbers-rev0.1.0.zip` with 2 layers, 1.6 mm thickness, and a 0.1 mm (4 mil) minimum track/space. The RP2350 QFN needs that space. The smallest drill is 0.25 mm.
- Assembly: also upload `fc-bom-rev0.1.0.csv` and `fc-cpl-rev0.1.0.csv`. The CPL uses KiCad coordinates, so Y is negative.
- The ICM-42688-P has been out of stock at LCSC. Check the price and stock with PCBWay before ordering.
