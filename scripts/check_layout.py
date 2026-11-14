"""Check what KiCad's DRC cannot see in the layout. Any failed check fails the script.

    <KiCad's python3> scripts/check_layout.py <board.kicad_pcb>

It needs KiCad's pcbnew module, so scripts/build.sh runs it with KiCad's Python.

DRC passes a board whose ground is a chain of thin tracks, or whose pour hangs together by a hair.
The checks, one function each:

  ground vias   every SMD ground pad has a ground via, or a through-hole ground pad, close by
  ground pour   the bottom pour is one piece, and stays mostly one piece when its narrow necks are cut
  3.3 V pour    every 3.3 V pad on the top sits in a pour, not at the end of a thin track
  IMU           no via under the IMU

Each check prints what it measured and returns its failures. The exit status is 1 if there are any.
The limits and the names the checks look for are the constants below: change them with the design.
"""
import math
import sys

import pcbnew

GND = "GND"
V33 = "+3V3"
IMU = "U3"

MAX_GND_VIA_MM = 2.0  # an SMD ground pad farther than this from every ground via fails
BAR_WIDTH_MM = 1.0  # a ground track this wide or wider is the servo ground bar, not a stub to a via
GND_NECK_MM = 0.5  # ground pour narrower than this counts as cut
V33_NECK_MM = 0.3  # the same for the 3.3 V pour, which is only reported
MIN_SOLID_GND = 0.8  # the share of the ground pour that must stay in one piece once its necks are cut

ORIGIN_MM = 100.0  # the board's top-left corner on the KiCad sheet: positions are printed from there
NM2_PER_MM2 = 1e12  # KiCad measures in nanometres


def distance_mm(a: pcbnew.VECTOR2I, b: pcbnew.VECTOR2I) -> float:
    """The distance between two points of the board, in mm."""
    return math.hypot(pcbnew.ToMM(a.x - b.x), pcbnew.ToMM(a.y - b.y))


def position(point: pcbnew.VECTOR2I) -> str:
    """A point as "(x, y)" in mm from the board's top-left corner."""
    return f"({pcbnew.ToMM(point.x) - ORIGIN_MM:.1f}, {pcbnew.ToMM(point.y) - ORIGIN_MM:.1f})"


def vias(board: pcbnew.BOARD, net: str) -> list:
    """The vias of one net."""
    return [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == net]


def pads(board: pcbnew.BOARD, net: str) -> list:
    """The pads of one net, each as (name, pad) with a name like "U1.47"."""
    return [(f"{f.GetReference()}.{p.GetNumber()}", p) for f in board.GetFootprints() for p in f.Pads()
            if p.GetNetname() == net]


def piece_area(poly: pcbnew.SHAPE_POLY_SET, i: int) -> float:
    """The area of piece i of a polygon set, holes taken out, in mm2."""
    return pcbnew.SHAPE_POLY_SET(poly.UnitSet(i)).Area() / NM2_PER_MM2


def largest_piece(poly: pcbnew.SHAPE_POLY_SET) -> int:
    """The index of the largest piece of a polygon set."""
    return max(range(poly.OutlineCount()), key=lambda i: piece_area(poly, i))


def main_pour(board: pcbnew.BOARD, net: str, layer: int) -> pcbnew.SHAPE_POLY_SET:
    """The filled copper of the net's main zone on a layer.

    The main zone has priority 0. The small 3.3 V zones copied with the MCU core have a higher one.
    """
    for zone in board.Zones():
        if zone.GetNetname() == net and zone.GetAssignedPriority() == 0 and not zone.GetIsRuleArea():
            return zone.GetFilledPolysList(layer)
    sys.exit(f"LAYOUT CHECK FAILED: the board has no {net} pour")


def without_necks(pour: pcbnew.SHAPE_POLY_SET, neck_mm: float) -> pcbnew.SHAPE_POLY_SET:
    """The pour shrunk by half of neck_mm on every side, so that anything narrower than neck_mm is gone.

    What was joined only through such a neck comes out as separate pieces.
    """
    cut = pcbnew.SHAPE_POLY_SET(pour)
    cut.Unfracture()  # KiCad stores holes as zero-width slits to the outline; shrinking would open those up
    cut.Deflate(pcbnew.FromMM(neck_mm / 2), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, pcbnew.FromMM(0.01))
    return cut


def print_pour(net: str, pour: pcbnew.SHAPE_POLY_SET, solid: pcbnew.SHAPE_POLY_SET, neck_mm: float) -> None:
    """One line on a pour: its pieces, its area, and the largest piece left once its necks are cut."""
    print(f"{net} pour: {pour.OutlineCount()} piece(s), {pour.Area() / NM2_PER_MM2:.0f} mm2; "
          f"largest solid part ignoring necks under {neck_mm} mm: {piece_area(solid, largest_piece(solid)):.0f} mm2")


