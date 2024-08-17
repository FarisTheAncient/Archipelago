
from worlds.LauncherComponents import Component, components, Type, launch_subprocess
from typing import Dict, Optional, List, Any, Union


def launch_client():
    import sys
    from .TrackerClient import launch as TCMain
    if not sys.stdout or "--nogui" not in sys.argv:
        launch_subprocess(TCMain, name="Universal Tracker client")
    else:
        TCMain()

class TrackerWorld:
    pass

class UTMapTabData:
    """The holding class for all the poptracker integration values"""

    map_page_folder:str
    """The name of the folder within the .apworld that contains the poptracker pack"""

    map_page_maps:List[str]
    """The relative paths within the map_page_folder of the map.json"""

    map_page_locations:List[str]
    """The relative paths within the map_page_folder of the location.json"""

    def __init__(self, map_page_folder:str, map_page_maps:Union[List[str],str], map_page_locations:Union[List[str],str]):
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
