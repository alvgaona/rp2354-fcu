"""Single source of truth for the rev 0.1.0 flight-controller board.

Every part: ref -> (symbol, value, footprint, MPN, manufacturer, LCSC, {pin: net}).
Pins not listed get a no-connect flag. Refs of the RP2354A support circuit match
Raspberry Pi's RP2350A minimal design so build_pcb.py can transplant its layout.
"""

REV = "0.1.0"
TITLE = "RP2354A flight controller"

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
# Footprints copied from the Raspberry Pi minimal design (layout transplanted as-is).
RC = "rpi:generic_capc1005x50"
RCW = "rpi:generic_capc1005x50_wide"
RR = "rpi:generic_resc1005x35"

PARTS = {}


def part(ref, sym, value, fp, mpn, mfr, lcsc, pins):
    PARTS[ref] = dict(sym=sym, value=value, fp=fp, mpn=mpn, mfr=mfr, lcsc=lcsc, pins=pins)


def R(ref, value, a, b, mpn, lcsc, fp=R0402):
    part(ref, "Device:R", value, fp, mpn, "UNI-ROYAL", lcsc, {"1": a, "2": b})


def C(ref, value, a, b, mpn, mfr, lcsc, fp=C0402):
    part(ref, "Device:C", value, fp, mpn, mfr, lcsc, {"1": a, "2": b})


# ---------------- MCU: RP2354A (2 MB flash in package) ----------------
GPIO = {
    2: "GPS_TX", 3: "GPS_RX",  # GPIO0/1 = UART0
    # GPIO4-11 = PWM slices 2-5. GPIO2/3 (pins 4/5) are left free: C8's vias block their escape.
    7: "PWM1_MCU", 8: "PWM2_MCU", 9: "PWM3_MCU", 10: "PWM4_MCU",
    12: "PWM5_MCU", 13: "PWM6_MCU", 14: "PWM7_MCU", 15: "PWM8_MCU",
    27: "IMU_MISO", 28: "IMU_CS", 29: "IMU_SCK", 31: "IMU_MOSI",  # GPIO16-19 = SPI0
    32: "IMU_INT1",  # GPIO20
    37: "LED",  # GPIO25
    40: "VBAT_SENSE",  # GPIO26/ADC0
}
u1 = {str(p): "+3V3" for p in (1, 11, 20, 30, 38, 45, 44, 49, 53, 54)}
u1.update({str(p): "+1V1" for p in (6, 23, 39, 50)})
u1.update({str(p): n for p, n in GPIO.items()})
# RUN has an internal pull-up; the optional reset button is omitted (power-cycle instead).
u1.update({"21": "XIN", "22": "XOUT", "24": "SWCLK", "25": "SWDIO",
           "46": "VREG_AVDD", "47": "GND", "48": "VREG_LX", "51": "USB_DM_MCU", "52": "USB_DP_MCU",
           "60": "QSPI_SS", "61": "GND"})
part("U1", "MCU_RaspberryPi:RP2354A", "RP2354A", "rpi:rpi_rp2350a_vias", "RP2354A", "Raspberry Pi", "C41378174", u1)

# Core regulator (exact parts required by the RP2350 hardware design guide)
part("L1", "Device:L", "3.3u", "rpi:abracon_aota-b201610s3r3-101-t", "AOTA-B201610S3R3-101-T", "Abracon", "C42411119",
     {"1": "+1V1", "2": "VREG_LX"})
for ref, a in (("C6", "+3V3"), ("C7", "+1V1"), ("C9", "VREG_AVDD")):
    C(ref, "4.7u", a, "GND", "GRM155R60J475ME47D", "Murata", "C82453", fp=RCW if ref != "C9" else RC)
R("R3", "33", "+3V3", "VREG_AVDD", "0402WGF330JTCE", "C25105", fp=RR)
for ref in ("C8", "C10", "C11"):
    C(ref, "100n", "+1V1", "GND", "CL05B104KO5NNNC", "Samsung", "C1525", fp=RC)
