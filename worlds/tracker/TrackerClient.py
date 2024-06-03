import asyncio
import logging
import traceback
import typing
from collections.abc import Callable
from CommonClient import CommonContext, gui_enabled, get_base_parser, server_loop, ClientCommandProcessor
import os
import time
import sys
from typing import Dict, Optional, List
from BaseClasses import Region, Location, ItemClassification

from BaseClasses import CollectionState, MultiWorld, LocationProgressType
from worlds.generic.Rules import exclusion_rules, locality_rules
from Options import StartInventoryPool
from settings import get_settings
from Utils import __version__, output_path
from worlds import AutoWorld
from worlds.tracker import TrackerWorld
from collections import Counter

from Generate import main as GMain, mystery_argparse

# webserver imports
import urllib.parse

logger = logging.getLogger("Client")

DEBUG = False
ITEMS_HANDLING = 0b111


class TrackerCommandProcessor(ClientCommandProcessor):

    def _cmd_inventory(self):
        """Print the list of current items in the inventory"""
        logger.info("Current Inventory:")
        all_items, prog_items, events = updateTracker(self.ctx)
        for item, count in sorted(all_items.items()):
            logger.info(str(count) + "x: " + item)

    def _cmd_prog_inventory(self):
        """Print the list of current items in the inventory"""
        logger.info("Current Inventory:")
        all_items, prog_items, events = updateTracker(self.ctx)
        for item, count in sorted(prog_items.items()):
            logger.info(str(count) + "x: " + item)

    def _cmd_event_inventory(self):
        """Print the list of current items in the inventory"""
        logger.info("Current Inventory:")
        all_items, prog_items, events = updateTracker(self.ctx)
        for event in sorted(events):
            logger.info(event)

    def _cmd_manually_collect(self, item_name: str):
        """Manually adds an item name to the CollectionState to test"""
        self.ctx.manual_items.append(item_name)
        updateTracker(self.ctx)
        logger.info("Added {item_name} to manually collect")

    def _cmd_reset_manually_collect(self):
        """Resets the list of items manually collected by /manually_collect"""
        self.ctx.manual_items = []
        updateTracker(self.ctx)
        logger.info("Reset manually collect")


