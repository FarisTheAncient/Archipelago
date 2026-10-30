import math
import os
import random
from typing import Any, Union

from BaseClasses import CollectionState, Item, MultiWorld, Tutorial
from Options import OptionError
from worlds.AutoWorld import LogicMixin, WebWorld, World
from settings import Group, FilePath

from . import body_visibility, contracts, items, locations, regions, rules
from .data import lifter_chains
from .parts import part_manager_for
from .ksc_sites import ksc_site_slot_data
from .rules import GoalSpec, resolve_goal_spec, goal_spec_location_names
from .capability import CAPABILITY_ITEMS, RocketCapability
from .data.feasibility import (
    MODEL_INFEASIBLE_BASE, MODEL_INFEASIBLE_DELTAS, BASE_RELEVANT_PACKS,
)
from .bodies import (
    ALL_BODIES, Achievement, BodyName, EdgeType, MissionBuilder, MissionType,
    RandomOrbitParams, TouristSpec, effective_physics_profile_name,
    effective_gameplay_difficulty,
    generate_random_orbit_params, generate_rescue_orbit_params,
    generate_surface_rescue_site_lats, generate_survey_site_lats,
    generate_tourist_manifests, home_relative_science_values,
)
from .items import (
    ITEM_NAME_TO_ID, PROGRESSIVE_LAUNCH_PAD_CAPS, SCIENCE_PACK_AMOUNTS,
    PROGRESSIVE_RD_NAME, PROGRESSIVE_RD_COUNT,
    PROGRESSIVE_VAB_NAME, PROGRESSIVE_TRACKING_STATION_NAME,
    PROGRESSIVE_ASTRONAUT_COMPLEX_NAME, PROGRESSIVE_MISSION_CONTROL_NAME,
)
from .locations import (
    ALL_EVENTS, EVENT_BY_NAME, EventName, KSC_BIOMES, KSC_LOCATION_PREFIX,
    LOCATION_NAME_TO_ID, LocationBuilder, MAX_TECH_SLOTS,
    THRESHOLD_LOCATION_NAMES, TechTreeLocation, event_locations,
    effective_starting_inv_count, effective_tech_slots_per_node,
)

# Curated edge bans: graph subsections too tedious to fly, banned by POLICY
# (independent of the dv feasibility verdict).  Expressed as edges, not
# locations: a mission is banned iff every one of its profiles must traverse a
# banned edge (``MissionBuilder.missions_using_edges``).  Eve's atmospheric
# ascent → Eve return + sample-return are banned (you land, then must ascend to
# come back); Eve flag/landing/orbit, which don't ascend, stay allowed.
# ``AllowEveOnExpert`` drops the ban.  To curate another body, add its edge here
# — the missions, locations (EXCLUDED), contracts, and goals all follow.
_BANNED_EDGES: frozenset[tuple[BodyName, EdgeType]] = frozenset(
    {(BodyName.EVE, EdgeType.ATMOSPHERIC_ASCENT)}
)
from .options import BuffDensity, Difficulty, Goal, GoalContractMode, KSP1Options, PhysicsDifficulty, STARTING_BODY_POOLS, StartingBody, TrapDensity
from .tech_tree import MAX_TIER, NODES_BY_TIER, TECH_NODES, TIER_TO_BAND
from .effects import RD_FACILITY_THRESHOLDS


class KSP1State(LogicMixin):
    """Inject per-player stale flag + cached result onto CollectionState.

    Two independent state-local caches, both invalidated by ``collect``/``remove``:
    the RocketCapability, and the cheap accessible-science sum (which every one of
    the 62 tech-node region entrances would otherwise recompute from scratch for
    the same state — the science sum is identical across all tiers).
    """
    ksp1_cap_stale: dict[int, bool]
    ksp1_cap_result: dict[int, RocketCapability]
    ksp1_sci_stale: dict[int, bool]
    ksp1_sci_result: dict[int, float]

    def init_mixin(self, multiworld: MultiWorld) -> None:
        players = multiworld.get_game_players("Kerbal Space Program 1")
        self.ksp1_cap_stale = {p: True for p in players}
        self.ksp1_cap_result = {}
        self.ksp1_sci_stale = {p: True for p in players}
        self.ksp1_sci_result = {}


class KSP1WebWorld(WebWorld):
    theme = "ocean"
    tutorials = [
        Tutorial(
            "Setup Guide",
            "A guide to setting up the Kerbal Space Program Archipelago client",
            "English",
            "setup_en.md",
            "setup/en",
            ["nickdavies"],
        )
    ]


def _validate_goal_spec_has_targets(
    spec: GoalSpec, options: KSP1Options, home: BodyName,
) -> None:
    """Raise ``OptionError`` if the resolved goal has nothing to achieve.

    Happens when every body in the chosen preset is the player's home —
    e.g. ``goal=mun_flag`` with ``starting_body=mun``, or
    ``goal=duna_return`` with ``starting_body=duna``.  ``resolve_goal_spec``
    strips home from every body list, so a preset whose only target was
    home becomes empty.  We fail loudly at gen time instead of letting
    fill produce a trivially-winnable seed.
    """
    has_targets = (
        spec.complete_tech_tree
        or spec.flag_bodies
        or spec.return_bodies
        or spec.sample_return_bodies
        or spec.orbit_bodies
        or spec.flyby_bodies
    )
    if has_targets:
        return
    raise OptionError(
        f"KSP1: starting_body={home.value!r} is incompatible with "
        f"goal={options.goal.current_key!r} — every body in the preset is "
        "the home body, so the goal would be trivially complete at launch. "
        "Pick a different starting body, a different goal, or use a "
        "custom goal that targets a non-home body."
    )


def _validate_goal_not_excluded(
    spec: GoalSpec, exclude_locations: frozenset[str],
) -> None:
    """Raise ``OptionError`` if any mission-event goal location is in
    ``exclude_locations``.

    Excluding a mission-event goal location (e.g. ``Tylo Return 1`` for a
    Laythe-home ``jool_moons_return`` seed) is always a user mistake: the
    location holds no progression, but the goal still requires reaching
    it, and the sphere ladder treats excluded goals as unreachable and
    blows up at fill time.

    Tech-tree goal locations (Complete Tech Tree preset) are
    *intentionally* compatible with ``exclude_late_tech_tree`` — the
    player "completes" them by spending science, not by AP placing
    progression there.  Skipped here.
    """
    from .rules import goal_spec_location_names
    goal_names = set(goal_spec_location_names(spec))
    # Tech-tree goal locations are exempt (the player completes them by spending
    # science, not by AP placing progression).  ``goal_spec_location_names`` adds
    # them as exactly ``str(TechTreeLocation(leaf, 1))``; subtract that same
    # structured set rather than prefix-matching the name.
    from .tech_tree import LEAF_TECH_NODES
    tech_goal_names = {
        str(TechTreeLocation(n.display_name, 1)) for n in LEAF_TECH_NODES
    }
    mission_goal_names = goal_names - tech_goal_names
    conflict = mission_goal_names & exclude_locations
    if not conflict:
        return
    sorted_conflict = sorted(conflict)
    raise OptionError(
        f"KSP1: exclude_locations covers goal location(s) "
        f"{sorted_conflict!r} for goal {spec.display_name!r}.  Remove "
        "these names from exclude_locations (or pick a different goal). "
        "Default exclude_locations is empty as of v0.4 — if these came "
        "from an older yaml, delete the stale entries."
    )


def _validate_goal_contracts_registrable(goal_contract_specs) -> None:
    """Raise ``OptionError`` if any goal contract lacks a registered location.

    Goal contracts are emitted for every goal achievement unconditionally — no
    ``body_compatible`` filter (see ``_goal_contract_specs``) — so a goal body
    that can't host its mission type would produce a ``ContractSpec`` whose
    location was never registered, and the lookup would ``KeyError`` deep in
    ``create_regions``.  The orbit/flyby body lists are option-validated against
    ``ORBITABLE_BODY_NAMES`` (the star has no missions), so this is defense in
    depth: fail fast with a clear message if any path ever slips one through.
    """
    from .locations import CONTRACT_LOCATION_NAME_SET
    bad = sorted(
        s.location_name for s in goal_contract_specs
        if s.location_name not in CONTRACT_LOCATION_NAME_SET
    )
    if not bad:
        return
    raise OptionError(
        f"KSP1: goal targets a body that can't host its mission type — no "
        f"registered location for {bad!r}.  The star (Sun) has no "
        "orbit/flyby/landing missions; remove it from your goal body lists."
    )


