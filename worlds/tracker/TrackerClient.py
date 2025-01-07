import asyncio
import logging
import tempfile
import traceback
import typing
import inspect
from collections.abc import Callable
from CommonClient import CommonContext, gui_enabled, get_base_parser, server_loop, ClientCommandProcessor
import os
import time
import sys
from typing import Dict, Optional, Union, List, Set, Any
from BaseClasses import ItemClassification


from BaseClasses import CollectionState, MultiWorld, LocationProgressType
from worlds.generic.Rules import exclusion_rules, locality_rules
from Options import StartInventoryPool
from settings import get_settings
from Utils import __version__, output_path
from worlds import AutoWorld
from worlds.tracker import TrackerWorld, UTMapTabData, CurrentTrackerState
from collections import Counter,defaultdict
from MultiServer import mark_raw

from Generate import main as GMain, mystery_argparse

if typing.TYPE_CHECKING:
    from kvui import GameManager
    from argparse import Namespace

# webserver imports
import urllib.parse

if not sys.stdout:  # to make sure sm varia's "i'm working" dots don't break UT in frozen
    sys.stdout = open(os.devnull, 'w', encoding="utf-8")  # from https://stackoverflow.com/a/6735958

logger = logging.getLogger("Client")

UT_VERSION = "v0.1.15"
DEBUG = False
ITEMS_HANDLING = 0b111
REGEN_WORLDS = {name for name, world in AutoWorld.AutoWorldRegister.world_types.items() if getattr(world, "ut_can_gen_without_yaml", False)}
UT_MAP_TAB_KEY = "UT_MAP"


class TrackerCommandProcessor(ClientCommandProcessor):
    ctx: "TrackerGameContext"

    def _cmd_inventory(self):
        """Print the list of current items in the inventory"""
        logger.info("Current Inventory:")
        currentState = updateTracker(self.ctx)
        for item, count in sorted(currentState.all_items.items()):
            logger.info(str(count) + "x: " + item)

    def _cmd_prog_inventory(self):
        """Print the list of current items in the inventory"""
        logger.info("Current Inventory:")
        currentState = updateTracker(self.ctx)
        for item, count in sorted(currentState.prog_items.items()):
            logger.info(str(count) + "x: " + item)

    def _cmd_event_inventory(self):
        """Print the list of current items in the inventory"""
        logger.info("Current Inventory:")
        currentState = updateTracker(self.ctx)
        for event in sorted(currentState.events):
            logger.info(event)

    def _cmd_load_map(self,map_id: str="0"):
        """Force a poptracker map id to be loaded"""
        if self.ctx.tracker_world is not None:
            self.ctx.load_map(map_id)
            updateTracker(self.ctx)
        else:
            logger.info("No world with internal map loaded")

    def _cmd_list_maps(self):
        """List the available maps to load with /load_map"""
        if self.ctx.tracker_world is not None:
            for i,map in enumerate(self.ctx.maps):
                logger.info("Map["+str(i)+"] = '"+map["name"]+"'")
        else:
            logger.info("No world with internal map loaded")

    @mark_raw
    def _cmd_manually_collect(self, item_name: str = ""):
        """Manually adds an item name to the CollectionState to test"""
        self.ctx.manual_items.append(item_name)
        updateTracker(self.ctx)
        logger.info(f"Added {item_name} to manually collect.")

    def _cmd_reset_manually_collect(self):
        """Resets the list of items manually collected by /manually_collect"""
        self.ctx.manual_items = []
        updateTracker(self.ctx)
        logger.info("Reset manually collect.")

    @mark_raw
    def _cmd_ignore(self, location_name: str = ""):
        """Ignore a location so it doesn't appear in the tracker list"""
        if not self.ctx.game:
            logger.info("Game not yet loaded")
            return

        location_name_to_id = AutoWorld.AutoWorldRegister.world_types[self.ctx.game].location_name_to_id
        if location_name not in location_name_to_id:
            logger.info(f"Unrecognized location {location_name}")
            return

        self.ctx.ignored_locations.add(location_name_to_id[location_name])
        updateTracker(self.ctx)
        logger.info(f"Added {location_name} to ignore list.")

    @mark_raw
    def _cmd_unignore(self, location_name: str = ""):
        """Stop ignoring a location so it appears in the tracker list again"""
        if not self.ctx.game:
            logger.info("Game not yet loaded")
            return

        location_name_to_id = AutoWorld.AutoWorldRegister.world_types[self.ctx.game].location_name_to_id
        if location_name not in location_name_to_id:
            logger.info(f"Unrecognized location {location_name}")
            return

        location = location_name_to_id[location_name]
        if location not in self.ctx.ignored_locations:
            logger.info(f"{location_name} is not on ignore list.")
            return

        self.ctx.ignored_locations.remove(location)
        updateTracker(self.ctx)
        logger.info(f"Removed {location_name} from ignore list.")

    def _cmd_list_ignored(self):
        """List the ignored locations"""
        if len(self.ctx.ignored_locations) == 0:
            logger.info("No ignored locations")
            return
        if not self.ctx.game:
            logger.info("Game not yet loaded")
            return

        logger.info("Ignored locations:")
        location_names = [self.ctx.location_names.lookup_in_game(location) for location in self.ctx.ignored_locations]
        for location_name in sorted(location_names):
            logger.info(location_name)

    def _cmd_reset_ignored(self):
        """Reset the list of ignored locations"""
        self.ctx.ignored_locations.clear()
        updateTracker(self.ctx)
        logger.info("Reset ignored locations.")


