
from worlds.LauncherComponents import Component, components, Type, launch_subprocess
from typing import Dict, Optional, List, Any, Union, ClassVar
from settings import Group, Bool, LocalFolderPath, _world_settings_name_cache
from worlds.AutoWorld import World

def launch_client():
    import sys
    from .TrackerClient import launch as TCMain
    if not sys.stdout or "--nogui" not in sys.argv:
        launch_subprocess(TCMain, name="Universal Tracker client")
    else:
        TCMain()


class TrackerSettings(Group):
    class TrackerPlayersPath(LocalFolderPath):
        """Alternative Players folder for UT to use"""

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

    map_page_folder:str
    """The name of the folder within the .apworld that contains the poptracker pack"""

    map_page_maps:List[str]
    """The relative paths within the map_page_folder of the map.json"""

    map_page_locations:List[str]
    """The relative paths within the map_page_folder of the location.json"""

    def __init__(self, map_page_folder:str="", map_page_maps:Union[List[str],str]="", map_page_locations:Union[List[str],str]=""):
        self.map_page_folder=map_page_folder
        if isinstance(map_page_maps,str):
            self.map_page_maps = [map_page_maps]
        else:
            self.map_page_maps = map_page_maps
        if isinstance(map_page_locations,str):
            self.map_page_locations = [map_page_locations]
        else:
            self.map_page_locations = map_page_locations
        pass

    def map_page_index(self, data: Dict[str, Any]) -> int:
        """Function used to fetch the map index that should be loaded,
          it will be passed in the data storage (eventually)
          Right now it should just return 0"""
        return 0

components.append(Component("Universal Tracker", None, func=launch_client, component_type=Type.CLIENT))