# KSP upgradeable facility ids (must match the client's CareerUpgradesManager).
# All are forced to max in the hacked career; per-building levels are emitted so
# real facility progression can be reintroduced one building at a time later.
_FACILITY_IDS: tuple[str, ...] = (
    "SpaceCenter/VehicleAssemblyBuilding",
    "SpaceCenter/SpaceplaneHangar",
    "SpaceCenter/LaunchPad",
    "SpaceCenter/Runway",
    "SpaceCenter/TrackingStation",
    "SpaceCenter/MissionControl",
    "SpaceCenter/AstronautComplex",
    "SpaceCenter/ResearchAndDevelopment",
    "SpaceCenter/Administration",
)
_MAX_FACILITY_LEVEL = 2  # stock 0/1/2 (level-3 buildings)

# Facilities the buildings_in_logic option gates as AP progression.  When the
# option is on these START at level 0 (the player upgrades them by collecting
# the curated building progressives); every other facility stays maxed.  The
# Launch Pad is gated separately via progressive_launch_pad (its tonnage caps
# ride their own slot_data key).  VAB/SPH stay maxed this release (their
# part-count gate is a follow-up).  The gated set: Astronaut Complex (EVA),
# Tracking Station (DSN comms range + patched conics), Mission Control (maneuver
# nodes) and R&D (science-cost cap on which tech nodes may be bought).
_GATED_FACILITY_IDS: tuple[str, ...] = (
    "SpaceCenter/AstronautComplex",
    "SpaceCenter/TrackingStation",
    "SpaceCenter/MissionControl",
    "SpaceCenter/ResearchAndDevelopment",
)

# item name -> {"facilities": [ids], "thresholds": [counts]}.  Emitted in
# slot_data (``career.facility_item_map``) so the dumb client actuates building
# unlocks generically instead of hardcoding names — adding a future building is a
# server-only change.  ``facilities`` is a list so one item can drive several
# (VAB drives VAB+SPH).  ``thresholds`` maps the accumulated item count to a
# facility level: level = count of thresholds that are <= the item count, then
# clamped by the client to the facility's max level and floored at the
# building_levels start (never lowered).  Increment buildings use [1, 2]; the R&D
# facility rides the Progressive R&D count on the deliberate
# ``RD_FACILITY_THRESHOLDS`` schedule (building upgrades placed so the science-cost
# cap never binds before the Progressive R&D band — see effects.py).
#
# VAB is LATENT this release (not in ``_GATED_FACILITY_IDS``, so it ships maxed and
# the client never lowers it): its part-count gate is a later server-only change,
# wired here so enabling it needs no client change.
_FACILITY_ITEM_MAP: dict[str, dict] = {
    PROGRESSIVE_ASTRONAUT_COMPLEX_NAME: {
        "facilities": ["SpaceCenter/AstronautComplex"], "thresholds": [1, 2]},
    PROGRESSIVE_TRACKING_STATION_NAME: {
        "facilities": ["SpaceCenter/TrackingStation"], "thresholds": [1, 2]},
    PROGRESSIVE_MISSION_CONTROL_NAME: {
        "facilities": ["SpaceCenter/MissionControl"], "thresholds": [1]},
    PROGRESSIVE_RD_NAME: {
        "facilities": ["SpaceCenter/ResearchAndDevelopment"],
        "thresholds": list(RD_FACILITY_THRESHOLDS)},
    PROGRESSIVE_VAB_NAME: {
        "facilities": ["SpaceCenter/VehicleAssemblyBuilding",
                       "SpaceCenter/SpaceplaneHangar"], "thresholds": [1, 2]},
}

class KSPSettings(Group):
    class UTPackPath(FilePath):
        """Path to the map pack zip"""
        required=False
        ut_dialog_name="Select Map Zip"

    ut_pack_path: Union[UTPackPath,str] = UTPackPath("")


