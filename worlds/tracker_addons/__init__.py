from BaseClasses import CollectionState
from collections import defaultdict, Counter
from typing import Callable, TYPE_CHECKING
import logging
from MultiServer import mark_raw

UT_FUNCTIONS:dict[str,Callable] = {}

ADDONS_ERRORS:list[str] = []

from Utils import tuplize_version

UT_ADDONS_VERSION = "v0.1.2"

UT_ADDONS_TUPLE = tuplize_version(UT_ADDONS_VERSION[1:].split("-",1)[0])

if TYPE_CHECKING:
    from worlds.tracker.TrackerClient import TrackerCommandProcessor

from worlds.tracker import UT_VERSION_TUPLE
if not UT_VERSION_TUPLE >= (0,3,1):
    raise ImportError(f"UT Addons {UT_ADDONS_VERSION} is missing compatible UT")

def register_function(name:str, func:Callable):
    if name in UT_FUNCTIONS:
        ADDONS_ERRORS.append(f"{func.__module__} tried to add function named '{name}' but one already exists from {UT_FUNCTIONS[name].__module__}")
    else:
        UT_FUNCTIONS[name] = func

logger = logging.getLogger("Client")

def stupid_thing(self: "TrackerCommandProcessor"):
    """Find the most 'Shallow' locations"""
    if not self.ctx.game:
        logger.info("Not yet loaded into a game")
        return
    struct = self.ctx.updateTracker()
    multiworld = self.ctx.tracker_core.multiworld
    if multiworld is None:
        logger.info("You broke it somehow, don't do that")
        return
    tracked_world = self.ctx.tracker_core.get_current_world()
    assert tracked_world
    assert struct.state
    from BaseClasses import Region
    from typing import Tuple, Iterator
    from itertools import zip_longest

    def flist_to_iter(path_value) -> Iterator[str]:
        while path_value:
            region_or_entrance, path_value = path_value
            yield region_or_entrance

    def get_path(state: CollectionState, region: Region) -> int:
        reversed_path_as_flist = state.path.get(region, (str(region), None))
        string_path_flat = reversed(list(map(str, flist_to_iter(reversed_path_as_flist))))
        # Now we combine the flat string list into (region, exit) pairs
        pathsiter = iter(string_path_flat)
        pathpairs = zip_longest(pathsiter, pathsiter)
        return len(list(pathpairs))
    
    temp_dict:defaultdict[int,list[Region]] = defaultdict(list)
    regions = [tracked_world.get_region(region) for region in struct.in_logic_regions]
    for region in regions:
        temp_dict[get_path(struct.state,region)].append(region)
    if len(temp_dict) < 1:
        logger.error("No regions?")
        return
    lowest_steps = temp_dict[sorted(temp_dict.keys())[0]]

    for region in lowest_steps:
        for location in region.locations:
            if location.address is not None and location.name in struct.in_logic_locations and location.can_reach(struct.state):
                logger.info(location.name)

def next_progression(self: "TrackerCommandProcessor"):
    """Finds all items that will unlock a check immediately when collected, and a best guess of how many new checks they will unlock."""
    self.ctx.updateTracker()
    if self.ctx.tracker_core is None or self.ctx.tracker_core.multiworld is None or self.ctx.tracker_core.player_id is None:
        return
    baseLocs = len(self.ctx.tracker_core.locations_available)
    counter = Counter()
    goal_items = []
    items_to_check = {item.name for item in self.ctx.tracker_core.multiworld.get_items() if item.player == self.ctx.tracker_core.player_id and item.advancement}
    for item in items_to_check:
        self.ctx.tracker_core.manual_items.append(item)
        update_ret = self.ctx.updateTracker()
        assert update_ret.state
        newlocs = len(self.ctx.tracker_core.locations_available) - baseLocs
        if newlocs:
            counter[item] = newlocs
        if self.ctx.tracker_core.multiworld.completion_condition[self.ctx.tracker_core.player_id](update_ret.state):
            goal_items.append(item)
        self.ctx.tracker_core.manual_items.pop()
    if not counter:
        logger.info("No item will unlock any checks right now.")
    for (item, count) in counter.most_common():
        logger.info(f"{item} unlocks {count} check{'s' if count > 1 else ''}{' (and goal)' if item in goal_items else ''}.")
    self.ctx.updateTracker()

@mark_raw
def glp(self: "TrackerCommandProcessor", dest_name: str = ""):
    """Alias for get_logical_path"""
    self.commands["get_logical_path"](self,dest_name)

@mark_raw
def nearest_location(self: "TrackerCommandProcessor", region_name: str=""):
    """Find the locations that are nearest to a given region"""
    current_world = self.ctx.tracker_core.get_current_world()
    if current_world is None:
        logger.error("Tracked World not found, fix that")
        return
    normal_origin = current_world.origin_region_name
    if region_name not in current_world.multiworld.regions.region_cache[current_world.player]:
        logger.error("Region name not found")
        return
    current_world.origin_region_name = region_name
    stupid_thing(self)
    current_world.origin_region_name = normal_origin
    self.ctx.updateTracker()

@mark_raw
def get_regions(self: "TrackerCommandProcessor", region_name: str=""):
    current_world = self.ctx.tracker_core.get_current_world()
    if current_world is None:
        logger.error("Tracked World not found, fix that")
        return
    for region in current_world.get_regions():
        if region_name and region_name not in region.name:
            continue
        logger.info(region.name)




register_function("next_progression", next_progression)
register_function("get_depth", stupid_thing)
register_function("glp", glp)
register_function("nearest_locations", nearest_location)
register_function("get_regions", get_regions)