class TrackerGameContext(CommonContext):
    from kvui import GameManager
    game = ""
    httpServer_task: typing.Optional["asyncio.Task[None]"] = None
    tags = CommonContext.tags | {"Tracker"}
    command_processor = TrackerCommandProcessor
    tracker_page = None
    watcher_task = None
    update_callback: Callable[[list[str]], bool] = None
    region_callback: Callable[[list[str]], bool] = None
    events_callback: Callable[[list[str]], bool] = None
    gen_error = None
    output_format = "Both"
    hide_excluded = False
    re_gen_passthrough = None

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.items_handling = ITEMS_HANDLING
        self.locations_checked = []
        self.locations_available = []
        self.datapackage = []
        self.multiworld: MultiWorld = None
        self.player_id = None
        self.manual_items = []

    def clear_page(self):
        if self.tracker_page is not None:
            self.tracker_page.resetData()

    def log_to_tab(self, line: str, sort: bool = False):
        if self.tracker_page is not None:
            self.tracker_page.addLine(line, sort)

    def set_callback(self, func: Optional[Callable[[list[str]], bool]] = None):
        self.update_callback = func

    def set_region_callback(self, func: Optional[Callable[[list[str]], bool]] = None):
        self.region_callback = func

    def set_events_callback(self, func: Optional[Callable[[list[str]], bool]] = None):
        self.events_callback = func

    def build_gui(self, manager: GameManager):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.tabbedpanel import TabbedPanelItem
        from kivy.uix.recycleview import RecycleView

        class TrackerLayout(BoxLayout):
            pass

        class TrackerView(RecycleView):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.data = []
                self.data.append({"text": "Tracker v0.1.4 Initializing"})

            def resetData(self):
                self.data.clear()

            def addLine(self, line: str, sort: bool = False):
                self.data.append({"text": line})
                if sort:
                    self.data.sort(key=lambda e: e["text"])

        tracker_page = TabbedPanelItem(text="Tracker Page")

        try:
            tracker = TrackerLayout(orientation="horizontal")
            tracker_view = TrackerView()
            tracker.add_widget(tracker_view)
            self.tracker_page = tracker_view
            tracker_page.content = tracker
            if self.gen_error is not None:
                for line in self.gen_error.split("\n"):
                    self.log_to_tab(line, False)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
        manager.tabs.add_widget(tracker_page)

        from kvui import HintLog
        # hook hint tab

        def update_available_hints(log: HintLog, hints: typing.Set[typing.Dict[str, typing.Any]]):
            data = []
            for hint in hints:
                in_logic = int(hint["location"]) in self.locations_available \
                    if int(hint["finding_player"]) == self.player_id else False
                data.append({
                    "receiving": {
                        "text": log.parser.handle_node({"type": "player_id", "text": hint["receiving_player"]})},
                    "item": {"text": log.parser.handle_node(
                        {"type": "item_id", "text": hint["item"], "flags": hint["item_flags"]})},
                    "finding": {"text": log.parser.handle_node({"type": "player_id", "text": hint["finding_player"]})},
                    "location": {"text": log.parser.handle_node({"type": "location_id", "text": hint["location"]})},
                    "entrance": {"text": log.parser.handle_node({"type": "color" if hint["entrance"] else "text",
                                                                 "color": "blue", "text": hint["entrance"]
                        if hint["entrance"] else "Vanilla"})},
                    "found": {
                        "text": log.parser.handle_node({"type": "color", "color": "green" if hint["found"] else
                                                        "yellow" if in_logic else "red",
                                                        "text": "Found" if hint["found"] else "In Logic" if in_logic
                                                        else "Not Found"})},
                })

            data.sort(key=log.hint_sorter, reverse=log.reversed)
            for i in range(0, len(data), 2):
                data[i]["striped"] = True
            data.insert(0, log.header)
            log.data = data

        HintLog.refresh_hints = update_available_hints

    def run_gui(self):
        from kvui import GameManager

        class TrackerManager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago")
            ]
            base_title = "Archipelago Tracker Client"

            def build(self):
                container = super().build()
                self.tabs.do_default_tab = True
                self.tabs.current_tab.height = 40
                self.tabs.tab_height = 40
                self.ctx.build_gui(self)

                return container

        self.ui = TrackerManager(self)
        self.load_kv()
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")
        return self

    def load_kv(self):
        from kivy.lang import Builder
        import pkgutil

        data = pkgutil.get_data(TrackerWorld.__module__, "Tracker.kv").decode()
        Builder.load_string(data)

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super(TrackerGameContext, self).server_auth(password_requested)

        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == 'Connected':
            if self.multiworld is None:
                self.log_to_tab("Internal world was not able to be generated, check your yamls and relaunch", False)
                return
            player_ids = [i for i, n in self.multiworld.player_name.items() if n == self.username]
            if len(player_ids) < 1:
                self.log_to_tab("Player's Yaml not in tracker's list", False)
                return
            self.player_id = player_ids[0]  # should only really ever be one match
            self.game = args["slot_info"][str(args["slot"])][1]

            if callable(getattr(self.multiworld.worlds[self.player_id], "interpret_slot_data", None)):
                temp = self.multiworld.worlds[self.player_id].interpret_slot_data(args["slot_data"])
                if temp:
                    self.re_gen_passthrough = {self.game: temp}
                    self.run_generator()

            updateTracker(self)
            self.watcher_task = asyncio.create_task(game_watcher(self), name="GameWatcher")
        elif cmd == 'RoomUpdate':
            updateTracker(self)

    async def disconnect(self, allow_autoreconnect: bool = False):
        if "Tracker" in self.tags:
            self.game = ""
            self.re_gen_passthrough = None
        await super().disconnect(allow_autoreconnect)

    def _set_host_settings(self, host):
        if 'universal_tracker' not in host:
            host['universal_tracker'] = {}
        if 'player_files_path' not in host['universal_tracker']:
            host['universal_tracker']['player_files_path'] = None
        if 'include_region_name' not in host['universal_tracker']:
            host['universal_tracker']['include_region_name'] = False
        if 'include_location_name' not in host['universal_tracker']:
            host['universal_tracker']['include_location_name'] = True
        if 'hide_excluded_locations' not in host['universal_tracker']:
            host['universal_tracker']['hide_excluded_locations'] = False
        report_type = "Both"
        if host['universal_tracker']['include_location_name']:
            if host['universal_tracker']['include_region_name']:
                report_type = "Both"
            else:
                report_type = "Location"
        else:
            report_type = "Region"
        host.save()
        return host['universal_tracker']['player_files_path'], report_type, host['universal_tracker'][
            'hide_excluded_locations']

    def run_generator(self):
        try:
            host = get_settings()
            yaml_path, self.output_format, self.hide_excluded = self._set_host_settings(host)
            # strip command line args, they won't be useful from the client anyway
            sys.argv = sys.argv[:1]
            args, _settings = mystery_argparse()
            if yaml_path:
                args.player_files_path = yaml_path
            args.skip_output = True
            GMain(args, self.TMain)
            temp_precollect = {}
            for player_id, items in self.multiworld.precollected_items.items():
                temp_items = [item for item in items if item.code == None]
                temp_precollect[player_id] = temp_items
            self.multiworld.precollected_items = temp_precollect
        except Exception as e:
            tb = traceback.format_exc()
            self.gen_error = tb
            logger.error(tb)

    def TMain(self, args, seed=None, baked_server_options: Optional[Dict[str, object]] = None):
        if not baked_server_options:
            baked_server_options = get_settings().server_options.as_dict()
        assert isinstance(baked_server_options, dict)
        if args.outputpath:
            os.makedirs(args.outputpath, exist_ok=True)
            output_path.cached_path = args.outputpath


        start = time.perf_counter()
        # initialize the multiworld
        multiworld = MultiWorld(args.multi)

        ###
        # Tracker Specific change to allow for worlds to know they aren't real
        ###
        multiworld.generation_is_fake = True
        if self.re_gen_passthrough is not None:
            multiworld.re_gen_passthrough = self.re_gen_passthrough

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

        self.multiworld = multiworld
        return