for ref in ("C12", "C13", "C14", "C15", "C16", "C17", "C18"):
    C(ref, "100n", "+3V3", "GND", "CL05B104KO5NNNC", "Samsung", "C1525", fp=RC)

# Crystal (ABM8-272-T3 + 15p + 1k, as specified by Raspberry Pi)
part("X1", "Device:Crystal_GND24", "12MHz", "rpi:generic_xtalcc320x250x80-4", "ABM8-272-T3", "Abracon", "C20625731",
     {"1": "XIN", "2": "GND", "3": "XTAL_OUT", "4": "GND"})
C("C3", "15p", "XIN", "GND", "GRM1555C1H150JA01D", "Murata", "C76950", fp=RC)
C("C4", "15p", "XTAL_OUT", "GND", "GRM1555C1H150JA01D", "Murata", "C76950", fp=RC)
R("R2", "1k", "XOUT", "XTAL_OUT", "0402WGF1001TCE", "C11702", fp=RR)

# USB-C (device, 5.1k Rd on CC) + 27R series termination close to the chip
part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "fc:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
     "TYPE-C-31-M-12", "HRO", "C165948",
     {"A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND", "SH": "GND",
      "A4": "VBUS", "B4": "VBUS", "A9": "VBUS", "B9": "VBUS",
      "A5": "CC1", "B5": "CC2", "A6": "USB_D+", "B6": "USB_D+", "A7": "USB_D-", "B7": "USB_D-"})
R("R1", "5.1k", "CC1", "GND", "0402WGF5101TCE", "C25905")
R("R5", "5.1k", "CC2", "GND", "0402WGF5101TCE", "C25905")
R("R7", "27", "USB_D+", "USB_DP_MCU", "0402WGF270JTCE", "C25100", fp=RR)
R("R8", "27", "USB_D-", "USB_DM_MCU", "0402WGF270JTCE", "C25100", fp=RR)

# BOOTSEL button, SWD debug (Raspberry Pi debug-probe pinout)
SW = "rpi:wurthelek_434133025816"
part("SW1", "Switch:SW_MEC_5G", "BOOTSEL", SW, "434133025816", "Wurth Elektronik", "C5504987",
     {"1": "GND", "2": "GND", "3": "USB_BOOT", "4": "USB_BOOT"})
R("R6", "1k", "QSPI_SS", "USB_BOOT", "0402WGF1001TCE", "C11702")
part("J4", "Connector_Generic_MountingPin:Conn_01x03_MountingPin", "SWD",
     "Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal", "SM03B-SRSS-TB(LF)(SN)", "JST", "C160403",
     {"1": "SWCLK", "2": "GND", "3": "SWDIO", "MP": "GND"})
part("D3", "Device:LED", "RED", "LED_SMD:LED_0603_1608Metric", "KT-0603R", "Hubei KENTO", "C2286",
     {"1": "GND", "2": "LED_A"})
R("R19", "1k", "LED", "LED_A", "0402WGF1001TCE", "C11702")

# ---------------- Power: 2S LiPo / USB -> diode-OR -> AP63203 buck -> 3.3 V ----------------
part("J6", "Connector_Generic:Conn_01x02", "2S LiPo", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
     "B2B-XH-A(LF)(SN)", "JST", "C158012", {"1": "VBAT", "2": "GND"})
part("D1", "Device:D_Schottky", "B5819W", "Diode_SMD:D_SOD-123", "B5819W SL", "CJ", "C8598",
     {"1": "VIN", "2": "VBAT"})  # reverse-polarity protection + OR with USB
part("D2", "Device:D_Schottky", "B5819W", "Diode_SMD:D_SOD-123", "B5819W SL", "CJ", "C8598",
     {"1": "VIN", "2": "VBUS"})
part("U2", "Regulator_Switching:AP63203WU", "AP63203WU", "Package_TO_SOT_SMD:TSOT-23-6", "AP63203WU-7",
     "Diodes Inc", "C780769", {"1": "+3V3", "2": "VIN", "3": "VIN", "4": "GND", "5": "SW_BUCK", "6": "BST"})