class TrackerGameContext(CommonContext):
    game = ""
    quit_after_update = False
    tags = CommonContext.tags | {"Tracker"}
    command_processor = TrackerCommandProcessor
    tracker_page = None
    map_page = None
    tracker_world: Optional[UTMapTabData] = None
    coord_dict: Dict[str, List] = {}
    map_page_coords_func = None
    watcher_task = None
    update_callback: Optional[Callable[[List[str]], bool]] = None
    region_callback: Optional[Callable[[List[str]], bool]] = None
    events_callback: Optional[Callable[[List[str]], bool]] = None
    gen_error = None
    output_format = "Both"
    hide_excluded = False
    tracker_failed = False
    re_gen_passthrough = None
    cached_multiworlds: List[MultiWorld] = []
    cached_slot_data: List[Dict[str, Any]] = []
    ignored_locations: Set[int]
    location_alias_map: Dict[int,str] = {}

    def __init__(self, server_address, password, no_connection: bool = False,quit_after_update: bool = False):
        if no_connection:
            from worlds import network_data_package
            self.item_names = self.NameLookupDict(self, "item")
            self.location_names = self.NameLookupDict(self, "location")
            self.update_data_package(network_data_package)
        else:
            super().__init__(server_address, password)
        self.items_handling = ITEMS_HANDLING
        self.locations_checked = []
        self.locations_available = []
        self.datapackage = []
        self.multiworld: MultiWorld = None
        self.launch_multiworld: MultiWorld = None
        self.player_id = None
        self.manual_items = []
        self.ignored_locations = set()
        self.quit_after_update = quit_after_update

    def load_pack(self):
        PACK_NAME = self.multiworld.worlds[self.player_id].__class__.__module__
        self.maps = []
        for map_page in self.tracker_world.map_page_maps:
            self.maps += load_json(PACK_NAME, f"/{self.tracker_world.map_page_folder}/{map_page}")
        self.locs = []
        for loc_page in self.tracker_world.map_page_locations:
            self.locs += load_json(PACK_NAME, f"/{self.tracker_world.map_page_folder}/{loc_page}")
        self.load_map(None)


    def load_map(self,map_id:Union[int, str, None]):
        """REMEMBER TO RUN UPDATE_TRACKER!"""
        if not self.ui or self.tracker_world is None:
            return
        if map_id is None:
            key = str(self.slot)+"_"+str(self.team)+"_"+(self.tracker_world.map_page_setting_key if self.tracker_world.map_page_setting_key else UT_MAP_TAB_KEY)
            map_id = self.tracker_world.map_page_index(self.stored_data.get(key,""))
            if map_id < 0 or map_id >= len(self.maps):
                return #special case, don't load a new map
        m=None
        if isinstance(map_id,str) and not map_id.isdecimal():
            for map in self.maps:
                if map["name"] == map_id:
                    m = map
                    break
            else:
                logger.error("Attempted to load a map that doesn't exist")
                return
        else:
            if isinstance(map_id,str):
                map_id = int(map_id)
            m = self.maps[map_id]
        location_name_to_id=AutoWorld.AutoWorldRegister.world_types[self.game].location_name_to_id
        PACK_NAME = self.multiworld.worlds[self.player_id].__class__.__module__
        # m = [m for m in self.maps if m["name"] == map_name]
        self.ui.source = f"ap:{PACK_NAME}/{self.tracker_world.map_page_folder}/{m['img']}"
        self.ui.loc_size = m["location_size"] if "location_size" in m else 65 #default location size per poptracker/src/core/map.h
        self.ui.loc_border = m["location_border_thickness"] if "location_border_thickness" in m else 8 #default location size per poptracker/src/core/map.h
        temp_locs = [location for location in self.locs]
        map_locs = []
        while temp_locs:
            temp_loc = temp_locs.pop()
            if "map_locations" in temp_loc:
                map_locs.append(temp_loc)
            elif "children" in temp_loc:
                temp_locs.extend(temp_loc["children"])
        self.coords = {
            (map_loc["x"], map_loc["y"]) :
                [ section["name"] for section in location["sections"] if "name" in section and section["name"] in location_name_to_id and location_name_to_id[section["name"]] in self.server_locations ]
            for location in map_locs
            for map_loc in location["map_locations"]
            if map_loc["map"] == m["name"] and any("name" in section and section["name"] in location_name_to_id and location_name_to_id[section["name"]] in self.server_locations for section in location["sections"])
        }
        self.coord_dict = self.map_page_coords_func(self.coords)

    def clear_page(self):
        if self.tracker_page is not None:
            self.tracker_page.resetData()

    def log_to_tab(self, line: str, sort: bool = False):
        if self.tracker_page is not None:
            self.tracker_page.addLine(line, sort)

    def set_callback(self, func: "Optional[Callable[[List[str]], bool]]" = None):
        self.update_callback = func

    def set_region_callback(self, func: "Optional[Callable[[List[str]], bool]]" = None):
        self.region_callback = func

    def set_events_callback(self, func: "Optional[Callable[[List[str]], bool]]" = None):
        self.events_callback = func

    def build_gui(self, manager: "GameManager"):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.tabbedpanel import TabbedPanelItem
        from kivy.uix.recycleview import RecycleView
        from kivy.uix.widget import Widget
        from kivy.properties import StringProperty, NumericProperty, BooleanProperty
        try:
            from kvui import ApAsyncImage #one of these needs to be loaded
        except ImportError:
            from .TrackerKivy import ApAsyncImage #use local until ap#3629 gets merged/released

        class TrackerLayout(BoxLayout):
            pass

        class TrackerView(RecycleView):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.data = []
                self.data.append({"text": f"Tracker {UT_VERSION} Initializing for AP version {__version__}"})

            def resetData(self):
                self.data.clear()

            def addLine(self, line: str, sort: bool = False):
                self.data.append({"text": line})
                if sort:
                    self.data.sort(key=lambda e: e["text"])

        class ApLocation(Widget):
            from kivy.properties import DictProperty,ColorProperty
            locationDict = DictProperty()
            color = ColorProperty("#DD00FF")
            def __init__(self, sections,**kwargs):
                for location_name in sections:
                    self.locationDict[location_name]="none"
                self.bind(locationDict=self.update_color)
                super().__init__(**kwargs)

            def update_status(self, location, status):
                if location in self.locationDict:
                    if self.locationDict[location] != status:
                        self.locationDict[location] = status
            @staticmethod
            def update_color(self,locationDict):
                if any(status == "in_logic" for status in locationDict.values()) and any(status == "out_of_logic" for status in locationDict.values()):
                    self.color = "#FF9F20"
                elif any(status == "in_logic" for status in locationDict.values()):
                    self.color = "#20FF20"
                elif any(status == "out_of_logic" for status in locationDict.values()):
                    self.color = "#CF1010"
                else:
                    self.color = "#3F3F3F"

        class VisualTracker(BoxLayout):
            def load_coords(self,coords):
                self.ids.location_canvas.clear_widgets()
                returnDict = defaultdict(list)
                for coord,sections in coords.items():
                    #https://discord.com/channels/731205301247803413/1170094879142051912/1272327822630977727
                    temp_loc = ApLocation(sections,pos=(coord))
                    self.ids.location_canvas.add_widget(temp_loc)
                    for location_name in sections:
                        returnDict[location_name].append(temp_loc)
                return returnDict

        tracker_page = TabbedPanelItem(text="Tracker Page")
        map_page = TabbedPanelItem(text="Map Page")

        try:
            tracker = TrackerLayout(orientation="horizontal")
            tracker_view = TrackerView()
            tracker.add_widget(tracker_view)
            self.tracker_page = tracker_view
            tracker_page.content = tracker
            map = VisualTracker()
            self.map_page_coords_func = map.load_coords
            self.map_page = map_page
            map_page.content = map
            if self.gen_error is not None:
                for line in self.gen_error.split("\n"):
                    self.log_to_tab(line, False)
        except Exception as e:
            # TODO back compat, fail gracefully if a kivy app doesn't have our properties
            self.map_page_coords_func = lambda *args: None
            tb = traceback.format_exc()
            print(tb)
        manager.tabs.add_widget(tracker_page)
        @staticmethod
        def set_map_tab(self,value,*args,map_page=map_page):
            if value:
                self.add_widget(map_page)
                self.tab_width = self.tab_width * (len(self.tab_list)-1)/len(self.tab_list)
                #for some forsaken reason, the tab panel doesn't auto adjust tab width by itself
                #it is happy to let the header have a scroll bar until the window forces it to resize
            else:
                self.remove_widget(map_page)
                self.tab_width = self.tab_width * (len(self.tab_list)+1)/len(self.tab_list)

        manager.tabs.apply_property(show_map=BooleanProperty(False))
        manager.tabs.fbind("show_map",set_map_tab)

    def make_gui(self):
        ui = super().make_gui()  # before the kivy imports so kvui gets loaded first
        from kvui import HintLog, HintLabel, TooltipLabel
        from kivy.properties import StringProperty, NumericProperty, BooleanProperty
        try:
            from kvui import ImageLoader #one of these needs to be loaded
        except ImportError:
            from .TrackerKivy import ImageLoader #use local until ap#3629 gets merged/released

        class TrackerManager(ui):
            source = StringProperty("")
            loc_size = NumericProperty(20)
            loc_border = NumericProperty(5)
            enable_map = BooleanProperty(False)
            base_title = f"Tracker {UT_VERSION} for AP version"  # core appends ap version so this works

            def build(self):
                class TrackerHintLabel(HintLabel):
                    logic_text = StringProperty("")

                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        logic = TooltipLabel(
                            sort_key="name",  # is lying to computer and player but fixing it will need core changes
                            text="", halign='center', valign='center', pos_hint={"center_y": 0.5},
                            )
                        self.add_widget(logic)

                        def set_text(_, value):
                            logic.text = value
                        self.bind(logic_text=set_text)

                    def refresh_view_attrs(self, rv, index, data):
                        super().refresh_view_attrs(rv, index, data)
                        if data["item"]["text"] == rv.header["item"]["text"]:
                            self.logic_text = "[u]In Logic[/u]"
                            return
                        ctx = ui.get_running_app().ctx
                        if "status" in data:
                            loc = data["status"]["hint"]["location"]
                            from NetUtils import HintStatus
                            found = data["status"]["hint"]["status"] == HintStatus.HINT_FOUND
                        else:
                            prefix = len("[color=00FF7F]")
                            suffix = len("[/color]")
                            loc_name = data["location"]["text"][prefix:-1*suffix]
                            loc = AutoWorld.AutoWorldRegister.world_types[ctx.game].location_name_to_id.get(loc_name)
                            found = "Not Found" not in data["found"]["text"]

                        in_logic = loc in ctx.locations_available
                        self.logic_text = rv.parser.handle_node({
                            "type": "color", "color": "green" if found else
                            "orange" if in_logic else "red",
                            "text": "Found" if found else "In Logic" if in_logic
                            else "Not Found"})

                def kv_post(self, base_widget):
                    self.viewclass = TrackerHintLabel
                HintLog.on_kv_post = kv_post

                container = super().build()
                self.tabs.do_default_tab = True
                self.tabs.current_tab.height = 40
                self.tabs.tab_height = 40
                self.ctx.build_gui(self)

                return container

        self.load_kv()
        return TrackerManager

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

    def regen_slots(self, world, slot_data, tempdir: Optional[str] = None) -> bool:
        if callable(getattr(world, "interpret_slot_data", None)):
            temp = world.interpret_slot_data(slot_data)

            # back compat for worlds that trigger regen with interpret_slot_data, will remove eventually
            if temp:
                self.player_id = 1
                self.re_gen_passthrough = {self.game: temp}
                self.run_generator(slot_data, tempdir)
            return True
        else:
            return False

    def on_package(self, cmd: str, args: dict):
        try:
            if cmd == 'Connected':
                if self.launch_multiworld is None:
                    self.log_to_tab("Internal world was not able to be generated, check your yamls and relaunch", False)
                    return
                self.game = args["slot_info"][str(args["slot"])][1]
                slot_name = args["slot_info"][str(args["slot"])][0]
                if getattr(AutoWorld.AutoWorldRegister.world_types[self.game],"disable_ut",False):
                    self.log_to_tab("World Author has requested UT be disabled on this world, please respect their decision")
                    return
                if slot_name in self.launch_multiworld.world_name_lookup:
                    internal_id = self.launch_multiworld.world_name_lookup[slot_name]
                    if self.launch_multiworld.worlds[internal_id].game == self.game:
                        self.multiworld = self.launch_multiworld
                        self.player_id = internal_id
                        self.regen_slots(self.multiworld.worlds[self.player_id],args["slot_data"])
                    elif self.launch_multiworld.worlds[internal_id].game == "Archipelago":
                        connected_cls = AutoWorld.AutoWorldRegister.world_types[self.game]
                        if not self.regen_slots(connected_cls,args["slot_data"]):
                            raise "TODO: add error - something went very wrong with interpret_slot_data"
                    else:
                        world_dict = {name: self.launch_multiworld.worlds[slot].game for name, slot in self.launch_multiworld.world_name_lookup.items()}
                        tb = f"Tried to match game '{args['slot_info'][str(args['slot'])][1]}'" + \
                            f" to slot name '{args['slot_info'][str(args['slot'])][0]}'" + \
                            f" with known slots {world_dict}"
                        self.gen_error = tb
                        logger.error(tb)
                        return
                else:
                    if getattr(AutoWorld.AutoWorldRegister.world_types[self.game], "ut_can_gen_without_yaml", False):
                        with tempfile.TemporaryDirectory() as tempdir:
                            self.write_empty_yaml(self.game, slot_name, tempdir)
                            self.player_id = 1
                            slot_data = args["slot_data"]
                            world = None
                            temp_isd = inspect.getattr_static(AutoWorld.AutoWorldRegister.world_types[self.game], "interpret_slot_data", None)
                            if isinstance(temp_isd,(staticmethod,classmethod)) and callable(temp_isd):
                                world = AutoWorld.AutoWorldRegister.world_types[self.game]
                            else:
                                self.re_gen_passthrough = {self.game: slot_data}
                                self.run_generator(args["slot_data"],tempdir)
                                world = self.multiworld.worlds[self.player_id]
                            self.regen_slots(world,slot_data,tempdir)
                    else:
                        self.log_to_tab(f"Player's Yaml not in tracker's list. Known players: {list(self.launch_multiworld.world_name_lookup.keys())}", False)
                        return

                if self.ui is not None and getattr(self.multiworld.worlds[self.player_id], "tracker_world", None):
                    self.tracker_world = UTMapTabData(**self.multiworld.worlds[self.player_id].tracker_world)
                    
                    key = str(self.slot)+"_"+str(self.team)+"_"+(self.tracker_world.map_page_setting_key if self.tracker_world.map_page_setting_key else UT_MAP_TAB_KEY)
                    self.set_notify(key)
                    self.load_pack()
                    self.ui.tabs.show_map = True
                else:
                    self.tracker_world = None

                if hasattr(self.multiworld.worlds[self.player_id],"location_id_to_alias"):
                    self.location_alias_map = self.multiworld.worlds[self.player_id].location_id_to_alias
                updateTracker(self)
                self.watcher_task = asyncio.create_task(game_watcher(self), name="GameWatcher")
            elif cmd == 'RoomUpdate':
                updateTracker(self)
            elif cmd == 'SetReply':
                key = str(self.slot)+"_"+str(self.team)+"_"+(self.tracker_world.map_page_setting_key if self.tracker_world.map_page_setting_key else UT_MAP_TAB_KEY)
                if "key" in args and args["key"] == key:
                    self.load_map(None)
                    updateTracker(self)
        except Exception as e:
            e.args= e.args+("This is likely caused by UT being out of date",)
            raise e

    def write_empty_yaml(self, game, player_name, tempdir):
        path = os.path.join(tempdir, f'{game}_{player_name}.yaml')
        with open(path, 'w') as f:
            f.write('name: ' + player_name + '\n')
            f.write('game: ' + game + '\n')
            f.write(game + ': {}\n')

    async def disconnect(self, allow_autoreconnect: bool = False):
        if "Tracker" in self.tags:
            self.game = ""
            self.re_gen_passthrough = None
            if self.ui:
                self.ui.tabs.show_map = False
            self.tracker_world = None
            self.multiworld = None
            # TODO: persist these per url+slot(+seed)?
            self.manual_items.clear()
            self.ignored_locations.clear()
            self.location_alias_map = {}

        await super().disconnect(allow_autoreconnect)

    def _set_host_settings(self):
        from . import TrackerWorld
        tracker_settings = TrackerWorld.settings
        report_type = "Both"
        if tracker_settings['include_location_name']:
            if tracker_settings['include_region_name']:
                report_type = "Both"
            else:
                report_type = "Location"
        else:
            report_type = "Region"
        return tracker_settings['player_files_path'], report_type, tracker_settings[
            'hide_excluded_locations']

    def run_generator(self, slot_data: Optional[Dict] = None, override_yaml_path: Optional[str] = None):
        def move_slots(args: "Namespace", slot_name: str):
            """
            helper function to copy all the proper option values into slot 1,
            may need to change if/when multiworld.option_name dicts get fully removed
            """
            player = {name: i for i, name in args.name.items()}[slot_name]
            if player == 1:
                return args
            for option_name, option_value in args._get_kwargs():
                if isinstance(option_value, Dict) and player in option_value:
                    setattr(args, option_name, {1: option_value[player]})
            return args

        try:
            yaml_path, self.output_format, self.hide_excluded = self._set_host_settings()
            # strip command line args, they won't be useful from the client anyway
            sys.argv = sys.argv[:1]
            args = mystery_argparse()
            if override_yaml_path:
                args.player_files_path = override_yaml_path
            elif yaml_path:
                args.player_files_path = yaml_path
            args.skip_output = True

            if self.quit_after_update:
                from logging import ERROR
                args.log_level = ERROR

            g_args, seed = GMain(args)
            if slot_data or override_yaml_path:
                if slot_data and slot_data in self.cached_slot_data:
                    print("found cached multiworld!")
                    index = next(i for i, s in enumerate(self.cached_slot_data) if s == slot_data)
                    self.multiworld = self.cached_multiworlds[index]
                    return
                if not self.game:
                    raise "No Game found for slot, this should not happen ever"
                g_args.multi = 1
                g_args.game = {1: self.game}
                g_args.player_ids = {1}

                # TODO confirm that this will never not be filled
                g_args = move_slots(g_args, self.slot_info[self.slot].name)

                self.multiworld = self.TMain(g_args, seed)
                assert len(self.cached_slot_data) == len(self.cached_multiworlds)
                self.cached_multiworlds.append(self.multiworld)
                self.cached_slot_data.append(slot_data)
            else:
                # skip worlds that we know will regen on connect
                g_args.game = {
                    slot: game if game not in REGEN_WORLDS else "Archipelago"
                    for slot, game in g_args.game.items()
                    }
                self.launch_multiworld = self.TMain(g_args, seed)
                self.multiworld = self.launch_multiworld

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


