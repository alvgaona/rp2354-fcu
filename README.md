<div align="center">

# rp2354-fcu

**A 40 × 40 mm flight control unit built around the RP2354A.**

[![Rev 0.1.0](https://img.shields.io/badge/rev-0.1.0-orange.svg)](hw/fc.kicad_pcb)
[![KiCad 10](https://img.shields.io/badge/KiCad-10-314cb0.svg)](https://www.kicad.org)
[![Pixi](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json)](https://pixi.sh)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

## Overview

rp2354-fcu is a 2-layer flight controller that fits the 30.5 mm mounting pattern. It takes a 2S LiPo or USB, reads an IMU and a GPS, and drives eight servos or ESCs.

- RP2354A microcontroller with 2 MB of flash in the package
- ICM-42688-P IMU on SPI
- GPS connector (JST-GH) for an off-board module such as the NEO-6M
- Eight 3-pin servo/ESC outputs
- 2S LiPo (JST-XH) or USB-C power through a 3.3 V buck converter
- SWD on JST-SH in the Raspberry Pi debug probe pinout

The MCU core (regulator, crystal, decoupling and USB) is copied from Raspberry Pi's RP2350A minimal design, including its layout.

Rev 0.1.0 passes KiCad's ERC and DRC, but it has not been manufactured or tested yet.

The [hardware reference](docs/hardware.md) has the power notes, the GPIO map, the connector pinouts and how to order the board from JLCPCB.

## Build

The design lives in `hw/` and is the source of truth, so edit it in KiCad 10. The build checks it and writes everything you need to order and view the board.

You need KiCad 10 and [pixi](https://pixi.sh). Install the font `hw/fonts/IBMPlexMono-Medium.ttf` first (double-click it), because the text on the back of the board uses it.

```sh
pixi run build
```

The build runs ERC, DRC with schematic parity, and `scripts/check_layout.py`, and stops on any error before it exports anything. That last script checks what DRC cannot. It wants a ground via near every ground pad, the ground pour in one solid piece, no pad fed only by a thin 3.3 V track, and nothing drilled under the IMU.

It then writes these files to `build/`.

- Gerbers, BOM and placement files for JLCPCB (`fc-gerbers.zip`, `fc-bom.csv` and `fc-cpl.csv`)
- The schematic as a PDF (`fc-schematic.pdf`)
- The assembled board in 3D (`fc.glb`)
- The board package with all of the above plus the KiCad files (`fc-rev<rev>.zip`)

## License

[MIT](LICENSE).
