from fuzz import BaseHook, GenOutcome
from typing import List, Dict, Set
import collections
import logging
from . import TrackerCore, DeferredEntranceMode
from BaseClasses import MultiWorld,Location,ItemClassification
from NetUtils import NetworkItem
logger = logging.getLogger("Fuzzer")


class Hook(BaseHook):
    ut_core:TrackerCore.TrackerCore
    player_files_path:str
    status = None

    def before_generate(self, args):
        self.status = None
        self.player_files_path = args.player_files_path
        self.ut_core = TrackerCore.TrackerCore(logger,False,False)
        self.ut_core.enforce_deferred_connections = DeferredEntranceMode.disabled
        self.ut_core.run_generator(None,None,args.player_files_path) #initial UT gen

    def after_generate(self, mw:MultiWorld, output_path):
        # Default to OptionError in case generation failed or is invalid, so
        # that it gets marked as ignored as we're not testing for that
        self.status = GenOutcome.OptionError
        if mw is None:
            return
        if len(mw.worlds)>1:
            return
        assert self.player_files_path
        self.status = GenOutcome.Success
        import zipfile
        with zipfile.ZipFile(output_path+"/AP_"+mw.seed_name+".zip") as zf:
            for file in zf.namelist():
                if file.endswith(".archipelago"):
                    data = zf.read(file)
                    break
            else:
                raise Exception("No .archipelago found in archive.")
        from MultiServer import Context
        temp = Context.decompress(data)

        slot_data = temp["slot_data"][1] #slot 0 is reserved

        self.ut_core.set_slot_params(mw.worlds[1].game,1,mw.player_name[1],1)
        self.ut_core.initalize_tracker_core(mw.worlds[1].__class__,slot_data)
        assert self.ut_core.multiworld, self.ut_core.gen_error

        remaining_locations = [location.address for location in mw.worlds[1].get_locations() if location.address is not None]
        current_inventory = [NetworkItem(item.code,-2,item.player,item.classification) for item in mw.precollected_items[1] if item.code is not None]
        new_items = []
        new_inventory = []

        # Recalc spheres
        for sphere_number, sphere in enumerate(mw.get_sendable_spheres()):
            current_sphere: Dict[str,Location] = {}
            for sphere_location in sphere:
                if sphere_location.address is not None:
                    current_sphere[sphere_location.name] = sphere_location
            current_inventory.extend(new_items)
            new_inventory.clear()
            new_items.clear()
            if current_sphere:
                self.ut_core.set_missing_locations(set(remaining_locations))
                self.ut_core.set_items_received(current_inventory)
                update_ret = self.ut_core.updateTracker()
                missed_locations = []
                for in_logic_location in update_ret.in_logic_locations:
                    if in_logic_location in current_sphere:
                        true_item = current_sphere[in_logic_location].item
                        new_items.append(NetworkItem(true_item.code,true_item.location.address,true_item.player,true_item.classification))
                        if ItemClassification.progression in true_item.classification:
                            new_inventory.append(true_item.name)
                        remaining_locations.remove(current_sphere[in_logic_location].address)
                        del current_sphere[in_logic_location]
                    else:
                        missed_locations.append(in_logic_location)
                if len(current_sphere) > 0:
                    print(f"Locations `{','.join(current_sphere.keys())}` were in server logic but not expected in UT")
                    print(f"UT logic sphere `{','.join(update_ret.in_logic_locations)}`")
                    print(f"Locations that weren't created in UT = [{','.join([loc for loc in current_sphere if loc not in self.ut_core.multiworld.regions.location_cache[self.ut_core.player_id]])}]")
                if len(missed_locations) > 0:
                    print(f"Locations {','.join(missed_locations)} were expected to be in logic but weren't")
                    print(f"Server logic sphere `{','.join([location.name for location in sphere if location.address is not None])}`")
                if len(current_sphere)>0 or len(missed_locations)>0:
                    print(f"After sphere #{sphere_number}")
                    item_id_to_name = self.ut_core.multiworld.worlds[self.ut_core.player_id].item_id_to_name
                    print(f"New Inventory = [{','.join(new_inventory)}]")
                    print(f"Current Inventory = [{','.join([item_id_to_name[item.item] for item in current_inventory if item.flags & 1])}]")
                    print(f"UT accessable regions `{','.join([region.name for region in update_ret.state.reachable_regions[1]])}`")
                    print(f"State inventory = `{','.join([f'{k}:{v}' for k,v in update_ret.state.prog_items[1].items()])}`")
                    self.status = GenOutcome.Failure
                    return
            else:
                return #if get_sendable_spheres returns an empty sphere that means we're done, the next sphere will be any unreachable locations... which aren't reachable...

                
        # Do the magic here, set `self.status` accordingly to `GenOutcome.Failure`/`GenOutcome.Success`

    def reclassify_outcome(self, outcome, exc):
        return (self.status if self.status is not None else outcome), exc