C("C1", "10u", "VIN", "GND", "CL21A106KAYNNNE", "Samsung", "C15850", fp=C0805)
C("C2", "100n", "BST", "SW_BUCK", "CL05B104KO5NNNC", "Samsung", "C1525")
part("L2", "Device:L", "3.9u", "Inductor_SMD:L_Changjiang_FNR3015S", "FNR3015S3R9MT", "Changjiang", "C167751",
     {"1": "SW_BUCK", "2": "+3V3"})
C("C5", "22u", "+3V3", "GND", "CL21A226MAQNNNE", "Samsung", "C45783", fp=C0805)
C("C19", "22u", "+3V3", "GND", "CL21A226MAQNNNE", "Samsung", "C45783", fp=C0805)
# Battery voltage sense: 10k/3.3k -> 8.4 V reads 2.08 V on ADC0
R("R9", "10k", "VBAT", "VBAT_SENSE", "0402WGF1002TCE", "C25744")
R("R10", "3.3k", "VBAT_SENSE", "GND", "0402WGF3301TCE", "C25890")
C("C20", "100n", "VBAT_SENSE", "GND", "CL05B104KO5NNNC", "Samsung", "C1525")

# ---------------- IMU: ICM-42688-P on SPI0 ----------------
part("U3", "fc:ICM-42688-P", "ICM-42688-P", "easyeda:LGA-14_L3.0-W2.5-P0.50-TL", "ICM-42688-P",
     "TDK InvenSense", "C1850418",
     # RESV pins 2, 3, 10, 11 are "no connect or GND" in the datasheet. 2 and 3 are left open so the INT1
     # track can pass them; 10 and 11 are grounded together with pin 9 (FSYNC, unused) to share its via.
     # Pin 7 (RESV) must be GND.
     {"1": "IMU_MISO", "4": "IMU_INT1", "5": "+3V3", "6": "GND", "7": "GND",
      "8": "+3V3", "9": "GND", "10": "GND", "11": "GND", "12": "IMU_CS", "13": "IMU_SCK", "14": "IMU_MOSI"})
C("C21", "100n", "+3V3", "GND", "CL05B104KO5NNNC", "Samsung", "C1525")  # VDD
C("C22", "2.2u", "+3V3", "GND", "CL05A225MQ5NSNC", "Samsung", "C12530")  # VDD
C("C23", "10n", "+3V3", "GND", "CL05B103KB5NNNC", "Samsung", "C15195")  # VDDIO

# ---------------- External connections ----------------
part("J5", "Connector_Generic_MountingPin:Conn_01x04_MountingPin", "GPS",
     "Connector_JST:JST_GH_SM04B-GHS-TB_1x04-1MP_P1.25mm_Horizontal", "SM04B-GHS-TB(LF)(SN)", "JST", "C189895",
     {"1": "+3V3", "2": "GPS_TX", "3": "GPS_RX", "4": "GND", "MP": "GND"})
for i in range(1, 9):
    R(f"R{10 + i}", "220", f"PWM{i}_MCU", f"PWM{i}", "0402WGF2200TCE", "C25091")
    # signal / servo rail (fed by ESC BEC, isolated from 3V3) / GND
    part(f"J{6 + i}", "Connector_Generic:Conn_01x03", f"OUT{i}", "fc:PinHeader_1x03_P2.54mm_Vertical_Tight",
         "2.54-1*3P", "BOOMELE", "C49257", {"1": f"PWM{i}", "2": "SERVO_V", "3": "GND"})
for i in range(1, 5):
    part(f"H{i}", "Mechanical:MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3", "", "", "", {})

def nets():
    out = {}
    for ref, p in PARTS.items():
        for pin, net in p["pins"].items():
            out.setdefault(net, []).append((ref, pin))
    return out


if __name__ == "__main__":
    for n, conns in sorted(nets().items()):
        if len(conns) < 2:
            print("SINGLE-PIN NET", n, conns)
    print(len(PARTS), "parts", len(nets()), "nets")
