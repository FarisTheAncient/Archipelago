"""
Region definitions for KSP1 Archipelago.

Region layout:
  * ``Menu`` — the root; holds non-body locations (KSC biomes, starting
    inventory, body-agnostic Splashdown, victory/threshold events).
  * One region per **tech tree node** (62), connected from Menu with entrance
    rules that enforce: progressive R&D band, cumulative science budget, and
    parent-node dependencies (AND/OR by ``any_to_unlock``).
  * One region per **celestial body** that owns (or transitively parents)
    locations.  Planets connect from Menu; each moon connects from its planet
    region, so a moon is reachable only if its planet is.  Every per-body
    location (mission events, home specials, contract completions) lives in its
    body's region.  A **hidden** body's entrance additionally requires its
    ``Discover`` item; the home body always connects straight from Menu (it is
    the start, never gated behind a possibly-hidden parent).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from BaseClasses import CollectionState, Region

from .bodies import ALL_BODIES, BODY_BY_NAME, BodyName
from .items import PROGRESSIVE_RD_NAME, discover_item_name
from .tech_tree import NODE_BY_ID, TECH_NODES, TechNode, TIER_TO_BAND

if TYPE_CHECKING:
    from .world import KSP1World


def body_region_name(body: BodyName) -> str:
    """Canonical AP region name for a celestial body.

    Single source of truth for the body→region-name mapping; both region
    creation (here) and location assignment (``locations.create_all_locations``)
    call this rather than forming the string inline.
    """
    return str(body)


def create_all_regions(world: KSP1World) -> None:
    from .rules import _can_afford_tier, effective_science_safety

    player = world.player
    difficulty = world.options.difficulty.value
    safety = effective_science_safety(world.options, difficulty)
    home = world.mission_builder.home

    menu = Region("Menu", player, world.multiworld)
    world.multiworld.regions.append(menu)

    # Every gated Discover item gates a body region's entrance (its missions /
    # contracts).  Record them as logic-required so the sphere-ladder demote
    # keeps them PROGRESSION; a gate item demoted to USEFUL is skipped by AP's
    # advancement sweep, making the gated locations unreachable.
    # (``_assert_gate_items_progression`` is the backstop.)  The tech tree needs
    # no explicit Discover gate: a hidden body's science is gated on its Discover
    # item in the science rule, so the tiers that need it become affordable only
    # after discovery — the accurate model, which fill provisions on its own.
    world.logic_required_items.update(
        discover_item_name(b) for b in getattr(world, "gated_hidden_bodies", ())
    )

    for node in TECH_NODES:
        region = Region(node.display_name, player, world.multiworld)
        world.multiworld.regions.append(region)

        rule = _make_node_entrance_rule(node, player, safety, home, _can_afford_tier)
        menu.connect(region, rule=rule)

    _create_body_regions(world, menu)

    if world._ut_active:
        _create_fake_entrances(world,menu)


def location_owning_bodies(world: KSP1World) -> frozenset[BodyName]:
    """Bodies that own at least one emitted location in this world.

    A body owns a location if it has emitted mission events, home-body specials,
    or per-body contract completions.  Shared by ``bodies_needing_regions``
    (region creation) and the hidden-body pruning in ``generate_early`` so both
    agree on which bodies actually carry locations.
    """
    lb = world.location_builder
    owning: set[BodyName] = set()
    for ml in lb.mission_locations:
        owning.add(ml.body)
    for hloc in lb.locations:
        if hloc.body is not None:
            owning.add(hloc.body)
    for spec in (*world.contract_specs, *world.goal_contract_specs):
        owning.add(spec.body)
    return frozenset(owning)


def bodies_needing_regions(world: KSP1World) -> list[BodyName]:
    """Bodies that own — or transitively parent — at least one location.

    A moon's planet is included even when the planet owns nothing itself, so the
    moon region has a parent to hang off.  Returned in ``ALL_BODIES`` order
    (parents precede their moons) for stable, hash-seed-independent ordering.
    """
    needed: set[BodyName] = set()
    for body in location_owning_bodies(world):
        cur: BodyName | None = body
        while cur is not None and cur not in needed:
            needed.add(cur)
            cur = BODY_BY_NAME[cur].parent

    return [b.name for b in ALL_BODIES if b.name in needed]

def _create_fake_entrances(world: KSP1World, menu: Region) -> None:
    """Create the fake entrances that will be rendered on the UT map tab"""
    from .bodies import MissionType, _mission_dv

    home = world.mission_builder.home
    mw = world.multiworld
    relevent_missions = [MissionType.ORBIT,MissionType.LAND,MissionType.RETURN,MissionType.ESCAPE,MissionType.ORBIT_RETURN,MissionType.SOI_RETURN]
    bodies = bodies_needing_regions(world)
    for body in bodies:
        region = world.get_region(body_region_name(body))
        for mission in relevent_missions:
            dv = _mission_dv(body, home, mission)
            if dv != float("inf"):
                new_region = Region(f"{region.name} - {str(mission)} dV {str(int(dv))}",world.player,mw)
                region.connect(new_region,f"{region.name} - {str(mission)}")


def _create_body_regions(world: KSP1World, menu: Region) -> None:
    """Create and connect the per-body region hierarchy.

    Every region is created before any connection is made, so a moon's planet
    region always exists when we connect the moon to it.  Connection rules:

      * The **home** body connects straight from Menu, ungated — it is the start
        and must stay reachable even when its parent planet is hidden.
      * A **moon** connects from its planet region (so reaching it requires
        reaching the planet — the structural parent→child gate); a **planet**
        connects from Menu.
      * A **hidden** body additionally requires its ``Discover`` item on the
        entrance.  Visible bodies stay ungated (reachable exactly as before).
    """
    player = world.player
    mw = world.multiworld
    home = world.mission_builder.home
    gated = frozenset(getattr(world, "gated_hidden_bodies", ()))

    bodies = bodies_needing_regions(world)
    regions_by_body: dict[BodyName, Region] = {}
    for body in bodies:
        region = Region(body_region_name(body), player, mw)
        mw.regions.append(region)
        regions_by_body[body] = region

    for body in bodies:
        region = regions_by_body[body]
        rule = _discover_gate(body, player) if body in gated else None
        parent = BODY_BY_NAME[body].parent
        if body == home:
            menu.connect(region)
        elif parent is not None and parent in regions_by_body:
            regions_by_body[parent].connect(region, rule=rule)
        else:
            menu.connect(region, rule=rule)


def _discover_gate(
    body: BodyName, player: int
) -> Callable[[CollectionState], bool]:
    """Entrance rule for a hidden body: reachable once its Discover item is held.

    Parent→child gating is structural (a moon connects from its planet region),
    so a hidden moon transitively requires its parent's Discover too.
    """
    item_name = discover_item_name(body)
    return lambda state: state.has(item_name, player)


def _make_node_entrance_rule(
    node: TechNode,
    player: int,
    safety: float,
    home: BodyName,
    can_afford_tier: Callable[[CollectionState, int, int, float, BodyName], bool],
) -> Callable[[CollectionState], bool]:
    """Build an entrance rule for a tech node region.

    Checks R&D band, science budget, and parent node reachability (AND/OR).
    A hidden body's science is gated on its Discover item inside the science
    budget itself (rules._cheap_bankable_science), so no extra gate is needed
    here — a science-hungry tier simply isn't affordable until enough of the
    system is discovered.
    """
    band = TIER_TO_BAND[node.tier]
    real_parents = [p for p in node.parents if p != "start"]
    # Pre-resolve parent display names to avoid repeated dict lookups.
    parent_region_names = [NODE_BY_ID[p].display_name for p in real_parents]
    tier = node.tier
    any_to_unlock = node.any_to_unlock

    def rule(state: CollectionState) -> bool:
        if band > 0 and not state.has(PROGRESSIVE_RD_NAME, player, band):
            return False
        if not can_afford_tier(state, player, tier, safety, home):
            return False
        if not parent_region_names:
            return True
        if any_to_unlock:
            return any(state.can_reach_region(name, player) for name in parent_region_names)
        else:
            return all(state.can_reach_region(name, player) for name in parent_region_names)

    return rule
