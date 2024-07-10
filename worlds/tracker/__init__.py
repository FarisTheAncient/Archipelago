
from worlds.LauncherComponents import Component, components, Type, launch_subprocess


def launch_client():
    import sys
    from .TrackerClient import launch as TCMain
    if not sys.stdout or "--nogui" not in sys.argv:
        launch_subprocess(TCMain, name="Universal Tracker client")
    else:
        TCMain()

class TrackerWorld:
    pass

components.append(Component("Universal Tracker", None, func=launch_client, component_type=Type.CLIENT))
