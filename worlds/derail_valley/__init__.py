from worlds.AutoWorld import WebWorld, World
from typing import Set, List, ClassVar, Union, Any
from BaseClasses import Tutorial, Item
from settings import Group, FilePath

from .items import DVItem, get_items, get_classification, get_starting_items, get_filler_items
from .locations import get_locations, get_all_locations_data
from .rules import set_location_rules
from .options import dv_option_groups, DVOptions, DemoLocoBehaviour
from .regions import init_areas

class DVSettings(Group):
    class UTPackPath(FilePath):
        required = False
        ut_dialog_name = "Select DVMapsPlus Zip"

    ut_pack_path: Union[UTPackPath, str] = UTPackPath()

class DVWeb(WebWorld):
    theme = "stone"

    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up the Derail Valley randomizer"
        "and connecting to an Archipelago server.",
        "English",
        "AP_setup.md",
        "setup/en",
        ["Bacucysone"]
    )
    rich_text_options_doc=True
    option_groups = dv_option_groups
    tutorials = [setup_en]


class DVWorld(World):
    """Drive a collection of locomotives to earn money, licenses, and find the relic demonstrator locomotives"""
    game = "Derail Valley"
    # option_definitions = DVOptions
    data_version=1
    web = DVWeb()

    options_dataclass = DVOptions  # options the player can set
    options: DVOptions  # typing hints for option results
    topology_present = True  # show path to required location checks in spoiler
    settings: DVSettings

    # This struct controls how UT renders the maps
    tracker_world: ClassVar[dict[str, Any]] = {
        "external_pack_key": "ut_pack_path", # From the Group ealier
        "map_page_folder": "tracker",
        "map_page_maps": "maps.json",
        "map_page_locations": "locations.json"
    }

    # The following two dicts are required for the generation to know which
    # items exist. They could be generated from json or something else. They can
    # include events, but don't have to since events will be placed manually.

    all_items = get_items()
    all_locations = get_all_locations_data()

    all_stations = ["CME", "CMS", "CP", "CS", "CW", "FF", "FM", "FRC", "FRS", "GF", "HB", "IME", "IMW", "MB", "MF", "OR", "OWC", "OWN", "SM", "SW"]
    all_stations_unlock = [f"{x} Station unlock" for x in all_stations]
    all_locos = ["DE2", "DM3", "DH4", "DE6", "S060", "S282"]
    all_locos_license = [f"{x} locomotive license" for x in all_locos]
    item_name_to_id = {data.name: data.code for
                       data in all_items if data.code is not None}
    location_name_to_id = {loc_type.name: loc_type.code for
                            loc_type in all_locations if loc_type.code is not None}
    starting_items: List[Item] = []
    starting_station: str

    def create_item(self, name:str):
        id = self.item_name_to_id[name]
        classe = get_classification(name)
        return DVItem(name, classe, id, self.player)
        

    def create_regions(self) -> None:
        locations = init_areas(self)
        set_location_rules(self, locations)
    
    def get_excluded_items(self)-> Set[Item]:
        excluded: Set[Item] = set()
        return excluded

    def get_common_items(self, excluded_items: List[Item]) -> List[Item]:
        pool : List[Item] = []
        for data in self.all_items:
            name = data.name
            if name not in excluded_items:
                for _ in range(data.amount):
                    new_item = self.create_item(name)
                    pool.append(new_item)
        return pool

    def get_filler_item_name(self):
        return self.random.choice(get_filler_items()).name

    def pad_items(self, pool: List[Item]) -> None:
        for _ in range(len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)):
            item = self.create_item(self.get_filler_item_name())
            pool.append(item)

    def create_items(self):
        excluded_items = get_starting_items(self)
        possible_stations = []
        for item in excluded_items:
            if item in self.all_stations_unlock:
                possible_stations.append(item.split(" ")[0])
            self.push_precollected(self.create_item(item))
        if self.options.dispatcher.value == 1:
            excluded_items.append("Dispatcher license")
            dispatcher_license = self.create_item("Dispatcher license")
            self.multiworld.get_location("Dispatcher license", self.player).place_locked_item(dispatcher_license)
        if self.options.demo_loco_spawn == DemoLocoBehaviour.option_vanilla:
            excluded_items.extend(["Demo locomotive "+ loco for loco in self.all_locos])
        if len(possible_stations) == 0:
            possible_stations.append("SM") # This spawns you at SM if you don't have a license
        self.starting_station = self.random.choice(possible_stations)
        pool = self.get_common_items(excluded_items)
        nb_unfilled_locations = len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)
        pool.extend([self.create_item("Double job token") for _ in range(int(nb_unfilled_locations * self.options.double_tokens.value / 100.0))])
        self.pad_items(pool)
        self.multiworld.itempool += pool
    
    def fill_slot_data(self):
        # Do some checks on the options data
        if self.options.random_license_price_max.value < self.options.random_license_price_min.value:
            self.options.random_license_price_max.value = self.options.random_license_price_min.value + 1000
        slotdata = {
            "Money": self.options.money.value,
            "Config": {
                "ShuntThreshold":[self.options.nb_shunts.value for _ in range(20)],
                "FreightThreshold": [self.options.nb_freights.value for _ in range(20)],
                "LocoJobsThreshold": [self.options.nb_locos.value for _ in range(6)],
                "VictoryCondition": self.options.victory_condition.value,
                "Victory": self.options.nb_stations.value,
                "VictoryThreshold": self.options.nb_jobs.value,
                "VictoryDemoLoco": self.options.nb_demo_locos.value,
                "HintsOnLocoLicense": self.options.hints_loco.value == 1,
                "HintsOnStationLicense": self.options.hints_station.value == 1,
                "DeathLink": self.options.death_link.value == 1,
                "HintsOnLicenseManager": self.options.hints_license_manager == 1,
                "RandomiseLicensePrices": self.options.randomise_license_prices == 1,
                "RandomiseLicensePricesMin": self.options.random_license_price_min.value,
                "RandomiseLicensePricesMax": self.options.random_license_price_max.value,
                "VanillaDemoLoco": self.options.demo_loco_spawn.value,
                "RelicSpawnChecks": self.options.demo_checks.value == 1,
                "MuseumChecks": self.options.museum_checks.value == 1,
            },
            "StartStation": self.starting_station
        }
        return slotdata
    def get_job_hint(self):
        return None if self.options.hints_first == 1 and self.options.start_job.value == 4 else ""
    def get_loco_hint(self):
        return None if self.options.hints_first == 1 and self.options.start_loco.value == 7 else ""
    def get_station_hint(self):
        return None if self.options.hints_first == 1 and self.options.station_licenses.value == 0 else ""
    def pre_output(self):
        all_jobs = {"Freight haul license", "Logistical haul license", "Shunting license"}
        all_locos = set(self.all_locos_license)
        all_stations = set(self.all_stations_unlock)
        first_found = [self.get_job_hint(), self.get_loco_hint(), self.get_station_hint()]
        for locations in self.multiworld.get_spheres():
            items = {location.item.name for location in locations if location.item.player == self.player}
            maybe_job = items & all_jobs
            if first_found[0] is None and len(maybe_job) > 0:
                first_found[0] = maybe_job.pop()
            maybe_loco = items & all_locos
            if first_found[1] is None and len(maybe_loco) > 0:
                first_found[1] = maybe_loco.pop()
            maybe_station = items & all_stations
            if first_found[2] is None and len(maybe_station) > 0:
                first_found[2] = maybe_station.pop()
            if first_found[0] is not None and first_found[1] is not None and first_found[2] is not None:
                break
        self.options.start_hints.value |= {x for x in first_found if x is not None and len(x) > 0}
