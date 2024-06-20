import logging
import typing
import os
import time
from typing import Dict, Optional

from BaseClasses import CollectionState, MultiWorld, LocationProgressType
from worlds.generic.Rules import exclusion_rules, locality_rules
from Options import StartInventoryPool
from settings import get_settings
from Utils import __version__, output_path
from worlds import AutoWorld


def tracker_changes(re_gen_passthrough, multiworld: MultiWorld):
    ###
    # Tracker Specific change to allow for worlds to know they aren't real
    #
    # to update, copy in the current Main.main(),
    # make sure re_gen_passthrough is added as an argument,
    # inject this method after the multiworld is created,
    # and return the multiworld between generate_basic and modifying itempool
    ###
    multiworld.generation_is_fake = True
    if re_gen_passthrough is not None:
        multiworld.re_gen_passthrough = re_gen_passthrough


def TMain(re_gen_passthrough, args, seed=None, baked_server_options: Optional[Dict[str, object]] = None):
    if not baked_server_options:
        baked_server_options = get_settings().server_options.as_dict()
    assert isinstance(baked_server_options, dict)
    if args.outputpath:
        os.makedirs(args.outputpath, exist_ok=True)
        output_path.cached_path = args.outputpath

    start = time.perf_counter()
    # initialize the multiworld
    multiworld = MultiWorld(args.multi)

    tracker_changes(re_gen_passthrough, multiworld)

    logger = logging.getLogger()
    multiworld.set_seed(seed, args.race, str(args.outputname) if args.outputname else None)
    multiworld.plando_options = args.plando_options
    multiworld.plando_items = args.plando_items.copy()
    multiworld.plando_texts = args.plando_texts.copy()
    multiworld.plando_connections = args.plando_connections.copy()
    multiworld.game = args.game.copy()
    multiworld.player_name = args.name.copy()
    multiworld.sprite = args.sprite.copy()
    multiworld.sprite_pool = args.sprite_pool.copy()

    multiworld.set_options(args)
    multiworld.set_item_links()
    multiworld.state = CollectionState(multiworld)
    logger.info('Archipelago Version %s  -  Seed: %s\n', __version__, multiworld.seed)

    logger.info(f"Found {len(AutoWorld.AutoWorldRegister.world_types)} World Types:")
    longest_name = max(len(text) for text in AutoWorld.AutoWorldRegister.world_types)

    max_item = 0
    max_location = 0
    for cls in AutoWorld.AutoWorldRegister.world_types.values():
        if cls.item_id_to_name:
            max_item = max(max_item, max(cls.item_id_to_name))
            max_location = max(max_location, max(cls.location_id_to_name))

    item_digits = len(str(max_item))
    location_digits = len(str(max_location))
    item_count = len(str(max(len(cls.item_names) for cls in AutoWorld.AutoWorldRegister.world_types.values())))
    location_count = len(str(max(len(cls.location_names) for cls in AutoWorld.AutoWorldRegister.world_types.values())))
    del max_item, max_location

    for name, cls in AutoWorld.AutoWorldRegister.world_types.items():
        if not cls.hidden and len(cls.item_names) > 0:
            logger.info(f" {name:{longest_name}}: {len(cls.item_names):{item_count}} "
                        f"Items (IDs: {min(cls.item_id_to_name):{item_digits}} - "
                        f"{max(cls.item_id_to_name):{item_digits}}) | "
                        f"{len(cls.location_names):{location_count}} "
                        f"Locations (IDs: {min(cls.location_id_to_name):{location_digits}} - "
                        f"{max(cls.location_id_to_name):{location_digits}})")

    del item_digits, location_digits, item_count, location_count

    # This assertion method should not be necessary to run if we are not outputting any multidata.
    if not args.skip_output:
        AutoWorld.call_stage(multiworld, "assert_generate")

    AutoWorld.call_all(multiworld, "generate_early")

    logger.info('')

    for player in multiworld.player_ids:
        for item_name, count in multiworld.worlds[player].options.start_inventory.value.items():
            for _ in range(count):
                multiworld.push_precollected(multiworld.create_item(item_name, player))

        for item_name, count in getattr(multiworld.worlds[player].options,
                                        "start_inventory_from_pool",
                                        StartInventoryPool({})).value.items():
            for _ in range(count):
                multiworld.push_precollected(multiworld.create_item(item_name, player))
            # remove from_pool items also from early items handling, as starting is plenty early.
            early = multiworld.early_items[player].get(item_name, 0)
            if early:
                multiworld.early_items[player][item_name] = max(0, early-count)
                remaining_count = count-early
                if remaining_count > 0:
                    local_early = multiworld.early_local_items[player].get(item_name, 0)
                    if local_early:
                        multiworld.early_items[player][item_name] = max(0, local_early - remaining_count)
                    del local_early
            del early

    logger.info('Creating MultiWorld.')
    AutoWorld.call_all(multiworld, "create_regions")

    logger.info('Creating Items.')
    AutoWorld.call_all(multiworld, "create_items")

    logger.info('Calculating Access Rules.')

    for player in multiworld.player_ids:
        # items can't be both local and non-local, prefer local
        multiworld.worlds[player].options.non_local_items.value -= multiworld.worlds[player].options.local_items.value
        multiworld.worlds[player].options.non_local_items.value -= set(multiworld.local_early_items[player])

    AutoWorld.call_all(multiworld, "set_rules")

    for player in multiworld.player_ids:
        exclusion_rules(multiworld, player, multiworld.worlds[player].options.exclude_locations.value)
        multiworld.worlds[player].options.priority_locations.value -= multiworld.worlds[player].options.exclude_locations.value
        for location_name in multiworld.worlds[player].options.priority_locations.value:
            try:
                location = multiworld.get_location(location_name, player)
            except KeyError as e:  # failed to find the given location. Check if it's a legitimate location
                if location_name not in multiworld.worlds[player].location_name_to_id:
                    raise Exception(f"Unable to prioritize location {location_name} in player {player}'s world.") from e
            else:
                location.progress_type = LocationProgressType.PRIORITY

    # Set local and non-local item rules.
    if multiworld.players > 1:
        locality_rules(multiworld)
    else:
        multiworld.worlds[1].options.non_local_items.value = set()
        multiworld.worlds[1].options.local_items.value = set()
    
    AutoWorld.call_all(multiworld, "generate_basic")

    return multiworld