def check_ground_vias(board: pcbnew.BOARD) -> list[str]:
    """Every SMD ground pad sits within MAX_GND_VIA_MM of a way down to the bottom pour.

    A way down is a ground via or a through-hole ground pad. Also prints how much thin ground track
    there is: it should only be the stubs from pads to their vias.
    """
    ground_vias = vias(board, GND)
    ground_pads = pads(board, GND)
    ways_down = [v.GetPosition() for v in ground_vias] + [p.GetPosition() for _, p in ground_pads if p.HasHole()]
    gap, pad = max((min(distance_mm(p.GetPosition(), w) for w in ways_down), name)
                   for name, p in ground_pads if not p.HasHole())
    print(f"ground: {len(ground_vias)} vias, farthest pad from one: {pad} at {gap:.2f} mm")

    stubs_mm = sum(pcbnew.ToMM(t.GetLength()) for t in board.GetTracks()
                   if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() == GND
                   and pcbnew.ToMM(t.GetWidth()) < BAR_WIDTH_MM)
    print(f"ground: {stubs_mm:.0f} mm of track in total (stubs to vias; the servo ground bar is not counted)")

    return [f"{pad} is {gap:.2f} mm from the nearest ground via"] if gap > MAX_GND_VIA_MM else []


def check_ground_pour(board: pcbnew.BOARD) -> list[str]:
    """The bottom ground pour is one piece, and MIN_SOLID_GND of it stays one piece without its necks.

    Also prints the ground vias that land outside that solid piece. They are connected, but only
    through copper narrower than GND_NECK_MM.
    """
    failures = []
    pour = main_pour(board, GND, pcbnew.B_Cu)
    solid = without_necks(pour, GND_NECK_MM)
    print_pour(GND, pour, solid, GND_NECK_MM)
    if pour.OutlineCount() != 1:
        failures.append(f"ground pour is in {pour.OutlineCount()} pieces")

    main = largest_piece(solid)
    weak = [position(v.GetPosition()) for v in vias(board, GND) if not solid.Contains(v.GetPosition(), main)]
    print(f"ground vias reaching the main ground area only through a neck under {GND_NECK_MM} mm: {len(weak)} {weak}")
    if piece_area(solid, main) < MIN_SOLID_GND * pour.Area() / NM2_PER_MM2:
        failures.append(f"less than {MIN_SOLID_GND:.0%} of the ground pour is solid once necks under "
                        f"{GND_NECK_MM} mm are cut")
    return failures


def check_3v3_pour(board: pcbnew.BOARD) -> list[str]:
    """Every 3.3 V pad on the top layer sits in 3.3 V pour.

    The pour is the largest piece of the main 3.3 V zone, or one of the small zones copied with the
    MCU core. A pad outside both is fed by a track only.
    """
    pour = main_pour(board, V33, pcbnew.F_Cu)
    print_pour(V33, pour, without_necks(pour, V33_NECK_MM), V33_NECK_MM)

    main = largest_piece(pour)
    core_zones = [z for z in board.Zones() if z.GetNetname() == V33 and z.GetAssignedPriority() > 0]
    outside = sorted(name for name, p in pads(board, V33)
                     if p.IsOnLayer(pcbnew.F_Cu) and not pour.Contains(p.GetPosition(), main)
                     and not any(z.HitTestFilledArea(pcbnew.F_Cu, p.GetPosition()) for z in core_zones))
    print(f"{V33} pads fed by a track only, not by a pour: {outside}")
    return [f"{V33} pads outside every 3V3 pour: {outside}"] if outside else []


def check_imu(board: pcbnew.BOARD) -> list[str]:
    """No via inside the box around the IMU's pads: a via there puts stress and solder under the sensor."""
    imu = board.FindFootprintByReference(IMU)
    if imu is None:
        return [f"the board has no {IMU} (the IMU)"]
    box = pcbnew.BOX2I()
    for pad in imu.Pads():
        box.Merge(pad.GetBoundingBox())
    under = [f"{t.GetNetname()} {position(t.GetPosition())}" for t in board.GetTracks()
             if t.Type() == pcbnew.PCB_VIA_T and box.Contains(t.GetPosition())]
    print(f"vias under the IMU: {len(under)} {under}")
    return [f"via under the IMU: {under}"] if under else []


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    board = pcbnew.LoadBoard(sys.argv[1])

    failures = []
    for check in (check_ground_vias, check_ground_pour, check_3v3_pour, check_imu):
        failures += check(board)
    if failures:
        sys.exit("LAYOUT CHECK FAILED: " + "; ".join(failures))
    print("layout check: ok")


if __name__ == "__main__":
    main()
