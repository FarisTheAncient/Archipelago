
from worlds.LauncherComponents import Component, components, Type, launch_subprocess, icon_paths
from settings import Group, Bool, UserFolderPath, _world_settings_name_cache
from typing import Dict, Optional, List, Any, Union, ClassVar, NamedTuple, Callable
from worlds.AutoWorld import World
from BaseClasses import CollectionState
from collections import Counter


def launch_client(*args):
    try:
        from worlds.LauncherComponents import launch
        from .TrackerClient import launch as TCMain
        launch(TCMain, name="Universal Tracker client", args=args)
    except ImportError:
        launch_if_needed(*args)


# TODO remove once we can only keep compat with 0.6.0+
def launch_if_needed(*args):
    import sys
    from .TrackerClient import launch as TCMain
    if not sys.stdout or "--nogui" not in sys.argv:
        launch_subprocess(TCMain, name="Universal Tracker client", args=args)
    else:
        TCMain(*args)


class CurrentTrackerState(NamedTuple):
    all_items: Counter
    prog_items: Counter
    events: List[str]
    state: CollectionState


class TrackerSettings(Group):
    class TrackerPlayersPath(UserFolderPath):
        """Players folder for UT look for YAMLs"""

    class RegionNameBool(Bool):
        """Show Region names in the UT tab"""

    class LocationNameBool(Bool):
        """Show Location names in the UT tab"""

    class HideExcluded(Bool):
        """Have the UT tab ignore excluded locations"""

    player_files_path: TrackerPlayersPath = TrackerPlayersPath("Players")
    include_region_name: Union[RegionNameBool, bool] = False
    include_location_name: Union[LocationNameBool, bool] = True
    hide_excluded_locations: Union[HideExcluded, bool] = False


class TrackerWorld(World):
    settings: ClassVar[TrackerSettings]
    settings_key = "universal_tracker"

    # to make auto world register happy so we can register our settings
    game = "Universal Tracker"
    hidden = True
    item_name_to_id = {}
    location_name_to_id = {}


class UTMapTabData:
    """The holding class for all the poptracker integration values"""

    map_page_folder: str
    """The name of the folder within the .apworld that contains the poptracker pack"""

    map_page_maps: List[str]
    """The relative paths within the map_page_folder of the map.json"""

    map_page_locations: List[str]
    """The relative paths within the map_page_folder of the location.json"""

    map_page_setting_key: str
    """Data storage key used to determine which page should be loaded"""

    map_page_index: Callable[[Any], int]
    """Function that gets called to map the data storage string to the map index"""

    def __init__(
            self, map_page_folder: str = "", map_page_maps: Union[List[str], str] = "",
            map_page_locations: Union[List[str], str] = "", map_page_setting_key: str | None = None,
            map_page_index: Callable[[Any], int] | None = None, **kwargs):
        self.map_page_folder = map_page_folder
        if isinstance(map_page_maps, str):
            self.map_page_maps = [map_page_maps]
        else:
            self.map_page_maps = map_page_maps
        if isinstance(map_page_locations, str):
            self.map_page_locations = [map_page_locations]
        else:
            self.map_page_locations = map_page_locations
        self.map_page_setting_key = map_page_setting_key
        if map_page_index and callable(map_page_index):
            self.map_page_index = map_page_index
        else:
            self.map_page_index = lambda _: 0
        pass


icon_paths["ut_ico"] = f"ap:{__name__}/icon.png"
components.append(Component("Universal Tracker", None, func=launch_client, component_type=Type.CLIENT, icon="ut_ico",
                            description="A Generic tracker that uses your AP install to duplicate generation logic"))
