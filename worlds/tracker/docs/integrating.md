# Adding a tracker tab to your CommonClient client

With the addition of ctx.make_gui() in 0.5.1 adding a UT tracker tab is very simplified,
When you import CommonContext, try and import the UT context instead
```py

tracker_loaded = False
try:
    from worlds.tracker.TrackerClient import TrackerGameContext as SuperContext
    tracker_loaded = True
except ModuleNotFoundError:
    from CommonClient import CommonContext as SuperContext
```

You'll also need to remove the "Tracker" tag from your context by resetting it back to {"AP"}
```py
class YourGameContext(SuperContext):
    tags = {"AP"}
```

if you edit your GameManager at all, just use super().make_gui() to inheret UT's ui if it got loaded
```py
def make_gui(self):
    ui = super().make_gui()
    ui.base_title = "Minit CLIENT"
    return ui
```

and when you start your client up add a call to ctx.run_generate() if the UT apworld was found
```py
if tracker_loaded:
    ctx.run_generator()
if gui_enabled:
    ctx.run_gui()
```

# Calling UT's tracker engine directly

This one is a bit stranger because UT is built off of client code that doesn't need a reason to run if there is no connection, but the functionality is fully there still. 
Here's an example that instantiates the ctx object without a connection, runs generation, and then picks the correct player id from UT's internal multiworld.
Then with the ctx created you can check which locations are in logic by:
1. Setting ctx.missing_locations to the location IDs to be checked
1. Filling ctx.items_received to be the NetworkItem representation of items received (Note: only the id will be checked by UT so that's why a single value tuple is valid in this example)
1. Running updateTracker() on the ctx
1. checking ctx.locations_available for the avaliable location IDs


```py
from worlds.tracker.TrackerClient import TrackerGameContext, updateTracker


def get_tracker_ctx(name):
    ctx = TrackerGameContext("", "", no_connection=True)
    ctx.run_generator()

    ctx.player_id = ctx.launch_multiworld.world_name_lookup[name]
    return ctx


def get_in_logic(ctx, items=[], locations=[]):
    ctx.items_received = [(item,) for item in items]  # to account for the list being ids and not Items
    ctx.missing_locations = locations
    updateTracker(ctx)
    return ctx.locations_available


name = "qwintBug"
ctx = get_tracker_ctx(name)
print(get_in_logic(ctx, items=[16777224, 16777227, 16777289], locations=[16777360, 16777370, 16777410]))

# [16777370, 16777410]
```

# Adding a map page

Worlds can define a structure with the following fields in order to inform UT that a poptracker pack has been embeded

```py
from typing import ClassVar

    tracker_world: ClassVar = {
        "map_page_folder" : <Name of the folder that has all of poptracker files in it, not used for external poptracker packs>
        "map_page_maps" : <Relative location(s) of the maps.json file(s), may be a list if more then one file exists>
        "map_page_locations" : <Relative location(s) of the locations.json file(s), may be a list if more then one file exists>
        "map_page_setting_key" : <optional tag that informs which data storage key will be watched for auto tabbing>
        "map_page_index" : <optional function with signature Callable[Any,int] that will control the auto tabbing>
        "external_pack_key" : <optional string that is the name of the setting string that UT reads in order to find the external pop tracker pack>
        "poptracker_name_mapping" : <optional Dict that maps the poptracker pack names to the location id as they exist in the datapackage >
    }
```

You can more easily define the setting key with slot and team values by defining a `__init__` function for your World class and including the following
```py
        "map_page_setting_key": f"{self.player}_CURRENT_MAP"
```

for `external_pack_key` you can define the setting like this, this should point to a zipped poptracker pack
```py
from settings import FilePath
class UTPackPath(FilePath):
    #required = False #You can uncomment this to allow users to not have the poptracker map, if the key is "" then the map tab won't be rendered
    pass
```

The contents of maps.json and locations.json are the same as poptracker format with the exception that all logic is derived from UT's internal world, and the location names must match exactly with AP location names

# World flags

UT supports a number of world flags that determine how UT will handle the world, the following is the current list

 * `disable_ut` : This causes UT to ignore the world, to be used only if the world is known to have issues when loaded in UT and fixing it would be more trouble then it's worth (Merged game/existing compatent poptracker etc)
 * `ut_can_gen_without_yaml` : Tells UT that the game will do a full regen

# Adding In-Logic Callbacks

To be filled out later