def updateTracker(ctx: TrackerGameContext):
    if ctx.player_id is None or ctx.multiworld is None:
        logger.error("Player YAML not installed or Generator failed")
        ctx.log_to_tab("Check Player YAMLs for error", False)
        return

    state = CollectionState(ctx.multiworld)
    state.sweep_for_events(
        locations=(location for location in ctx.multiworld.get_locations() if (not location.address)))
    prog_items = Counter()
    all_items = Counter()

    callback_list = []

    for item_name in [item[0] for item in ctx.items_received] + ctx.manual_items:
        try:
            world_item = ctx.multiworld.create_item(ctx.multiworld.worlds[ctx.player_id].item_id_to_name[item_name],
                                                    ctx.player_id)
            state.collect(world_item, True)
            if world_item.classification == ItemClassification.progression or world_item.classification == ItemClassification.progression_skip_balancing:
                prog_items[world_item.name] += 1
            if world_item.code is not None:
                all_items[world_item.name] += 1
        except:
            ctx.log_to_tab("Item id " + str(item_name) + " not able to be created", False)
    state.sweep_for_events(
        locations=(location for location in ctx.multiworld.get_locations() if (not location.address)))

    ctx.clear_page()
    regions = []
    locations = []
    for temp_loc in ctx.multiworld.get_reachable_locations(state, ctx.player_id):
        if temp_loc.address == None or isinstance(temp_loc.address, list):
            continue
        elif ctx.hide_excluded and temp_loc.progress_type == LocationProgressType.EXCLUDED:
            continue
        try:
            if (temp_loc.address in ctx.missing_locations):
                # logger.info("YES rechable (" + temp_loc.name + ")")
                region = ""
                if temp_loc.parent_region is None:
                    region = ""
                else:
                    region = temp_loc.parent_region.name
                if ctx.output_format == "Both":
                    ctx.log_to_tab(region + " | " + temp_loc.name, True)
                elif ctx.output_format == "Location":
                    ctx.log_to_tab(temp_loc.name, True)
                if region not in regions:
                    regions.append(region)
                    if ctx.output_format == "Region":
                        ctx.log_to_tab(region, True)
                callback_list.append(temp_loc.name)
                locations.append(temp_loc.address)
        except:
            ctx.log_to_tab("ERROR: location " + temp_loc.name + " broke something, report this to discord")
            pass
    events = [location.item.name for location in state.events if location.player == ctx.player_id]

    ctx.tracker_page.refresh_from_data()
    ctx.locations_available = locations
    if f"_read_hints_{ctx.team}_{ctx.slot}" in ctx.stored_data:
        ctx.ui.update_hints()
    if ctx.update_callback is not None:
        ctx.update_callback(callback_list)
    if ctx.region_callback is not None:
        ctx.region_callback(regions)
    if ctx.events_callback is not None:
        ctx.events_callback(events)
    if len(callback_list) == 0:
        ctx.log_to_tab("All " + str(len(ctx.checked_locations)) + " accessible locations have been checked! Congrats!")
    return (all_items, prog_items, events)


async def game_watcher(ctx: TrackerGameContext) -> None:
    while not ctx.exit_event.is_set():
        try:
            await asyncio.wait_for(ctx.watcher_event.wait(), 0.125)
        except asyncio.TimeoutError:
            continue
        ctx.watcher_event.clear()
        try:
            updateTracker(ctx)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)


async def main(args):
    ctx = TrackerGameContext(args.connect, args.password)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    ctx.run_generator()

    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()

    await ctx.exit_event.wait()
    await ctx.shutdown()


def launch():
    parser = get_base_parser(description="Gameless Archipelago Client, for text interfacing.")
    parser.add_argument('--name', default=None, help="Slot Name to connect as.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    args = parser.parse_args()

    if args.url:
        url = urllib.parse.urlparse(args.url)
        args.connect = url.netloc
        if url.username:
            args.name = urllib.parse.unquote(url.username)
        if url.password:
            args.password = urllib.parse.unquote(url.password)

    asyncio.run(main(args))
