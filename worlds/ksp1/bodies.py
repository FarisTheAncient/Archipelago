"""
Celestial body data, mission graph, and difficulty profiles for KSP1 Archipelago.

Delta-v values sourced from the KSP-DeltaV-Planner (planets.ts / kerbin.ts).
Physics values from the KSP wiki.  All values are conservative estimates that
err toward overestimating the required delta-v (golden rule).

Mission profile structure
-------------------------
``MissionBuilder`` owns the mission graph for a given home body.  Internally
it maintains two edge sets: an *outbound* graph (explore-out from the home
body, free to capture into any intermediate SOI) and a *return* graph
(restricted: paths must terminate at home.surface and may not capture into
any non-home SOI on the way back).  For each ``(target_body, mission_type)``
the builder enumerates simple paths through these graphs and stores them
as profile alternatives.

The builder is owned by ``KSP1World`` (see ``world.mission_builder``) — this
is the data-lifetime layer where the Phase 4 ``StartingBody`` option will
plug in.  Inter-planet transfer dvs come from Hohmann math at solar-frame
radii (see ``planet_transfer_dv``); moon-system transfers reuse the per-body
``dvLI`` / ``dvPL`` / ``dvPE`` values.  Plane-change cost is carried on
each transfer edge as ``plane_change_dv`` and the difficulty profile's
``plane_change_fraction`` controls how much of it is actually paid.

Node naming convention:
  "{body}_surface", "{body}_low_orbit", "{body}_soi", "{body}_intercept"
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum, StrEnum, auto
from functools import lru_cache
from typing import Optional


# ---------------------------------------------------------------------------
# Body names — single source of truth, catches typos at import time
# ---------------------------------------------------------------------------

class MissionType(StrEnum):
    """Mission profile types — keys into MissionBuilder.profiles_for."""
    ORBIT = "orbit"
    LAND = "land"
    RETURN = "return"
    SAMPLE_RETURN = "sample_return"
    FLAG_PLANT = "flag_plant"
    ESCAPE = "escape"
    # Rescue: reach the target's ORBIT, rendezvous, and bring a stranded Kerbal
    # home — like RETURN but the return starts from low orbit (no landing leg).
    RESCUE = "rescue"
    # Surface rescue: land NEAR a Kerbal stranded on the target's surface
    # (precision landing), take them aboard, and bring them home — RETURN's
    # trajectory plus a precision-landing surcharge on the descent and a
    # site-latitude plane change on the ascent back out.
    SURFACE_RESCUE = "surface_rescue"
    # Orbit-and-return: reach the target's ORBIT and bring the vessel home —
    # RESCUE's trajectory without the rendezvous phasing burn (no second craft to
    # meet).  Emitted both as a mission location (the middle return tier) and as
    # a contract type (TOURISM), so it carries feasibility-table rows.
    ORBIT_RETURN = "orbit_return"
    # SOI-and-return: reach the target's SOI boundary — a flyby — and bring the
    # vessel home.  No capture and no landing at the target; the turn-around
    # point is the SOI node rather than low orbit or the surface.  The shallowest
    # of the three return tiers.
    SOI_RETURN = "soi_return"
    # Home-body-only mission types (no MissionBuilder profile entry)
    SOUNDING = "sounding"
    FIRST_LAUNCH = "first_launch"
    FIRST_LANDING = "first_landing"
    FIRST_STAGING = "first_staging"
    SPLASHDOWN = "splashdown"


class Achievement(StrEnum):
    """A flight-log entry a vessel or kerbal actually recorded at a body.

    THIS IS NOT AN ORDERED SCALE. Do not add a comparison operator, an ordering
    key, an int backing you can >=, or an "at least this deep" helper. Two
    independent reasons, both of which look like missed optimisations:

      1. The difficulty ordering inverts with direction of travel. Outbound from
         home it is suborbital < flyby < orbit < surface; arriving from outside
         the system it is flyby < orbit < suborbital < surface, because
         suborbital sits on the far side of orbital capture on the way down.
      2. Deeper does not imply shallower. A direct-entry landing reaches the
         surface without ever orbiting, so Surface must not satisfy an Orbit
         requirement.

    Every check asks whether the one entry it needs is present in the log's set.
    Stock KSP does the same — ReturnFrom's independent HasEntry() tests. The
    client mirrors this enum as MissionAchievement with the same warning.
    """
    SUBORBITAL = "suborbital"
    FLYBY = "flyby"
    ORBIT = "orbit"
    SURFACE = "surface"

    # StrEnum inherits str's lexicographic ordering, which would silently answer
    # "is this deep enough?" with alphabetical nonsense. Make the question itself
    # an error so the ban above is mechanical, not just documented.
    def _no_order(self, other):
        raise TypeError(
            "Achievement is not an ordered scale — test set membership for the "
            "exact entry you need (see the Achievement docstring).")

    __lt__ = _no_order
    __le__ = _no_order
    __gt__ = _no_order
    __ge__ = _no_order


class BodyName(StrEnum):
    KERBIN = "Kerbin"
    MUN = "Mun"
    MINMUS = "Minmus"
    MOHO = "Moho"
    EVE = "Eve"
    GILLY = "Gilly"
    DUNA = "Duna"
    IKE = "Ike"
    DRES = "Dres"
    JOOL = "Jool"
    LAYTHE = "Laythe"
    VALL = "Vall"
    TYLO = "Tylo"
    BOP = "Bop"
    POL = "Pol"
    EELOO = "Eeloo"
    KERBOL = "Sun"


# ---------------------------------------------------------------------------
# Difficulty profiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DifficultyProfile:
    """PHYSICS overheads only (dv margins, TWR floors, drag). Resolved from the
    PhysicsDifficulty option. Player skill/equipment gates live on
    GameplayDifficulty, resolved from the separate base Difficulty option."""
    fixed_margin: float         # m/s added to every dv budget
    percent_margin: float       # fraction multiplied on top (0.15 = 15%)
    plane_change_fraction: float # fraction of worst-case plane-change dv included
    min_twr_atmo: float         # minimum TWR for atmospheric ascent/landing
    min_twr_vac: float          # minimum TWR for vacuum ascent/landing
    ship_cd: float              # ship body drag coefficient (parachute discount)
    # Hover-translate seconds budgeted to correct residual horizontal error onto
    # a precision landing target (surface rescue).  Consumed by
    # precision_landing_dv: surcharge = g * precision_hover_s +
    # 2 * PRECISION_TRANSLATE_V, defined as exactly 0 when the budget is 0.
    precision_hover_s: float


# Physics-difficulty profiles, keyed by the PhysicsDifficulty option's level
# names (generous/comfortable/small = old casual/normal/expert physics; zero =
# the retired "insane" 0-margin profile).  This is the PHYSICS axis only —
# base Difficulty (tech slots / inventory / science / contract pacing / the
# GameplayDifficulty gates below) is separate.  Resolve a world's profile name
# with effective_physics_profile_name.
DIFFICULTY_PROFILES: dict[str, DifficultyProfile] = {
    # plane_change_fraction models a window-timing SKILL: matching an inclined
    # target's plane is mostly avoidable by departing at the node, but it's a
    # non-obvious optimization beginners don't do.  So generous pays ~full,
    # tighter levels are expected to time it (lower and lower tolerance up the
    # ladder).  Only ASCENT-to-encounter edges carry a plane change; descending
    # X→parent is always free (see _add_home_return_paths).
    "generous": DifficultyProfile(
        fixed_margin=200, percent_margin=0.30, plane_change_fraction=1.00,
        min_twr_atmo=1.5, min_twr_vac=1.2, ship_cd=0.0,
        precision_hover_s=45.0,
    ),
    "comfortable": DifficultyProfile(
        fixed_margin=100, percent_margin=0.15, plane_change_fraction=0.25,
        min_twr_atmo=1.5, min_twr_vac=1.2, ship_cd=0.1,
        precision_hover_s=30.0,
    ),
    "small": DifficultyProfile(
        fixed_margin=50, percent_margin=0.05, plane_change_fraction=0.05,
        min_twr_atmo=1.3, min_twr_vac=1.1, ship_cd=0.2,
        precision_hover_s=15.0,
    ),
    # No dv margin at all: every budget must close exactly.
    "zero": DifficultyProfile(
        fixed_margin=0, percent_margin=0.00, plane_change_fraction=0.00,
        min_twr_atmo=1.2, min_twr_vac=1.0, ship_cd=0.2,
        precision_hover_s=0.0,
    ),
}

# Horizontal translate speed (m/s) assumed while correcting residual landing
# error onto a precision target; precision_landing_dv's 2x term pays the
# accelerate + decelerate cost of that translation.
PRECISION_TRANSLATE_V = 30.0


@dataclass(frozen=True)
class GameplayDifficulty:
    """Player skill/equipment gates, resolved from the base Difficulty option
    (casual/normal/expert) — NOT the physics PhysicsDifficulty profile. These are
    orthogonal to dv margins: whether holding a precise attitude needs a reaction
    wheel or RCS (gimbal alone suffices on expert), whether an SRB-steered
    ascent needs RCS, and whether a docking approach needs an RCS translation
    kit (an expert player can dock on main-engine translation with wheels
    alone; docking always needs at least wheels). A player can run forgiving
    physics at an expert skill setting, so these must track base Difficulty,
    not the margins."""
    precise_pointing_needs_reaction_control: bool
    srb_needs_rcs: bool
    docking_needs_rcs: bool


# Base Difficulty.value → gameplay gates.  Raw-int keys (mirrors
# _AUTO_PHYSICS_BY_DIFFICULTY) so bodies.py stays free of an options import.
# casual/normal expect the assists; expert flies without them.
_GAMEPLAY_BY_DIFFICULTY: dict[int, GameplayDifficulty] = {
    0: GameplayDifficulty(precise_pointing_needs_reaction_control=True,  srb_needs_rcs=True,
                          docking_needs_rcs=True),   # casual
    1: GameplayDifficulty(precise_pointing_needs_reaction_control=True,  srb_needs_rcs=True,
                          docking_needs_rcs=True),   # normal
    2: GameplayDifficulty(precise_pointing_needs_reaction_control=False, srb_needs_rcs=False,
                          docking_needs_rcs=False),  # expert
}

# Strictest gates — the conservative default for callers that don't resolve a
# world's difficulty (test/generator/feasibility paths).  The real runtime
# (get_capability) and the sphere ladder pass the world's actual value;
# over-requiring here is Golden-Rule-safe.
CONSERVATIVE_GAMEPLAY = _GAMEPLAY_BY_DIFFICULTY[0]


def effective_gameplay_difficulty(options) -> GameplayDifficulty:
    """Gameplay gates for this world, from the base Difficulty option."""
    return _GAMEPLAY_BY_DIFFICULTY[options.difficulty.value]


# Base Difficulty.value → default physics profile when PhysicsDifficulty=auto.
# Raw-int keys (mirrors locations.py's difficulty tables) so bodies.py stays
# free of an options import (options.py imports bodies — the reverse would cycle).
_AUTO_PHYSICS_BY_DIFFICULTY: dict[int, str] = {
    0: "generous",     # casual
    1: "comfortable",  # normal
    2: "small",        # expert
}


def effective_physics_profile_name(options) -> str:
    """Physics profile key for this world.  Honors the PhysicsDifficulty option
    when set; otherwise derives from base Difficulty.  The returned string is a
    key of ``DIFFICULTY_PROFILES`` (generous/comfortable/small/zero)."""
    pd = getattr(options, "physics_difficulty", None)
    if pd is not None and pd.value != 0:   # 0 == PhysicsDifficulty.option_auto
        return pd.current_key              # generous/comfortable/small/zero
    return _AUTO_PHYSICS_BY_DIFFICULTY[options.difficulty.value]


def physics_profile_name_from_slot_data(slot_data: dict) -> str:
    """Diagnostic helper: physics profile key for a seed's ``slot_data``.

    Prefers an explicit ``physics_difficulty`` profile name when present;
    otherwise derives from the base ``difficulty`` index assuming
    PhysicsDifficulty=auto.  (Physics difficulty is generation-only, so it is
    not written to slot_data today — non-auto seeds degrade to their auto
    profile here.  Add the key to make diagnostics exact.)"""
    name = slot_data.get("physics_difficulty")
    if name in DIFFICULTY_PROFILES:
        return name
    return _AUTO_PHYSICS_BY_DIFFICULTY[slot_data.get("difficulty", 1)]


def effective_dv(base_dv: float, profile: DifficultyProfile,
                 plane_change_dv: float = 0.0) -> float:
    """Return the margin-adjusted dv budget for an edge."""
    pc = plane_change_dv * profile.plane_change_fraction
    return (base_dv + pc + profile.fixed_margin) * (1.0 + profile.percent_margin)


def precision_landing_dv(surface_gravity: float,
                         profile: DifficultyProfile) -> float:
    """Hover-translate surcharge for a precision landing (land NEAR a target).

    Gravity-scaled: correcting residual horizontal error costs gravity losses
    for the profile's budgeted hover time plus accel/decel of the translate
    speed — nearly free on Gilly, expensive on Tylo.  Exactly 0 when the
    profile budgets no hover time (the zero profile closes every budget
    exactly)."""
    if profile.precision_hover_s <= 0.0:
        return 0.0
    return (surface_gravity * profile.precision_hover_s
            + 2.0 * PRECISION_TRANSLATE_V)


# ---------------------------------------------------------------------------
# Body dataclasses
# ---------------------------------------------------------------------------

# Clearance kept above the tallest terrain peak when computing the lowest safe
# orbit radius (m).  Covers terrain-mesh variation and gives a margin so a
# circular orbit at the floor doesn't clip a peak on a bad pass.  Conservative
# (Golden Rule): raising it only pushes orbit targets higher.
_TERRAIN_ORBIT_CLEARANCE_M: float = 1000.0


@dataclass(frozen=True)
class BodyDeltaV:
    """Raw delta-v components from the planner graph.  None = not applicable."""
    dvGL: float                  # Ground <-> Low Orbit
    dvLE: Optional[float]        # Low Orbit <-> SOI edge (planets only)
    dvEI: Optional[float]        # SOI edge <-> Intercept (planets only)
    dvK: Optional[float]         # Intercept <-> Kerbin elliptical (planets)
    dvLI: Optional[float]        # Low Orbit <-> Intercept (direct, moons)
    dvPL: Optional[float]        # Intercept <-> Parent Low Orbit (Kerbin moons)
    dvPE: Optional[float]        # Intercept <-> Parent Elliptical (other moons)
    dvPlaneChange: float         # Worst-case plane change (0 if negligible)


@dataclass(frozen=True)
class Body:
    name: BodyName
    parent: Optional[BodyName]      # None for planets, parent name for moons
    surface_gravity: float          # m/s²
    has_atmosphere: bool
    atm_pressure_kpa: float         # sea-level, 0 for vacuum bodies
    atm_density_kg_m3: float        # sea-level air density, 0 for vacuum
    can_land: bool
    low_orbit_alt_km: float         # defines "low orbit" for location checks
    solar_distance_au: float        # real semi-major axis / Kerbin's (Kerbin = 1.0).
                                    # Heliocentric Hohmann radius (transfer/capture v∞),
                                    # ION/solar logic, and relay-tier opposition distance.
                                    # SMA averages over eccentricity — exact for near-circular
                                    # bodies; for eccentric ones (Moho 0.20, Eeloo 0.26, Dres
                                    # 0.145) it models a competently-timed window, not worst case.
    landing_leg_tier: int           # minimum leg tier required for landing
    power_requirement: str          # "solar" | "solar_marginal" | "rtg"
    eva_jetpack_twr: float          # precomputed: 0.5/(0.09375*surface_gravity)
    dv: BodyDeltaV
    radius_km: float                # body equatorial radius (KSP wiki value)
    # Sidereal rotation period (s) and SOI radius (km), KSP wiki values (same
    # provenance as radius_km). Drive the polar ascent penalty
    # (surface_rotation_velocity) and synchronous-orbit physics (stationary
    # feasibility + raise dv). A future runtime body dumper (planet-pack support)
    # replaces these. VERIFY the less-common bodies' exact values vs the wiki.
    rotation_period_s: float        # sidereal day, seconds
    soi_radius_km: float            # sphere-of-influence radius

    # --- Orbit around parent (moons only; 0 for planets) ---
    # Periapsis / apoapsis radius of this moon's orbit around its PARENT body
    # (km from the parent's centre), from KSP stock orbital elements
    # PeR=a(1-e), ApR=a(1+e). Used to carve collision-safe altitude bands for
    # rescue orbits around a planet (exclude each moon's full PeR..ApR range +
    # its SOI) and to size the home-moon->parent Hohmann for child->parent
    # rescues. VERIFY the less-common moons' exact values vs the wiki.
    parent_periapsis_km: float = 0.0
    parent_apoapsis_km: float = 0.0

    # --- Suborbital altitude ladder ---
    # Top of the home-body altitude-record milestone ladder (km).  For
    # atmospheric bodies this is the Kármán-equivalent (where the atmo
    # ends); for vacuum bodies it's ``low_orbit_alt_km - 5`` (a 5 km
    # buffer below low orbit).  Used by ``home_altitude_milestones`` to
    # generate the per-home suborbital location set.
    safe_altitude_km: float = 0.0
    # Atmospheric pressure scale height (m).  KSP atmospheres decay as
    # p(h) ≈ exp(-h / scale_height).  0 = vacuum body, no Isp weighting.
    atm_scale_height_m: float = 0.0
    # Highest terrain elevation above the datum radius (km), from the KSP wiki
    # "Highest point".  KSP bodies can be lumpy enough that the science/space
    # "low orbit" boundary sits BELOW a mountain peak — Gilly's low orbit is 6 km
    # but its peaks reach ~6.4 km.  Used by ``min_orbit_radius_m`` to keep contract
    # orbit targets (and rescue spawns) above the terrain; kept separate from
    # ``low_orbit_alt_km`` so science/capability "in space low" semantics don't
    # move.  0.0 = no data (no terrain floor applied; falls back to low orbit).
    max_terrain_km: float = 0.0
    # Elevation (m ASL) of this body's designated HOME launch site (the
    # AP_KSC_Sites pad the client places when this body is the starting
    # body).  0.0 = at/near sea level (no adjustment).  Consumed by
    # ``home_pad_ascent_dv`` — the HOME ascent starts from the pad, so an
    # elevated site skips the densest atmosphere slab.
    pad_altitude_m: float = 0.0
    # Destination-lander ascents assume a HIGHLANDS touchdown at roughly the
    # home pad's elevation band (operator decision, 2026-07-03): the landing
    # site is player-controlled and aiming for high ground is the universal
    # Eve strategy, so charging the full sea-level ascent would be a
    # false-negative machine.  When True, the trunk ascent edge uses
    # ``home_pad_ascent_dv()`` for destination landers too (else sea-level
    # ``dvGL``).
    #
    # DURABLE CAVEAT: a splashdown on such a body is ONE-WAY.  Logic assumes
    # the ascent starts from highlands, so no mission may ever assume an
    # ascent after an ocean landing — future biome/splashed-science work must
    # keep splashdown-reachable checks strictly non-return.
    assume_highlands_landing: bool = False

    # --- Science budget (for tech-tree access rules) ---
    has_ocean: bool = False         # body has splashable liquid surface
    num_biomes: int = 1             # distinct landed biomes
    num_splash_biomes: int = 0      # distinct ocean/splash biomes
    space_low_mult: float = 1.0     # InSpaceLow science multiplier
    space_high_mult: float = 1.0    # InSpaceHigh science multiplier
    fly_low_mult: float = 0.0       # FlyingLow multiplier (0 = no atmosphere)
    fly_high_mult: float = 0.0      # FlyingHigh multiplier (0 = no atmosphere)
    landed_mult: float = 0.0        # Landed multiplier (0 = can't land)
    splashed_mult: float = 0.0      # Splashed multiplier (0 = no ocean)
    # Stock KSP CelestialBodyScienceParams.RecoveryValue.  The client writes
    # ``recovery_mult * science_scalar(body, home)`` into the matching field
    # of ``CelestialBody.scienceValues`` at runtime.  NaN sentinel + the
    # ``__post_init__`` check below force every Body constructor to set
    # this explicitly — no silent default to "0 = unrecoverable" or to
    # Kerbin's value.
    recovery_mult: float = float("nan")

    def __post_init__(self) -> None:
        if math.isnan(self.recovery_mult):
            raise ValueError(
                f"Body({self.name}): recovery_mult is required (got NaN). "
                f"Add the stock KSP RecoveryValue to the Body() constructor."
            )

    # ------------------------------------------------------------------
    # Orbital constants
    # ------------------------------------------------------------------
    @property
    def gm(self) -> float:
        """Gravitational parameter (m³/s²) — ``surface_gravity·R²``."""
        r = self.radius_km * 1000.0
        return self.surface_gravity * r * r

    @property
    def lo_radius_m(self) -> float:
        """Low-orbit radius (m) from body centre."""
        return (self.radius_km + self.low_orbit_alt_km) * 1000.0

    # Vacuum-ascent gravity-loss allowance: surface→orbit from an airless
    # start costs ~10% over circular orbital velocity at a modelled TWR.
    # Used as the altitude-independent floor when scaling ``dvGL`` down for
    # an elevated home pad.
    _VAC_ASCENT_LOSS_FACTOR = 1.1

    def home_pad_ascent_dv(self) -> float:
        """Surface→low-orbit dv (m/s) from this body's designated HOME pad.

        ``dvGL`` is tabulated at sea level.  An elevated pad starts above
        the densest atmosphere, so the ATMOSPHERIC EXCESS — everything
        ``dvGL`` charges beyond the vacuum-ascent floor
        (``_VAC_ASCENT_LOSS_FACTOR × v_circ``) — shrinks with the pressure
        remaining above the pad.  The excess scales by **√(pressure
        fraction)**, not linearly: pure drag loss tracks the remaining
        column pressure, but much of the excess is drag-LIMITED gravity
        loss (terminal velocity ∝ 1/√ρ caps the climb rate), which decays
        as the square root.  √p errs on the conservative (higher-dv) side
        of community highland-ascent data — Eve's 6,140 m mesa pad yields
        ~6,415 m/s vs ~6,000-6,500 community figures for that band.

        Sea-level pads (``pad_altitude_m == 0``) and vacuum bodies return
        ``dvGL`` unchanged.
        """
        if (self.pad_altitude_m <= 0.0 or not self.has_atmosphere
                or self.atm_scale_height_m <= 0.0 or self.dv.dvGL <= 0.0):
            return self.dv.dvGL
        v_circ = math.sqrt(self.gm / self.lo_radius_m)
        vac_floor = self._VAC_ASCENT_LOSS_FACTOR * v_circ
        excess = max(0.0, self.dv.dvGL - vac_floor)
        p_frac = math.exp(-self.pad_altitude_m / self.atm_scale_height_m)
        return vac_floor + excess * math.sqrt(p_frac)

    @property
    def min_orbit_radius_m(self) -> float:
        """Lowest safe circular-orbit radius (m from centre) for an orbit a craft
        must actually fly: the greater of low orbit and a clearance above the
        tallest terrain peak.  For atmospheric bodies ``low_orbit_alt_km`` already
        sits above the Kármán line, so low orbit wins; for lumpy vacuum bodies
        (Gilly) the terrain floor wins.  This is the floor for contract orbit
        targets and rescue spawns — distinct from ``lo_radius_m`` (the science /
        capability 'in space low' boundary, which legitimately can sit below a
        peak)."""
        terrain_floor = (self.radius_km + self.max_terrain_km) * 1000.0 \
            + _TERRAIN_ORBIT_CLEARANCE_M
        return max(self.lo_radius_m, terrain_floor)

    @property
    def lo_circular_velocity(self) -> float:
        """Circular orbital velocity at low orbit (m/s)."""
        return math.sqrt(self.gm / self.lo_radius_m)

    @property
    def lo_escape_velocity(self) -> float:
        """Escape velocity at low orbit (m/s) — used in Oberth-combined burns."""
        return math.sqrt(2.0 * self.gm / self.lo_radius_m)

    # ------------------------------------------------------------------
    # Rotation / synchronous-orbit physics
    # ------------------------------------------------------------------
    @property
    def surface_rotation_velocity(self) -> float:
        """Equatorial surface rotation speed (m/s) — the eastward assist a
        prograde equatorial launch gets free and a polar launch forgoes.
        ``2πR / sidereal_period``; 0 if the period is unknown."""
        if self.rotation_period_s <= 0.0:
            return 0.0
        return 2.0 * math.pi * self.radius_km * 1000.0 / self.rotation_period_s

    @property
    def sync_orbit_radius_m(self) -> float:
        """Synchronous (stationary) orbit radius from body centre (m):
        ``(GM·T² / 4π²)^(1/3)``. inf if the rotation period is unknown."""
        if self.rotation_period_s <= 0.0:
            return float("inf")
        return (self.gm * self.rotation_period_s ** 2
                / (4.0 * math.pi * math.pi)) ** (1.0 / 3.0)

    @property
    def is_orbitable(self) -> bool:
        """True if a craft can establish orbit / fly by here — every body except
        the star (Kerbol). Gas giants (Jool) qualify: you orbit or fly by them
        even though you can't land. The star is not a mission destination, so it
        has no orbit/flyby/stationary contracts or locations."""
        return self.name != BodyName.KERBOL

    @property
    def has_stationary_orbit(self) -> bool:
        """True iff a synchronous orbit sits above the surface and inside the
        SOI. False for tidally-locked moons whose sync altitude is beyond their
        SOI (no geostationary orbit exists there)."""
        soi_m = self.soi_radius_km * 1000.0
        if soi_m <= 0.0:
            return False
        r_sync = self.sync_orbit_radius_m
        return self.radius_km * 1000.0 < r_sync < soi_m

    def hohmann_dv(self, r1_m: float, r2_m: float) -> float:
        """Hohmann two-burn delta-v (m/s) between two circular orbits at radii
        ``r1_m`` and ``r2_m`` (from this body's centre). Symmetric — works for a
        raise (r2 > r1) or a lower (r2 < r1). 0 if either radius is unknown /
        non-positive / infinite or the two coincide. Used for the random-rescue
        in-system transfer (e.g. a child→parent Hohmann between the home moon's
        orbital radius and the rescue orbit)."""
        mu = self.gm
        if (mu <= 0.0 or math.isinf(r1_m) or math.isinf(r2_m)
                or r1_m <= 0.0 or r2_m <= 0.0 or r1_m == r2_m):
            return 0.0
        a_t = (r1_m + r2_m) / 2.0
        v1 = math.sqrt(mu / r1_m)
        v2 = math.sqrt(mu / r2_m)
        vt1 = math.sqrt(mu * (2.0 / r1_m - 1.0 / a_t))
        vt2 = math.sqrt(mu * (2.0 / r2_m - 1.0 / a_t))
        return abs(vt1 - v1) + abs(v2 - vt2)

    def raise_dv(self, r_target_m: float) -> float:
        """Hohmann two-burn delta-v (m/s) to raise from low orbit to a circular
        orbit at ``r_target_m``. 0 if the target is at/below low orbit or unknown.
        Used for the stationary-orbit raise and the random-orbit apoapsis raise."""
        if math.isinf(r_target_m) or r_target_m <= self.lo_radius_m:
            return 0.0
        return self.hohmann_dv(self.lo_radius_m, r_target_m)

    @property
    def stationary_raise_dv(self) -> float:
        """Hohmann delta-v to raise from low orbit to synchronous orbit (m/s).
        0 if sync is at/below low orbit (very fast rotators) or unknown."""
        return self.raise_dv(self.sync_orbit_radius_m)

    def transfer_circular_to_ellipse_dv(
        self, r_start_m: float, r_pe_m: float, r_ap_m: float
    ) -> float:
        """Delta-v (m/s) to go from a circular orbit at ``r_start_m`` to a target
        orbit with periapsis ``r_pe_m`` and apoapsis ``r_ap_m`` (all radii from
        this body's centre).  The unifying primitive behind every orbit-reach
        cost: a two-burn Hohmann to the *near* side of the target (its periapsis if
        the target sits above ``r_start``, its apoapsis if below), then a single
        burn to set the *far* side.  If ``r_start`` lies between the target's
        periapsis and apoapsis, the target ellipse already crosses your circle, so
        only a velocity-match burn at ``r_start`` is charged.  0 if GM is unknown."""
        mu = self.gm
        if mu <= 0.0 or math.isinf(r_pe_m) or math.isinf(r_ap_m) or r_start_m <= 0.0:
            return 0.0
        r_pe_m, r_ap_m = min(r_pe_m, r_ap_m), max(r_pe_m, r_ap_m)
        a = (r_pe_m + r_ap_m) / 2.0
        if r_start_m <= r_pe_m:
            # Hohmann up to the periapsis, then burn there to raise the apoapsis.
            near = self.hohmann_dv(r_start_m, r_pe_m)
            far = math.sqrt(mu * (2.0 / r_pe_m - 1.0 / a)) - math.sqrt(mu / r_pe_m)
            return max(0.0, near + far)
        if r_start_m >= r_ap_m:
            # Hohmann down to the apoapsis, then burn there to lower the periapsis.
            near = self.hohmann_dv(r_start_m, r_ap_m)
            far = math.sqrt(mu / r_ap_m) - math.sqrt(mu * (2.0 / r_ap_m - 1.0 / a))
            return max(0.0, near + far)
        # Target ellipse already passes through r_start — just match velocity there.
        return abs(math.sqrt(mu * (2.0 / r_start_m - 1.0 / a)) - math.sqrt(mu / r_start_m))

    # ------------------------------------------------------------------
    # Suborbital ascent physics
    # ------------------------------------------------------------------
    def suborbital_dv_required(self, altitude_km: float, twr: float = 1.2) -> float:
        """Delta-v needed to apoapsis-touch ``altitude_km`` from this body's
        surface at constant ascent ``twr`` — the inverse of the straight-up,
        no-drag gravity-loss model ``h = dv²·(twr−1)/(2·g·twr·1000)``.  The
        sounding evaluator turns each altitude milestone into this dv target
        (swept over a few TWRs) and hands it to the shared ascent optimizer.

        Returns ``math.inf`` if TWR ≤ 1.  Delta-v required FALLS as TWR rises
        (less gravity drag), so evaluating at a floor TWR gives the widest bar;
        the sweep finds the lightest pad-fitting rocket across TWRs.
        """
        if twr <= 1.0:
            return math.inf
        if altitude_km <= 0.0:
            return 0.0
        return math.sqrt(
            2.0 * self.surface_gravity * twr * 1000.0 * altitude_km / (twr - 1.0)
        )


def _jetpack_twr(g: float) -> float:
    """Jetpack thrust ~0.5 kN, Kerbal mass ~0.09375 t."""
    return 0.5 / (0.09375 * g)


# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------

class EdgeType(Enum):
    ATMOSPHERIC_ASCENT      = auto()  # surface -> orbit, atmospheric body
    VACUUM_ASCENT           = auto()  # surface -> orbit, airless body
    PURE_VACUUM             = auto()  # orbital transfer, no TWR requirement
    PLANET_TRANSFER         = auto()  # interplanetary, plane change fraction applied
    VACUUM_LANDING          = auto()  # orbit -> surface, airless body
    ATMO_LANDING            = auto()  # orbit -> surface, staged aero + propulsive mix
    AEROBRAKE_CAPTURE       = auto()  # SOI capture using atmosphere (not landing)


class ReboardMode(Enum):
    """How a crewed surface sample must re-board the lander after EVA.

    A surface sample requires the kerbal to leave the craft and climb back
    in with the sample; jumping is uncontrollable (a low-g jump drifts the
    kerbal hundreds of metres from the craft), so some controlled aid is
    always required.  Which aids qualify depends on gravity, set at profile
    build time from the body's ``eva_jetpack_twr``.
    """
    NONE              = auto()  # no re-board required (not a crewed landing edge)
    LADDER_ONLY       = auto()  # high-g: the jetpack can't lift off; must climb a ladder
    LADDER_OR_JETPACK = auto()  # low-g: the jetpack lifts off, so it or a ladder works


# ---------------------------------------------------------------------------
# Mission edge
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionEdge:
    source: str
    destination: str
    edge_type: EdgeType
    base_dv: float                      # m/s, nominal delta-v
    body: BodyName                      # body name for physics lookups
    # Baked-in by ``MissionBuilder._edge`` at construction.  ``home`` is
    # fixed per world, so ``min_relay_tier(body, home)`` is a constant
    # for the life of the MissionBuilder.  The per-edge attribute lets
    # the capability hot loop ``flags.relay_tier < edge.relay_tier``
    # read directly instead of doing ``relay_table[edge.body]`` (or the
    # older ``BODY_BY_NAME[edge.body].name`` + lru-cache function call).
    relay_tier: int = 0
    plane_change_dv: float = 0.0        # worst-case plane change
    min_twr: float = 0.0                # 0.0 = no TWR requirement
    requires_throttleable: bool = False
    requires_attitude_control: bool = False  # gimbal OR rcs OR reaction_wheel
    needs_heat_shield: bool = False
    needs_landing_legs: bool = False
    # Crewed-sample re-board requirement, set at profile build time from the
    # body's eva_jetpack_twr (see ReboardMode).  NONE on every non-sample edge.
    reboard: ReboardMode = ReboardMode.NONE
    # ATMO_LANDING context: the speed the craft carries into the atmosphere
    # (low-orbit circular for a landing from orbit; padded escape speed for a
    # reentry from an interplanetary return).  Feeds the entry-bleed model.
    entry_speed: float = 0.0
    # True on the home-recovery descent (intercept -> home surface): the leg
    # where solar panels may already be destroyed by reentry heating and no
    # further power is needed.  Typed replacement for string-matching the
    # destination node name against "<home>_surface".
    is_recovery: bool = False
    # Landing must hit a designated site (surface rescue).  The dv cost is
    # difficulty-resolved at evaluation time (precision_landing_dv), so the
    # edge only carries the flag: added to the descent burn on vacuum
    # landings, forced as a terminal-divert burn on atmo landings (a
    # pure-chute mix cannot steer to a target).
    precision_landing: bool = False


# ---------------------------------------------------------------------------
# Body database
# ---------------------------------------------------------------------------

KERBIN = Body(
    name=BodyName.KERBIN, parent=None,
    max_terrain_km=6.7674,   # wiki: tallest peak 6767.4 m (inert: atmospheric, Kármán governs)
    rotation_period_s=21549.425, soi_radius_km=84159.286,
    surface_gravity=9.81, has_atmosphere=True,
    atm_pressure_kpa=101.325, atm_density_kg_m3=1.225,
    can_land=True, low_orbit_alt_km=80,
    solar_distance_au=1.0,
    landing_leg_tier=2,
    power_requirement="solar",
    eva_jetpack_twr=_jetpack_twr(9.81),
    dv=BodyDeltaV(
        dvGL=3400, dvLE=950, dvEI=None, dvK=None,
        dvLI=None, dvPL=None, dvPE=None, dvPlaneChange=0,
    ),
    radius_km=600,
    safe_altitude_km=70.0,  # Kármán line; atmosphere edge
    atm_scale_height_m=5000.0,
    # Biome counts from runtime BiomeMap + BiomeSplit dump (KSP.log
    # search "STOCK BiomeSplit"): 7 land_only + 4 mixed.  Mixed biomes
    # (Grasslands, Shores, Tundra, Water) support BOTH landed and
    # splashed science, so they count toward num_biomes AND
    # num_splash_biomes.  Same convention applies to all ocean bodies.
    has_ocean=True, num_biomes=11, num_splash_biomes=4,
    # Stock KSP CelestialBodyScienceParams — verified against runtime
    # dump in KSP.log (search "STOCK ScienceValues").  See bodies.py
    # comment block on home-relative science scaling for how these are
    # consumed.  Note splashed/flying are 1.0 even on bodies that lack
    # them — KSP uses 1.0 as the "n/a baseline" not 0.0; the
    # has_atmosphere / has_ocean flags gate science_budget's branches.
    space_low_mult=1.0, space_high_mult=1.5,
    fly_low_mult=0.7, fly_high_mult=0.9,
    landed_mult=0.3, splashed_mult=0.4,
    recovery_mult=1.0,
)

MUN = Body(
    name=BodyName.MUN, parent=BodyName.KERBIN,
    max_terrain_km=7.061,    # wiki: >7061 m near south pole
    rotation_period_s=138984.38, soi_radius_km=2429.559,   # tidally locked
    parent_periapsis_km=12000, parent_apoapsis_km=12000,   # around Kerbin: a=12000 e=0
    surface_gravity=1.63, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=14,
    solar_distance_au=1.0,
    landing_leg_tier=1,
    power_requirement="solar",
    eva_jetpack_twr=_jetpack_twr(1.63),
    dv=BodyDeltaV(
        dvGL=580, dvLE=None, dvEI=None, dvK=None,
        dvLI=310, dvPL=860, dvPE=None, dvPlaneChange=0,
    ),
    radius_km=200,
    safe_altitude_km=19.0,  # low orbit 14 + 5 buffer (vacuum)
    num_biomes=17,
    space_low_mult=3.0, space_high_mult=2.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=4.0, splashed_mult=1.0,
    recovery_mult=2.0,
)

MINMUS = Body(
    name=BodyName.MINMUS, parent=BodyName.KERBIN,
    max_terrain_km=5.7,      # wiki: highest areas over 5.7 km
    rotation_period_s=40400.0, soi_radius_km=2247.428,
    parent_periapsis_km=47000, parent_apoapsis_km=47000,   # around Kerbin: a=47000 e=0
    surface_gravity=0.491, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=10,
    solar_distance_au=1.0,
    landing_leg_tier=1,
    power_requirement="solar",
    eva_jetpack_twr=_jetpack_twr(0.491),
    dv=BodyDeltaV(
        dvGL=180, dvLE=None, dvEI=None, dvK=None,
        dvLI=160, dvPL=930, dvPE=None, dvPlaneChange=340,
    ),
    radius_km=60,
    safe_altitude_km=15.0,  # low orbit 10 + 5 buffer (vacuum)
    num_biomes=9,
    space_low_mult=4.0, space_high_mult=2.5,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=5.0, splashed_mult=1.0,
    recovery_mult=2.5,
)

MOHO = Body(
    name=BodyName.MOHO, parent=None,
    max_terrain_km=6.817,    # wiki: highest point 6817 m
    rotation_period_s=1210000.0, soi_radius_km=9646.663,
    surface_gravity=2.70, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=20,
    solar_distance_au=0.387,
    landing_leg_tier=1,
    power_requirement="solar",
    eva_jetpack_twr=_jetpack_twr(2.70),
    dv=BodyDeltaV(
        dvGL=870, dvLE=None, dvEI=None, dvK=760,
        dvLI=2410, dvPL=None, dvPE=None, dvPlaneChange=2520,
    ),
    radius_km=250,
    safe_altitude_km=25.0,  # low orbit 20 + 5 buffer (vacuum)
    num_biomes=12,
    space_low_mult=8.0, space_high_mult=7.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=10.0, splashed_mult=1.0,
    recovery_mult=7.0,
)

EVE = Body(
    name=BodyName.EVE, parent=None,
    max_terrain_km=7.526,    # wiki: peak 7526 m (inert: atmospheric, Kármán governs)
    rotation_period_s=80500.0, soi_radius_km=85109.365,
    surface_gravity=16.7, has_atmosphere=True,
    atm_pressure_kpa=506.625, atm_density_kg_m3=5.0,
    can_land=True, low_orbit_alt_km=90,
    solar_distance_au=0.72,
    landing_leg_tier=2,
    power_requirement="solar",
    eva_jetpack_twr=_jetpack_twr(16.7),
    dv=BodyDeltaV(
        # Sea-level ascent is ~11,500-12,000 m/s (community-verified: modern
        # dv maps and sea-level ascent reports).  The long-tabulated 8,000 was
        # implicitly a HIGHLANDS figure — keeping it as "sea level" while the
        # elevated-pad derivation also discounted altitude double-counted the
        # terrain benefit.  In-logic Eve ascents never pay this raw figure:
        # the home ascent launches from the mesa pad, and destination landers
        # assume a highlands touchdown (assume_highlands_landing) — both
        # resolve to ~9,000 via home_pad_ascent_dv().
        dvGL=12000, dvLE=1330, dvEI=80, dvK=90,
        dvLI=None, dvPL=None, dvPE=None, dvPlaneChange=430,
    ),
    radius_km=700,
    safe_altitude_km=90.0,  # Kármán line; atmosphere edge
    atm_scale_height_m=7000.0,
    # The AP home pad sits on the 25°S/-159° mesa at 6,140 m ASL
    # (AP_KSC_Sites/generate.py: "OFF-EQUATOR mesa: +536m vs equator") —
    # the recommender deliberately targets Eve's highest usable ground.
    pad_altitude_m=6140.0,
    assume_highlands_landing=True,
    # 4 land_only + 1 water_only + 8 mixed per BiomeSplit dump.
    # Two tiny biomes (Craters, Akatsuki Lake) weren't sampled by the
    # 5° grid; conservatively excluded.
    has_ocean=True, num_biomes=12, num_splash_biomes=9,
    space_low_mult=7.0, space_high_mult=5.0,
    fly_low_mult=6.0, fly_high_mult=6.0,
    landed_mult=8.0, splashed_mult=8.0,
    recovery_mult=5.0,
)

GILLY = Body(
    name=BodyName.GILLY, parent=BodyName.EVE,
    max_terrain_km=6.4,      # ~6400 m: not on wiki; operator playthrough + community measurement. AUDIT.
    rotation_period_s=28255.0, soi_radius_km=126.123,
    parent_periapsis_km=14175, parent_apoapsis_km=48825,   # around Eve: a=31500 e=0.55
    surface_gravity=0.049, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=6,
    solar_distance_au=0.72,
    landing_leg_tier=1,
    power_requirement="solar",
    eva_jetpack_twr=_jetpack_twr(0.049),
    dv=BodyDeltaV(
        dvGL=30, dvLE=None, dvEI=None, dvK=None,
        dvLI=410, dvPL=None, dvPE=60, dvPlaneChange=0,
    ),
    radius_km=13,
    safe_altitude_km=11.0,  # low orbit 6 + 5 buffer (tiny vacuum body)
    num_biomes=3,
    space_low_mult=8.0, space_high_mult=6.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=9.0, splashed_mult=1.0,
    recovery_mult=6.0,
)

DUNA = Body(
    name=BodyName.DUNA, parent=None,
    max_terrain_km=8.264,    # wiki: terrain up to 8264 m (inert: atmospheric, Kármán governs)
    rotation_period_s=65517.859, soi_radius_km=47921.949,
    surface_gravity=2.94, has_atmosphere=True,
    atm_pressure_kpa=6.755, atm_density_kg_m3=0.096,
    can_land=True, low_orbit_alt_km=50,
    solar_distance_au=1.52,
    landing_leg_tier=1,
    power_requirement="solar_marginal",
    eva_jetpack_twr=_jetpack_twr(2.94),
    dv=BodyDeltaV(
        dvGL=1450, dvLE=360, dvEI=250, dvK=130,
        dvLI=None, dvPL=None, dvPE=None, dvPlaneChange=10,
    ),
    radius_km=320,
    safe_altitude_km=50.0,  # Kármán line; atmosphere edge
    atm_scale_height_m=3000.0,
    num_biomes=14,
    space_low_mult=7.0, space_high_mult=5.0,
    fly_low_mult=5.0, fly_high_mult=5.0,
    landed_mult=8.0, splashed_mult=1.0,
    recovery_mult=5.0,
)

IKE = Body(
    name=BodyName.IKE, parent=BodyName.DUNA,
    max_terrain_km=12.75,    # wiki gives 12.75 km RANGE (max-min), used as a conservative upper bound. AUDIT.
    rotation_period_s=65517.862, soi_radius_km=1049.599,   # tidally locked
    parent_periapsis_km=3104, parent_apoapsis_km=3296,     # around Duna: a=3200 e=0.03
    surface_gravity=1.10, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=10,
    solar_distance_au=1.52,
    landing_leg_tier=1,
    power_requirement="solar_marginal",
    eva_jetpack_twr=_jetpack_twr(1.10),
    dv=BodyDeltaV(
        dvGL=390, dvLE=None, dvEI=None, dvK=None,
        dvLI=180, dvPL=None, dvPE=30, dvPlaneChange=0,
    ),
    radius_km=130,
    safe_altitude_km=15.0,  # low orbit 10 + 5 buffer (vacuum)
    num_biomes=8,
    space_low_mult=7.0, space_high_mult=5.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=8.0, splashed_mult=1.0,
    recovery_mult=5.0,
)

DRES = Body(
    name=BodyName.DRES, parent=None,
    max_terrain_km=5.7,      # wiki: highest points just under 5.7 km
    rotation_period_s=34800.0, soi_radius_km=32832.840,
    surface_gravity=1.13, has_atmosphere=False,  # wiki: 0.115 g; GM/R² = 1.128
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=25,
    solar_distance_au=3.003,
    landing_leg_tier=1,
    power_requirement="solar_marginal",
    eva_jetpack_twr=_jetpack_twr(1.13),
    dv=BodyDeltaV(
        dvGL=430, dvLE=None, dvEI=None, dvK=610,
        dvLI=1290, dvPL=None, dvPE=None, dvPlaneChange=1010,
    ),
    radius_km=138,
    safe_altitude_km=30.0,  # low orbit 25 + 5 buffer (vacuum)
    num_biomes=8,
    space_low_mult=7.0, space_high_mult=6.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=8.0, splashed_mult=1.0,
    recovery_mult=6.0,
)

JOOL = Body(
    name=BodyName.JOOL, parent=None,
    max_terrain_km=0.0,      # gas giant: no solid surface, cannot land (inert: atmospheric)
    rotation_period_s=36000.0, soi_radius_km=2455985.2,
    surface_gravity=7.85, has_atmosphere=True,
    atm_pressure_kpa=1519.88, atm_density_kg_m3=10.0,
    can_land=False, low_orbit_alt_km=210,
    solar_distance_au=5.057,
    landing_leg_tier=0,
    power_requirement="rtg",
    eva_jetpack_twr=_jetpack_twr(7.85),
    dv=BodyDeltaV(
        dvGL=14000, dvLE=2810, dvEI=160, dvK=980,
        dvLI=None, dvPL=None, dvPE=None, dvPlaneChange=270,
    ),
    radius_km=6000,
    safe_altitude_km=200.0,  # Kármán line; atmosphere edge (gas giant)
    atm_scale_height_m=10000.0,
    num_biomes=0,
    # KSP stock has landed=30 for Jool, but can_land=False above gates
    # the science_budget landed branch.  Storing the stock value so
    # client-side slot_data matches what KSP uses if a player somehow
    # triggers a landed experiment (no-op in practice).
    space_low_mult=7.0, space_high_mult=6.0,
    fly_low_mult=12.0, fly_high_mult=9.0,
    landed_mult=30.0, splashed_mult=1.0,
    recovery_mult=6.0,
)

LAYTHE = Body(
    name=BodyName.LAYTHE, parent=BodyName.JOOL,
    max_terrain_km=0.0,      # no wiki figure; inert anyway (atmospheric, Kármán governs)
    rotation_period_s=52980.879, soi_radius_km=3723.646,   # tidally locked
    parent_periapsis_km=27184, parent_apoapsis_km=27184,   # around Jool: a=27184 e=0
    surface_gravity=7.85, has_atmosphere=True,
    atm_pressure_kpa=60.795, atm_density_kg_m3=0.73,
    can_land=True, low_orbit_alt_km=60,
    solar_distance_au=5.057,
    landing_leg_tier=2,
    power_requirement="rtg",
    eva_jetpack_twr=_jetpack_twr(7.85),
    dv=BodyDeltaV(
        dvGL=2900, dvLE=None, dvEI=None, dvK=None,
        dvLI=1070, dvPL=None, dvPE=930, dvPlaneChange=0,
    ),
    radius_km=500,
    safe_altitude_km=50.0,  # Kármán line; atmosphere edge
    atm_scale_height_m=4000.0,
    # 2 land_only + 4 water_only + 3 mixed per BiomeSplit dump.
    has_ocean=True, num_biomes=5, num_splash_biomes=7,
    space_low_mult=9.0, space_high_mult=8.0,
    fly_low_mult=11.0, fly_high_mult=10.0,
    landed_mult=14.0, splashed_mult=12.0,
    recovery_mult=8.0,
)

VALL = Body(
    name=BodyName.VALL, parent=BodyName.JOOL,
    max_terrain_km=7.976,    # wiki: elevation up to 7976 m
    rotation_period_s=105962.09, soi_radius_km=2406.401,   # tidally locked
    parent_periapsis_km=43152, parent_apoapsis_km=43152,   # around Jool: a=43152 e=0
    surface_gravity=2.31, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=15,
    solar_distance_au=5.057,
    landing_leg_tier=1,
    power_requirement="rtg",
    eva_jetpack_twr=_jetpack_twr(2.31),
    dv=BodyDeltaV(
        dvGL=860, dvLE=None, dvEI=None, dvK=None,
        dvLI=910, dvPL=None, dvPE=620, dvPlaneChange=0,
    ),
    radius_km=300,
    safe_altitude_km=20.0,  # low orbit 15 + 5 buffer (vacuum)
    num_biomes=9,
    space_low_mult=9.0, space_high_mult=8.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=12.0, splashed_mult=1.0,
    recovery_mult=8.0,
)

TYLO = Body(
    name=BodyName.TYLO, parent=BodyName.JOOL,
    max_terrain_km=11.29,    # wiki: peaks >11290 m
    rotation_period_s=211926.36, soi_radius_km=10856.51,   # tidally locked
    parent_periapsis_km=68500, parent_apoapsis_km=68500,   # around Jool: a=68500 e=0
    surface_gravity=7.85, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=30,
    solar_distance_au=5.057,
    landing_leg_tier=2,
    power_requirement="rtg",
    eva_jetpack_twr=_jetpack_twr(7.85),
    dv=BodyDeltaV(
        dvGL=2270, dvLE=None, dvEI=None, dvK=None,
        dvLI=1100, dvPL=None, dvPE=400, dvPlaneChange=0,
    ),
    radius_km=600,
    safe_altitude_km=35.0,  # low orbit 30 + 5 buffer (vacuum)
    num_biomes=9,
    space_low_mult=10.0, space_high_mult=8.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=12.0, splashed_mult=1.0,
    recovery_mult=8.0,
)

BOP = Body(
    name=BodyName.BOP, parent=BodyName.JOOL,
    max_terrain_km=21.758,   # wiki: highest point 21758 m (tallest in the system)
    rotation_period_s=544507.43, soi_radius_km=1221.061,   # tidally locked
    parent_periapsis_km=98302, parent_apoapsis_km=158698,  # around Jool: a=128500 e=0.235
    surface_gravity=0.589, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=10,
    solar_distance_au=5.057,
    landing_leg_tier=1,
    power_requirement="rtg",
    eva_jetpack_twr=_jetpack_twr(0.589),
    dv=BodyDeltaV(
        dvGL=230, dvLE=None, dvEI=None, dvK=None,
        dvLI=900, dvPL=None, dvPE=220, dvPlaneChange=2440,
    ),
    radius_km=65,
    safe_altitude_km=15.0,  # low orbit 10 + 5 buffer (vacuum)
    num_biomes=5,
    space_low_mult=9.0, space_high_mult=8.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=12.0, splashed_mult=1.0,
    recovery_mult=8.0,
)

POL = Body(
    name=BodyName.POL, parent=BodyName.JOOL,
    max_terrain_km=4.0,      # wiki: cliffs up to ~4 km (approximate, low confidence). AUDIT.
    rotation_period_s=901902.62, soi_radius_km=1042.139,   # tidally locked
    parent_periapsis_km=149158, parent_apoapsis_km=210622, # around Jool: a=179890 e=0.17085
    surface_gravity=0.373, has_atmosphere=False,
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=6,
    solar_distance_au=5.057,
    landing_leg_tier=1,
    power_requirement="rtg",
    eva_jetpack_twr=_jetpack_twr(0.373),
    dv=BodyDeltaV(
        dvGL=130, dvLE=None, dvEI=None, dvK=None,
        dvLI=820, dvPL=None, dvPE=160, dvPlaneChange=700,
    ),
    radius_km=44,
    safe_altitude_km=11.0,  # low orbit 6 + 5 buffer (tiny vacuum body)
    num_biomes=4,
    space_low_mult=9.0, space_high_mult=8.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=12.0, splashed_mult=1.0,
    recovery_mult=8.0,
)

EELOO = Body(
    name=BodyName.EELOO, parent=None,
    max_terrain_km=3.9,      # wiki: highest points almost 3.9 km
    rotation_period_s=19460.0, soi_radius_km=119082.94,
    surface_gravity=1.69, has_atmosphere=False,  # wiki: 0.172 g; GM/R² = 1.687
    atm_pressure_kpa=0, atm_density_kg_m3=0,
    can_land=True, low_orbit_alt_km=10,
    solar_distance_au=6.626,
    landing_leg_tier=1,
    power_requirement="rtg",
    eva_jetpack_twr=_jetpack_twr(1.69),
    dv=BodyDeltaV(
        dvGL=620, dvLE=None, dvEI=None, dvK=1140,
        dvLI=1370, dvPL=None, dvPE=None, dvPlaneChange=1330,
    ),
    radius_km=210,
    safe_altitude_km=15.0,  # low orbit 10 + 5 buffer (vacuum)
    num_biomes=11,
    space_low_mult=12.0, space_high_mult=10.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=15.0, splashed_mult=1.0,
    recovery_mult=10.0,
)

KERBOL = Body(
    name=BodyName.KERBOL, parent=None,
    rotation_period_s=432000.0, soi_radius_km=float("inf"),
    surface_gravity=17.1, has_atmosphere=True,
    atm_pressure_kpa=16200.0, atm_density_kg_m3=350.0,
    can_land=False, low_orbit_alt_km=1000,
    solar_distance_au=0.0,
    landing_leg_tier=0,
    power_requirement="solar",
    eva_jetpack_twr=_jetpack_twr(17.1),
    dv=BodyDeltaV(
        dvGL=67000, dvLE=None, dvEI=None, dvK=6000,
        dvLI=13700, dvPL=None, dvPE=None, dvPlaneChange=0,
    ),
    radius_km=261600,
    # Kerbol can't be landed/launched-from; safe_altitude is meaningless
    # but a non-zero value keeps the home-altitude-milestone math safe
    # if anyone ever tries.  Atmosphere ends ~600 km on the wiki.
    safe_altitude_km=600.0,
    num_biomes=0,
    space_low_mult=11.0, space_high_mult=2.0,
    fly_low_mult=1.0, fly_high_mult=1.0,
    landed_mult=1.0, splashed_mult=1.0,
    recovery_mult=4.0,
)

# Authoritative list of all bodies
ALL_BODIES: list[Body] = [
    KERBIN, MUN, MINMUS,
    MOHO, EVE, GILLY,
    DUNA, IKE, DRES,
    JOOL, LAYTHE, VALL, TYLO, BOP, POL,
    EELOO, KERBOL,
]

BODY_BY_NAME: dict[BodyName, Body] = {b.name: b for b in ALL_BODIES}


# ---------------------------------------------------------------------------
# Interplanetary transfer dv (Body-aware wrapper around rocket_math.hohmann_v_inf)
# ---------------------------------------------------------------------------

def planet_transfer_dv(src: "Body", dst: "Body") -> tuple[float, float, float]:
    """Hohmann transfer dvs between two bodies, accounting for the Oberth
    effect at departure.

    Both bodies use their parent-system solar radius for the heliocentric
    Hohmann math (moons inherit their planet's ``solar_distance_au``).
    Kerbol is not a valid argument — it isn't a mission destination
    (``locations.get_body_events`` returns ``()`` for it) and the helper
    is never called with it.
    Returns ``(depart_lo_dv, arrive_v_inf, plane_change_dv)``:

    * ``depart_lo_dv`` is the **combined one-burn TLI** from the source
      body's low orbit to the destination intercept.  Computed as
      ``sqrt(v_escape² + v_inf_solar²) - v_circ`` at the source's low orbit,
      where ``v_inf_solar`` is the heliocentric Hohmann v∞ at the source.
      This is the dv a player actually spends at low orbit periapsis; the
      Oberth effect collapses the naive two-burn (escape + transfer)
      into a single, much cheaper burn.
    * ``arrive_v_inf`` is the residual heliocentric velocity at the
      destination intercept.  In our model we treat arrival as a passive
      coast into the destination SOI (the orbital insertion burn at the
      destination low orbit is the separate ``dvLE``/``dvLI`` capture edge,
      which already captures the Oberth side of arrival).  This value
      is currently informational; capability code uses the low orbit depart dv
      plus the destination's capture edge.
    * ``plane_change_dv`` is the worst-case inclination-change cost
      between the two bodies' orbital planes.  The fraction actually
      paid is governed by ``DifficultyProfile.plane_change_fraction``
      (see ``effective_dv``).
    """
    from .rocket_math import hohmann_v_inf, GM_SUN, KERBIN_SOLAR_RADIUS_M
    r1 = src.solar_distance_au * KERBIN_SOLAR_RADIUS_M
    r2 = dst.solar_distance_au * KERBIN_SOLAR_RADIUS_M
    v_inf_solar_src, v_inf_solar_dst = hohmann_v_inf(r1, r2, GM_SUN)
    # Oberth-combined departure burn from src's low orbit.  Burning at
    # low-orbit periapsis is far cheaper than escaping to SOI first and
    # then adding v∞ — the engine sees a high local velocity that converts
    # kinetic energy efficiently.
    v_esc = src.lo_escape_velocity
    v_circ = src.lo_circular_velocity
    depart_lo_dv = math.sqrt(v_esc * v_esc + v_inf_solar_src * v_inf_solar_src) - v_circ
    plane_change = max(src.dv.dvPlaneChange, dst.dv.dvPlaneChange)
    return depart_lo_dv, v_inf_solar_dst, plane_change


# ---------------------------------------------------------------------------
# Mission profile graph type aliases
# ---------------------------------------------------------------------------

MissionProfiles = dict[tuple[BodyName, MissionType], list[list[MissionEdge]]]


# ---------------------------------------------------------------------------
# Progressive Launch Pad: per-home cap scaling
# ---------------------------------------------------------------------------

# Kerbin baseline tonnage caps by collected count of "Progressive Launch
# Pad" (index = number of copies received).  Other homes scale these by
# their surface→low-orbit dv ratio.  Index 0 (no copies) is the starting
# cap; index N is "unlimited" so the player isn't blocked at the goal.
_PROGRESSIVE_LAUNCH_PAD_CAPS_KERBIN: tuple[float, ...] = (
    20.0, 100.0, 400.0, float("inf"))

# Reference Isp used in the rocket-equation scaling (m/s).  Roughly an
# LV-909 vacuum engine — a mid-tier optimization point that matches
# typical mission designs.  Higher Isp → smaller cap ratio swing across
# homes (because the mass penalty per Δdv is exponential in 1/Isp).
_PROGRESSIVE_LAUNCH_PAD_ISP_REF: float = 3000.0


def progressive_launch_pad_caps_for(home: BodyName) -> tuple[float, ...]:
    """Per-home tonnage caps for the Progressive Launch Pad item.

    Scales the Kerbin baseline by ``exp(Δ(pad ascent dv) / Isp_ref)``.
    This matches the rocket equation's ``payload * exp(Δdv / Isp_eff)``
    mass scaling so each cap tier opens up a similar "effective span of
    missions" regardless of home gravity well.  The scaling input is
    ``home_pad_ascent_dv()`` — the dv a pad launch actually pays — not raw
    sea-level ``dvGL``: for an elevated home pad (Eve's mesa) the raw
    figure would inflate the caps past what any home launch needs
    (12,000 → 17.6× Kerbin vs the pad's ~9,000 → 6.5×).  Identical for
    sea-level pads, where the two values coincide.

    The infinity entry stays as infinity — that final cap removes the
    constraint entirely so heavy goal missions stay feasible after the
    player collects all copies.
    """
    import math
    kerbin_dv = BODY_BY_NAME[BodyName.KERBIN].home_pad_ascent_dv() or 3400.0
    home_dv = BODY_BY_NAME[home].home_pad_ascent_dv() or kerbin_dv
    ratio = math.exp((home_dv - kerbin_dv) / _PROGRESSIVE_LAUNCH_PAD_ISP_REF)
    return tuple(
        cap * ratio if cap != float("inf") else cap
        for cap in _PROGRESSIVE_LAUNCH_PAD_CAPS_KERBIN
    )


# ---------------------------------------------------------------------------
# Safe target orbits (shared by RANDOM_ORBIT and KERBAL_RESCUE contracts)
# ---------------------------------------------------------------------------

# Clearance kept below/above each moon's SOI when carving a safe band, and below
# the body's own SOI (m).  Conservative buffer so an inclined/eccentric moon
# never clips the orbit.
_MOON_BAND_MARGIN_M: float = 500_000.0


def safe_orbit_bands(body: "Body", bodies) -> list[tuple[float, float]]:
    """Moon-collision-safe radial bands ``[lo, hi]`` (m from ``body``'s centre)
    that a contract target orbit may occupy.

    The floor is ``body.min_orbit_radius_m`` — above the tallest terrain peak and
    (for atmospheric bodies) the Kármán line.  For a body WITH moons, each moon's
    full ``PeR..ApR`` range (plus its SOI and a margin) is excluded; the surviving
    gaps between/below the moons are returned, capped at the outermost moon's
    exclusion top (no absurd near-SOI band).  Moonless bodies get one band from
    the floor up to ``0.7·SOI`` — wide enough for genuinely eccentric orbits.

    Slivers narrower than 1 km are dropped.  May return ``[]`` (no safe band — a
    dense planet-pack edge case); callers fall back to a circular orbit at the
    floor.  Pure function of the body geometry, so deterministic."""
    floor = body.min_orbit_radius_m
    soi_m = body.soi_radius_km * 1000.0
    moons = [m for m in bodies if m.parent == body.name]
    if moons:
        excl = sorted(
            (m.parent_periapsis_km * 1000.0 - m.soi_radius_km * 1000.0
             - _MOON_BAND_MARGIN_M,
             m.parent_apoapsis_km * 1000.0 + m.soi_radius_km * 1000.0
             + _MOON_BAND_MARGIN_M)
            for m in moons)
        merged: list[tuple[float, float]] = []
        for lo, hi in excl:
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        ceiling = merged[-1][1]
        if soi_m > 0.0:
            ceiling = min(ceiling, soi_m - _MOON_BAND_MARGIN_M)
        gaps: list[tuple[float, float]] = []
        cur = floor
        for lo, hi in merged:
            if lo > cur:
                gaps.append((cur, min(lo, ceiling)))
            cur = max(cur, hi)
            if cur >= ceiling:
                break
        if cur < ceiling:
            gaps.append((cur, ceiling))
    else:
        # Moonless: one band up to 0.7·SOI so highly eccentric orbits are allowed
        # (the dv to reach them is charged correctly per regime, so feasibility —
        # not an arbitrary altitude cap — limits how wild they get).
        cap = 0.7 * soi_m if soi_m > 0.0 else 3.0 * floor
        gaps = [(floor, max(cap, floor * 1.05))]
    return [(lo, hi) for lo, hi in gaps if hi - lo > 1000.0]


def _weighted_gap_pick(
    gaps: list[tuple[float, float]], rng
) -> tuple[float, float]:
    """Pick a band from ``gaps``, weighted by width (a wide gap between two
    distant moons is more likely than a narrow sliver)."""
    total = sum(hi - lo for lo, hi in gaps)
    pick = rng.uniform(0.0, total)
    acc = 0.0
    for lo, hi in gaps:
        acc += hi - lo
        if pick <= acc:
            return (lo, hi)
    return gaps[-1]


@dataclass(frozen=True)
class RandomOrbitParams:
    """A seeded target orbit for a RANDOM_ORBIT contract — the client renders it
    and the player matches it within the deviation window.  Periapsis and apoapsis
    are placed anywhere inside a single moon-safe band (see ``safe_orbit_bands``),
    so the orbit can be a tame circle or a wild ellipse depending on the band's
    width, but it never crosses a moon's path.  Inclination varies 0-90°.  The dv
    to reach the orbit is modelled per arrival regime (home / capture / in-system
    moon transfer) in ``ContractTypeDef.transform_mission`` via ``orbit_reach_dv``.

    ``lan_deg`` (longitude of ascending node) and ``arg_pe_deg`` (argument of
    periapsis) are the orbit's spatial *orientation*.  They are randomized purely
    for visual variety — reaching any LAN is a launch-window / arrival-timing
    choice and the argument of periapsis is set by where you burn, so neither
    costs delta-v and neither affects ``orbit_reach_dv`` (which depends only on the
    periapsis/apoapsis radii and the inclination magnitude)."""
    inclination_deg: float
    sma_m: float
    eccentricity: float
    lan_deg: float = 0.0
    arg_pe_deg: float = 0.0

    @property
    def apoapsis_m(self) -> float:
        return self.sma_m * (1.0 + self.eccentricity)

    @property
    def periapsis_m(self) -> float:
        return self.sma_m * (1.0 - self.eccentricity)


def generate_random_orbit_params(rng, bodies) -> dict[BodyName, RandomOrbitParams]:
    """Seeded moon-safe target orbit per orbitable body.  Picks a width-weighted
    safe band, then places periapsis and apoapsis anywhere inside it (full
    eccentricity range — a narrow band yields a near-circle, a wide one a steep
    ellipse) with inclination 0-90° and a fully random spatial orientation
    (longitude of ascending node + argument of periapsis, 0-360°, free variety).
    Deterministic for a given ``rng`` so UT regen restores the same orbits from
    slot_data instead of re-rolling."""
    out: dict[BodyName, RandomOrbitParams] = {}
    for b in bodies:
        if not b.is_orbitable:
            continue
        gaps = safe_orbit_bands(b, bodies)
        incl = rng.uniform(0.0, 90.0)
        lan = rng.uniform(0.0, 360.0)
        arg_pe = rng.uniform(0.0, 360.0)
        if not gaps:
            out[b.name] = RandomOrbitParams(
                inclination_deg=incl, sma_m=b.min_orbit_radius_m, eccentricity=0.0,
                lan_deg=lan, arg_pe_deg=arg_pe)
            continue
        lo, hi = _weighted_gap_pick(gaps, rng)
        r1, r2 = rng.uniform(lo, hi), rng.uniform(lo, hi)
        r_pe, r_ap = (r1, r2) if r1 <= r2 else (r2, r1)
        sma = (r_pe + r_ap) / 2.0
        ecc = (r_ap - r_pe) / (r_ap + r_pe) if (r_ap + r_pe) > 0.0 else 0.0
        out[b.name] = RandomOrbitParams(
            inclination_deg=incl, sma_m=sma, eccentricity=ecc,
            lan_deg=lan, arg_pe_deg=arg_pe)
    return out


def generate_rescue_orbit_params(rng, bodies) -> dict[BodyName, float]:
    """Seeded collision-safe circular rescue-orbit radius (m from the body's
    centre) per orbitable body.  The client spawns the stranded Kerbal here and
    the capability model charges the dv to reach it, so the two agree.  Reuses the
    shared ``safe_orbit_bands`` carve (terrain/atmosphere floor + moon exclusion),
    picking a single width-weighted circular radius.  Deterministic for a given
    ``rng`` so UT regen restores the same orbits from slot_data."""
    out: dict[BodyName, float] = {}
    for b in bodies:
        if not b.is_orbitable:
            continue
        gaps = safe_orbit_bands(b, bodies)
        if not gaps:
            out[b.name] = b.min_orbit_radius_m   # no safe band (planet-pack)
            continue
        lo, hi = _weighted_gap_pick(gaps, rng)
        out[b.name] = rng.uniform(lo, hi)
    return out


# Seeded surface-rescue site latitude bound (degrees).  The floor keeps a
# nonzero plane-change term on every instance (no degenerate equator-only
# contracts); the ceiling keeps worst-case ascent plane reconciliation
# (2*v_LO*sin(lat/2)) within reach of the feasibility filter on heavy bodies.
_SURFACE_RESCUE_LAT_MIN_DEG = 5.0
_SURFACE_RESCUE_LAT_MAX_DEG = 45.0


def generate_surface_rescue_site_lats(rng, bodies) -> dict[BodyName, float]:
    """Seeded surface-rescue site latitude BOUND (degrees, symmetric ±band) per
    landable body.  The capability model charges the ascent plane change for
    this latitude and the client places the stranded Kerbal anywhere with
    ``|lat| <= bound`` (longitude is physics-free), so every placeable site
    costs no more than what logic charged.  Deterministic for a given ``rng``
    so UT regen restores the same values from slot_data."""
    out: dict[BodyName, float] = {}
    for b in bodies:
        if not b.can_land:
            continue
        out[b.name] = rng.uniform(_SURFACE_RESCUE_LAT_MIN_DEG,
                                  _SURFACE_RESCUE_LAT_MAX_DEG)
    return out


# Tourists per TOURISM contract (seat count the vessel must carry + return).
# One tourist per contract: one seeded flight objective, not a pair.
TOURISM_CREW = 1

# First-name pool for seeded tourist names. The client resolves these against
# the roster and falls back to a unique name on collision (it persists the real
# name), so these are display hints — but kept deterministic for UT regen.
_TOURIST_NAMES: tuple[str, ...] = (
    "Lodan", "Gwenzon", "Desnie", "Sherzor", "Adelie", "Mortimer",
    "Ludred", "Nedzer", "Obrin", "Sigsby", "Thomsen", "Elindy",
)


@dataclass(frozen=True)
class TouristSpec:
    """One tourist on a TOURISM contract: a named passenger to deliver to a
    destination situation and recover.  ``entry`` is the ``Achievement`` their
    flight log must record at the destination; every tourism objective is an
    orbit-and-return, so it is always ``Achievement.ORBIT``
    (``Achievement.SUBORBITAL`` is reserved for a future pre-orbit tourism
    option).  The capability model prices tourism as reaching the body's ORBIT and
    returning, so ``entry`` is client flavour only."""
    name: str
    female: bool
    entry: Achievement


def generate_tourist_manifests(
    rng, bodies
) -> dict[BodyName, tuple[TouristSpec, ...]]:
    """Seeded TOURISM tourist manifest per orbitable body — ``TOURISM_CREW``
    tourist(s) with distinct seeded names/genders, each an orbit-and-return
    objective.  Deterministic for a given ``rng`` so UT regen restores the same
    manifests."""
    out: dict[BodyName, tuple[TouristSpec, ...]] = {}
    for b in bodies:
        if not b.is_orbitable:
            continue
        names = rng.sample(_TOURIST_NAMES, TOURISM_CREW)
        out[b.name] = tuple(
            TouristSpec(f"{nm} Kerman", rng.random() < 0.5, Achievement.ORBIT)
            for nm in names)
    return out


def generate_survey_site_lats(rng, bodies) -> dict[BodyName, float]:
    """Seeded SURFACE_SURVEY waypoint latitude BOUND (degrees, symmetric ±band)
    per landable body — INCLUDING home (a home surface survey is valid early
    content, unlike surface rescue which excludes home).  Same lat band and
    determinism as ``generate_surface_rescue_site_lats``; the capability model
    charges reaching this latitude (home ascent inclination) and the client picks
    the water-free waypoint within ``|lat| <= bound``."""
    out: dict[BodyName, float] = {}
    for b in bodies:
        if not b.can_land:
            continue
        out[b.name] = rng.uniform(_SURFACE_RESCUE_LAT_MIN_DEG,
                                  _SURFACE_RESCUE_LAT_MAX_DEG)
    return out


# Aerobrake-capture circularisation residual (m/s) — the dv left after an
# atmospheric SOI capture drops you into low orbit.  Shared with the
# AEROBRAKE_CAPTURE edge in ``_build_graph`` so the capture cost the base profile
# charges and the cost ``orbit_reach_dv`` discounts against never drift.
_AEROBRAKE_CAPTURE_RESIDUAL_DV: float = 100.0


def _interplanetary_arrival_v_inf(home_body: BodyName, target_body: BodyName):
    """Heliocentric Hohmann arrival v∞ (m/s) at a PLANET target when the transfer
    crosses planetary systems, else ``None``.  Prices a direct propulsive capture
    straight into a specific orbit.  Returns ``None`` for moon targets (their
    capture v∞ is intra-system, not the planet's heliocentric value) and for
    same-system transfers, so the caller falls back to the conservative
    aerobrake-then-raise cost."""
    tgt = BODY_BY_NAME[target_body]
    if tgt.parent is not None:
        return None
    root = BODY_BY_NAME[home_body]
    while root.parent is not None:
        root = BODY_BY_NAME[root.parent]
    if root.name == target_body:
        return None
    return planet_transfer_dv(root, tgt)[1]


def orbit_reach_dv(
    home_body: BodyName, target_body: BodyName,
    r_pe_m: float, r_ap_m: float, *, round_trip: bool,
) -> float:
    """Radial delta-v (m/s) to reach a target orbit (periapsis ``r_pe_m``,
    apoapsis ``r_ap_m``, radii from the target's centre) BEYOND what the base
    mission profile to the target's low orbit already charges.  Inclination is
    *not* included here — it is a launch-from-home cost only (off home the plane is
    set for free at capture/transfer) and is added by ``transform_mission``.

    Dispatches on the arrival regime (the three the base graph conflates):

    * **A — orbit around home** (``target == home``): the base ascent reaches home
      low orbit; raise from there to the target orbit.
    * **C — moon home → its parent's system** (``target == home.parent``): the base
      escapes the home moon into the parent frame at the moon's orbital radius
      (and then mis-charges the descent as free — see bug 099), so charge the full
      in-well transfer from the moon's orbital radius to the target orbit.
    * **B — capture from outside the target's SOI** (everything else, e.g. Kerbin→
      Jool or Kerbin→Mun): the base reaches the target's low orbit (aerobrake for
      atmospheric planets, propulsive otherwise).  A propulsive capture into a
      *higher* vacuum orbit costs no more than the low capture the base already
      charges, so vacuum one-way orbits need nothing extra.  At an **atmospheric**
      target the cheap aerobrake only reaches low orbit, so reaching the orbit is
      the cheaper of (aerobrake to low, then raise) and (capture straight into the
      orbit) — the latter priced from the interplanetary arrival v∞ so a steep
      orbit isn't over-charged by forcing the low-orbit detour.  A **round trip**
      (rescue) is propulsive both ways from low orbit regardless of atmosphere, so
      it doubles the low→orbit raise.

    Round trips double the radial cost (out and back).
    """
    tgt = BODY_BY_NAME[target_body]
    if target_body == home_body:
        one_way = tgt.transfer_circular_to_ellipse_dv(tgt.lo_radius_m, r_pe_m, r_ap_m)
        return 2.0 * one_way if round_trip else one_way
    home = BODY_BY_NAME[home_body]
    if home.parent == target_body:
        r_moon = home.parent_periapsis_km * 1000.0
        one_way = tgt.transfer_circular_to_ellipse_dv(r_moon, r_pe_m, r_ap_m)
        return 2.0 * one_way if round_trip else one_way
    # Case B — capture from outside the target SOI.
    aero_then_raise = tgt.transfer_circular_to_ellipse_dv(tgt.lo_radius_m, r_pe_m, r_ap_m)
    if round_trip:
        # Rescue: already captured at low orbit, must propulsively raise to the
        # stranded orbit and lower back — both ways, regardless of atmosphere.
        return 2.0 * aero_then_raise
    if not tgt.has_atmosphere:
        return 0.0
    v_inf = _interplanetary_arrival_v_inf(home_body, target_body)
    if v_inf is None:
        return aero_then_raise   # atmo moon / same system: conservative fallback
    mu = tgt.gm
    a = (r_pe_m + r_ap_m) / 2.0
    direct_capture = (math.sqrt(v_inf * v_inf + 2.0 * mu / r_pe_m)
                      - math.sqrt(mu * (2.0 / r_pe_m - 1.0 / a)))
    return max(0.0, min(aero_then_raise,
                        direct_capture - _AEROBRAKE_CAPTURE_RESIDUAL_DV))


# ---------------------------------------------------------------------------
# MissionBuilder
# ---------------------------------------------------------------------------

class MissionBuilder:
    """Owns the mission graph for a given home body.

    The graph is a weighted DAG of ``MissionEdge`` objects between body
    nodes (``"{body}_surface"`` / ``"{body}_low_orbit"`` / ``"{body}_soi"``
    / ``"{body}_intercept"``).  Two edge sets are maintained:

    * ``_outbound`` — explore-out from ``home.surface``.  Includes captures
      into every body's SOI, both propulsive and aerobrake variants where
      applicable.
    * ``_return`` — restricted: paths must terminate at ``home.surface``
      and may not capture into any non-home SOI on the way back.  Edges
      cover ascents, escapes, the ``planet.SOI → home.intercept``
      interplanetary return burn, the home reentry, and combined
      ``moon.low orbit → home.intercept`` shortcuts for moons of the home body.

    For each ``(target_body, mission_type)`` the builder enumerates simple
    paths through these graphs.  Edges that have a *scheme* tag
    (``"aero"`` / ``"prop"``) are alternatives at the same decision point;
    paths that mix incompatible scheme tags are dropped, so each kept
    profile uses a consistent scheme (aerobrake-capture pairs with aero-
    landing, etc.).

    Interplanetary transfer dvs come from ``planet_transfer_dv`` (solar-
    frame Hohmann).  Moon-system transfers reuse the per-body ``dvLI`` /
    ``dvPL`` / ``dvPE`` values.  Plane change is carried on transfer
    edges as ``plane_change_dv`` and discounted by the difficulty
    profile's ``plane_change_fraction`` in ``effective_dv``.
    """

    # EdgeType shorthand — kept class-level so the long edge-construction
    # methods stay readable without polluting the module namespace.
    _AT  = EdgeType.ATMOSPHERIC_ASCENT
    _VA  = EdgeType.VACUUM_ASCENT
    _PV  = EdgeType.PURE_VACUUM
    _PT  = EdgeType.PLANET_TRANSFER
    _VL  = EdgeType.VACUUM_LANDING
    _AL  = EdgeType.ATMO_LANDING
    _AB  = EdgeType.AEROBRAKE_CAPTURE

    # Cap on profile alternatives kept per ``(body, mission_type)``.  Two is
    # enough to cover the aero/prop CAPTURE scheme choice at an atmospheric
    # planet (landing itself is a single edge whose chute/burn mix is decided
    # at capability time) — the path enumerator can produce more (e.g.
    # moon-SOI vs combined-escape routing variants) but anything past the two
    # cheapest is dominated by them and just inflates capability-evaluation
    # work in the sphere ladder's hot loop.
    _MAX_PROFILE_ALTS = 2

    # Rescue rendezvous/phasing margin (m/s) — the cost of matching and closing
    # on the stranded craft's orbit, baked into the RESCUE profile at the target
    # body. Modest (a coplanar same-orbit rendezvous is cheap) and conservative.
    _RESCUE_RENDEZVOUS_DV = 200.0

    def __init__(self, home: BodyName):
        self.home: BodyName = home
        # Player skill/equipment gates (reaction-wheel/RCS/nav assists) for this
        # world, resolved from the base Difficulty + HomeSystem options. Populated
        # by the world in generate_early (same lifecycle as random_orbit_params
        # below); the conservative default stands for test/CLI builders that don't
        # set it. Carried here so the sphere ladder's _evaluate and the capability
        # evaluators reach it without threading a param through the bumper.
        self.gameplay: GameplayDifficulty = CONSERVATIVE_GAMEPLAY
        # Per-body seeded target orbits for RANDOM_ORBIT contracts. Populated by
        # the world in generate_early (fresh or UT-restored); empty until then.
        # transform_mission reads these to model the home-orbit extra cost, so
        # the sphere ladder (which calls spec.mission_transform(mission_builder))
        # sees the same cost without any per-contract param threading.
        self.random_orbit_params: dict[BodyName, "RandomOrbitParams"] = {}
        # Per-body seeded collision-safe rescue-orbit radius (m from centre) for
        # KERBAL_RESCUE contracts. Same lifecycle as random_orbit_params:
        # populated by the world (fresh or UT-restored), read by transform_mission
        # to charge the dv to reach the orbit and by build_parameters to tell the
        # client where to spawn the stranded Kerbal.
        self.rescue_orbit_params: dict[BodyName, float] = {}
        # Per-body seeded surface-rescue site latitude bound (degrees) for
        # SURFACE_RESCUE contracts. Same lifecycle as rescue_orbit_params:
        # read by transform_mission to charge the ascent plane change for the
        # site latitude and by build_parameters to bound the client's spawn.
        self.surface_rescue_site_lats: dict[BodyName, float] = {}
        # Per-body seeded SURFACE_SURVEY waypoint latitude bound (degrees),
        # including home. Same lifecycle: read by transform_mission to charge the
        # home ascent inclination for the site latitude, and by build_parameters
        # to bound the client's waypoint pick.
        self.survey_site_lats: dict[BodyName, float] = {}
        # Per-body seeded tourist manifest for TOURISM. Same lifecycle; read by
        # build_parameters to emit one tourist objective per passenger.
        self.tourist_manifests: dict[BodyName, tuple["TouristSpec", ...]] = {}
        # Per-seed bound lifter table (pad -> home low orbit), or None to use
        # raw physics for the home-ascent build.  Populated by the world in
        # generate_early (same lifecycle as random_orbit_params); read only by
        # the sphere-ladder evaluator path (``use_lifter_table=True``), never
        # by the post_fill cross-check / spoiler / feasibility generator, which
        # stay on raw physics.  ``Optional[BoundLifterTable]`` — untyped here to
        # avoid importing lifter_binding at module import.
        self.lifter_table = None
        # Precomputed relay-tier table keyed by destination BodyName.
        # Built before edge construction so ``_edge`` can stamp the
        # value onto every ``MissionEdge.relay_tier`` directly — the
        # capability hot loop then reads a struct field instead of
        # doing any lookup.  Public so callers (capability_format etc.)
        # can read tiers without re-computing.
        self.relay_tier_by_body: dict[BodyName, int] = relay_tier_table_for(home)
        # Per-home Progressive Launch Pad tonnage caps.  Scales with the
        # home body's surface→low-orbit dv so the same number of copies
        # opens up roughly the same span of mission difficulty across
        # homes.  See ``progressive_launch_pad_caps_for``.
        self.launch_pad_caps: tuple[float, ...] = progressive_launch_pad_caps_for(home)
        # Per-node edge lists, tagged with ("", "aero", or "prop"):
        self._outbound: dict[str, list[tuple[str, MissionEdge]]] = defaultdict(list)
        self._return: dict[str, list[tuple[str, MissionEdge]]] = defaultdict(list)
        self._build_graph()
        self._profiles: MissionProfiles = {}
        self._build_profiles()
        self._validate()
        # Missions the world has declared unachievable: curated edge-bans (e.g.
        # Eve ascent) ∪ per-home dv-infeasible (offline table).  Empty by default
        # — the world sets it at generation time (the offline table generator
        # keeps it empty so it measures RAW maximal capability).  The capability
        # assessment treats these as access=False, so contracts / goals / location
        # rules that route through capability inherit the ban without their own
        # check.  See ``world.py`` (``_BANNED_EDGES`` / ``unachievable_missions``).
        self.unachievable: frozenset[tuple[BodyName, MissionType]] = frozenset()

    # ------------------------------------------------------------------
    # Public lookup API
    # ------------------------------------------------------------------

    @property
    def home_body(self) -> "Body":
        """The resolved ``Body`` object for the home body name.

        Convenience for callers that need physics properties (gravity,
        atmosphere flags) rather than just the ``BodyName`` enum value.
        """
        return BODY_BY_NAME[self.home]

    def profiles_for(
        self, body: BodyName, mission_type: MissionType
    ) -> list[list[MissionEdge]]:
        """Return profile alternatives for ``(body, mission_type)`` or ``[]``."""
        return self._profiles.get((body, mission_type), [])

    def has_profile(self, body: BodyName, mission_type: MissionType) -> bool:
        return (body, mission_type) in self._profiles

    def is_achievable(self, body: BodyName, mission_type: MissionType) -> bool:
        """False iff ``(body, mission_type)`` is in the world-declared
        ``unachievable`` set (curated edge-ban ∪ dv-infeasible).  Capability and
        every reachability consumer route through this so a ban can't be missed.
        """
        return (body, mission_type) not in self.unachievable

    def missions_using_edges(
        self, banned_edges: "frozenset[tuple[BodyName, EdgeType]]"
    ) -> frozenset[tuple[BodyName, MissionType]]:
        """Graph-derive the missions banned by an edge set: a ``(body,
        mission_type)`` is banned iff it HAS profiles and EVERY profile
        alternative traverses a banned ``(edge.body, edge.edge_type)``.

        This is the curated-ban expansion: ban one edge (e.g. Eve ascent) and
        every mission with no clean alternative around it is banned — the
        ``downstream`` closure, computed from the graph rather than hand-listed.
        A mission with no profiles is NOT banned (empty profile = trivially
        achievable, e.g. Kerbin launchpad sample return).
        """
        if not banned_edges:
            return frozenset()
        banned: set[tuple[BodyName, MissionType]] = set()
        for (body, mt), profiles in self._profiles.items():
            if profiles and all(
                any((e.body, e.edge_type) in banned_edges for e in profile)
                for profile in profiles
            ):
                banned.add((body, mt))
        return frozenset(banned)

    def all_keys(self):
        return self._profiles.keys()

    def all_profiles(self) -> MissionProfiles:
        """Return the underlying ``(body, mission_type) → profiles`` dict.

        Returned dict is the builder's live state — callers must not mutate it.
        """
        return self._profiles

    # ------------------------------------------------------------------
    # Contract mission-profile builders. Contracts inject extra maneuvers
    # into a base profile via ``ContractTypeDef.transform_mission``; these
    # keep the node-name + edge-type conventions owned by the graph builder.
    # Each returns a NEW edge list (the input is never mutated).
    # ------------------------------------------------------------------
    def add_ascent_penalty(
        self, edges: list[MissionEdge], body: BodyName, extra_dv: float
    ) -> list[MissionEdge]:
        """Return ``edges`` with ``body``'s surface→low-orbit ascent edge's dv
        increased by ``extra_dv`` (e.g. the rotation-assist loss of a polar
        launch). Charged on the ascent edge so it is paid at the low
        (atmospheric) Isp launch stage — conservative. No-op if ``extra_dv`` is
        non-positive or the ascent edge isn't in the profile."""
        if extra_dv <= 0.0:
            return edges
        bnl = body.value.lower()
        src, dst = f"{bnl}_surface", f"{bnl}_low_orbit"
        return [
            replace(e, base_dv=e.base_dv + extra_dv)
            if (e.source == src and e.destination == dst) else e
            for e in edges
        ]

    def mark_precision_landing(
        self, edges: list[MissionEdge], body: BodyName
    ) -> list[MissionEdge]:
        """Return ``edges`` with ``body``'s orbit→surface landing edge flagged
        ``precision_landing`` (surface rescue: the descent must hit a
        designated site).  The dv cost is difficulty-resolved at evaluation
        time — see ``precision_landing_dv``.  No-op if the landing edge isn't
        in the profile."""
        bnl = body.value.lower()
        src, dst = f"{bnl}_low_orbit", f"{bnl}_surface"
        return [
            replace(e, precision_landing=True)
            if (e.source == src and e.destination == dst) else e
            for e in edges
        ]

    def add_ascent_plane_change(
        self, edges: list[MissionEdge], body: BodyName, pc_dv: float
    ) -> list[MissionEdge]:
        """Return ``edges`` with ``pc_dv`` added to the worst-case
        ``plane_change_dv`` of ``body``'s surface→low-orbit ascent edge.  A
        surface-rescue site at latitude φ forces an ascent plane of i ≥ φ,
        reconciled to the return/ejection plane for up to 2·v_LO·sin(φ/2) —
        free with window timing (launch into the plane containing site and
        departure asymptote), so it is priced by ``plane_change_fraction``
        like every other plane change.  No-op if ``pc_dv`` is non-positive or
        the ascent edge isn't in the profile."""
        if pc_dv <= 0.0:
            return edges
        bnl = body.value.lower()
        src, dst = f"{bnl}_surface", f"{bnl}_low_orbit"
        return [
            replace(e, plane_change_dv=e.plane_change_dv + pc_dv)
            if (e.source == src and e.destination == dst) else e
            for e in edges
        ]

    def bump_selfloop(
        self, edges: list[MissionEdge], extra_dv: float
    ) -> list[MissionEdge]:
        """Return ``edges`` with the (unique) pure-vacuum self-loop's dv increased
        by ``extra_dv``. A rescue profile carries exactly one such phasing/
        rendezvous self-loop; ``transform_mission`` bumps it by the round-trip
        cost of reaching the seeded rescue orbit. No-op if ``extra_dv`` is
        non-positive or no self-loop is present."""
        if extra_dv <= 0.0:
            return edges
        return [
            replace(e, base_dv=e.base_dv + extra_dv)
            if (e.source == e.destination and e.edge_type == self._PV) else e
            for e in edges
        ]

    def make_reach_edge(self, body: BodyName, dv: float) -> MissionEdge:
        """A pure-vacuum self-loop at ``body``'s low orbit carrying the delta-v to
        reach a specific target orbit from low orbit (the apoapsis raise / sync
        raise / in-well transfer ``orbit_reach_dv`` returns). Appended to a base
        ORBIT profile by ``transform_mission``; sums into the mission dv at vacuum
        Isp without changing the trajectory nodes."""
        bnl = body.value.lower()
        return self._edge(
            f"{bnl}_low_orbit", f"{bnl}_low_orbit", self._PV, dv, body,
            attitude=True,
        )

    def make_phasing_edge(self, body: BodyName, dv: float) -> MissionEdge:
        """A pure-vacuum low-orbit phasing/matching burn (the rendezvous margin a
        rescue adds at the target body). A self-loop on the target's low orbit so
        it sums into the mission dv without changing the trajectory."""
        bnl = body.value.lower()
        return self._edge(
            f"{bnl}_low_orbit", f"{bnl}_low_orbit", self._PV, dv, body,
            attitude=True,
        )

    # ------------------------------------------------------------------
    # Edge construction helpers (private)
    # ------------------------------------------------------------------

    def _edge(
        self,
        src: str, dst: str, et: EdgeType, dv: float, body: BodyName,
        pc: float = 0.0, min_twr: float = 0.0,
        throttle: bool = False, attitude: bool = False,
        heat: bool = False, legs: bool = False,
        entry_speed: float = 0.0, is_recovery: bool = False,
    ) -> MissionEdge:
        return MissionEdge(
            source=src, destination=dst, edge_type=et,
            base_dv=dv, body=body,
            relay_tier=self.relay_tier_by_body[body],
            plane_change_dv=pc,
            min_twr=min_twr, requires_throttleable=throttle,
            requires_attitude_control=attitude,
            needs_heat_shield=heat, needs_landing_legs=legs,
            entry_speed=entry_speed, is_recovery=is_recovery,
        )

    def _add_out(self, edge: MissionEdge, scheme: str = "") -> None:
        """Register ``edge`` in the outbound graph, optionally with a scheme tag."""
        self._outbound[edge.source].append((scheme, edge))

    def _add_ret(self, edge: MissionEdge, scheme: str = "") -> None:
        """Register ``edge`` in the return graph, optionally with a scheme tag."""
        self._return[edge.source].append((scheme, edge))

    def _add(
        self, body: BodyName, mission: MissionType, *profiles: list[MissionEdge]
    ) -> None:
        """Store one or more profile alternatives for ``(body, mission)``.

        Empty-profile passthrough (e.g. Kerbin FLAG_PLANT) is preserved.
        """
        self._profiles[(body, mission)] = list(profiles)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _planets(self) -> list["Body"]:
        """Bodies with no parent — the inter-planet transfer nodes."""
        return [b for b in ALL_BODIES if b.parent is None]

    def _moons_of(self, parent: BodyName) -> list["Body"]:
        return [b for b in ALL_BODIES if b.parent == parent]

    def _build_graph(self) -> None:
        """Populate ``_outbound`` and ``_return`` edge sets from body data."""
        for body in ALL_BODIES:
            self._add_body_trunk(body)
        for moon in ALL_BODIES:
            if moon.parent is not None and moon.name != BodyName.KERBOL:
                self._add_moon_outbound_access(moon)
        # Inter-planet outbound transfers (Hohmann depart at src's solar
        # radius).  Kerbol is skipped — it's not a mission destination
        # (``locations.get_body_events`` returns ``()`` for it) so no
        # transfer edges to/from it would ever be used.  Kerbol remains
        # in ``ALL_BODIES`` for its solar-distance reference.
        for src in self._planets():
            if src.name == BodyName.KERBOL:
                continue
            for dst in self._planets():
                if dst.name == BodyName.KERBOL or src.name == dst.name:
                    continue
                self._add_planet_outbound_transfer(src, dst)
        # Return-only edges that converge on home.surface.
        self._add_home_return_paths()

    def _planet_capture_dv(self, body: "Body", base_capture_dv: float) -> float:
        """Propulsive SOI→low-orbit capture cost (m/s) for ``body``.

        The capture burn is the hyperbolic-arrival insertion
        ``√(v∞² + 2µ/r) − √(µ/r)``, where ``v∞`` is the heliocentric Hohmann
        arrival speed for THIS world's home reaching ``body``.  ``v∞`` scales with
        the home's solar distance — a far home (e.g. Dres → Moho) arrives far
        faster than Kerbin does and must burn much harder to capture.  Computed
        straight from physics for every home: accurate to what the player actually
        flies, never anchored to (and so never floored at) the Kerbin delta-v-map
        value.  Coplanar Hohmann is itself conservative (the true optimal transfer
        is never more expensive), so this stays at-or-above the achievable cost.

        ``base_capture_dv`` (``dvLE``/``dvLI``) is kept only for arrivals the
        heliocentric model does not describe: a moon's tabulated capture is a
        parent-frame Oberth ejection, and an arrival inside the home's own system
        is an in-well transfer — both keep their tabulated value.
        """
        if body.parent is not None:                 # moon: dvLI is parent-frame Oberth
            return base_capture_dv
        root = self.home_body
        while root.parent is not None:              # moon-home → its root planet
            root = BODY_BY_NAME[root.parent]
        if root.name == body.name:                  # arriving in home's own system
            return base_capture_dv
        v_inf = planet_transfer_dv(root, body)[1]
        mu = body.gm
        r = body.lo_radius_m
        return math.sqrt(v_inf * v_inf + 2.0 * mu / r) - math.sqrt(mu / r)

    def _add_body_trunk(self, body: "Body") -> None:
        """Ascent, escape/capture, landing edges for a single body.

        Ascent, escape and aero/prop landing are direction-symmetric (they
        appear in both graphs).  Captures and passive arrivals (intercept →
        SOI) are outbound-only — the restricted return graph never captures
        into a non-home SOI.
        """
        bn = body.name
        bnl = bn.lower()
        s   = f"{bnl}_surface"
        lo = f"{bnl}_low_orbit"
        soi = f"{bnl}_soi"
        ic  = f"{bnl}_intercept"

        # Ascent — surface → low orbit (atmospheric or vacuum).  The HOME
        # body's ascent starts from its designated pad (an elevated site
        # pays less than the sea-level ``dvGL`` — Eve's mesa).  Destination
        # landers pay sea level, EXCEPT on assume_highlands_landing bodies
        # (Eve), where logic assumes a player-controlled highlands touchdown
        # at the pad's elevation band — see the field's one-way-splashdown
        # caveat.
        if body.can_land and body.dv.dvGL > 0:
            ascent_type = self._AT if body.has_atmosphere else self._VA
            min_twr_ascent = 1.3 if body.has_atmosphere else 1.2
            ascent_dv = (body.home_pad_ascent_dv()
                         if bn == self.home or body.assume_highlands_landing
                         else body.dv.dvGL)
            ascent = self._edge(
                s, lo, ascent_type, ascent_dv, bn,
                min_twr=min_twr_ascent, throttle=True, attitude=True,
            )
            self._add_out(ascent)
            self._add_ret(ascent)

        # SOI escape & capture (low orbit ↔ SOI).  Use ``dvLE`` when present
        # (Kerbin / Eve / Duna / Jool — planets that the data models with
        # an explicit low orbit→SOI burn), otherwise fall back to ``dvLI``
        # (Moho / Dres / Eeloo planets, and every moon).  Kerbol has no
        # escape node in our model: you start inside its SOI and never
        # leave the heliocentric frame, so skip these edges for Kerbol.
        escape_dv = body.dv.dvLE if body.dv.dvLE is not None else body.dv.dvLI
        if escape_dv is not None and bn != BodyName.KERBOL:
            escape = self._edge(lo, soi, self._PV, escape_dv, bn, attitude=True)
            self._add_out(escape)
            self._add_ret(escape)
            # Passive arrival — intercept → SOI (zero-dv coast, outbound only).
            passive = self._edge(ic, soi, self._PV, 0, bn, attitude=True)
            self._add_out(passive)
            # Capture — SOI → low orbit.  Aerobrake variant exists only for
            # atmospheric *planets* (atmospheric moons like Laythe are too
            # thin and orbital velocities too high relative to parent for
            # aerobrake-to-low orbit to be reliable; preserves existing
            # convention of prop-only capture for moons).  Scheme tags
            # are applied only when both alternatives exist at the same
            # decision point — that way a path can mix "aero capture at
            # Jool" with "prop landing at a moon of Jool" without the
            # scheme constraint blocking it.
            capture_has_aero_alt = body.has_atmosphere and body.parent is None
            capture_dv = self._planet_capture_dv(body, escape_dv)
            capture_prop = self._edge(soi, lo, self._PV, capture_dv, bn, attitude=True)
            self._add_out(capture_prop, scheme="prop" if capture_has_aero_alt else "")
            if capture_has_aero_alt:
                capture_aero = self._edge(
                    soi, lo, self._AB, _AEROBRAKE_CAPTURE_RESIDUAL_DV, bn, heat=True)
                self._add_out(capture_aero, scheme="aero")
            # Moon SOI → parent low orbit: passive transit when leaving a moon's
            # SOI.  After escape you find yourself in the parent's frame at
            # roughly low orbit altitude (Hill-sphere radius is small relative
            # to parent's orbital radius).  Required for moon-home outbound
            # paths to reach the parent system's transfer hub.
            if body.parent is not None:
                exit_to_parent = self._edge(
                    soi, f"{body.parent.lower()}_low_orbit",
                    self._PV, 0, bn, attitude=True,
                )
                self._add_out(exit_to_parent)
                self._add_ret(exit_to_parent)

        # Landing — low orbit → surface.
        if body.can_land and body.dv.dvGL > 0:
            if body.has_atmosphere:
                # One staged aero+propulsive edge: capability picks the
                # min-mass mix of shield bleed + drogues + mains + touchdown
                # burn (see capability._solve_atmo_landing).  base_dv=0 — the
                # burn is computed at evaluation time from the actual kit;
                # min_twr / throttle / attitude are mix-dependent and imposed
                # by capability only when a burn is chosen, so a passive chute
                # landing stays demand-free.  No scheme tag: landing no longer
                # forks the path.
                land = self._edge(
                    lo, s, self._AL, 0, bn, heat=True, legs=True,
                    entry_speed=body.lo_circular_velocity,
                )
                self._add_out(land)
            else:
                land = self._edge(
                    lo, s, self._VL, body.dv.dvGL, bn,
                    min_twr=1.2, throttle=True, attitude=True, legs=True,
                )
                self._add_out(land)

    def _add_moon_outbound_access(self, moon: "Body") -> None:
        """Parent.low orbit → moon.intercept TLI edge (outbound only).

        The combined moon-escape edge that pairs with this for returns
        (moon.low orbit → parent.low orbit or moon.low orbit → home.intercept) is registered
        from ``_add_home_return_paths`` so it can target the right node
        based on whether the moon's parent is also home.
        """
        tli_dv = moon.dv.dvPL if moon.dv.dvPL is not None else moon.dv.dvPE
        if tli_dv is None:
            return
        tli = self._edge(
            f"{moon.parent.lower()}_low_orbit", f"{moon.name.lower()}_intercept",
            self._PV, tli_dv, moon.parent,
            pc=moon.dv.dvPlaneChange, attitude=True,
        )
        self._add_out(tli)

    def _add_planet_outbound_transfer(self, src: "Body", dst: "Body") -> None:
        """``src.low orbit → dst.intercept`` — Oberth-combined TLI burn from src's
        low orbit.  Burning at low orbit periapsis is the realistic single-burn
        TLI a player executes; splitting into escape-then-transfer would
        double-count the escape energy that's already absorbed at low orbit."""
        depart_dv, _arrive, pc = planet_transfer_dv(src, dst)
        edge = self._edge(
            f"{src.name.lower()}_low_orbit", f"{dst.name.lower()}_intercept",
            self._PT, depart_dv, src.name, pc=pc, attitude=True,
        )
        self._add_out(edge)

    def _add_home_return_paths(self) -> None:
        """Register the return-only edges that converge on ``home.surface``.

        Restricted-return rule: paths through this graph cannot capture into
        any non-home SOI.  They can only ascend / escape SOIs and traverse
        interplanetary segments that terminate at ``home.intercept`` (or,
        for the home body's parent SOI when home is a moon, at home's
        intercept inside the parent frame).
        """
        home = self.home_body
        hn = home.name
        hnl = hn.lower()

        # Interplanetary returns: from each non-home planet's low orbit direct to
        # home.intercept (Oberth-combined TLI back home).  For moon-home,
        # the home's parent planet is handled via parent.low orbit → home.intercept
        # below (one fewer SOI traversal).
        for planet in self._planets():
            if planet.name == hn or planet.name == BodyName.KERBOL:
                continue
            if home.parent is not None and planet.name == home.parent:
                continue
            depart_dv, _, pc = planet_transfer_dv(planet, home)
            self._add_ret(self._edge(
                f"{planet.name.lower()}_low_orbit", f"{hnl}_intercept",
                self._PT, depart_dv, planet.name, pc=pc, attitude=True,
            ))

        # SOI-boundary interplanetary returns: from each non-home planet's SOI
        # node direct to home.intercept.  This is the only edge leaving a
        # planet's SOI in the return graph, and it is what makes SOI_RETURN
        # (flyby-and-come-home) a reachable mission.
        #
        # Gravity-assist geometry is not modelled, so the flyby buys nothing:
        # the craft leaves the SOI co-moving with the planet and pays the FULL
        # heliocentric excess to get home, with no Oberth benefit (it is already
        # outside the well).  For shallow wells that is deliberately more than
        # the Oberth-combined low-orbit departure above — Duna ≈ 615 m/s here vs
        # ≈ 511 m/s from low orbit — so a Duna-class SOI return can price a
        # little above an aerobrake orbit return.  That is a conservative
        # artifact of not modelling the assist, not an error.
        #
        # Home's parent is skipped, exactly like the low-orbit loop above: that
        # hop never leaves the parent's system, so it is neither a heliocentric
        # transfer nor priced like one.  It is registered in the moon-home branch
        # below, next to its low-orbit sibling.
        root = home
        while root.parent is not None:
            root = BODY_BY_NAME[root.parent]
        for planet in self._planets():
            if planet.name == hn or planet.name == BodyName.KERBOL:
                continue
            if home.parent is not None and planet.name == home.parent:
                continue
            # Departure v∞ AT THE PLANET for planet → home.  Hohmann is
            # symmetric, so this equals the arrival v∞ at the planet coming from
            # home's root — exactly what ``planet_transfer_dv`` returns in slot
            # 1.  One source for the Hohmann math, never a second copy.
            _, v_inf, pc = planet_transfer_dv(root, planet)
            self._add_ret(self._edge(
                f"{planet.name.lower()}_soi", f"{hnl}_intercept",
                self._PT, v_inf, planet.name, pc=pc, attitude=True,
            ))

        # Moons of home (planet-home case): low moon orbit → home reentry
        # intercept.  This is a SINGLE energy-preserving ejection burn, NOT
        # escape-then-separately-lower-Pe: ``dvLI`` already encodes the Oberth
        # ejection (√(v_inf² + 2·v_circ²) − v_circ) that drops you straight
        # onto a reentry trajectory, carrying your orbital energy out of the
        # moon.  It does NOT include ``dvPL`` — that is the from-LKO Hohmann /
        # parent low-orbit *circularization*, which a reentry never performs
        # (you aerobrake).  Adding it over-charged Mun returns ~3.8× and Minmus
        # ~2.7× (e.g. Minmus 160 + 930 = 1090 vs the correct ~160).
        #
        # No plane change, at any difficulty: lowering your orbit from a moon
        # down to its parent is always free — you keep whatever inclination you
        # have and aerobrake at any angle.  The moon's inclination IS paid once,
        # outbound, on the encounter edge (_add_moon_outbound_access) where you
        # RAISE to meet the inclined moon.  Charging it again here double-counted
        # it.  (Ascending-to-encounter pays a difficulty-scaled plane change;
        # descending-to-parent never does.)
        if home.parent is None:
            for moon in self._moons_of(hn):
                # Home-moon SOI → home reentry intercept.  The moon's own
                # ``soi → parent.low orbit`` exit edge dead-ends here (nothing
                # in the RETURN graph leaves home's low orbit), so without this
                # a home moon has no SOI_RETURN path at all.
                #
                # Priced as a plain periapsis-lowering burn, NOT ``dvLI``:
                # outside the moon's well you are co-moving with it on a
                # near-circular parent orbit, and dvLI's Oberth ejection bonus
                # was already spent on the escape edge that put you there.  The
                # moon's periapsis radius is the worst case (fastest point of an
                # eccentric orbit ⇒ largest burn) and matches the radius
                # ``orbit_reach_dv`` charges for the same parent-frame transfer.
                r_moon = moon.parent_periapsis_km * 1000.0
                if r_moon > 0.0:
                    self._add_ret(self._edge(
                        f"{moon.name.lower()}_soi", f"{hnl}_intercept",
                        self._PV,
                        home.transfer_circular_to_ellipse_dv(
                            r_moon, home.lo_radius_m, r_moon),
                        moon.name, attitude=True,
                    ))
                if moon.dv.dvLI is None:
                    continue
                self._add_ret(self._edge(
                    f"{moon.name.lower()}_low_orbit", f"{hnl}_intercept",
                    self._PV, moon.dv.dvLI, moon.name,
                    attitude=True,
                ))
        else:
            # Moon-home case: parent.low orbit → home.intercept (used by sibling
            # moons returning home, and by inter-planet returns that land at
            # parent.low orbit after the Hohmann arrival).  This RAISES to
            # *encounter* the inclined home moon — not a descent — so it pays
            # the moon's plane change.  effective_dv scales it by difficulty:
            # it's a window-timing skill experts mostly avoid and beginners pay
            # in full (see plane_change_fraction).
            tli_home = home.dv.dvPL if home.dv.dvPL is not None else home.dv.dvPE
            if tli_home is not None:
                self._add_ret(self._edge(
                    f"{home.parent.lower()}_low_orbit", f"{hnl}_intercept",
                    self._PV, tli_home, home.parent,
                    pc=home.dv.dvPlaneChange, attitude=True,
                ))
            # …and parent.SOI → home.intercept, so the parent has an SOI_RETURN.
            # PURE_VACUUM, not PLANET_TRANSFER: this hop never leaves the
            # parent's system, and the nav-requirement derivation keys on the
            # PLANET_TRANSFER edge type to mean "interplanetary" (see
            # ``mission_logic_needs`` and its tripwire test).
            #
            # Only the plane change is charged: falling from the parent's SOI
            # boundary back down to the home moon's orbit is free, and the
            # outbound leg to that SOI overcharges by far more (it routes
            # surface → moon SOI → parent low orbit → parent SOI, paying the
            # parent's full low-orbit escape on top of the moon's).  Plane
            # change is the home moon's own inclination, matching the low-orbit
            # sibling edge above — the parent's heliocentric figure is
            # meaningless here.
            self._add_ret(self._edge(
                f"{home.parent.lower()}_soi", f"{hnl}_intercept",
                self._PV, 0.0, home.parent,
                pc=home.dv.dvPlaneChange, attitude=True,
            ))

        # Foreign moons (parent != home; for moon-home, this includes home's
        # own siblings): moon.low orbit → parent.low orbit combined escape.  Lets return
        # paths from foreign moons rejoin the trunk graph at the parent's low orbit.
        # No plane change: an intra-system X→parent descent matches no target
        # plane (the moon's own inclination is left behind on escape).  NOTE:
        # routing moon→moon via parent.low orbit still forces a circularize-then-
        # re-eject layover a direct moon-to-moon transfer would avoid — a graph
        # gap tracked separately, not a per-edge dv fix.
        for moon in ALL_BODIES:
            if moon.parent is None or moon.name == hn:
                continue
            if home.parent is None and moon.parent == hn:
                continue  # moons of planet-home are handled above
            tli_dv = moon.dv.dvPL if moon.dv.dvPL is not None else moon.dv.dvPE
            if tli_dv is None:
                continue
            combined = moon.dv.dvLI + tli_dv
            self._add_ret(self._edge(
                f"{moon.name.lower()}_low_orbit", f"{moon.parent.lower()}_low_orbit",
                self._PV, combined, moon.name,
                attitude=True,
            ))

        # Home reentry (intercept → surface).  Atmospheric homes do a staged
        # aero descent; vacuum homes need a propulsive landing.  Entry speed is
        # higher than a landing-from-orbit (you arrive on a hyperbolic return),
        # so pad low-orbit escape velocity — covers the worst stock return
        # (Jool→Kerbin ≈ 4383 < 1.4·v_esc).  is_recovery: solar panels may be
        # gone by touchdown and no further power is needed on this leg.
        if home.can_land:
            if home.has_atmosphere:
                reentry = self._edge(
                    f"{hnl}_intercept", f"{hnl}_surface",
                    self._AL, 0, hn, heat=True,
                    entry_speed=1.4 * home.lo_escape_velocity,
                    is_recovery=True,
                )
            else:
                reentry = self._edge(
                    f"{hnl}_intercept", f"{hnl}_surface",
                    self._VL, home.dv.dvGL, hn,
                    min_twr=1.2, throttle=True, attitude=True, legs=True,
                    is_recovery=True,
                )
            self._add_ret(reentry)
            self._add_out(reentry)

    # ------------------------------------------------------------------
    # Path enumeration
    # ------------------------------------------------------------------

    def _find_outbound_paths(
        self, src: str, dst: str
    ) -> list[list[MissionEdge]]:
        return self._find_paths(self._outbound, src, dst)

    def _find_return_paths(
        self, src: str, dst: str
    ) -> list[list[MissionEdge]]:
        return self._find_paths(self._return, src, dst)

    def _find_paths(
        self,
        graph: dict[str, list[tuple[str, MissionEdge]]],
        src: str,
        dst: str,
    ) -> list[list[MissionEdge]]:
        """Enumerate scheme-consistent simple paths from ``src`` to ``dst``.

        A path can use edges with empty scheme tags freely.  Once an edge
        with a non-empty tag is taken, every subsequent tagged edge on
        that path must share the same tag — this is what keeps "aero
        capture + prop landing" from showing up as a profile alternative.

        Each path uses at most one ``PLANET_TRANSFER`` edge — gravity-
        assist routing through intermediate planet SOIs isn't modelled,
        so multi-hop interplanetary itineraries are unphysical and only
        bloat the alternative count without representing a real choice
        the player can make.

        Results are sorted by total ``base_dv`` ascending and capped at
        ``_MAX_PROFILE_ALTS``.
        """
        results: list[list[MissionEdge]] = []
        cap = self._MAX_PROFILE_ALTS

        def dfs(node: str, path: list[MissionEdge], scheme: str,
                visited: set[str], pt_count: int) -> None:
            if len(results) >= cap * 2:
                return
            if node == dst:
                results.append(list(path))
                return
            for edge_scheme, edge in graph.get(node, []):
                if edge.destination in visited:
                    continue
                if edge_scheme and scheme and edge_scheme != scheme:
                    continue
                next_pt = pt_count + (1 if edge.edge_type == EdgeType.PLANET_TRANSFER else 0)
                if next_pt > 1:
                    continue
                new_scheme = scheme or edge_scheme
                visited.add(edge.destination)
                path.append(edge)
                dfs(edge.destination, path, new_scheme, visited, next_pt)
                path.pop()
                visited.remove(edge.destination)

        dfs(src, [], "", {src}, 0)
        results.sort(key=lambda p: sum(e.base_dv for e in p))
        return results[:cap]

    # ------------------------------------------------------------------
    # Profile construction
    # ------------------------------------------------------------------

    def _build_profiles(self) -> None:
        """Populate ``self._profiles`` from the outbound + return graphs."""
        for body in ALL_BODIES:
            if body.name == self.home:
                self._build_home_profiles(body)
            else:
                self._build_destination_profiles(body)

        # FLAG_PLANT defaults to LAND when no explicit entry exists.  Home
        # body registers its own (empty) FLAG_PLANT in _build_home_profiles
        # and that entry is preserved by the membership check.
        for (body_name, mission_type) in list(self._profiles):
            if (mission_type == MissionType.LAND
                    and (body_name, MissionType.FLAG_PLANT) not in self._profiles):
                self._profiles[(body_name, MissionType.FLAG_PLANT)] = \
                    self._profiles[(body_name, MissionType.LAND)]

    def _build_home_profiles(self, home: "Body") -> None:
        """Profiles for the home body itself.

        Home gets the canonical short paths: ORBIT = ascent only; ESCAPE =
        ascent + SOI escape; LAND / ORBIT_RETURN = ascent + deorbit.

        Home's return tiers are the inverse of every other body's: the surface
        is where you start, so RETURN (surface round trip) is trivially true —
        walk out at the pad and recover — and it is ORBIT_RETURN that carries
        the "go up and come back" flight.  Trivial tiers are registered as ONE
        empty alternative (``_add(hn, mt, [])`` ⇒ ``[[]]``), never as zero
        alternatives: downstream, one empty alternative reads as trivially
        achievable while an entry holding no alternatives reads as infeasible.

        SOI_RETURN is deliberately NOT registered at home: "leave your home SOI
        and come back" is hard to explain to players, so the location is
        ``home_excluded`` and the contract side keeps it off home too.

        FLAG_PLANT and SAMPLE_RETURN are likewise trivial (the Kerbal walks out
        from the launchpad).
        """
        hn = home.name
        hnl = hn.lower()
        ascent_paths = self._find_outbound_paths(f"{hnl}_surface", f"{hnl}_low_orbit")
        if ascent_paths:
            ascent = ascent_paths[0]  # single ascent edge for a body
            self._add(hn, MissionType.ORBIT, ascent)

            if hn != BodyName.KERBOL:
                escape_paths = self._find_outbound_paths(
                    f"{hnl}_surface", f"{hnl}_soi",
                )
                if escape_paths:
                    self._add(hn, MissionType.ESCAPE, escape_paths[0])

            # LAND / RETURN — append a deorbit edge to the ascent path.
            # Prefer aero deorbit when atmospheric; fall back to whichever
            # exists (vacuum body uses VACUUM_LANDING with full dvGL).
            lo_edges = self._outbound.get(f"{hnl}_low_orbit", [])
            deorbit_aero = [e for s, e in lo_edges
                            if s == "aero" and e.destination == f"{hnl}_surface"]
            deorbit_any = [e for s, e in lo_edges
                           if e.destination == f"{hnl}_surface"]
            deorbit = (deorbit_aero or deorbit_any or [None])[0]
            if deorbit is not None:
                land_profile = ascent + [deorbit]
                self._add(hn, MissionType.LAND, land_profile)
                # ORBIT_RETURN — reach home orbit and come back down. Same
                # ascent+deorbit trajectory as LAND (no rendezvous phasing).
                self._add(hn, MissionType.ORBIT_RETURN, land_profile)
                # RESCUE — reach home orbit, rendezvous, and deorbit the rescued
                # Kerbal. Ascent + phasing burn (at low orbit) + deorbit.
                phasing = self.make_phasing_edge(hn, self._RESCUE_RENDEZVOUS_DV)
                self._add(hn, MissionType.RESCUE, ascent + [phasing, deorbit])

        # RETURN / FLAG_PLANT / SAMPLE_RETURN at home: walk out from the
        # launchpad (Kerbal EVA) and recover — no rocket required.  See user
        # note in CLAUDE.md about Kerbin SAMPLE_RETURN: this must stay empty.
        self._add(hn, MissionType.RETURN, [])
        self._add(hn, MissionType.FLAG_PLANT, [])
        self._add(hn, MissionType.SAMPLE_RETURN, [])

    def _build_destination_profiles(self, body: "Body") -> None:
        """Profiles for a non-home destination body."""
        bn = body.name
        # Kerbol is not a mission destination.  ``locations.get_body_events``
        # returns ``()`` for it (root body — no flyby/escape/landed checks
        # exist), so no caller ever queries ``mission_builder.profiles_for(
        # BodyName.KERBOL, …)``.  Generating profiles here would just be
        # dead state, and Hohmann math from Kerbol's deep gravity well
        # produces unrealistic dvs anyway (return ≈ 40 km/s).  Kerbol stays
        # in ``ALL_BODIES`` for its solar-distance reference, but earns
        # no profile entries.
        if bn == BodyName.KERBOL:
            return
        bnl = bn.lower()
        home_surface = f"{self.home.lower()}_surface"

        target_soi = f"{bnl}_soi"
        target_lo = f"{bnl}_low_orbit"
        target_surf = f"{bnl}_surface" if body.can_land else None

        # ESCAPE — reach the body's SOI boundary.
        escape_paths = self._find_outbound_paths(home_surface, target_soi)
        if escape_paths:
            self._add(bn, MissionType.ESCAPE, *escape_paths)

        # ORBIT — reach the body's low orbit node.
        orbit_paths = self._find_outbound_paths(home_surface, target_lo)
        if orbit_paths:
            self._add(bn, MissionType.ORBIT, *orbit_paths)

        # LAND — reach the body's surface.
        if body.can_land and target_surf is not None:
            land_paths = self._find_outbound_paths(home_surface, target_surf)
            if land_paths:
                self._add(bn, MissionType.LAND, *land_paths)

        # RETURN / SAMPLE_RETURN — outbound to the deepest accessible node,
        # then a restricted return path back to home.surface.  Cap the
        # cartesian product to MAX alternatives total (sort by dv to keep
        # the cheapest ones).
        return_origin = target_surf if body.can_land else target_lo
        home_surf = f"{self.home.lower()}_surface"
        outbound_alts = self._find_outbound_paths(home_surface, return_origin)
        return_alts = self._find_return_paths(return_origin, home_surf)
        if outbound_alts and return_alts:
            combos: list[list[MissionEdge]] = []
            for out in outbound_alts:
                for ret in return_alts:
                    combos.append(out + ret)
            combos.sort(key=lambda p: sum(e.base_dv for e in p))
            combos = combos[:self._MAX_PROFILE_ALTS]
            self._add(bn, MissionType.RETURN, *combos)
            # SAMPLE_RETURN requires landing to take a sample — only register
            # it for bodies you can actually land on.  Jool / Kerbol "return"
            # missions are flyby-and-back, not sample retrieval.
            if body.can_land:
                self._add(bn, MissionType.SAMPLE_RETURN, *combos)
                # SURFACE_RESCUE shares the land+return trajectory; the
                # precision-landing flag and the site-latitude plane change
                # are per-contract (seeded site), applied in
                # ``transform_mission``, not baked into the profile.
                # Destination bodies only — the home body is excluded from
                # surface rescue (matches stock RecoverAsset).
                self._add(bn, MissionType.SURFACE_RESCUE, *combos)

        # SOI_RETURN — flyby-and-come-home: the same outbound-×-return
        # cartesian product as RETURN, but the turn-around point is the SOI
        # node, so nothing is captured into and nothing is landed on.  The
        # outbound half is exactly ESCAPE's path set.
        soi_return_alts = self._find_return_paths(target_soi, home_surf)
        if escape_paths and soi_return_alts:
            soi_combos = [out + ret
                          for out in escape_paths
                          for ret in soi_return_alts]
            soi_combos.sort(key=lambda p: sum(e.base_dv for e in p))
            self._add(bn, MissionType.SOI_RETURN,
                      *soi_combos[:self._MAX_PROFILE_ALTS])

        # RESCUE — reach the target's orbit, rendezvous, bring the stranded
        # Kerbal home. The seeded rescue-orbit radius cost is added in
        # ``transform_mission`` (bumps the rendezvous self-loop); here we only
        # build the base "reach the body and come back" profile.
        if self.home_body.parent == bn:
            # CHILD -> PARENT (home is a moon, target is its parent planet).
            # You never descend to the parent's low orbit — you ESCAPE the home
            # moon (dvLI) into the parent frame at the moon's orbital radius,
            # then Hohmann up/down to the rescue orbit (added in transform), then
            # recapture into the home moon and land. Routing to the parent's deep
            # low orbit would over-charge 2.5-8.7x.
            home = self.home_body
            hnl_home = self.home.lower()
            ascent_paths = self._find_outbound_paths(
                f"{hnl_home}_surface", f"{hnl_home}_low_orbit")
            lo_edges = self._outbound.get(f"{hnl_home}_low_orbit", [])
            deorbit = next(
                (e for s, e in lo_edges
                 if s == "aero" and e.destination == f"{hnl_home}_surface"),
                next((e for s, e in lo_edges
                      if e.destination == f"{hnl_home}_surface"), None))
            dvli = home.dv.dvLI
            if ascent_paths and deorbit is not None and dvli is not None:
                node = f"{bnl}_rescue_orbit"   # synthetic: parent frame at r_moon
                eject = self._edge(f"{hnl_home}_low_orbit", node,
                                   self._PV, dvli, home.name, attitude=True)
                phasing = self._edge(node, node, self._PV,
                                     self._RESCUE_RENDEZVOUS_DV, bn, attitude=True)
                capture = self._edge(node, f"{hnl_home}_low_orbit",
                                     self._PV, dvli, home.name, attitude=True)
                self._add(bn, MissionType.RESCUE,
                          ascent_paths[0] + [eject, phasing, capture, deorbit])
                # ORBIT_RETURN — reach the parent's orbit and come home, no
                # rendezvous (tourists, not a second craft to meet).
                self._add(bn, MissionType.ORBIT_RETURN,
                          ascent_paths[0] + [eject, capture, deorbit])
        else:
            # General case: reach the target's LOW ORBIT (not surface),
            # rendezvous, and bring the stranded Kerbal home. Like RETURN but the
            # return always starts from low orbit (no landing+ascent leg at the
            # target), with a rendezvous/phasing burn baked in at low orbit.
            rescue_outbound = self._find_outbound_paths(home_surface, target_lo)
            rescue_return = self._find_return_paths(target_lo, home_surf)
            if rescue_outbound and rescue_return:
                phasing = self.make_phasing_edge(bn, self._RESCUE_RENDEZVOUS_DV)
                rescue_combos = [out + [phasing] + ret
                                 for out in rescue_outbound for ret in rescue_return]
                rescue_combos.sort(key=lambda p: sum(e.base_dv for e in p))
                self._add(bn, MissionType.RESCUE,
                          *rescue_combos[:self._MAX_PROFILE_ALTS])
                # ORBIT_RETURN — reach the body's low orbit and return home, no
                # rendezvous phasing (tourists ride along; there is no second
                # craft to meet).
                orbit_return_combos = [out + ret
                                       for out in rescue_outbound
                                       for ret in rescue_return]
                orbit_return_combos.sort(key=lambda p: sum(e.base_dv for e in p))
                self._add(bn, MissionType.ORBIT_RETURN,
                          *orbit_return_combos[:self._MAX_PROFILE_ALTS])

    # ------------------------------------------------------------------
    # Cross-validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        """Sanity-check the built profile graph.

        Two checks:
        1. Every body that has an ``ORBIT`` profile (and isn't Kerbol) must
           also declare an explicit ``ESCAPE`` profile.  Historically these
           were auto-generated by stripping the last edge of ORBIT, which
           silently dropped relay-tier gates when SOI-entry and orbit-
           insertion were merged into a single edge.  See bug 075 /
           ``plans/ssr_variance_investigation.md``.
        2. Every ``(body, event)`` that ``locations.get_body_events`` exposes
           as a real check must have a profile entry, except FLAG_PLANT
           (auto-derived from LAND above) and EVA-in-Orbit (shares the ORBIT
           profile via its ``mission_type``).  Missing entries would cause
           silent KeyError in rule-evaluation, so we surface them eagerly.
           ``get_body_events`` is home-agnostic, so a ``home_excluded`` event
           is skipped on the home body — this world never emits it, and the
           builder deliberately registers no profile for it (SOI Return at
           home).  Non-home bodies still need one.
        """
        # (1) ESCAPE coverage — intrinsic to the mission graph.
        for (body_name, mission_type) in list(self._profiles):
            if (mission_type == MissionType.ORBIT
                    and body_name != BodyName.KERBOL
                    and (body_name, MissionType.ESCAPE) not in self._profiles):
                raise RuntimeError(
                    f"{body_name} has an ORBIT profile but no ESCAPE profile. "
                    "Add an explicit ``self._add(body, MissionType.ESCAPE, ...)``."
                )

        # (2) Cross-module coverage — every body/event check must have a profile.
        # Deferred import: locations.py imports from bodies.py.
        from .locations import EVENT_BY_NAME, get_body_events
        for body in ALL_BODIES:
            for event_name in get_body_events(body):
                event = EVENT_BY_NAME[event_name]
                if event.mission_type == MissionType.FLAG_PLANT:
                    continue  # derived from LAND in _build_profiles
                if event.home_excluded and body.name == self.home:
                    continue  # never emitted here, so no profile is required
                key = (body.name, event.mission_type)
                if key not in self._profiles:
                    raise AssertionError(
                        f"MissionBuilder: no profile for {key} "
                        f"(location {body.name} {event_name} would have no rule)"
                    )

# ---------------------------------------------------------------------------
# Home-relative science scaling
#
# When ``home != Kerbin`` the player starts on an alien world; stock KSP's
# science multipliers (calibrated for Kerbin home) make every body's reward
# reflect "how alien from Kerbin" rather than "how alien from the player's
# actual home".
#
# Three rules, applied per-situation (landed/splashed/fly_low/.../recovery):
#   - body == home          -> Kerbin's stock value for that situation.
#                              Surface sample at Eeloo home == surface sample
#                              at Kerbin home, biome by biome.
#   - body == Kerbin        -> Laythe's stock value × Δv ratio.  Laythe is
#                              Kerbin's physical analog (atmosphere, ocean,
#                              similar gravity / size), so it gives the right
#                              shape for "Kerbin as the alien target".  The
#                              Δv ratio uses Laythe-from-Kerbin as the
#                              denominator — that's the canonical "alien
#                              Laythe-class planet" reward-per-Δv calibration,
#                              and applying it here means Kerbin-from-any-home
#                              feels exactly like Laythe-from-Kerbin in
#                              science / Δv terms.
#   - any other body        -> stock_mult × round-trip Δv ratio.  Uniform per
#                              body — every situation scales by the same
#                              factor.  Preserves Squad's reward-per-Δv
#                              calibration from Kerbin home onto every other
#                              home.
#
# ``effective_situation_mult`` is the single source of truth.  Both
# ``science_budget`` (rules + sphere-ladder) and ``home_relative_science_values``
# (slot_data emission) read from it.  Same arithmetic on both sides, so the
# server's accounting and the player's actual yields cannot drift.
# ---------------------------------------------------------------------------


# Slot-data field name -> Body attribute holding that situation's stock
# multiplier.  Used to translate the per-situation effective-mult call
# into the right ``getattr`` against the Body dataclass.
SITUATION_FIELD_TO_ATTR: dict[str, str] = {
    "landed":     "landed_mult",
    "splashed":   "splashed_mult",
    "fly_low":    "fly_low_mult",
    "fly_high":   "fly_high_mult",
    "space_low":  "space_low_mult",
    "space_high": "space_high_mult",
    "recovery":   "recovery_mult",
}


# Cache MissionBuilder per home — construction is heavy (builds the full
# mission graph + every (body, mission_type) profile) but the result is
# deterministic and pure.  Sharing a single builder per home across all
# ``_return_dv`` calls means we pay the cost ~once per process.
@lru_cache(maxsize=None)
def _mission_builder_for(home: BodyName) -> "MissionBuilder":
    return MissionBuilder(home=home)


# Squad calibrates outer-system interplanetary missions with roughly 1.67×
# the science-per-Δv of intra-Kerbin-system targets (Mun / Minmus).  When a
# body that was interplanetary from Kerbin becomes intra-system from the new
# home (e.g. Vall is sibling-moon-of-Jool from Laythe home, not a far Jool
# moon from Kerbin home), Squad's stock multiplier still carries that
# interplanetary premium — we strip it.
_INTERPLANETARY_PREMIUM: float = 1.67


@lru_cache(maxsize=None)
def _return_dv(body: BodyName, home: BodyName) -> float:
    """Cheapest round-trip Δv from ``home`` to ``body`` and back, using
    ``MissionType.RETURN`` profiles (both legs + capture / aerobrake).

    Round-trip rather than one-way because Kerbin's thick atmosphere
    makes one-way capture from any vacuum body nearly free (aerobrake);
    the return leg has to actually climb back out of Kerbin's gravity well.

    Returns ``inf`` when no return profile exists (e.g. Kerbol)."""
    builder = _mission_builder_for(home)
    profiles = builder.profiles_for(body, MissionType.RETURN)
    if not profiles:
        return float("inf")
    return min(sum(e.base_dv for e in profile) for profile in profiles)

@lru_cache(maxsize=None)
def _mission_dv(body: BodyName, home: BodyName, mission: MissionType) -> float:
    """Cheapest Δv from ``home`` to ``body`` using
    ``MissionType.mission`` profiles.

    I need this for crimes.

    Returns ``inf`` when no profile exists (e.g. Kerbol)."""
    builder = _mission_builder_for(home)
    profiles = builder.profiles_for(body, mission)
    if not profiles:
        return float("inf")
    return min(sum(e.base_dv for e in profile) for profile in profiles)


@lru_cache(maxsize=None)
def _return_edge_count(body: BodyName, home: BodyName) -> int:
    """Number of edges in the cheapest RETURN profile.  Each edge is a
    distinct mission phase (launch / SOI transition / capture / descent /
    return leg), so the count is a direct proxy for "planning complexity"
    — how many burn windows, how many transfers, how many SOI changes.

    Returns 0 if there's no return profile (caller falls back to 1.0)."""
    builder = _mission_builder_for(home)
    profiles = builder.profiles_for(body, MissionType.RETURN)
    if not profiles:
        return 0
    return len(min(profiles, key=lambda p: sum(e.base_dv for e in p)))


def _intra_system(body: BodyName, home: BodyName) -> bool:
    """Body and home share an SOI tree.  Four ways this is true:

    - ``body == home`` itself
    - body is home's moon         (e.g. Laythe → Vall, but only when home=Jool)
    - body is home's parent       (e.g. Laythe → Jool — Jool is Laythe's planet)
    - body is home's sibling moon (e.g. Laythe → Vall, both moons of Jool)

    Used by ``_mission_scalar`` to strip the interplanetary premium from
    bodies that become intra-system targets from the new home."""
    if body == home:
        return True
    body_obj = BODY_BY_NAME[body]
    home_obj = BODY_BY_NAME[home]
    if body_obj.parent == home:
        return True
    if body == home_obj.parent:
        return True
    if body_obj.parent is not None and body_obj.parent == home_obj.parent:
        return True
    return False


def _mission_scalar(
    body: BodyName, home: BodyName,
    ref_body: BodyName, ref_home: BodyName,
) -> float:
    """Composite scaling factor: Δv ratio × edge-count ratio × intra-system
    penalty, computed against a reference (body, home) pair.

    Three components, each independently motivated:

    1. **Δv ratio** ``dv(B,H) / dv(refB,refH)`` — preserves Squad's
       reward-per-Δv calibration across home changes.
    2. **Edge-count ratio** ``edges(B,H) / edges(refB,refH)`` — captures
       mission planning complexity orthogonal to Δv.  Eeloo→Mun and
       Kerbin→Mun have similar Δv but Eeloo→Mun is far more complex
       (multiple SOI transitions); the edge ratio rewards that.
    3. **Intra-system penalty** ``÷ 1.67`` when the actual case is
       intra-system but the reference is not.  Strips Squad's implicit
       "interplanetary premium" when a stock-interplanetary body becomes
       a sibling-moon hop from the new home.

    Falls back to 1.0 when reference data is missing / unreachable."""
    dv_now = _return_dv(body, home)
    dv_ref = _return_dv(ref_body, ref_home)
    if (dv_now == float("inf")
            or dv_ref == float("inf")
            or dv_ref == 0.0):
        return 1.0

    ec_now = _return_edge_count(body, home)
    ec_ref = _return_edge_count(ref_body, ref_home)
    edge_factor = (ec_now / ec_ref) if (ec_now > 0 and ec_ref > 0) else 1.0

    # Premium is only stripped when shifting interplanetary -> intra-system;
    # the converse (Mun from Eeloo: intra -> interplanetary) is handled by
    # the edge-count ratio naturally rewarding the added phases.
    actual_intra = _intra_system(body, home)
    ref_intra = _intra_system(ref_body, ref_home)
    intra_factor = (1.0 / _INTERPLANETARY_PREMIUM) if (actual_intra and not ref_intra) else 1.0

    return (dv_now / dv_ref) * edge_factor * intra_factor


def effective_situation_mult(
    body: BodyName, situation_attr: str, home: BodyName,
) -> float:
    """THE source of truth for home-relative science multipliers.  Returns
    the effective stock-equivalent multiplier for ``body``'s ``situation_attr``
    (a Body field name like ``"landed_mult"``) given the player's ``home``.

    ``science_budget`` (rules + sphere-ladder) computes per-situation
    contributions from this function; ``home_relative_science_values``
    emits the same values to the client.  Same function, no drift.
    """
    body_obj = BODY_BY_NAME[body]
    if home == BodyName.KERBIN:
        return getattr(body_obj, situation_attr)
    if body == home:
        # Home becomes "Kerbin home" — substitute Kerbin's stock value.
        return getattr(BODY_BY_NAME[BodyName.KERBIN], situation_attr)
    if body == BodyName.KERBIN:
        # Alien Kerbin: borrow Laythe's stock shape (physical analog —
        # atmosphere, ocean, similar gravity) and scale against
        # Laythe-from-Kerbin as the reference baseline.  Kerbin-from-any-
        # non-Kerbin-home then takes on Laythe-from-Kerbin's reward profile.
        laythe = BODY_BY_NAME[BodyName.LAYTHE]
        scalar = _mission_scalar(
            BodyName.KERBIN, home,
            BodyName.LAYTHE, BodyName.KERBIN,
        )
        return getattr(laythe, situation_attr) * scalar
    # Other non-home bodies: reference is body-from-Kerbin, the stock
    # calibration.  _mission_scalar applies Δv ratio + edge-count ratio
    # + intra-system penalty as appropriate.
    return getattr(body_obj, situation_attr) * _mission_scalar(
        body, home, body, BodyName.KERBIN,
    )


# Fixed, complete list of CelestialBodyScienceParams fields the client
# writes.  Every body entry in ``home_relative_science_values`` must
# contain ALL of these keys — missing fields hard-fail on the client.
SCIENCE_SITUATIONS: tuple[str, ...] = (
    "landed",
    "splashed",
    "fly_low",
    "fly_high",
    "space_low",
    "space_high",
    "recovery",
)


def home_relative_science_values(home: BodyName) -> dict[str, dict[str, float]]:
    """Slot-data shape: ``{body_name: {situation: absolute_value, ...}}``.
    Returns ``{}`` when ``home == Kerbin`` (the client treats absent key as
    "feature off, leave stock alone").

    When the key IS present, the dict MUST contain every body in
    ``ALL_BODIES`` and every situation in ``SCIENCE_SITUATIONS``.  The
    client validates this and hard-fails on any missing entry — no
    silent defaults, no "scalar 1.0 fallback".

    All values are computed via ``effective_situation_mult`` — the same
    function ``science_budget`` consumes on the server.  The client
    receives absolute values and writes them directly into
    ``CelestialBody.scienceValues``; no math happens on the client, so
    server and client cannot drift.
    """
    if home == BodyName.KERBIN:
        return {}
    out: dict[str, dict[str, float]] = {}
    for body in ALL_BODIES:
        out[body.name.value] = {
            field: effective_situation_mult(body.name, attr, home)
            for field, attr in SITUATION_FIELD_TO_ATTR.items()
        }
    return out


# ---------------------------------------------------------------------------
# Science budget estimator (used by tech-tree access rules)
# ---------------------------------------------------------------------------

def science_budget(
    body: Body,
    has_thermometer: bool,
    has_barometer: bool,
    has_capsule: bool,
    can_land_crewed: bool,
    home: BodyName,
    psi_tier: int = 0,
    *,
    can_land_uncrewed: bool,
) -> float:
    """
    Estimate the total science collectible from *body* given the player's
    current instrument and crew capabilities.

    Conservative (golden rule): uses min(fly_low, fly_high) for flying
    situations, does not count surface-sample crew value without crewed landing,
    and does not count surface *instrument* science without an (uncrewed)
    landing — surface readings require physically landing a craft, and the
    client only awards them on a real touchdown.  ``can_land_uncrewed`` is the
    player's ability to land a (robotic) craft; ``can_land_crewed`` (which
    implies it) additionally unlocks the surface-sample crew value.

    Base instrument values (from KSP science definitions):
      Thermometer: 8   Barometer: 12   Crew Report: 5   EVA Report: 8
      Surface Sample: 30

    Science = base_value * situation_multiplier * recovery_factor
    The recovery_factor (0.25 for transmit) is NOT applied here — we assume
    the player physically recovers the data, giving full science value.
    This is the upper bound; safety factors in can_afford_tier() discount it.

    ``psi_tier`` is the player's Progressive Science Instrument level (0–3).
    Each tier unlocks LIGHT (≤50 kg) experiment modules whose payload cost
    is negligible — Goo, Atmospheric Fluid Spectro-Variometer, Accelerometer,
    Gravimeter.  ``mobileMaterialsLab`` (Sci Jr., 200 kg) is intentionally
    NOT counted — its payload cost isn't modelled by the capability system,
    so counting its yield as free would over-estimate accessible science.

    ``home`` is the player's starting body.  Each situation multiplier is
    looked up through ``effective_situation_mult`` — the same function the
    slot_data emitter uses — so the rules-side accounting and the runtime
    yields the client writes into ``CelestialBody.scienceValues`` are
    arithmetically identical.  For Kerbin home this is just the stock mult.
    """
    base_instr: float = 0.0
    if has_thermometer:
        base_instr += 8.0
    if has_barometer:
        base_instr += 12.0

    # Progressive Science Instrument contributions, segmented by situation.
    # Tier 1 (light): Goo — works in every situation.
    # Tier 2 (light only): Atmospheric Spec — Landed/Flying on atmospheric
    #   bodies only.  Sci Jr. is skipped (too heavy to count for free).
    # Tier 3 (light): Accelerometer (Landed) + Gravimeter (Landed/Splashed/Space).
    psi_space = (10.0 if psi_tier >= 1 else 0.0) + (20.0 if psi_tier >= 3 else 0.0)
    psi_fly = (10.0 if psi_tier >= 1 else 0.0) + (20.0 if psi_tier >= 2 else 0.0)
    psi_landed = (
        (10.0 if psi_tier >= 1 else 0.0)
        + (20.0 if psi_tier >= 2 and body.has_atmosphere else 0.0)
        + (40.0 if psi_tier >= 3 else 0.0)
    )
    psi_splashed = (10.0 if psi_tier >= 1 else 0.0) + (20.0 if psi_tier >= 3 else 0.0)

    crew_orbital_val: float = (5.0 + 8.0) if has_capsule else 0.0
    crew_surface_val: float = (5.0 + 8.0 + 30.0) if (has_capsule and can_land_crewed) else 0.0

    bn = body.name
    eff_space_low  = effective_situation_mult(bn, "space_low_mult",  home)
    eff_space_high = effective_situation_mult(bn, "space_high_mult", home)
    eff_landed     = effective_situation_mult(bn, "landed_mult",     home)
    eff_splashed   = effective_situation_mult(bn, "splashed_mult",   home)

    # Orbital science (global, not per-biome)
    orbital = (base_instr + psi_space + crew_orbital_val) * (
        eff_space_low + eff_space_high
    )

    # Flying science (atmosphere only; use min to underestimate).
    # ``has_atmosphere`` is the real gate — the effective mults are 1.0 for
    # vacuum bodies (KSP's stock "n/a baseline") so a > 0 check is meaningless.
    flying = 0.0
    if body.has_atmosphere:
        eff_fly_low  = effective_situation_mult(bn, "fly_low_mult",  home)
        eff_fly_high = effective_situation_mult(bn, "fly_high_mult", home)
        flying = (base_instr + psi_fly + crew_orbital_val) * min(
            eff_fly_low, eff_fly_high
        )

    # Landed science (scales with biome count).  Surface INSTRUMENT readings
    # require landing a craft (uncrewed is enough — a probe places the
    # instruments); the surface SAMPLE crew value (in crew_surface_val)
    # additionally requires crewed landing.  A body the player can only orbit
    # yields no surface science.
    landed = 0.0
    if body.can_land and body.num_biomes > 0:
        landed_instr = (base_instr + psi_landed) * eff_landed if can_land_uncrewed else 0.0
        landed = (landed_instr + crew_surface_val * eff_landed) * body.num_biomes

    # Splashed science (ocean biomes only) — same landing gate.
    splashed = 0.0
    if body.has_ocean and body.num_splash_biomes > 0:
        splashed_instr = (base_instr + psi_splashed) * eff_splashed if can_land_uncrewed else 0.0
        splashed = (splashed_instr + crew_surface_val * eff_splashed) * body.num_splash_biomes

    return orbital + flying + landed + splashed


# ---------------------------------------------------------------------------
# Home-system bodies
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def home_system_bodies(home: BodyName) -> frozenset[BodyName]:
    """Bodies that share the home's "local neighbourhood" — no interplanetary
    transfer needed to reach them.

    - Home is a planet → ``{home} ∪ home's moons``.
    - Home is a moon → ``{home, home.parent} ∪ home.parent's other moons``.

    The home-system set gates the "launch clamps required for interplanetary"
    rule in capability and the item-pacing sphere-0 split in rules.  For
    home=Kerbin this returns ``{Kerbin, Mun, Minmus}``.

    Cached because ``min_relay_tier`` calls this once per edge during
    profile evaluation (~millions of times per fill) and the inputs only
    range over the 17 ``BodyName`` values.
    """
    home_body = BODY_BY_NAME[home]
    if home_body.parent is None:
        # Planet home: home + its moons.
        return frozenset(
            b.name for b in ALL_BODIES
            if b.name == home or b.parent == home
        )
    # Moon home: home + parent planet + parent's other moons.
    parent = home_body.parent
    return frozenset(
        b.name for b in ALL_BODIES
        if b.name == home or b.name == parent or b.parent == parent
    )


# ---------------------------------------------------------------------------
# Home-body altitude milestone ladder
# ---------------------------------------------------------------------------

# Hand-tuned fraction-of-safe-altitude schedule per N.  The shape is
# "denser at the low end, with a few round-number stops in the middle,
# converging on the safe-altitude target."  Not a pure power-law — the
# user prefers a few clustered low milestones over uniform spacing.
# Add new entries here as N grows; ``home_altitude_milestones`` rejects
# unknown N rather than guessing.
_HOME_ALTITUDE_FRACTIONS: dict[int, tuple[float, ...]] = {
    7: (0.071, 0.143, 0.229, 0.286, 0.429, 0.643, 1.0),
}


def home_altitude_milestones(home: Body, n: int = 7) -> list[int]:
    """Return the suborbital altitude-record milestones (km) for ``home``.

    Multiplies a hand-tuned fraction schedule by ``home.safe_altitude_km``,
    rounds to whole km, and deduplicates by forcing each subsequent
    milestone to be at least 1 km above the previous.  For Kerbin
    (safe=70) at ``n=7`` this yields ``[5, 10, 16, 20, 30, 45, 70]``.

    Raises ``ValueError`` if no fraction schedule exists for ``n``.  The
    expectation is that future scope (more milestones) edits
    ``_HOME_ALTITUDE_FRACTIONS`` to add an explicit hand-tuned curve.
    """
    fractions = _HOME_ALTITUDE_FRACTIONS.get(n)
    if fractions is None:
        raise ValueError(
            f"home_altitude_milestones: no fraction schedule for n={n}. "
            f"Known schedules: {sorted(_HOME_ALTITUDE_FRACTIONS)}. "
            f"Add an entry to _HOME_ALTITUDE_FRACTIONS."
        )
    if home.safe_altitude_km <= 0.0:
        raise ValueError(
            f"home_altitude_milestones: {home.name} has no safe_altitude_km "
            f"set (got {home.safe_altitude_km})."
        )
    raw = [f * home.safe_altitude_km for f in fractions]
    out: list[int] = []
    prev = 0
    for r in raw:
        # Strict-ascending dedup: each milestone is at least 1 km above
        # the previous.  Matters for tiny vacuum bodies (Gilly, Pol)
        # where the fraction schedule compresses into a few km.
        candidate = max(prev + 1, int(round(r)))
        if candidate > int(round(home.safe_altitude_km)):
            # Dedup pushed past the top.  The fraction schedule isn't
            # scaled appropriately for this body's safe_altitude.  Phase
            # 3a only generates Kerbin milestones in production, so this
            # only fires if a future caller asks for milestones on a
            # body with safe_altitude < n+a-few.  Real fix is a body-
            # scale-aware schedule (Phase 3b/4).
            raise ValueError(
                f"home_altitude_milestones: n={n} produces milestone "
                f"{candidate} km > safe_altitude={home.safe_altitude_km} km "
                f"for {home.name}.  Reduce n or add a body-tailored "
                f"fraction schedule."
            )
        out.append(candidate)
        prev = candidate
    return out


# ---------------------------------------------------------------------------
# Parent gating helper
# ---------------------------------------------------------------------------

def parent_chain(body: Body) -> list[str]:
    """Return [body.name, parent.name, grandparent.name, ...] up to a planet."""
    chain: list[str] = []
    current: Optional[Body] = body
    while current is not None:
        chain.append(current.name)
        current = BODY_BY_NAME.get(current.parent) if current.parent else None
    return chain


# ---------------------------------------------------------------------------
# Relay tier requirement
# ---------------------------------------------------------------------------

# Heliocentric-separation thresholds for relay-tier requirements.
#
# The antenna must hold the link for the whole stay at the target, so
# the relevant distance is the *worst-case* heliocentric separation:
# when target and home are at opposition the signal travels
# ``r_target + r_home`` (across the solar system with the sun in
# between).  Conjunction would be ``|r_target - r_home|`` but that's
# the fleeting best case — sizing the antenna for it leaves the player
# stranded for half the synodic period.
#
# The tier ceilings are physics-derived: a relay of antennaPower ``P_a`` against
# a level-3 DSN (2.5e11) closes a link out to ``sqrt(P_a * 2.5e11)`` metres.
# Tier 3 (RA-15, 1.5e10): ``sqrt(1.5e10 * 2.5e11) = 6.12e10 m = 4.50 AU``.
# Tier 4 (RA-100, 1e11):  ``sqrt(1e11   * 2.5e11) = 1.581e11 m = 11.63 AU``.
# With the real semi-major-axis ``solar_distance_au`` values this reproduces the
# original hand-tuned per-body tiers exactly (Moho 2, Eve / Duna / Dres 3, Jool /
# Eeloo 4) while staying homogeneous for any starting body.  The lower thresholds
# remain the original hand-tuned bands.
#
# The tier-4 ceiling matters for the DSN model (``comms.py``): with a below-max
# Tracking Station the separation is scaled up, and a scaled separation beyond
# 11.63 AU means *no antenna* can hold the link at that DSN — the ``uncapped``
# lookup returns tier 5 so the gate charges a Tracking-Station upgrade instead of
# falsely reporting the body reachable.  The plain (capped) lookup keeps its old
# ``return 4`` for the antenna gate, so the option-off path is byte-identical.
_RELAY_TIER_AU_THRESHOLDS: tuple[tuple[float, int], ...] = (
    (0.5, 0),    # negligible separation (unused — home_system bypass)
    (1.3, 1),    # innermost band — unused under stock home distances
    (1.5, 2),    # Moho (opposition 1.387 AU from Kerbin)
    (4.5, 3),    # RA-15 max range @ DSN L3; Eve (1.72) / Duna (2.52) / Dres (4.003)
    (11.63, 4),  # RA-100 max range @ DSN L3; boundary for "no antenna reaches"
)


def relay_tier_for_separation_au(sep_au: float, uncapped: bool = False) -> int:
    """Antenna tier needed to hold a link across ``sep_au`` of heliocentric
    separation at a *maxed* DSN ground station.  Extracted so the DSN model
    (``comms.py``) can reuse the exact threshold table with a scaled
    separation.  See ``_RELAY_TIER_AU_THRESHOLDS``.

    ``uncapped`` (default False) controls the beyond-tier-4 fallback.  The
    antenna gate caps at 4 (the highest real antenna) — its old behavior.  The
    DSN model passes ``uncapped=True`` so a scaled separation past tier-4's
    11.63 AU reach returns 5, meaning "no antenna reaches at this DSN" — the
    gate then demands a Tracking-Station upgrade rather than falsely passing.
    """
    for threshold, tier in _RELAY_TIER_AU_THRESHOLDS:
        if sep_au < threshold:
            return tier
    return 5 if uncapped else 4


def min_relay_tier(body: BodyName, home: BodyName, sep_scale: float = 1.0,
                   uncapped: bool = False) -> int:
    """Minimum relay tier required to keep a link between ``body`` and
    ``home``.

    Bodies in the home's local neighbourhood (the home itself, plus
    moons-of-home for planet homes, or parent-and-siblings for moon
    homes) return tier 0 — comms inside a parent SOI don't need an
    interplanetary antenna.  Everything else is gated by the worst-case
    heliocentric separation (``r_target + r_home``), which is what the
    antenna must hold for the half-synodic period when the bodies sit
    on opposite sides of the sun.

    ``sep_scale`` (default 1.0) multiplies the heliocentric separation before
    the tier lookup.  The thresholds are derived at a maxed DSN; a below-max
    DSN shrinks reach, which the DSN model (``comms.py``) expresses as
    ``sep_scale > 1.0`` (a farther *effective* separation → a higher required
    tier).  ``sep_scale == 1.0`` reproduces the maxed-DSN behavior exactly.

    Returns 0..4.  See ``_RELAY_TIER_AU_THRESHOLDS``.

    Hot-path callers should not invoke this directly — they should
    fetch a precomputed dict via ``relay_tier_table_for(home)`` (a flat
    dict lookup is faster than the function-call + branch path here,
    and the result depends only on ``home`` which is fixed per world).
    """
    if body == home or body in home_system_bodies(home):
        return 0
    max_sep_au = (BODY_BY_NAME[body].solar_distance_au
                  + BODY_BY_NAME[home].solar_distance_au)
    return relay_tier_for_separation_au(max_sep_au * sep_scale, uncapped)


# Per-home precomputed relay-tier tables.  The inner dict is keyed by
# destination ``BodyName`` and built once on first request for a given
# home, then reused — flat dict lookup is significantly faster than the
# ``min_relay_tier`` function path on the per-edge hot loop in
# ``_evaluate_profile`` (called millions of times during fill).
_RELAY_TIER_TABLES: dict[BodyName, dict[BodyName, int]] = {}


def relay_tier_table_for(home: BodyName) -> dict[BodyName, int]:
    """Return ``{body: min_relay_tier}`` for every BodyName, computed
    once per ``home`` and cached.  Use this in any tight loop instead
    of calling ``min_relay_tier`` per edge — a flat dict lookup is
    measurably faster than the function-call + branch path.
    """
    table = _RELAY_TIER_TABLES.get(home)
    if table is None:
        table = {b.name: min_relay_tier(b.name, home) for b in ALL_BODIES}
        _RELAY_TIER_TABLES[home] = table
    return table
