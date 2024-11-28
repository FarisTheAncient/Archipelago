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


# Adding In-Logic Callbacks

To be filled out later