class KSP1World(World):
    """
    Kerbal Space Program is a space flight simulation game where you design and
    fly rockets to explore the Kerbol system.  Parts are randomized across the
    multiworld, and mission completions are the location checks.
    """

    game = "Kerbal Space Program 1"
    web = KSP1WebWorld()
    ut_can_gen_without_yaml = True

    # Tech tree entrance rules use can_reach_region() for parent dependencies.
    # The auto version retries blocked connections when new regions are reached;
    # the explicit version requires manual indirect condition registration.
    explicit_indirect_conditions = False

    options_dataclass = KSP1Options
    options: KSP1Options
    settings: KSPSettings

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID

    # Fingerprint → RocketCapability, shared across all CollectionState copies
    capability_cache: dict[frozenset[tuple[str, int]], RocketCapability]

    # Resolved goal specification (preset or custom).
    goal_spec: GoalSpec

    # Mission graph builder for this world.  Pinned to Kerbin here; owned
    # by the world so its data lifetime matches the rest of the per-world
    # state.
    mission_builder: MissionBuilder

    # Per-world home-body location set (11 home specials: first launch /
    # landing / crash, altitude milestones, first staging — plus the single
    # body-agnostic "Splashdown" entry).  Owned alongside ``mission_builder``
    # so the two stay in sync on the same home.
    location_builder: LocationBuilder

    # AP location names whose mission the dv model can't verify from this
    # world's home, even given a full progressive kit + every part.
    # Looked up at world-init time from the checked-in base+delta
    # ``MODEL_INFEASIBLE_BASE`` table (regenerated offline by
    # ``scripts/generate_feasibility.py``).  Completion-condition rules
    # for these locations fall back to the "all-parts collected" proxy
    # because the dv model can't model their ascents (Eve's 8 km/s,
    # Laythe's atmospheric Jool-system return, etc.).
    model_infeasible_locations: frozenset[str]

    # Contracts generated for this seed (paced into the run as items). Non-goal
    # vs goal-achievement contracts; both are ContractSpec. Set in generate_early.
    contract_specs: list
    goal_contract_specs: list
    # Hidden-body visibility (set in generate_early). ``body_visibility_mode`` is
    # the RESOLVED concrete option value (auto already collapsed to
    # home_only/home_system). ``hidden_bodies`` is every body hidden at start;
    # ``gated_hidden_bodies`` is the subset that gets a Discover gate + item
    # (hidden bodies that own — or parent a hidden owner of — a location). All
    # empty when the feature is off (all_visible).
    body_visibility_mode: int
    hidden_bodies: frozenset
    gated_hidden_bodies: list
    # Goal-mode (count / progressive_unlock) state. Resolved in generate_early.
    # ``contracts_required`` is X (completed non-goal contracts needed for the
    # goal). ``contract_threshold_defs`` is the list of
    # ``(threshold_location_name, required_count, locked_item_name)`` triples —
    # each threshold is a pre-filled location the client reports once the
    # completed-contract count reaches ``required_count``, releasing the locked
    # goal contract item (or Progressive R&D copy for the tech-tree goal). Empty
    # in findable / starting modes.
    contracts_required: int
    contract_threshold_defs: list
    # Part ksp_names this seed's contracts require — promoted to progression in
    # items.create_item so AP guarantees them reachable before the contract.
    contract_required_part_names: frozenset[str]

    def __init__(self, multiworld: MultiWorld, player: int):
        super().__init__(multiworld, player)
        self._ut_active = False
        self.tracker_world = { #normally a ClassVar but the map index requires crimes
            "map_page_folder":"tracker",
            "external_pack_key":"ut_pack_path",
            "map_page_maps":"maps.json",
            "map_page_locations":"locations.json",
            "map_page_index":self.map_index
        }

    def map_index(self, data) -> int:
        return self.options.starting_body.value #This option is numbered the same as the json (for now)

    def generate_early(self) -> None:
        """Resolve goal spec and apply ExcludeLateTechTree."""
        self.capability_cache = {}

        # UT regen: restore options from original generation's slot_data before
        # part_manager / mission_builder / navigation gates are derived.
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        if isinstance(passthrough, dict) and self.game in passthrough:
            self._apply_slot_data(passthrough[self.game])

        # Resolve the home-system navigation requirements (HomeSystemConics /
        # HomeSystemNodes + Difficulty) to plain booleans once — the capability
        # translation reads these instead of options.  Rendezvous and
        # interplanetary always need conics+nodes; only local (moon) transfers
        # scale with these.
        from .options import (
            resolve_home_system_conics, resolve_home_system_nodes,
        )
        _diff = self.options.difficulty.value
        self.local_needs_conics: bool = resolve_home_system_conics(
            self.options.home_system_conics.value, _diff)
        self.local_needs_nodes: bool = resolve_home_system_nodes(
            self.options.home_system_nodes.value, _diff)
        # Every pooled item name that some access rule gates on (via
        # ``state.has``/``has_all``).  Populated at rule-construction time
        # through the ``rules.require_item(s)`` chokepoint — building the
        # has-closure and recording the dependency in one call makes it
        # impossible to gate on an item without marking it logic-required.
        # The sphere-ladder classification pass keeps every logic-required
        # pooled item PROGRESSION, and ``_assert_gate_items_progression``
        # fails generation if any slipped through — so "a needed item got
        # demoted to USEFUL and stranded" is a construction-time error, not
        # a rare unsolvable seed.
        self.logic_required_items: set[str] = set()
        # Pool keys (atmospheric/standard/planets/all) resolve to a
        # concrete body via the seed RNG, then overwrite the option so
        # downstream code (and slot_data) sees a single body just like
        # if the player had typed it explicitly.  sorted() before
        # choice() keeps the pick deterministic for a given seed.
        key = self.options.starting_body.current_key
        if key in STARTING_BODY_POOLS:
            picked = self.random.choice(sorted(STARTING_BODY_POOLS[key]))
            self.options.starting_body.value = getattr(
                StartingBody, f"option_{picked.value.lower()}"
            )
        # ``starting_body`` option keys are lowercase BodyName values
        # (``option_mun`` → key ``"mun"`` → ``BodyName.MUN``).  The
        # title-case round-trip rebuilds the canonical ``StrEnum`` value.
        home = BodyName(self.options.starting_body.current_key.title())
        # Eve-as-home is supported, but ONLY at expert difficulty (operator
        # decision, 2026-07-06): flying an Eve ascent for every mission is an
        # expert-player undertaking — claiming a casual/normal skill level
        # while planning to complete Eve-home missions is incoherent, and the
        # softer physics margins also make the generous-tail deep missions
        # fragile.  The mesa pad ascent (~8,996 m/s) closes under escalated
        # home-ascent builds with asparagus sub-stages
        # (ESCALATED_HOME_ASCENT_EDGES + parallel_substages), and any stack
        # the single mesa launch can't lift is composed by multi-launch
        # orbital assembly in Eve low orbit — verified honestly by the
        # feasibility table (fully open at the expert 'small' profile).
        if (home is BodyName.EVE
                and self.options.difficulty.value != Difficulty.option_expert):
            raise OptionError(
                "KSP1: starting_body=eve is only supported at "
                "difficulty=expert — an Eve ascent is an expert-player "
                "mission.  Raise the difficulty to expert, or pick a "
                "different starting body."
            )
        self.mission_builder = MissionBuilder(home=home)
        # Player skill/equipment gates (reaction-wheel/RCS/nav assists) from the
        # base Difficulty option.  Carried on the mission_builder so capability +
        # the sphere ladder reach it without threading a param (options.difficulty
        # is already restored by _apply_slot_data under UT before this point).
        self.mission_builder.gameplay = effective_gameplay_difficulty(self.options)
        # Pack-aware source of truth for which parts this world may use. The
        # enabled optional packs come from the option (Stock is always added by
        # PartManager); a disabled pack's parts are then absent from the item
        # pool, capability, the rank table, and the feasibility lookup.
        self.part_manager = part_manager_for(
            frozenset(self.options.enabled_part_packs.value))

        # Per-world RankContext for sphere-ladder + item.rank_sig.
        # ``home_has_atmosphere`` drives the SRB axis scorer; ``enabled_packs``
        # scopes the rank table to the parts this seed can actually grant.
        from .ranks import RankContext
        _atmo_homes = {BodyName.KERBIN, BodyName.EVE, BodyName.DUNA, BodyName.LAYTHE}
        self._rank_context = RankContext(
            home_has_atmosphere=(home in _atmo_homes),
            enabled_packs=self.part_manager.enabled_packs,
            local_needs_conics=self.local_needs_conics,
            local_needs_nodes=self.local_needs_nodes)

        # Model-infeasible-locations set: a checked-in static lookup keyed by
        # (difficulty, home), generated offline by
        # ``scripts/generate_feasibility.py`` so the banned-location set is
        # deterministic per commit hash and never drifts between seeds.  One
        # table per difficulty because feasibility depends on the dv margin.
        # An empty fallback covers homes not yet in the table (defensive).
        # Layered on top: the Eve curated ban (unless AllowEveOnExpert), so Eve
        # surface returns stay out even at difficulties where they're flyable.
        # Unachievable missions — the SINGLE source of truth, canonical as
        # ``(body, mission_type)`` tuples — from two sources unified here:
        #   1. dv-infeasible: the offline per-difficulty table (capability probed
        #      at maximal kit), read directly as ``(body, mission_type)`` pairs.
        #   2. curated edge bans: graph-derived from ``_BANNED_EDGES``.
        # Set on the MissionBuilder so capability (and everything routing through
        # it) treats them as access=False; ``model_infeasible_locations`` (names)
        # is derived from it for the name-keyed consumers (location pass, goal
        # spec, contracts).  The offline generator uses a RAW builder (empty
        # ``unachievable``) so the table keeps measuring true maximal capability.
        diff_name = effective_physics_profile_name(self.options)
        home = self.mission_builder.home
        # Resolve the model-infeasible table for this seed's enabled
        # capability-relevant packs: base ⊕ signed delta (delta absent for the
        # default config and for any pack set that doesn't change feasibility).
        relevant = tuple(sorted(self.part_manager.capability_relevant_packs()))
        _table = MODEL_INFEASIBLE_BASE.get(diff_name, {}).get(home, frozenset())
        if relevant != BASE_RELEVANT_PACKS:
            _add, _remove = MODEL_INFEASIBLE_DELTAS.get(relevant, {}).get(
                diff_name, {}).get(home, (frozenset(), frozenset()))
            _table = (_table | _add) - _remove
        # The table stores canonical (body, mission_type) pairs directly — the
        # deltas are pre-collapsed, so this set algebra needs no name parsing.
        unachievable: set[tuple[BodyName, MissionType]] = set(_table)
        # Eve curation: only base-expert seeds may opt Eve back in.  Gated on
        # base Difficulty (not Physics Difficulty) so a 'zero' physics run on a
        # casual/normal base can never surface Eve.
        eve_allowed = (self.options.allow_eve_on_expert.value
                       and self.options.difficulty.value == Difficulty.option_expert)
        if not eve_allowed:
            # The HOME body is exempt from the curated ban: picking a banned
            # body as the starting body IS the opt-in (every mission from an
            # Eve home traverses the Eve ascent as its pad launch — the ban,
            # written for Eve-as-destination round trips, would otherwise
            # void the whole seed).  The dv feasibility table still gates
            # honestly per difficulty.
            banned = frozenset(e for e in _BANNED_EDGES if e[0] != home)
            unachievable |= self.mission_builder.missions_using_edges(banned)
        self.unachievable_missions = frozenset(unachievable)
        self.mission_builder.unachievable = self.unachievable_missions
        # The builder emits only reachable mission locations — it needs the
        # unachievable set, so it is built here, once that set is known.  It is
        # the single owner of the emitted/excluded split; the name-keyed
        # ``model_infeasible_locations`` (goal spec, contracts) is just its
        # excluded view.  The offline feasibility generator constructs a RAW
        # builder (empty ``unachievable``) so it keeps probing true max kit.
        self.location_builder = LocationBuilder(
            home=home, unachievable=self.unachievable_missions)
        self.model_infeasible_locations = self.location_builder.excluded_mission_names
        self.goal_spec = resolve_goal_spec(
            self.options, self.mission_builder.home,
            self.model_infeasible_locations,
        )
        _validate_goal_spec_has_targets(
            self.goal_spec, self.options, self.mission_builder.home,
        )

        # Seeded target orbits for RANDOM_ORBIT contracts — must exist before
        # generate_contracts (the feasibility + harder-than-goal cap read the
        # real orbit cost via mission_builder.transform_mission). A derived RNG
        # keeps the draw count off the main sequence; UT regen restores the exact
        # orbits from slot_data instead of re-rolling.
        ut_orbits = getattr(self, "_ut_random_orbit_params", None)
        if ut_orbits is not None:
            self.mission_builder.random_orbit_params = ut_orbits
        else:
            self.mission_builder.random_orbit_params = generate_random_orbit_params(
                random.Random(self.random.getrandbits(64)), ALL_BODIES)

        # Seeded collision-safe rescue orbits for KERBAL_RESCUE contracts — same
        # timing/why as the random orbits above (the feasibility + cap read the
        # real reach-the-orbit cost via transform_mission). The derived-RNG draw
        # sits adjacent to the random-orbit draw to keep ordering stable; UT regen
        # restores the exact orbits from slot_data instead of re-rolling.
        ut_rescue = getattr(self, "_ut_rescue_orbit_params", None)
        if ut_rescue is not None:
            self.mission_builder.rescue_orbit_params = ut_rescue
        else:
            self.mission_builder.rescue_orbit_params = generate_rescue_orbit_params(
                random.Random(self.random.getrandbits(64)), ALL_BODIES)

        # Seeded SURFACE_RESCUE site-latitude bounds — same timing/why as the
        # rescue orbits above (feasibility + cap read the site's plane-change
        # cost via transform_mission). Derived-RNG draw adjacent to the other
        # orbit draws; UT regen restores the exact values from slot_data.
        ut_srescue = getattr(self, "_ut_surface_rescue_site_lats", None)
        if ut_srescue is not None:
            self.mission_builder.surface_rescue_site_lats = ut_srescue
        else:
            self.mission_builder.surface_rescue_site_lats = (
                generate_surface_rescue_site_lats(
                    random.Random(self.random.getrandbits(64)), ALL_BODIES))

        # Seeded SURFACE_SURVEY waypoint latitudes — same timing/why as the maps
        # above (transform_mission charges the home ascent inclination). Derived-
        # RNG draw adjacent to the others; UT regen restores the exact values.
        ut_survey = getattr(self, "_ut_survey_site_lats", None)
        if ut_survey is not None:
            self.mission_builder.survey_site_lats = ut_survey
        else:
            self.mission_builder.survey_site_lats = generate_survey_site_lats(
                random.Random(self.random.getrandbits(64)), ALL_BODIES)

        # Seeded TOURISM tourist manifests — same lifecycle. UT regen restores
        # the exact manifests so the client spawns the same tourists.
        ut_tourists = getattr(self, "_ut_tourist_manifests", None)
        if ut_tourists is not None:
            self.mission_builder.tourist_manifests = ut_tourists
        else:
            self.mission_builder.tourist_manifests = generate_tourist_manifests(
                random.Random(self.random.getrandbits(64)), ALL_BODIES)

        # Pre-cached home-ascent lifter: pick one of the offline-generated
        # chains for this (home, pack set) and load its bound table.  The
        # sphere-ladder evaluator consults it instead of re-searching the
        # pad->low-orbit stage (the dominant generation cost).  A derived RNG
        # draw keeps the profile choice off the main sequence (same discipline
        # as the orbit draws above); UT regen restores the exact profile_id.
        # None (no data for this home/pack/difficulty) => raw physics, so this
        # is a pure no-op wherever the table hasn't been generated.
        # KSP_NO_LIFTER_TABLE forces raw physics everywhere (A/B measurement +
        # safety switch); the profile_id draw is still consumed so seed numbers
        # match a table-on run for like-for-like comparison.
        _lifter_off = os.environ.get("KSP_NO_LIFTER_TABLE") == "1"
        pack_key = tuple(sorted(self.part_manager.capability_relevant_packs()))
        n_lifter = lifter_chains.n_profiles(home, pack_key)
        if n_lifter > 0:
            ut_lifter = getattr(self, "_ut_lifter_profile_id", None)
            if ut_lifter is not None:
                self.lifter_profile_id = ut_lifter
            else:
                self.lifter_profile_id = random.Random(
                    self.random.getrandbits(64)).randrange(n_lifter)
            if not _lifter_off:
                self.mission_builder.lifter_table = lifter_chains.load_lifter_table(
                    home, pack_key, self.lifter_profile_id,
                    effective_physics_profile_name(self.options))
        else:
            self.lifter_profile_id = None

        # Generate this seed's contracts (deterministic from the world seed).
        # UT regen restores the exact set from slot_data instead of re-rolling.
        ut_contracts = getattr(self, "_ut_contract_specs", None)
        if ut_contracts is not None:
            self.contract_specs = [s for s in ut_contracts if not s.is_goal]
            self.goal_contract_specs = [s for s in ut_contracts if s.is_goal]
        else:
            self.contract_specs, self.goal_contract_specs = (
                contracts.generate_contracts(self))
        self.contract_required_part_names = contracts.required_part_names_for(
            (*self.contract_specs, *self.goal_contract_specs),
            self.part_manager)
        # Reward locations each non-goal contract emits this seed. Read once here
        # so every per-seed consumer (region registration, access rules, /explain,
        # slot_data) shares one value.
        self.locations_per_contract = contracts.LOCATIONS_PER_CONTRACT
        _validate_goal_contracts_registrable(self.goal_contract_specs)

        # Goal contract mode: validate + resolve X and the threshold locations.
        self._resolve_goal_contract_mode()

        # Hidden-body visibility: resolve the mode (auto -> home_only/home_system
        # by goal reach) and derive which bodies start hidden and which of those
        # need a Discover gate + item. Consumed by create_regions (entrance
        # gates), create_items (pool) and fill_slot_data. The tech tree needs no
        # explicit gate — a hidden body's science is gated on its Discover item in
        # the science rule (rules._cheap_bankable_science), so the tiers that need
        # it require discovery through the ordinary affordability check.
        # all_visible / feature-off yields empty sets, so downstream is a no-op.
        self.body_visibility_mode = body_visibility.resolve_visibility_mode(
            self.options.body_visibility_mode.value, self.goal_spec,
            self.mission_builder.home)
        self.hidden_bodies = body_visibility.hidden_bodies(
            self.body_visibility_mode, self.mission_builder.home)
        self.gated_hidden_bodies = body_visibility.gated_hidden_bodies(
            self.hidden_bodies, regions.location_owning_bodies(self))

        if self.options.exclude_late_tech_tree:
            late_tier_locs: set[str] = {
                str(TechTreeLocation(node.display_name, slot))
                for node in NODES_BY_TIER.get(MAX_TIER, [])
                for slot in range(1, MAX_TECH_SLOTS + 1)
            }
            self.options.exclude_locations.value |= late_tier_locs

        # Final exclude_locations is resolved (yaml + late-tech-tree).  Now
        # verify no goal location ended up excluded — that combination is
        # always unsolvable, so fail at gen time with a clear message
        # rather than letting fill produce an opaque error hours later.
        _validate_goal_not_excluded(
            self.goal_spec, frozenset(self.options.exclude_locations.value),
        )

    def _resolve_goal_contract_mode(self) -> None:
        """Validate the goal-contract-mode configuration and build the threshold
        locations (count / progressive_unlock). Fail fast with ``OptionError`` on
        any unsolvable combination — predictable structural violations belong at
        generate_early, not as an opaque FillError later.

        Sets ``self.contracts_required`` (X) and ``self.contract_threshold_defs``
        (empty in findable / starting). UT regen restores X from slot_data; the
        threshold defs recompute deterministically from the restored contracts."""
        mode = self.options.goal_contract_mode.value
        is_random = self.options.goal.value == Goal.option_random_contracts
        is_tech = self.goal_spec.complete_tech_tree
        needs_thresholds = mode in (GoalContractMode.option_count,
                                    GoalContractMode.option_progressive_unlock)

        # random_contracts is a contracts-driven goal: only count / progressive
        # give it a win condition. findable / starting would be degenerate.
        if is_random and not needs_thresholds:
            raise OptionError(
                "KSP1: goal 'random_contracts' requires goal_contract_mode "
                "'count' or 'progressive_unlock' (it has no destination goal to "
                "find or start with)."
            )

        if not needs_thresholds:
            self.contracts_required = 0
            self.contract_threshold_defs = []
            return

        # count / progressive need contracts to count toward.
        n_contracts = len(self.contract_specs)
        if n_contracts == 0:
            raise OptionError(
                "KSP1: goal_contract_mode 'count'/'progressive_unlock' needs "
                "contracts to complete, but none were generated. Raise "
                "contracts_available (or enable more contract types)."
            )

        # Resolve X (auto = 80% of generated contracts, rounded up).
        ut_x = getattr(self, "_ut_contracts_required", None)
        if ut_x is not None:
            x = int(ut_x)
        else:
            raw_x = self.options.contracts_required_for_goal.value
            raw_y = self.options.contracts_available.value
            if raw_x >= 0 and raw_y >= 0 and raw_x > raw_y:
                raise OptionError(
                    f"KSP1: contracts_required_for_goal ({raw_x}) exceeds "
                    f"contracts_available ({raw_y})."
                )
            x = raw_x if raw_x >= 0 else math.ceil(0.8 * n_contracts)

        # Clamp to the contracts actually generated (candidate shortfall is not a
        # user error — warn and continue rather than abort).
        if x > n_contracts:
            import logging
            logging.warning(
                "KSP1: contracts_required_for_goal %d exceeds the %d contracts "
                "generated this seed; clamping to %d.", x, n_contracts, n_contracts)
            x = n_contracts
        if x < 1:
            raise OptionError(
                "KSP1: goal_contract_mode 'count'/'progressive_unlock' needs at "
                "least 1 contract required for the goal (got "
                f"{x}); pick a positive contracts_required_for_goal."
            )
        self.contracts_required = x

        # Which items the thresholds award, in unlock order:
        #   tech-tree goal -> Progressive R&D copies (count: just the final copy;
        #                     progressive: all PROGRESSIVE_RD_COUNT copies)
        #   body goal      -> goal contract items, easiest mission first
        if is_tech:
            n_copies = (1 if mode == GoalContractMode.option_count
                        else PROGRESSIVE_RD_COUNT)
            threshold_items = [PROGRESSIVE_RD_NAME] * n_copies
        else:
            threshold_items = [
                s.item_name for s in contracts.goal_contracts_easiest_first(self)
            ]

        k = len(threshold_items)
        defs: list = []
        for i, item_name in enumerate(threshold_items, start=1):
            # count: every goal item unlocks together at X. progressive: staggered
            # so the k-th unlocks exactly at X.
            count = x if mode == GoalContractMode.option_count else math.ceil(i * x / k)
            defs.append((THRESHOLD_LOCATION_NAMES[i - 1], count, item_name))
        self.contract_threshold_defs = defs

    def create_regions(self) -> None:
        regions.create_all_regions(self)
        locations.create_all_locations(self)
        rules.create_victory_location(self)
        rules.create_threshold_locations(self)

    def create_items(self) -> None:
        items.create_all_items(self)

    def set_rules(self) -> None:
        rules.set_all_rules(self)
        rules.set_completion_condition(self, self.goal_spec)
        # Build the sphere ladder here rather than in pre_fill: it needs only
        # locations, items, and the intrinsic rules just installed (it uses no
        # entrances/reachability and touches only its own player), and running
        # it before AP's locality_rules (Main.py, ahead of pre_fill) lets it
        # pin the exact home-orbit kit to the player's own world via
        # options.local_items — the sanctioned locality path.
        #
        # Skipped under Universal Tracker: UT regen runs without pre_fill on
        # purpose and falls back to live capability (see _ut_active), so the
        # ladder must stay unbuilt there. Historically that fell out of UT not
        # calling pre_fill; now that the build lives in set_rules (which UT does
        # call), the skip is explicit.
        if not self._ut_active:
            from .sphere_ladder import apply_sphere_ladder
            apply_sphere_ladder(self)

    def fill_hook(self, progitempool, usefulitempool, filleritempool,
                  fill_locations) -> None:
        """Order non-progression items MOST-restricted first for AP's fill.

        ``remaining_fill`` pops items from the END of the pool and places each
        at the first valid location.  A high-rank non-progression part is valid
        only at high spheres (its lower-bound placement rule), so if less-
        restricted items are placed first they can take the scarce high-sphere
        spots and wedge the few high-rank parts at the end (observed: SSR alien
        FILL_ERR on a couple of tank/adapter parts).  Sorting OUR non-progression
        items by ladder position so the hardest sit at the END (popped first)
        makes fill go most-restricted → least-restricted — a generic remedy for
        ordering-induced (not capacity) fill failures.

        Progression is deliberately left untouched: its restrictive fill already
        succeeds, and biasing the progression order is the known-negative lever
        (it exposes counted-progressive self-locking — see the fill-failure
        post-mortem).  Other players' items keep their order.
        """
        from .sphere_ladder import _item_min_sphere
        ladder = getattr(self, "_sphere_ladder", None)
        if ladder is None:
            return
        spheres = ladder.spheres
        for pool in (usefulitempool, filleritempool):
            mine = [it for it in pool if it.player == self.player]
            if not mine:
                continue
            # ascending min_sphere → hardest (highest) last → popped first
            mine.sort(key=lambda it: _item_min_sphere(it, spheres))
            it = iter(mine)
            for i, item in enumerate(pool):
                if item.player == self.player:
                    pool[i] = next(it)

    def pre_output(self) -> None:
        # strict_ladder cross-check: the cheap sphere-bracket access rules
        # were used during fill.  Swap the saved capability access rules
        # back in and confirm the placement is winnable under real physics.
        #
        # This runs in pre_output, NOT post_fill, and the distinction is
        # load-bearing.  ``can_beat_game`` is an ALL-WORLDS check (every slot's
        # completion condition), and other worlds finalise their beatability at
        # different pipeline points than their per-player post_fill.  Super
        # Metroid is the concrete case: its slot only becomes winnable in
        # ``stage_post_fill`` (it sets ``onlyBossLeft``), which AP's call_all
        # runs AFTER every per-player post_fill (worlds/AutoWorld.py:214).  So a
        # can_beat_game from KSP's post_fill sees SM as unbeatable no matter the
        # player order and aborts a perfectly good seed, mislabelled as a KSP
        # physics divergence.  pre_output runs after the whole post_fill/
        # stage_post_fill call_all AND progression balancing AND every world's
        # finalize_multiworld, so all slots are in their final beatable state —
        # yet still before get_sendable_spheres / the spoiler playthrough, so the
        # restore below keeps those cheap.
        saved = getattr(self, "_strict_ladder_saved_rules", None)
        if not saved:
            return
        # Snapshot the cheap bracket rules the fill used, then swap the saved
        # capability rules in for the cross-check.  AP's can_beat_game reads
        # loc.access_rule, so the physics check must temporarily install the real
        # rules — but it is ONE sweep (~1.3s).  Leaving them installed would make
        # the spoiler playthrough's prune pass (many can_beat_game sweeps) re-pay
        # the full get_capability cost (~25s), so restore the cheap rules after a
        # passing check — the spoiler then describes the seed with the same
        # (conservative) rules the fill actually used.
        cheap_rules = {}
        for loc in self.multiworld.get_locations(self.player):
            orig = saved.get(loc.name)
            if orig is not None:
                cheap_rules[loc.name] = loc.access_rule
                loc.access_rule = orig
        # Contract-ruled locations are first-class in ``saved`` now: their real
        # rule (award gate AND the live ``contract_access`` oracle) was merged in
        # by sphere_ladder._install_ladder_rules, so the swap above already put
        # them on the real capability path.  The beatability sweep therefore
        # verifies contract capability alongside missions — no separate
        # mode-toggle needed (contract_access is already computed inside the
        # get_capability the mission rules trigger, so it costs nothing extra).
        # The cheap rules are restored only on the success path — on the failure
        # path below generation aborts, so the installed rules no longer matter.
        if self._ksp_slot_beatable():
            for loc in self.multiworld.get_locations(self.player):
                if loc.name in cheap_rules:
                    loc.access_rule = cheap_rules[loc.name]
            return  # cheap-rule fill is winnable under capability — done

        # The cheap-rule fill produced a placement capability can't solve — a
        # cheap-rule-vs-capability divergence.  There is no rescue: the old
        # whole-seed re-fill was single-player-shaped (it cleared only THIS
        # world's locations, so it could never relocate KSP progression items
        # scattered into other games' worlds) and was deleted.  Divergences are
        # a measured-rare bracketing bug; fail with an actionable message and
        # the punch-list summary.
        hint = (
            "reroll the seed"
            if self.options.accessibility.current_key == "minimal"
            else "reroll the seed, or set accessibility: minimal (the "
                 "supported default for KSP1)"
        )
        raise OptionError(
            f"KSP1 '{self.player_name}': the post-fill physics cross-check "
            "could not verify this seed is completable — a cheap-rule vs "
            f"capability divergence, not an options problem.  Fix: {hint}.  "
            f"home={self.mission_builder.home} "
            f"goal={self.options.goal.current_key} — "
            f"{self._strict_ladder_divergence_summary()}"
        )

    def _ksp_slot_beatable(self) -> bool:
        """Player-scoped ``can_beat_game``: is THIS KSP slot's goal reachable
        under the currently-installed (real-capability) rules?

        The advancement sweep is global — KSP progression items can be placed in
        other players' worlds, and reaching them may require other games' items —
        but only KSP's own completion condition is checked.  Other worlds'
        beatability is their own concern (and AP's core ``can_beat_game`` at
        output time); KSP's physics cross-check must not abort generation, under
        a "physics divergence" message, because some unrelated slot is unbeatable.
        Mirrors ``MultiWorld.can_beat_game`` (BaseClasses.py) but passes
        ``self.player`` to ``has_beaten_game`` so the verdict is KSP-only — which
        also makes it agree with the KSP-scoped divergence summary below."""
        from BaseClasses import CollectionState
        mw = self.multiworld
        state = CollectionState(mw)
        if mw.has_beaten_game(state, self.player):
            return True
        for _ in state.sweep_for_advancements(
                yield_each_sweep=True, checked_locations=state.locations_checked):
            if mw.has_beaten_game(state, self.player):
                return True
        return False

    def _strict_ladder_divergence_summary(self) -> str:
        """Short description of what capability can't reach under the cheap
        fill — the punch-list for closing the divergence.  Scans this world's
        locations AND this world's own progression items placed in other
        players' worlds (in a multiworld the latter are exactly the items a
        local-only scan is blind to)."""
        from BaseClasses import CollectionState, ItemClassification
        st = CollectionState(self.multiworld)
        st.sweep_for_advancements()
        unreached = [
            (l.name, l.item.name)
            for l in self.multiworld.get_locations()
            if l.item and (l.item.classification & ItemClassification.progression)
            and (l.player == self.player or l.item.player == self.player)
            and not l.can_reach(st)
        ]
        sample = ", ".join(f"{n}<-{it}" for n, it in unreached[:5])
        return f"{len(unreached)} unreachable progression; e.g. {sample}"

    def create_item(self, name: str) -> items.KSP1Item:
        return items.create_item(self, name)

    def get_filler_item_name(self) -> str:
        return items.get_filler_item_name(self)

    def fill_slot_data(self) -> dict[str, Any]:
        d = self.options.as_dict(
            "goal", "difficulty", "start_with_launch_clamps", "buildings_in_logic")
        # DeathLink: purely client-side. When on, losing the craft or a Kerbal is
        # broadcast to the multiworld and an incoming death destroys the craft.
        # Generation/logic never reads it.  death_link_on_revert additionally
        # charges a death for reverting a flight that actually launched; it is
        # meaningless without death_link and the client ignores it when off.
        d["death_link"] = self.options.death_link.value                       # 0/1
        d["death_link_on_revert"] = self.options.death_link_on_revert.value   # 0/1
        # Traps: the item NAME is the entire client signal — no payload here.
        # These two keys exist only for Universal Tracker regen fidelity:
        # unlike death_link, trap options reshape the item pool (filler
        # substitution), so regen must restore them.
        d["trap_density"] = self.options.trap_density.value
        d["trap_type_weights"] = dict(self.options.trap_type_weights.value)
        # Buffs: same contract as traps — the item NAME is the entire client
        # signal, and these two keys exist only so Universal Tracker regen
        # reproduces the same filler pool (buffs displace science packs).
        d["buff_density"] = self.options.buff_density.value
        d["buff_types"] = sorted(self.options.buff_types.value)
        # Home body — used by the client mod to drive every per-body
        # comparison (KSC biome prefixes, altitude polling guard, splashdown
        # detection, first-launch / first-landing / first-crash events).
        d["starting_body"] = self.mission_builder.home.value
        # Part packs this seed was generated with (Stock is always present).
        # The client validates the optional packs against installed expansions
        # and warns on a mismatch (enabled-but-not-owned / owned-but-disabled);
        # it needs no part-level detail — contracts arrive fully resolved.
        d["enabled_part_packs"] = sorted(self.part_manager.enabled_packs)
        # KSC site row for an alien starting body: the landing coordinate
        # (lat/lon/terrain alt) + map-decal flag where the cloned KSC cluster
        # is placed.  The client materialises the alien KSC from this instead
        # of carrying a per-body table.  Absent for a Kerbin start (stock KSC).
        ksc_site = ksc_site_slot_data(self.mission_builder.home)
        if ksc_site is not None:
            d["ksc_site"] = ksc_site
        d["tech_slots_per_node"] = effective_tech_slots_per_node(
            self.options, self.options.difficulty.value
        )
        # Resolved physics profile name (generous/comfortable/small/zero).  The
        # C# client ignores it, but Universal Tracker regen needs it to rebuild
        # logic with the same dv margins (else an explicit-physics seed would
        # regen at the auto profile).  Stored as the resolved name so it is also
        # directly usable by the capability diagnostic tools.
        d["physics_difficulty"] = effective_physics_profile_name(self.options)
        d["node_bands"] = {n.node_id: TIER_TO_BAND[n.tier] for n in TECH_NODES}
        d["goal_locations"] = goal_spec_location_names(self.goal_spec)
        d["goal_display_name"] = self.goal_spec.display_name
        # Authoritative data for C# client — eliminates hardcoded dicts.
        d["event_scales"] = {e.name: e.scale for e in ALL_EVENTS}
        d["tech_display_names"] = {n.node_id: n.display_name for n in TECH_NODES}
        # Per-home biome_key -> AP location name map.  The client populates
        # its detection table directly from this; it has no hardcoded copy.
        # ``location_builder.ksc_biomes`` filters out the ``KSC`` catchall
        # entry on non-Kerbin homes (the surrounding terrain doesn't
        # report as that biome off Kerbin).
        d["ksc_biome_locations"] = {
            key: KSC_LOCATION_PREFIX + name
            for key, name in self.location_builder.ksc_biomes
        }
        home_altitude_thresholds = [
            int(loc.threshold_km * 1000)
            for loc in self.location_builder.locations
            if loc.mission_type == MissionType.SOUNDING and loc.threshold_km is not None
            and loc.threshold_km >= 1.0  # exclude "First Crash" (0.1 km)
        ]
        d["home_altitude_thresholds"] = home_altitude_thresholds
        # Backwards-compat alias for client v0.3.x.  The renamed
        # ``home_altitude_thresholds`` key is the canonical form going
        # forward; the legacy ``kerbin_altitude_thresholds`` key will be
        # retired in a future breaking release.
        d["kerbin_altitude_thresholds"] = home_altitude_thresholds
        d["science_packs"] = dict(SCIENCE_PACK_AMOUNTS)
        # Home-relative science scaling.  Server-side ``science_budget``
        # (rules + sphere-ladder) and the client both consume the SAME
        # ``science_scalar(body, home) * stock_mult`` math; the values
        # below are the absolute CelestialBody.scienceValues the client
        # writes.  Key omitted for Kerbin home; client treats absent
        # key as "feature off, leave stock alone".  When present, the
        # dict contains every body and every situation — the client
        # hard-fails on a missing entry (no silent defaults).
        sci_values = home_relative_science_values(self.mission_builder.home)
        if sci_values:
            d["science_values"] = sci_values
        d["starting_inv_count"] = effective_starting_inv_count(
            self.options, self.options.difficulty.value
        )
        # Mass-cap progression: only set when option is enabled. Caps are in
        # tonnes, indexed by collected count of "Progressive Launch Pad"
        # (0..N). The sentinel -1.0 marks "unlimited" so JSON can carry it.
        if self.options.progressive_launch_pad:
            d["progressive_launch_pad_caps"] = [
                cap if cap != float("inf") else -1.0
                for cap in self.mission_builder.launch_pad_caps
            ]

        # Hacked-career directives — server→client, always emitted, actuated
        # verbatim by the dumb client. Career replaces the prior game mode; the
        # client rejects non-Career saves.
        #
        # buildings_in_logic OFF: every facility maxed.  ON (default): the
        # curated-gated facilities (Astronaut Complex, Tracking Station,
        # Mission Control) START at level 0 so the player upgrades them via
        # AP building progressives; ungated facilities stay maxed.
        building_levels = {b: _MAX_FACILITY_LEVEL for b in _FACILITY_IDS}
        if self.options.buildings_in_logic:
            for b in _GATED_FACILITY_IDS:
                building_levels[b] = 0
        d["career"] = {
            "building_levels": building_levels,
            "facility_item_map": _FACILITY_ITEM_MAP,
            "infinite_funds": True,
            "infinite_reputation": True,
            "unlimited_contracts": True,
        }
        # Contract manifest: each entry is self-describing; the client builds a
        # native KSP contract from `parameters` and reports `location` on
        # completion. Goal contracts ride the same array.
        d["contracts"] = [
            spec.to_slot_dict(
                self.mission_builder, self.locations_per_contract,
                part_manager=self.part_manager)
            for spec in (*self.contract_specs, *self.goal_contract_specs)
        ]
        # Seeded RANDOM_ORBIT target orbits, per body — carried so UT regen
        # restores the exact orbits (the client also gets them via each
        # contract's specific_orbit parameter; this is the server-side record).
        d["random_orbit_params"] = {
            str(body): {
                "inclination": p.inclination_deg,
                "sma": p.sma_m,
                "eccentricity": p.eccentricity,
                "lan": p.lan_deg,
                "arg_pe": p.arg_pe_deg,
            }
            for body, p in self.mission_builder.random_orbit_params.items()
        }
        # Seeded KERBAL_RESCUE orbits, per body (radius from centre, m) — carried
        # so UT regen restores the exact orbits; the client also gets each via the
        # contract's rescue parameter (sma). Server-side record.
        d["rescue_orbit_params"] = {
            str(body): r
            for body, r in self.mission_builder.rescue_orbit_params.items()
        }
        # Seeded SURFACE_RESCUE site-latitude bounds, per body (deg) — carried so
        # UT regen restores the exact values; the client also gets each via the
        # contract's surface_rescue parameter (lat). Server-side record.
        d["surface_rescue_site_lats"] = {
            str(body): lat
            for body, lat in self.mission_builder.surface_rescue_site_lats.items()
        }
        # Seeded SURFACE_SURVEY waypoint latitudes, per body (deg) — carried so UT
        # regen restores the exact values; the client gets each via the contract's
        # survey_waypoint parameter (lat + seed). Server-side record.
        d["survey_site_lats"] = {
            str(body): lat
            for body, lat in self.mission_builder.survey_site_lats.items()
        }
        # Seeded TOURISM manifests, per body — carried so UT regen restores the
        # exact tourists; the client also gets each via the tourist parameters.
        d["tourist_manifests"] = {
            str(body): [
                {"name": t.name, "female": t.female, "entry": str(t.entry)}
                for t in manifest
            ]
            for body, manifest in self.mission_builder.tourist_manifests.items()
        }
        # Goal contract mode. ``contract_thresholds`` is the client's watcher map
        # {completed-contract-count -> [threshold locations to report]}: when the
        # player's completed non-goal-contract count reaches a key, the client
        # reports those locations, releasing the goal contract item(s). Empty in
        # findable / starting. ``contracts_required``/``contracts_available`` are
        # carried for UT regen fidelity.
        d["goal_contract_mode"] = self.options.goal_contract_mode.value
        d["contracts_required"] = self.contracts_required
        d["contracts_available"] = self.options.contracts_available.value
        thresholds_map: dict[str, list[str]] = {}
        for loc_name, count, _item in self.contract_threshold_defs:
            thresholds_map.setdefault(str(count), []).append(loc_name)
        d["contract_thresholds"] = thresholds_map
        # Pre-cached lifter profile chosen this seed (or None when no table
        # covers this home/pack/difficulty).  Carried only so UT regen picks
        # the same chain and reproduces the fill; the client ignores it.
        d["lifter_profile_id"] = self.lifter_profile_id
        # Hidden-body visibility.  The resolved mode (never "auto") is always
        # carried so UT regen recomputes the identical hidden set instead of
        # re-resolving auto.  The client-facing keys are emitted only when the
        # feature actually hides something: ``body_item_map`` ({Discover item ->
        # body string}) drives the client's hide/reveal without string parsing;
        # ``allow_undiscovered_bodies`` and ``deep_hide`` are client-only
        # depth/behaviour flags (no server logic effect).
        d["body_visibility_mode"] = self.body_visibility_mode
        if self.gated_hidden_bodies:
            d["body_item_map"] = {
                items.discover_item_name(b): str(b)
                for b in self.gated_hidden_bodies
            }
            d["allow_undiscovered_bodies"] = bool(
                self.options.allow_undiscovered_bodies)
            # Client depth flag: True => deep hide (sphere physically vanishes).
            # Hard-coded on for now; purely client-side (no bearing on logic).
            d["deep_hide"] = True
        return d

    # ------------------------------------------------------------------
    # Universal Tracker hooks
    # ------------------------------------------------------------------

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any] | None) -> dict[str, Any] | None:
        """UT hook: return slot_data to trigger regen with re_gen_passthrough."""
        return slot_data

    def _apply_slot_data(self, slot_data: dict[str, Any]) -> None:
        """Restore options from slot_data during UT regen."""
        # Marks this world as a Universal Tracker regen.  UT rebuilds logic
        # through set_rules only and never runs pre_fill, so the fill-time cheap
        # ladder proxies (_cheap_contract_reps, _science_body_event_reps) are
        # absent.  Contract and science-node access rules read this flag to fall
        # back to the live get_capability oracle instead of their conservative
        # pre-ladder floor (which would report every contract and every tech node
        # permanently out of logic).  Never set during normal generation.
        self._ut_active = True
        self.options.goal.value = slot_data["goal"]
        self.options.difficulty.value = slot_data["difficulty"]
        self.options.start_with_launch_clamps.value = slot_data["start_with_launch_clamps"]
        self.options.buildings_in_logic.value = int(slot_data["buildings_in_logic"])
        self.options.enabled_part_packs.value = frozenset(
            p for p in slot_data["enabled_part_packs"] if p != "Stock")
        # Physics profile: restore as an explicit level so regen logic matches
        # the original margins regardless of base difficulty.  The resolved name
        # (never "auto") maps back through the option's own name_lookup.  Absent
        # on pre-PhysicsDifficulty seeds → leave at the option default (auto).
        phys = slot_data.get("physics_difficulty")
        if phys is not None:
            _name_to_value = {n: v for v, n in PhysicsDifficulty.name_lookup.items()}
            self.options.physics_difficulty.value = _name_to_value[phys]
        # Restore the chosen home body.  ``starting_body`` in slot_data
        # is the canonical ``BodyName`` string (``"Kerbin"`` / ``"Mun"``
        # / ...) — the same value the client mod reads.  Reverse-map to
        # the option integer; ``MissionBuilder`` is built from the restored
        # option in ``generate_early`` after this call returns.
        starting_body = slot_data.get("starting_body")
        if starting_body:
            from .options import StartingBody as _SB
            self.options.starting_body.value = getattr(
                _SB, f"option_{starting_body.lower()}"
            )

        # Stash contracts so generate_early reconstructs the exact set rather
        # than re-randomizing (the contract pick is seed-RNG-derived).
        self._ut_contract_specs = [
            contracts.ContractSpec.from_slot_dict(entry)
            for entry in slot_data.get("contracts", [])
        ]

        # Goal contract mode: restore the options and the resolved X. The
        # threshold defs themselves recompute deterministically in
        # generate_early from the restored contracts + X (evaluate_contract is
        # pure), so only X needs carrying to avoid any auto-derivation drift.
        if "goal_contract_mode" in slot_data:
            self.options.goal_contract_mode.value = slot_data["goal_contract_mode"]
        if "contracts_available" in slot_data:
            self.options.contracts_available.value = slot_data["contracts_available"]
        self._ut_contracts_required = slot_data.get("contracts_required")

        # Traps reshape filler padding, so regen restores both options.  Absent
        # keys mean a pre-trap seed: restore to ``none`` (NOT the option
        # default) so old seeds regenerate trap-free.
        self.options.trap_density.value = int(
            slot_data.get("trap_density", TrapDensity.option_none))
        trap_weights = slot_data.get("trap_type_weights")
        if trap_weights is not None:
            self.options.trap_type_weights.value = dict(trap_weights)

        # Buffs reshape filler padding the same way.  Absent keys mean a
        # pre-buff seed: restore to ``none`` (NOT the option default) so old
        # seeds regenerate buff-free.
        self.options.buff_density.value = int(
            slot_data.get("buff_density", BuffDensity.option_none))
        buff_types = slot_data.get("buff_types")
        if buff_types is not None:
            self.options.buff_types.value = set(buff_types)

        # Restore the exact RANDOM_ORBIT target orbits (re-rolling would diverge).
        rop = slot_data.get("random_orbit_params")
        if rop:
            self._ut_random_orbit_params = {
                BodyName(body): RandomOrbitParams(
                    inclination_deg=entry["inclination"],
                    sma_m=entry["sma"],
                    eccentricity=entry["eccentricity"],
                    # Orientation fields are additive — default 0 when restoring a
                    # slot_data written before they existed.
                    lan_deg=entry.get("lan", 0.0),
                    arg_pe_deg=entry.get("arg_pe", 0.0),
                )
                for body, entry in rop.items()
            }

        # Restore the exact KERBAL_RESCUE orbits (re-rolling would diverge).
        rescue_op = slot_data.get("rescue_orbit_params")
        if rescue_op:
            self._ut_rescue_orbit_params = {
                BodyName(body): float(r) for body, r in rescue_op.items()
            }

        # Restore the exact SURFACE_RESCUE site latitudes (re-rolling would
        # diverge). Absent on pre-feature seeds -> generate_early re-picks.
        srescue_lats = slot_data.get("surface_rescue_site_lats")
        if srescue_lats:
            self._ut_surface_rescue_site_lats = {
                BodyName(body): float(lat) for body, lat in srescue_lats.items()
            }

        # Restore the exact SURFACE_SURVEY waypoint latitudes (re-rolling would
        # diverge). Absent on pre-feature seeds -> generate_early re-picks.
        survey_lats = slot_data.get("survey_site_lats")
        if survey_lats:
            self._ut_survey_site_lats = {
                BodyName(body): float(lat) for body, lat in survey_lats.items()
            }

        # Restore the exact TOURISM manifests (re-rolling would diverge).
        # Absent on pre-feature seeds -> generate_early re-picks.
        tourists = slot_data.get("tourist_manifests")
        if tourists:
            self._ut_tourist_manifests = {
                BodyName(body): tuple(
                    TouristSpec(t["name"], bool(t["female"]),
                                Achievement(t["entry"]))
                    for t in manifest
                )
                for body, manifest in tourists.items()
            }

        # Restore the chosen lifter profile so regen consults the same bound
        # chain (re-rolling would diverge the fill).  Absent on pre-feature
        # seeds -> generate_early re-picks from the seed RNG.
        if "lifter_profile_id" in slot_data:
            self._ut_lifter_profile_id = slot_data["lifter_profile_id"]

        # Restore hidden-body visibility: the resolved mode, so generate_early
        # recomputes the identical hidden set rather than re-resolving auto.
        # Absent on pre-feature seeds -> all_visible, so an old seed never
        # spuriously hides bodies.
        from .options import BodyVisibilityMode as _BVM
        self.options.body_visibility_mode.value = slot_data.get(
            "body_visibility_mode", _BVM.option_all_visible)
        if "allow_undiscovered_bodies" in slot_data:
            self.options.allow_undiscovered_bodies.value = int(
                slot_data["allow_undiscovered_bodies"])

        # A custom goal isn't a single enum value — its body lists ARE the goal,
        # and resolve_goal_spec rebuilds the spec from those option values during
        # regen. Recover them from the goal *contracts* (the victory sentinels),
        # which carry (contract_type, body) structurally; goal_locations holds
        # contract display names that don't round-trip back to a body list.
        if slot_data["goal"] == Goal.option_custom:
            for attr, bodies in contracts.goal_body_lists_from_specs(
                    self._ut_contract_specs).items():
                getattr(self.options, attr).value = bodies

    def explain_rule(self, target_name: str, state: CollectionState) -> list[dict] | None:
        """UT hook: /explain <location> shows rocket design, /explain parts [filter] shows inventory."""
        from .bodies import DIFFICULTY_PROFILES
        from .capability import compute_capability_from_items, evaluate_mission_detailed
        from .capability_format import (
            CHECK_MAP, format_rocket_output, format_parts_list,
            format_contract_output, _discovery_lines,
        )

        # Sub-command: /explain parts [filter]
        if target_name.startswith("parts"):
            filter_text = target_name[5:].strip()
            item_counts: dict[str, int] = {}
            for name in self.item_name_to_id:
                count = state.count(name, self.player)
                if count > 0:
                    item_counts[name] = count
            if filter_text:
                filter_lower = filter_text.lower()
                item_counts = {k: v for k, v in item_counts.items() if filter_lower in k.lower()}
            lines = format_parts_list(item_counts)
            return [{"type": "text", "text": "\n".join(lines)}]

        # Default: look up location, compute capability, show rocket design.
        loc_obj = None
        for loc in self.multiworld.get_locations(self.player):
            if loc.name == target_name:
                loc_obj = loc
                break
        if loc_obj is None:
            return None  # fall back to UT default

        in_logic = loc_obj.can_reach(state)
        info = CHECK_MAP.get(target_name)
        difficulty_name = effective_physics_profile_name(self.options)

        # Hidden-body discovery gate — general over location type: any body
        # location is unreachable until its (and its ancestors') Discover items
        # are held, regardless of rocket physics.  Rendered as a leading section
        # on every report; empty when nothing is gated.
        discovery = _discovery_lines(self._discovery_status(loc_obj, state))

        # Pass the SAME pad-cap gate the live access rules use
        # (_compute_capability), or /explain would render at unlimited pad —
        # disagreeing with the real "In logic" verdict and never showing the
        # multi-launch assembly a constrained pad forces.
        cap, flags = compute_capability_from_items(
            lambda name: state.count(name, self.player),
            difficulty_name,
            bool(self.options.start_with_launch_clamps.value),
            self.mission_builder,
            progressive_launch_pad=bool(self.options.progressive_launch_pad.value),
        )

        # Contract locations aren't in CHECK_MAP — their feasibility needs the
        # extra-payload + mission-transform eval, not the bare milestone path — so
        # render them generically from the spec. Works for any contract type,
        # current or future, with no per-type handling here.
        contract_spec = self._contract_spec_for_name(target_name)
        if contract_spec is not None:
            lines = format_contract_output(
                contract_spec, in_logic,
                state.has(contract_spec.item_name, self.player),
                flags, DIFFICULTY_PROFILES[difficulty_name], difficulty_name,
                self.mission_builder, proxy=False,
                part_manager=self.part_manager,
            )
            return [{"type": "text", "text": "\n".join(discovery + lines)}]

        result = None
        if info is not None:
            diff = DIFFICULTY_PROFILES[difficulty_name]
            result = evaluate_mission_detailed(
                flags, diff, info.body_name, info.mission_type, info.crewed,
                self.mission_builder,
                threshold_km=info.threshold_km,
            )

        lines = format_rocket_output(
            target_name, in_logic, False, info, result, flags,
            difficulty_name, self.mission_builder,
        )
        return [{"type": "text", "text": "\n".join(discovery + lines)}]

    def _discovery_status(self, loc_obj, state: CollectionState):
        """Hidden-body Discover gate for a location's body, for ``/explain``.

        General over location type: the body is read from the location's own
        region (body regions are named by the body), so missions, contracts and
        any future body location are covered uniformly.  Returns ``None`` when
        the hidden-bodies feature gates nothing, or the location has no body
        (KSC / tech / Menu regions)."""
        from .capability_format import DiscoveryStatus
        from .rules import first_undiscovered_body
        from .items import discover_item_name
        gated = frozenset(getattr(self, "gated_hidden_bodies", ()))
        region = loc_obj.parent_region
        if not gated or region is None:
            return None
        try:
            body = BodyName(region.name)
        except ValueError:
            return None  # not a body region (KSC / tech / Menu)
        blocker = first_undiscovered_body(state, self.player, body, gated)
        if blocker is None:
            return DiscoveryStatus(discovered=True)
        return DiscoveryStatus(False, str(blocker), discover_item_name(blocker))

    def _contract_spec_for_name(self, name: str):
        """The ContractSpec whose location matches ``name``, or None. Looks up the
        world's own specs (the source of truth) rather than parsing the display
        name, so /explain covers every contract type without per-type handling."""
        for spec in (*self.contract_specs, *self.goal_contract_specs):
            if name in spec.location_names(self.locations_per_contract):
                return spec
        return None

    def custom_ut_sort(self, region_label: str, location_label: str) -> str:
        """UT hook: sort by body order (ALL_BODIES), then tech tree, then KSC."""
        body_order = {b.name: f"A_{i:02d}" for i, b in enumerate(ALL_BODIES)}
        for prefix, sort_key in body_order.items():
            if location_label.startswith(prefix + " "):
                return f"{sort_key}_{location_label}"
        if region_label.startswith("Tech "):
            return f"B_{location_label}"
        if location_label.startswith(KSC_LOCATION_PREFIX) or location_label.startswith("Starting "):
            return f"Z_{location_label}"
        return f"C_{location_label}"

    def collect_item(self, state: CollectionState, item: Item, remove: bool = False) -> str | None:
        if item.advancement or item.name in CAPABILITY_ITEMS:
            return item.name
        return None

    def collect(self, state: CollectionState, item: Item) -> bool:
        change = super().collect(state, item)
        if change:
            state.ksp1_cap_stale[self.player] = True
            state.ksp1_sci_stale[self.player] = True
        return change

    def remove(self, state: CollectionState, item: Item) -> bool:
        change = super().remove(state, item)
        if change:
            state.ksp1_cap_stale[self.player] = True
            state.ksp1_sci_stale[self.player] = True
        return change