def load_json(pack, path):
    import pkgutil
    import json
    return json.loads(pkgutil.get_data(pack, path).decode('utf-8-sig'))

def updateTracker(ctx: TrackerGameContext) -> CurrentTrackerState:
    if ctx.tracker_failed:
        return #just return and don't bug the player
    if ctx.player_id is None or ctx.multiworld is None:
        logger.error("Player YAML not installed or Generator failed")
        ctx.log_to_tab("Check Player YAMLs for error", False)
        ctx.tracker_failed = True
        return

    state = CollectionState(ctx.multiworld)
    state.sweep_for_advancements(
        locations=(location for location in ctx.multiworld.get_locations() if (not location.address)))
    prog_items = Counter()
    all_items = Counter()

    callback_list = []

    item_id_to_name = ctx.multiworld.worlds[ctx.player_id].item_id_to_name
    for item_name in [item_id_to_name[item[0]] for item in ctx.items_received] + ctx.manual_items:
        try:
            world_item = ctx.multiworld.create_item(item_name, ctx.player_id)
            state.collect(world_item, True)
            if ItemClassification.progression in world_item.classification:
                prog_items[world_item.name] += 1
            if world_item.code is not None:
                all_items[world_item.name] += 1
        except:
            ctx.log_to_tab("Item id " + str(item_name) + " not able to be created", False)
    state.sweep_for_advancements(
        locations=(location for location in ctx.multiworld.get_locations() if (not location.address)))

    ctx.clear_page()
    regions = []
    locations = []
    for temp_loc in ctx.multiworld.get_reachable_locations(state, ctx.player_id):
        if temp_loc.address == None or isinstance(temp_loc.address, List):
            continue
        elif ctx.hide_excluded and temp_loc.progress_type == LocationProgressType.EXCLUDED:
            continue
        elif temp_loc.address in ctx.ignored_locations:
            continue
        try:
            if (temp_loc.address in ctx.missing_locations):
                # logger.info("YES rechable (" + temp_loc.name + ")")
                region = ""
                if temp_loc.parent_region is None:
                    region = ""
                else:
                    region = temp_loc.parent_region.name
                temp_name = temp_loc.name
                if temp_loc.address in ctx.location_alias_map:
                    temp_name += f" ({ctx.location_alias_map[temp_loc.address]})"
                if ctx.output_format == "Both":
                    ctx.log_to_tab(region + " | " + temp_name, True)
                elif ctx.output_format == "Location":
                    ctx.log_to_tab(temp_name, True)
                if region not in regions:
                    regions.append(region)
                    if ctx.output_format == "Region":
                        ctx.log_to_tab(region, True)
                callback_list.append(temp_loc.name)
                locations.append(temp_loc.address)
        except:
            ctx.log_to_tab("ERROR: location " + temp_loc.name + " broke something, report this to discord")
            pass
    events = [location.item.name for location in state.advancements if location.player == ctx.player_id]

    if ctx.tracker_page:
        ctx.tracker_page.refresh_from_data()
    ctx.locations_available = locations
    if ctx.ui and f"_read_hints_{ctx.team}_{ctx.slot}" in ctx.stored_data:
        ctx.ui.update_hints()
    if ctx.update_callback is not None:
        ctx.update_callback(callback_list)
    if ctx.region_callback is not None:
        ctx.region_callback(regions)
    if ctx.events_callback is not None:
        ctx.events_callback(events)
    if len(ctx.ignored_locations) > 0:
        ctx.log_to_tab(f"{len(ctx.ignored_locations)} ignored locations")
    if len(callback_list) == 0:
        ctx.log_to_tab("All " + str(len(ctx.checked_locations)) + " accessible locations have been checked! Congrats!")
    if ctx.tracker_world is not None and ctx.ui is not None:
        #ctx.load_map()
        location_id_to_name=AutoWorld.AutoWorldRegister.world_types[ctx.game].location_id_to_name
        for location in ctx.server_locations:
            loc_name = location_id_to_name[location]
            relevent_coords = ctx.coord_dict.get(loc_name,[])
            if location in ctx.checked_locations or location in ctx.ignored_locations:
                status = "completed"
            elif location in ctx.locations_available:
                status = "in_logic"
            for coord in relevent_coords:
                coord.update_status(loc_name,status)
    if ctx.quit_after_update:
        name = ctx.player_names[ctx.slot]
        logger.error("Game: " + ctx.game + " | Slot Name : " + name+" | In logic locations : " + str(len(locations)))
        ctx.exit_event.set()

    return CurrentTrackerState(all_items, prog_items, events,state)


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
    ctx = TrackerGameContext(args.connect, args.password,quit_after_update=args.count)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    ctx.run_generator()

    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()

    await ctx.exit_event.wait()
    await ctx.shutdown()


def launch(*args):
    parser = get_base_parser(description="Gameless Archipelago Client, for text interfacing.")
    parser.add_argument('--name', default=None, help="Slot Name to connect as.")
    if sys.stdout:  # If terminal output exists, offer gui-less mode
        parser.add_argument('--count', default=False, action='store_true', help="just return a count of in logic checks")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    args = parser.parse_args(args)

    if args.url:
        url = urllib.parse.urlparse(args.url)
        args.connect = url.netloc
        if url.username:
            args.name = urllib.parse.unquote(url.username)
        if url.password:
            args.password = urllib.parse.unquote(url.password)
    if args.count:
        from logging import ERROR
        logger.setLevel(ERROR)

    asyncio.run(main(args))


if __name__ == "__main__":
    launch(*sys.argv[1:])
