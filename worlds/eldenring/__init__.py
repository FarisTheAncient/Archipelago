from collections.abc import Sequence
from collections import defaultdict
from enum import Enum
from itertools import combinations
from dataclasses import replace, dataclass, asdict
import settings, typing, Utils, math, json
from logging import warning
from typing import cast, Any, Callable, Dict, Set, List, Optional, TextIO, Union, Tuple

from BaseClasses import CollectionState, MultiWorld, Region, Location, LocationProgressType, Entrance, ItemClassification
from Fill import remaining_fill, fill_restrictive, sweep_from_pool, FillError

from worlds.AutoWorld import World, WebWorld
from worlds.generic.Rules import CollectionRule, ItemRule, add_rule, add_item_rule

from .bosses import ERBossInfo, all_bosses, base_bosses, dlc_bosses, default_rykard_location, default_serpent_location, all_boss_locations_dictionary
from .items import ERItem, ERItemData, ERItemCategory, filler_item_names_dlc, filler_item_names_vanilla, item_descriptions, item_table, item_table_vanilla, item_table_dlc, item_table_tp_dlc, item_name_groups
from .locations import ERLocation, ERLocationData, location_tables, location_descriptions, location_dictionary, location_name_groups, region_order, region_order_dlc, dupable_locations
from .options import EROptions, option_groups, shard_list
from .presets import er_options_presets
from Options import OptionError, Option

# Settings
class EldenRingSettings(settings.Group):
    class ForceLocalItems(list):
        """Choose certain categories to be local only for all EldenRing worlds.
        If every category is set to local, Accessory and AshofWar will be unset to dodge fill errors.
        - [Est Items] **Item Group**
        - [472] **Weapon**: All Weapons and Ammo.
        - [423] **Armor**: All Armors.
        - [160] **Accessory**: All Talismans.
        - [105] **AshofWar**: All Ashes of War.
        - [3250] **Goods**: The two below
        - [1000] **Filler**: All Crafting Mats, and some craftables.
        - [2200] **Non-Filler**: Smithing stones, Spells and Spirit ashes."""
    
    class ForceRegionLock(settings.Bool):
        """Forces region_lock on, since sphere 1 would have ~2.1k checks."""
    
    class GoalBossesAllowed(int):
        """How many Goal Bosses can Elden Ring have.
        There are 207 Bosses total in Base + DLC, and 165 in Base game."""
    
    force_local_items: typing.Union[ForceLocalItems, list] = ["Filler"]
    force_region_lock: typing.Union[ForceRegionLock, bool] = True
    goal_bosses_allowed: typing.Union[GoalBossesAllowed, int] = 150

# Web stuff
class EldenRingWeb(WebWorld):
    rich_text_options_doc = True
    theme = "stone"
    option_groups = option_groups
    options_presets = er_options_presets
    item_descriptions = item_descriptions
    
class _LocationStatus(Enum):
    """An enum representing different possible states a location may be in given a player's options.
    """

    ABSENT = 0b000
    """The location is totally inaccessible from the game.

    For example: DLC locations with `enable_dlc: false`.
    """

    UNRANDOMIZED_UNMISSABLE = 0b001
    """The location is unrandomized but not missable.

    For example, an unmissable but explicitly excluded location with
    `excluded_location_behavior: do_not_randomize`.
    """

    UNRANDOMIZED_MISSABLE = 0b011
    """The location is unrandomized as well as missable.

    For example, any missable location with `missable_location_behavior: do_not_randomize`.
    """

    RANDOMIZED_UNMISSABLE = 0b101
    """The location is accessible from the game, randomized, and can't be missed."""

    RANDOMIZED_MISSABLE = 0b111
    """The location is accessible from the game, randomized, but can be missed."""

    @property
    def is_absent(self) -> bool:
        """Returns whether this location is totally inaccessible from the game."""
        return self == _LocationStatus.ABSENT

    @property
    def is_randomized(self) -> bool:
        """Returns whether this location is accessible and can contain a random item."""
        return self.value & 0b101 == 0b101

    @property
    def is_missable(self) -> bool:
        """Returns whether this location is accessible but also missable."""
        return self.value & 0b011 == 0b011

# Main World
class EldenRing(World):
    """ 
    Elden Ring Archipeligo.
    """ # description

    game = "EldenRing"
    options: EROptions
    options_dataclass = EROptions
    web = EldenRingWeb()
    settings: typing.ClassVar[EldenRingSettings]
    base_id = 69000
    required_client_version = (0, 6, 7)
    topology_present = True
    item_name_to_id = {data.name: data.ap_code for data in item_table.values() if data.ap_code is not None}
    location_name_to_id = {
        location.name: location.ap_code
        for locations in location_tables.values()
        for location in locations
        if location.ap_code is not None
    } | {
        f"{location.name}, extra item {_}": 8000000 + (location.ap_code - 7000000) + (len(location_dictionary) * _)
        for locations in location_tables.values()
        for location in locations
        if location.ap_code is not None and location.name in dupable_locations
        for _ in range(1, 8) # how many dupes to prefill, dupe 1 and 2
        if dupable_locations[location.name] >= _
    }
    location_name_groups = location_name_groups
    item_name_groups = item_name_groups
    location_descriptions = location_descriptions
    item_descriptions = item_descriptions
    great_rune_item_names = (
        "Godrick's Great Rune",
        "Rykard's Great Rune",
        "Radahn's Great Rune",
        "Morgott's Great Rune",
        "Mohg's Great Rune",
        "Malenia's Great Rune",
        "Great Rune of the Unborn",
    )
    
    rykard_location: ERBossInfo = None
    serpent_location: ERBossInfo = None
    """If enemy randomization is enabled, this is the boss who Rykard should replace.
    
    This is used to determine where the Serpent-Hunter can be placed.
    """
    
    # UT stuff
    soft_logic_enabled: bool = None
    location_id_to_alias: Dict[int, str] = {}
    ut_can_gen_without_yaml = True
    
    base_enabled: bool = None
    dlc_excluded: bool = None
    all_excluded_locations: Set[str] = set()
    all_priority_locations: Set[str] = set()
    all_possible_priority_locations: Set[str] = set()
    all_duplicate_locations: Set[str] = set()
    all_starting_items: list[int] = []
    starting_inventory: list[str] = [] # start inv from options
    goal_bosses: list[ERBossInfo] = []
    dupe_location_dictionary: Dict[str, ERLocationData] = {}
    dupe_location_tables: Dict[str, list[ERLocationData]] = {}
    prio_in_region: Dict[str, list[str]] = {}
    
    local_items: Set[str] = set()
    # this is only used to output local count in create_items

    def post_fill(self):
        badly_placed_items: Dict[str, str] = {}
        if self.options.important_at_priority_only:
            for loc in self.multiworld.get_filled_locations(self.player):
                if loc.progress_type != LocationProgressType.PRIORITY and loc.item.classification == ItemClassification.progression and not loc.locked: # not preplaced
                    badly_placed_items[loc.name] = loc.item
                    # a location that is not prio got a prio item and wasn't preplaced !!!!!!! fail gen
                    # raise OptionError(f"\n  A progression item: {loc.item},\n  was placed on a non-priority location: ({loc.name}),\n  you most likely have to little priority locations.")
              
        if len(badly_placed_items) > 0:
            raise OptionError(f"{self.player_name} misplaced prog: {badly_placed_items}"
                              f"\nIf there are about 1-3 misplaced items just gen again till it works,"
                              f"\nIf there are 10+ you don't have enough priority locations, add more groups.")

    def __init__(self, multiworld: MultiWorld, player: int):
        super().__init__(multiworld, player)
        self.location_name_to_id = {
            location.name: location.ap_code
            for locations in location_tables.values()
            for location in locations
            if location.ap_code is not None
        }
        self.base_itempool = None
        self.dlc_itempool = None
        self.created_regions = None
        self.all_excluded_locations = set()
        self.all_priority_locations = set()
        self.all_possible_priority_locations = set()
        self.all_duplicate_locations = set()
        self.prio_in_region = {}
        self.all_starting_items = []
        self.starting_inventory = []
        self.goal_bosses = []
        self.dupe_location_dictionary = {}
        self.dupe_location_tables = {}
        self.ignored_marker_entrance_rules: Set[str] = set()
        self.local_items = set()
        self.explicit_indirect_conditions = False
        self.soft_logic_enabled = True
        self.location_id_to_alias: dict[int, str] = {}

    def generate_early(self) -> None:
        re_gen_passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        if re_gen_passthrough and self.game in re_gen_passthrough:
            self.soft_logic_enabled = False
            slot_data: dict[str, Any] = re_gen_passthrough[self.game]
            slot_options: dict[str, Any] = slot_data.get("options", {})
            for key, value in slot_options.items():
                opt: Optional[Option] = getattr(self.options, key, None)
                if opt is not None:
                    setattr(self.options, key, opt.from_any(value))
        
            # Inform Universal Tracker where Rykard is being randomized to.
            if slot_options["enemy_rando"] and slot_options["rykard_encounter"] == False:
                force_bosses = slot_data["forceBosses"]
                for boss in all_bosses:
                    if boss.id in force_bosses and force_bosses[boss.id] == default_rykard_location.id:
                        self.rykard_location = boss
                    if boss.id in force_bosses and force_bosses[boss.id] == default_serpent_location.id:
                        self.serpent_location = boss
        else:
            # Randomize Rykard and Serpent manually so that we know where to place the Serpent-Hunter.
            if self.options.enemy_rando and not self.options.rykard_encounter: # only force if not given SH
                self.rykard_location = self.random.choice(
                    [boss for boss in all_bosses if self._allow_boss_for_rykard(boss)])
                self.serpent_location = self.random.choice(
                    [boss for boss in all_bosses if self._allow_boss_for_rykard(boss) and boss.name != self.rykard_location.name])
            elif not self.options.enemy_rando:
                self.rykard_location = default_rykard_location
                self.serpent_location = default_serpent_location
        
        for region in location_tables: # make sure table has all values
            self.dupe_location_tables.setdefault(region, [])
        
        self.dlc_excluded = "DLC" in self.options.exclude_locations.excluded_groups()
        if self.dlc_excluded and self.options.excluded_location_behavior.value >= 3:
            # do not rando or omit, just disabled the dlc lol
            self.options.enable_dlc.value = False
        
        self.base_enabled = not (self.options.dlc_start == 1 and self.options.enable_dlc)
        self.created_regions = set()
        self.all_excluded_locations.update(self.options.exclude_locations.value)
        
        self.all_priority_locations.update(self.options.priority_location_groups.value)
        for loc in self.all_priority_locations.copy():
            if (not self.base_enabled and not location_dictionary[loc].dlc 
                or not self.options.enable_dlc and location_dictionary[loc].dlc 
                or location_dictionary[loc].missable or loc in self.all_excluded_locations):
                self.all_priority_locations.remove(loc)
            
        # remove excluded from prio then make sure excluded doesnt contain prog or useful
        for loc in self.all_excluded_locations.copy():
            if (not self.base_enabled and not location_dictionary[loc].dlc 
                or not self.options.enable_dlc and location_dictionary[loc].dlc
                or ItemClassification.progression in item_table[location_dictionary[loc].default_item_name].is_important(self.options)
                or ItemClassification.useful in item_table[location_dictionary[loc].default_item_name].is_important(self.options)):
                self.all_excluded_locations.remove(loc)
                self.options.exclude_locations.value.remove(loc)
        
        local_item_only_lowercase = set(key.lower() for key in self.options.local_item_only.value)
        [local_item_only_lowercase.add(key.lower()) for key in self.settings.force_local_items]
        
        if (len(local_item_only_lowercase.intersection(("weapon", "armor", "accessory", "goods"))) == 4
            or len(local_item_only_lowercase.intersection(("weapon", "armor", "accessory", "filler", "non-filler"))) == 5):
            # is everything local, make sure accessory and ashofwar is atleast not local to attempt to avoid fill error, still a rare chance
            warning(f"\nEldenRing Player {self.player_name} has too many categories of local_item_only set to local, this can cause a fill error."
                    f"\nRemoving Accessory and AshofWar from local only to attempt to dodge fill error, or fix yaml to not make everything local.")
            local_item_only_lowercase.remove("accessory")
            if "ashofwar" in local_item_only_lowercase:
                local_item_only_lowercase.remove("ashofwar")
        
        # verify shard counts
        for (shard, shard_dict) in self.options.key_item_shards.value.items():
            if len(shard_dict) != 2 or 'Req' not in shard_dict or 'Max' not in shard_dict:
                raise OptionError(f"Player {self.player_name} has {shard} that doesn't contain Req and Max entries.")

            if shard == "RoldMedallionShards" and shard_dict['Max'] > 1:
                if self.options.great_runes_required_mountain.value >= 0:
                    warning(f"EldenRing Player {self.player_name} has {shard_dict['Max']} RoldMedallionShards in key_item_shards, "
                            f"so great_runes_required_mountain = {self.options.great_runes_required_mountain.value} will be ignored")
                self.options.great_runes_required_mountain.value = -1

            for val in shard_dict:
                max_shard_count = 10
                if shard_dict[val] < 1:
                    shard_dict[val] = 1
                    # warning(f"{shard} {val} less then 1")
                if shard_dict[val] > max_shard_count:
                    shard_dict[val] = max_shard_count
                    # warning(f"{shard} {val} greater then {max_shard_count}")
            if shard_dict['Req'] > shard_dict['Max']:
                warning(f"EldenRing Player {self.player_name} requires {shard_dict['Req']} out of {shard_dict['Max']} {shard}, "
                        f"so both values will be set to {shard_dict['Max']}")
                shard_dict['Req'] = shard_dict['Max']
        
        if self.options.important_at_priority_only and len(self.all_priority_locations) < 50: # make sure player adds enough locations
            raise OptionError(f"Player {self.player_name} has important_at_priority_only enabled but has {len(self.all_priority_locations)} "
                              f"priority locations, less than 50 required. Add groups to priority_location_groups.")
        
        m_goal_bosses = self._goal_bosses()
        if self.options.exclude_dungeon.value: # exclude dungeon bosses
            m_goal_bosses = [boss for boss in m_goal_bosses if not boss.dungeon]
        
        if self.multiworld.players != 1: # this only applies when not solo
            if len(m_goal_bosses) > self.settings.goal_bosses_allowed:
                raise OptionError(f"EldenRing host.yaml goal_bosses_allowed Error: "
                                f"Player {self.player_name} has Goal Bosses count set higher then allowed amount. "
                                f"Current amount: {len(m_goal_bosses)}, allowed amount: {self.settings.goal_bosses_allowed}.")
            elif self.settings.force_region_lock and self.options.world_logic == "open_world":
                self.options.world_logic.value = 0
        
        if self.options.enable_dlc:
            if not self.dlc_excluded: # if dlc not excluded, add dlc bosses
                self.goal_bosses += [boss for boss in m_goal_bosses if boss in dlc_bosses]
        elif len([boss for boss in m_goal_bosses if boss in base_bosses]) == 0: # dlc disabled, is there a base game boss?
            raise OptionError(f"Player {self.player_name} has no boss goals in Base Game but has DLC disabled.")
        
        if self.base_enabled:
            self.goal_bosses += [boss for boss in m_goal_bosses if boss in base_bosses]
        elif self.dlc_excluded: # dlc only, is dlc excluded?
            raise OptionError(f"Player {self.player_name} has DLC excluded but DLC only is on.")
        elif len([boss for boss in m_goal_bosses if boss in dlc_bosses]) == 0: # dlc only, is there a dlc boss?
            raise OptionError(f"Player {self.player_name} has no boss goals in DLC but is doing DLC Only.")
        else: # if dlc only no separate_prog
            self.options.separate_progression.value = False
        
        if self.options.enable_dlc and self.base_enabled and len([boss for boss in m_goal_bosses if boss in base_bosses + dlc_bosses]) == 0: # is there a goal boss?
            raise OptionError(f"Player {self.player_name} no valid Goal bosses, please set a valid Goal boss.")
        
        using_table = {}
        if self.base_enabled: 
            using_table.update(item_table_vanilla)
            if self.options.enable_tp_dlc: using_table.update(item_table_tp_dlc)
        if self.options.enable_dlc: using_table.update(item_table_dlc)
        for item in using_table.values(): # loop of whole item table
            if item.is_important(self.options) not in (ItemClassification.progression, ItemClassification.progression_deprioritized, ItemClassification.useful):
                match item.category:
                    case ERItemCategory.GOODS:
                        if (('goods' in local_item_only_lowercase) 
                            or ('filler' in local_item_only_lowercase and (item.replacable or item_table[item.base_name].filler))
                            or ('non-filler' in local_item_only_lowercase and not (item.replacable or item_table[item.base_name].filler))):
                            self.options.local_items.value.add(item.name)
                    case ERItemCategory.WEAPON:
                        if 'weapon' in local_item_only_lowercase:
                            self.options.local_items.value.add(item.name)
                    case ERItemCategory.ARMOR:
                        if 'armor' in local_item_only_lowercase:
                            self.options.local_items.value.add(item.name)
                    case ERItemCategory.ACCESSORY:
                        if 'accessory' in local_item_only_lowercase:
                            self.options.local_items.value.add(item.name)
                    case ERItemCategory.ASHOFWAR:
                        if 'ashofwar' in local_item_only_lowercase:
                            self.options.local_items.value.add(item.name)
        
        self.local_items = self.options.local_items.value
        
        for i in self.options.start_inventory.value:
            for _ in range(self.options.start_inventory.value[i]):
                self.starting_inventory.append(i)
        self.options.start_inventory.value = {} # remove so items aren't precollected
    
    def _allow_boss_for_rykard(self, boss: ERBossInfo) -> bool:
        """Returns whether boss is a valid location for Rykard in this seed."""
        if not boss.allow_rykard and self.options.restrictive_bosses: return False 
        else: return True
        
        # removed base / dlc restriction, so dlc only doesnt have both rykard and serpent in it everytime
        # or not self.options.enable_dlc and boss.dlc or not self.base_enabled and not boss.dlc

    #MARK: Connections
    def create_regions(self) -> None:
        # Create Vanilla Regions
        regions: Dict[str, Region] = {"Menu": self.create_region("Menu", {})}
        if self.base_enabled:  regions.update({region_name: self.create_region(region_name, location_tables[region_name]) for region_name in region_order})
        else: regions.update({"Roundtable Hold DLC Only": self.create_region("Roundtable Hold DLC Only", location_tables["Roundtable Hold DLC Only"])})

        # Create DLC Regions
        if self.options.enable_dlc: regions.update({region_name: self.create_region(region_name, location_tables[region_name]) for region_name in region_order_dlc})

        # Connect Regions
        def create_connection(from_region: str, to_region: str):
            connection = Entrance(self.player, f"Go To {to_region}", regions[from_region])
            regions[from_region].exits.append(connection)
            connection.connect(regions[to_region])

        regions["Menu"].exits.append(Entrance(self.player, "New Game", regions["Menu"]))
        
        if self.options.enable_dlc and self.options.dlc_start != 0:
            self.multiworld.get_entrance("New Game", self.player).connect(regions["Gravesite Plain"])
            if self.options.dlc_start == 1: create_connection("Gravesite Plain", "Roundtable Hold DLC Only")
            else: create_connection("Gravesite Plain", "Roundtable Hold")
        else:
            self.multiworld.get_entrance("New Game", self.player).connect(regions["Limgrave"])
            create_connection("Limgrave", "Roundtable Hold")
            
        # Base game Regions
        if self.base_enabled:
            create_connection("Limgrave", "Fringefolk Hero's Grave")
            create_connection("Limgrave", "Stormhill")
            create_connection("Limgrave", "Coastal Cave")
            create_connection("Limgrave", "Groveside Cave")
            create_connection("Limgrave", "Stormfoot Catacombs")
            create_connection("Limgrave", "Limgrave Tunnels")
            create_connection("Limgrave", "Murkwater Cave")
            create_connection("Limgrave", "Murkwater Catacombs")
            create_connection("Limgrave", "Highroad Cave")
            create_connection("Limgrave", "Deathtouched Catacombs")
            
            
            create_connection("Coastal Cave", "Church of Dragon Communion")
            

                
            create_connection("Stormhill", "Stormveil Start")
            create_connection("Stormveil Start", "Stormveil Castle")
            create_connection("Stormveil Castle", "Stormveil Throne")
            create_connection("Stormveil Castle", "Divine Tower of Limgrave")
            
            create_connection("Limgrave", "Weeping Peninsula")
            # Weeping Peninsula
            create_connection("Weeping Peninsula", "Impaler's Catacombs")
            create_connection("Weeping Peninsula", "Tombsward Catacombs")
            create_connection("Weeping Peninsula", "Tombsward Cave")
            create_connection("Weeping Peninsula", "Morne Tunnel")
            create_connection("Weeping Peninsula", "Earthbore Cave")
            create_connection("Weeping Peninsula", "Divine Bridge") # in leyndell
            
            create_connection("Limgrave", "Siofra River")
            # Siofra
            
            create_connection("Stormhill", "Liurnia of The Lakes")
            # Liurnia of The Lakes
            create_connection("Liurnia of The Lakes", "Bellum Highway")
            create_connection("Liurnia of The Lakes", "Road's End Catacombs")
            create_connection("Liurnia of The Lakes", "Black Knife Catacombs")
            create_connection("Liurnia of The Lakes", "Cliffbottom Catacombs")
            create_connection("Liurnia of The Lakes", "Stillwater Cave")
            create_connection("Liurnia of The Lakes", "Lakeside Crystal Cave")
            create_connection("Liurnia of The Lakes", "Academy Crystal Cave")
            create_connection("Liurnia of The Lakes", "Raya Lucaria Crystal Tunnel")
            create_connection("Liurnia of The Lakes", "Caria Manor")
            create_connection("Liurnia of The Lakes", "Carian Study Hall")
            create_connection("Liurnia of The Lakes", "Carian Study Hall (Inverted)")
            create_connection("Liurnia of The Lakes", "Ruin-Strewn Precipice")
            create_connection("Liurnia of The Lakes", "Ainsel River")
            
            create_connection("Liurnia of The Lakes", "The Four Belfries (Chapel of Anticipation)")
            create_connection("Liurnia of The Lakes", "The Four Belfries (Nokron)")
            create_connection("Liurnia of The Lakes", "The Four Belfries (Farum Azula)")
            
            create_connection("Liurnia of The Lakes", "Raya Lucaria Academy")
            create_connection("Raya Lucaria Academy", "Raya Lucaria Academy Main")
            create_connection("Raya Lucaria Academy Main", "Raya Lucaria Academy Chest")
            create_connection("Raya Lucaria Academy Main", "Raya Lucaria Academy Library")
            
            
            create_connection("Limgrave", "Caelid")
            # Caelid
            create_connection("Caelid", "Caelid Catacombs")
            create_connection("Caelid", "Gaol Cave")
            create_connection("Caelid", "Sellia Crystal Tunnel")
            create_connection("Caelid", "Abandoned Cave")
            create_connection("Caelid", "Great-Jar")
            create_connection("Caelid", "Minor Erdtree Catacombs")
            create_connection("Caelid", "Gale Tunnel")
            create_connection("Caelid", "Redmane Castle Post Radahn")
            
            create_connection("Caelid", "Dragonbarrow")
            create_connection("Dragonbarrow", "Dragonbarrow Cave")
            create_connection("Dragonbarrow", "Sellia Hideaway")
            create_connection("Dragonbarrow", "Divine Tower of Caelid")
            
            create_connection("Caelid", "Wailing Dunes")
            create_connection("Wailing Dunes", "War-Dead Catacombs")
            
            create_connection("Limgrave", "Nokron, Eternal City Start")
            create_connection("Nokron, Eternal City Start", "Nokron, Eternal City")
            create_connection("Nokron, Eternal City", "Deeproot Depths")
            
            create_connection("Deeproot Depths", "Deeproot Depths Boss")
            create_connection("Deeproot Depths", "Ainsel River Main")
            
            create_connection("Ainsel River Main", "Lake of Rot")
            create_connection("Lake of Rot", "Moonlight Altar")
            
            create_connection("Liurnia of The Lakes", "Altus Plateau")
            # Altus
            create_connection("Altus Plateau", "Sainted Hero's Grave")
            create_connection("Altus Plateau", "Unsightly Catacombs")
            create_connection("Altus Plateau", "Perfumer's Grotto")
            create_connection("Altus Plateau", "Sage's Cave")
            create_connection("Altus Plateau", "Old Altus Tunnel")
            create_connection("Altus Plateau", "Altus Tunnel")
            
            
            create_connection("Altus Plateau", "Mt. Gelmir")
            # Mt Gelmir
            create_connection("Mt. Gelmir", "Wyndham Catacombs")
            create_connection("Mt. Gelmir", "Gelmir Hero's Grave")
            create_connection("Mt. Gelmir", "Seethewater Cave")
            create_connection("Mt. Gelmir", "Volcano Cave")
            
            create_connection("Mt. Gelmir", "Volcano Manor Entrance")
            
            create_connection("Volcano Manor Entrance", "Volcano Manor Drawing Room")
            create_connection("Volcano Manor Drawing Room", "Volcano Manor")
            create_connection("Volcano Manor", "Volcano Manor Upper")
        
            create_connection("Raya Lucaria Academy Main", "Volcano Manor Dungeon")
            
            
            
            
            
            create_connection("Altus Plateau", "Capital Outskirts")
            # Capital Outskirts
            create_connection("Capital Outskirts", "Auriza Hero's Grave")
            create_connection("Capital Outskirts", "Auriza Side Tomb")
            create_connection("Capital Outskirts", "Sealed Tunnel")
            
            create_connection("Capital Outskirts", "Leyndell, Royal Capital")
            # Leyndell Royal
            create_connection("Leyndell, Royal Capital", "Leyndell, Royal Capital Unmissable")
            create_connection("Leyndell, Royal Capital", "Leyndell, Royal Capital Throne")
            create_connection("Leyndell, Royal Capital", "Divine Tower of East Altus")
            
            # Sewers
            create_connection("Leyndell, Royal Capital", "Subterranean Shunning-Grounds")
            create_connection("Subterranean Shunning-Grounds", "Leyndell Catacombs")
            create_connection("Subterranean Shunning-Grounds", "Frenzied Flame Proscription")
            create_connection("Frenzied Flame Proscription", "Deeproot Depths Upper")
            
            
            create_connection("Divine Tower of East Altus", "Forbidden Lands")
            # Forbidden Lands
            create_connection("Forbidden Lands", "Hidden Path to the Haligtree")
            
            
            create_connection("Forbidden Lands", "Mountaintops of the Giants")
            # Mountaintops
            create_connection("Mountaintops of the Giants", "Giant-Conquering Hero's Grave")
            create_connection("Mountaintops of the Giants", "Giants' Mountaintop Catacombs")
            create_connection("Mountaintops of the Giants", "Spiritcaller Cave")
            create_connection("Mountaintops of the Giants", "Flame Peak")
            
            
            create_connection("Flame Peak", "Farum Azula")
            # Farum Azula
            create_connection("Farum Azula", "Farum Azula Main")
            create_connection("Farum Azula Main", "Leyndell, Ashen Capital")
            
            
            create_connection("Hidden Path to the Haligtree", "Consecrated Snowfield")
            # Snowfield
            create_connection("Consecrated Snowfield", "Consecrated Snowfield Catacombs")
            create_connection("Consecrated Snowfield", "Cave of the Forlorn")
            create_connection("Consecrated Snowfield", "Yelough Anix Tunnel")

            create_connection("Consecrated Snowfield", "Miquella's Haligtree")
            # Haligtree
            create_connection("Miquella's Haligtree", "Elphael, Brace of the Haligtree")
            
            if (self.options.dlc_timing == 2
                or not location_dictionary["LL/(RC): Pureblood Knight's Medal - talk to Varré after invading Magnus in AP and returning the bloodsoaked Lord of Blood's Favor"].should_randomize(self.options)):
                create_connection("Consecrated Snowfield", "Mohgwyn Palace")
            elif self.options.dlc_timing == 1:
                create_connection("Altus Plateau", "Mohgwyn Palace")
            else:
                create_connection("Limgrave", "Mohgwyn Palace")
            
            create_connection("Leyndell, Ashen Capital", "Leyndell, Ashen Capital Throne")
            create_connection("Leyndell, Ashen Capital Throne", "Erdtree")

        # Connect DLC Regions
        if self.options.enable_dlc:
            if self.options.dlc_start == 0:
                create_connection("Mohgwyn Palace", "Gravesite Plain")
            elif self.options.dlc_start == 2:
                create_connection("Gravesite Plain", "Limgrave")
            
            create_connection("Gravesite Plain", "Belurat Gaol")
            create_connection("Gravesite Plain", "Belurat")
            create_connection("Belurat", "Belurat Swamp")
            
            create_connection("Gravesite Plain", "Dragon's Pit")
            create_connection("Dragon's Pit", "Jagged Peak Foot")
            create_connection("Jagged Peak Foot", "Jagged Peak")
            
            create_connection("Jagged Peak Foot", "Charo's Hidden Grave")
            create_connection("Charo's Hidden Grave", "Lamenter's Gaol (Entrance)")
            create_connection("Lamenter's Gaol (Entrance)", "Lamenter's Gaol (Upper)")
            create_connection("Lamenter's Gaol (Upper)", "Lamenter's Gaol (Lower)")
            
            create_connection("Gravesite Plain", "Ellac River")
            create_connection("Ellac River", "Cerulean Coast")
            create_connection("Ellac River", "Rivermouth Cave")
            create_connection("Cerulean Coast", "Stone Coffin Fissure")
            create_connection("Cerulean Coast", "Finger Ruins of Rhia")
            
            create_connection("Gravesite Plain", "Fog Rift Catacombs")
            create_connection("Gravesite Plain", "Ruined Forge Lava Intake")
            create_connection("Gravesite Plain", "Castle Ensis")
            create_connection("Gravesite Plain", "Scadu Altus")
            create_connection("Scadu Altus", "Fog Rift Fort")
            create_connection("Scadu Altus", "Bonny Gaol")
            create_connection("Scadu Altus", "Ruined Forge of Starfall Past")
            create_connection("Scadu Altus", "Rauh Ruins Limited")
            
            create_connection("Scadu Altus", "Cathedral of Manus Metyr")
            create_connection("Cathedral of Manus Metyr", "Finger Ruins of Miyr")
            
            create_connection("Scadu Altus", "Rauh Base")
            create_connection("Rauh Base", "Scorpion River Catacombs")
            create_connection("Rauh Base", "Taylew's Ruined Forge")
            
            create_connection("Scadu Altus", "Shadow Keep, Church District")
            create_connection("Shadow Keep, Church District", "Shadow Keep, Church District Lower")
            create_connection("Shadow Keep, Church District Lower", "Scadutree Base")
            
            create_connection("Shadow Keep, Church District", "Shadow Keep Storehouse Back")
            create_connection("Shadow Keep Storehouse Back", "Scaduview")
            create_connection("Scaduview", "Hinterland")
            create_connection("Hinterland", "Finger Ruins of Dheo")
            
            create_connection("Scadu Altus", "Shadow Keep")
            create_connection("Shadow Keep", "Shadow Keep Storehouse")
            create_connection("Shadow Keep Storehouse", "Shadow Keep, West Rampart")
            create_connection("Shadow Keep, West Rampart", "Ancient Ruins of Rauh")
            create_connection("Ancient Ruins of Rauh", "Enir Ilim")
            
            create_connection("Shadow Keep", "Recluses' River")
            create_connection("Recluses' River", "Darklight Catacombs")
            create_connection("Darklight Catacombs", "Abyssal Woods")
            create_connection("Abyssal Woods", "Midra's Manse")
    
    # For each region, add the associated locations retrieved from the corresponding location_table
    def create_region(self, region_name, location_table: List[ERLocationData]) -> Region:
        new_region = Region(region_name, self.player, self.multiworld)

        # Use this to un-exclude event locations so the fill doesn't complain about items behind
        # them being unreachable.
        excluded = self.options.exclude_locations.value

        for location in location_table:
            status = self._location_status(location)
            if status.is_absent:
                continue
            elif status.is_randomized:
                new_location = ERLocation(self.player, location, new_region)
                
                if (
                    # Exclude missable locations that don't allow useful items
                    status.is_missable
                    and self.options.missable_location_behavior == "forbid_useful"
                    or (
                        # Unless they are excluded to a higher degree already
                        location.name in self.all_excluded_locations
                        and self.options.excluded_location_behavior == "forbid_useful"
                    )
                ): 
                    new_location.progress_type = LocationProgressType.EXCLUDED
                #     if location.name in self.all_priority_locations: # if its excluded remove it from priority
                #         self.all_priority_locations.remove(location.name)
                # elif location.name in self.all_priority_locations:
                #     if location.hidden: self.all_priority_locations.remove(location.name)
            else:
                # Don't consider non-randomized locations to be AP-excluded
                if location.name in excluded:
                    excluded.remove(location.name)
                    # Only remove from all_excluded if excluded does not have priority over missable
                    if not (self.options.missable_location_behavior < self.options.excluded_location_behavior):
                        self.all_excluded_locations.remove(location.name)
                
                # Replace non-randomized items with events that give the default item
                event_item = (
                    self.create_item(location.default_item_name) if location.default_item_name
                    else ERItem.event(location.name, self.player)
                )

                new_location = ERLocation(
                    self.player,
                    location,
                    parent = new_region,
                )
                new_location.place_locked_item(event_item)

            new_region.locations.append(new_location)

        self.multiworld.regions.append(new_region)
        self.created_regions.add(region_name)
        return new_region
    
    def create_items(self) -> None:
        # Gather all default items on randomized locations
        self.itempool = []
        num_required_extra_items = 0
        for location in cast(List[ERLocation], self.multiworld.get_unfilled_locations(self.player)):
            if not self._location_status(location.name).is_randomized:
                raise Exception(f"ER generation bug: Added an unavailable location. {location.name}")
            
            default_item_name = cast(str, location.data.default_item_name)
            item = item_table[default_item_name]
            
            if item.should_skip(self.options):
                num_required_extra_items += 1
            else:
                new_item = self.create_item(default_item_name)
                if not location.data.dlc:
                    self.itempool.append(new_item)
                elif location.data.dlc:
                    # make base items dlc if in dlc
                    new_item.found_in_dlc = True
                    self.itempool.append(new_item)
        
        injectables = self._create_injectable_items(num_required_extra_items)
        num_required_extra_items -= len(injectables)
        self.itempool.extend(injectables)
        
        self._fill_local_items()
        
        if self.options.important_at_priority_only.value:
            self._create_dupe_locations()
            num_required_extra_items += len(self.all_duplicate_locations)
        
        self.itempool.extend(self.create_item(self.get_filler_item_name()) for _ in range(
            (len(self.multiworld.get_unfilled_locations(self.player))) - len(self.itempool)))
        
        self.multiworld.itempool += self.itempool
        
        # warning(f"priority locations: {len(self.all_priority_locations)} important items: {len([i for i in self.itempool if i.classification == ItemClassification.progression])}")
        warning(f"EldenRing {self.player_name} local items: {len([i for i in self.itempool if i.data.name in self.local_items])} of {len(self.itempool)}")
        
    def _create_dupe_locations(self) -> None:
        """Create duplicate locations."""
        important_items = []
        for item in self.itempool:
            if item.classification == ItemClassification.progression: # , ItemClassification.progression_deprioritized
                important_items.append(item)
        
        dlc_priority = [loc for loc in self.all_priority_locations if location_dictionary[loc].dlc and self.options.enable_dlc]
        base_priority = [loc for loc in self.all_priority_locations if not location_dictionary[loc].dlc and self.base_enabled]
        early_base = [loc for loc in self.all_priority_locations if not location_dictionary[loc].dlc and location_dictionary[loc].region_value <= 44 and self.base_enabled] # lim, storm, weep, liurnia, raya
        early_dlc = [loc for loc in self.all_priority_locations if location_dictionary[loc].dlc and location_dictionary[loc].region_value <= len(region_order) + 9 
                     and location_dictionary[loc].region_value > len(region_order) and self.options.enable_dlc] # grave, belurat, dragon pit, ensis
        
        if self.base_enabled or self.options.dlc_start == 0 and self.options.enable_dlc: early_dlc = [] # start not in dlc, no early dlc
        else: early_base = [] # base off or dlc start, no early base
        
        loc_needed = len([i for i in important_items if not i.data.is_dlc and not i.found_in_dlc]) - len(base_priority)
        dlc_loc_needed = len([i for i in important_items if (i.data.is_dlc or i.found_in_dlc) and self.options.enable_dlc]) - len(dlc_priority)
        
        if not self.base_enabled: # if base injected in dlc only, make them dlc
            dlc_loc_needed += loc_needed
            loc_needed = 0
        
        if not dlc_priority and dlc_loc_needed and (self.options.dlc_messmer_kindle or self.options.dlc_scadutree_fragments) and self.options.enable_dlc: 
            raise OptionError(f"Player {self.player_name} has no dlc priority locations but dlc only progression items.")
        
        # save all possible prio locations
        self.all_possible_priority_locations = self.all_priority_locations
        # make sure not to many priority locations exist
        if self.multiworld.players > 1:
            while loc_needed < 0:
                removed = self.random.choice(sorted(base_priority))
                base_priority.remove(removed)
                self.all_priority_locations.remove(removed)
                loc_needed += 1
            while dlc_loc_needed < 0:
                removed = self.random.choice(sorted(dlc_priority))
                dlc_priority.remove(removed)
                self.all_priority_locations.remove(removed)
                dlc_loc_needed += 1
        
        # need to modify progress type here after create_regions
        for location in self.multiworld.get_locations(self.player):
            if location.name in self.all_priority_locations:
                location.progress_type = LocationProgressType.PRIORITY
        
        # this can make more prio then prog exist, but it should be very little
        required_region_dupes = self._required_locations()
        
        times_duped = {}
        while loc_needed + dlc_loc_needed > 0 or len(required_region_dupes) > 0: # how many dupes
            required_prio = None
            if len(required_region_dupes) > 0: # if locations are required add them
                required_prio = required_region_dupes.pop(0)
            
            if required_prio != None:
                location = required_prio
            elif loc_needed > 0:
                if len(base_priority) == 0:
                    warning(f"Player {self.player_name} ran out of base priority locations, add more.")
                    break # leave while loop
                else:
                    location = self.random.choice(sorted(base_priority + early_base * (self.options.important_at_priority_early - 1)))
            elif dlc_loc_needed > 0:
                if len(dlc_priority) == 0:
                    warning(f"Player {self.player_name} ran out of dlc priority locations, add more.")
                    break # leave while loop
                else:
                    location = self.random.choice(sorted(dlc_priority + early_dlc * (self.options.important_at_priority_early - 1)))
            
            found = False
            for region in self.multiworld.get_regions(self.player):
                for loc in region.locations:
                    if location == loc.name:
                        if location in times_duped: times_duped[location] = times_duped[location] + 1 # add 1 to location
                        else: times_duped[location] = 1 # add to dict
                        new_code = 0
                        if f"{location}, extra item {times_duped[location]}" in EldenRing.location_name_to_id:
                            new_code = EldenRing.location_name_to_id[f"{location}, extra item {times_duped[location]}"]
                            dupe_location = ERLocation( # replace works, yippee
                                self.player,
                                replace(location_dictionary[location], 
                                    name=f"{location}, extra item {times_duped[location]}", 
                                    default_item_name = "Dummy item",
                                    ap_code = new_code),
                                parent = region
                            )
                            dupe_location.progress_type = LocationProgressType.PRIORITY
                            region.locations.append(dupe_location)
                            self.dupe_location_dictionary.update({dupe_location.data.name: dupe_location.data})
                            self.dupe_location_tables[region.name].append(dupe_location.data)
                            self.all_duplicate_locations.add(dupe_location.data.name)
                            found = True
                            if not location_dictionary[location].dlc: loc_needed -= 1
                            else: dlc_loc_needed -= 1
                            break
                        else: # can't be duped
                            if location in base_priority:
                                base_priority.remove(location)
                                if location in early_base:
                                    early_base.remove(location)
                            elif location in dlc_priority:
                                dlc_priority.remove(location)
                                if location in early_dlc:
                                    early_dlc.remove(location)
                            found = True
                            break
                if found: break
        
        self.all_priority_locations.update(self.all_duplicate_locations)
        self.all_possible_priority_locations.update(self.all_duplicate_locations)

    # MARK: Priority Fixer
    # currently guarantees access to main path, and some side paths
    def _required_locations(self) -> list[str]:
        """Figure out what regions require more priority locations to avoid fill errors."""
        # map region names to prio locations in region
        for region in location_tables:
            self.prio_in_region.setdefault(region, [])
            for prio in self.all_priority_locations:
                if location_dictionary[prio].region_name == region:
                    self.prio_in_region[region].append(prio)
        
        locations_needed = []
        if self.options.world_logic == "region_lock":
            # if starting region has no locations create one
            if self.base_enabled and self.options.dlc_start == 0 and len(self.prio_in_region["Limgrave"]) < 1: 
                warning(f"Player {self.player_name} has no Priority locations within Limgrave region. Adding priority location \"LG/(SG): Finger Severer - beside grace\".")
                self.all_priority_locations.add("LG/(SG): Finger Severer - beside grace")
                self.prio_in_region["Limgrave"].append("LG/(SG): Finger Severer - beside grace")
                
            if self.options.enable_dlc and len(self.prio_in_region["Gravesite Plain"]) < 1:
                warning(f"Player {self.player_name} has no Priority locations within Gravesite Plain region. Adding priority location \"GP/TPC: Scadutree Fragment - by cross\".")
                self.all_priority_locations.add("GP/TPC: Scadutree Fragment - by cross")
                self.prio_in_region["Gravesite Plain"].append("GP/TPC: Scadutree Fragment - by cross")
            
            total_required = 0
            
            if self.base_enabled and self.options.dlc_start == 0:
                
                # before Liurnia
                prio_locations = self._find_prio_locations("Limgrave")
                total_required += 7 # weeping and siofra and Liurnia + bonus 4 just in case :)
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # stormveil
                option, min_shard = self._shard_exists("Rusty Key Shard")
                if option and option["Max"] > 1: total_required += min_shard
                else: total_required += 2
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))               
                                              
                # before Altus
                prio_locations = self._find_prio_locations("Liurnia of The Lakes")
                total_required += 2 # required to access altus, dectus shards later
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                total_required += 1 # raya lucaria, make shards later
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before Caelid
                prio_locations = self._find_prio_locations("Altus Plateau")
                total_required += 3 # caelid mt gelmir and volcano
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # dragonbarrow
                prio_locations = self._find_prio_locations("Caelid")
                total_required += 1
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # deeproot
                prio_locations = self._find_prio_locations("Nokron, Eternal City")
                total_required += 1
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required)) 
                
                # before Leyndell
                prio_locations = self._find_prio_locations("Capital Outskirts")
                total_required += self.options.great_runes_required_leyndell
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before Mountaintops
                prio_locations = self._find_prio_locations("Forbidden Lands")
                option, min_shard = self._shard_exists("Rold Medallion Shard")
                if option and option["Max"] > 1: total_required += min_shard
                else: total_required += self.options.great_runes_required_mountain
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before farum            
                prio_locations = self._find_prio_locations("Mountaintops of the Giants")
                total_required += 1 # lock, can be shards later
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before ashen cap        
                prio_locations = self._find_prio_locations("Farum Azula")
                total_required += 1 # lock, can be shards later
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before erdtree      
                prio_locations = self._find_prio_locations("Leyndell, Ashen Capital")
                total_required += self.options.great_runes_required_erdtree
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
 
            if self.options.separate_progression:
                total_required = 0
 
            if self.options.enable_dlc:
                # before gravesite
                if self.options.dlc_start == 0:
                    prio_locations = self._find_prio_locations("DLC Path")
                    total_required += 1 # gravesite lock
                    locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before ensis
                prio_locations = self._find_prio_locations("Gravesite Plain")
                total_required += 8 # ensis lock, belurat, ellac, jagged peak + bonus 4 just in case
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before cerulean
                prio_locations = self._find_prio_locations("Ellac River")
                total_required += 1 
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before stone coffin
                prio_locations = self._find_prio_locations("Cerulean Coast")
                total_required += 1 
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before shadow keep
                prio_locations = self._find_prio_locations("Scadu Altus")
                total_required += 3 # shadow keep lock, rauh base, abssal woods
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before ancient ruins
                prio_locations = self._find_prio_locations("Shadow Keep")
                total_required += 1 # ancient ruins lock
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))
                
                # before ilir ilim
                prio_locations = self._find_prio_locations("Ancient Ruins of Rauh")
                option, min_shard = self._shard_exists("Messmer's Kindling Shard")
                if option and option["Max"] > 1: total_required += min_shard
                else: total_required += 1 # kindle
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required))                                 
        else:
            total_required = 0
            
            if self.options.enable_dlc:
                # before ilir ilim
                prio_locations = self._find_prio_locations("Ancient Ruins of Rauh")
                option, min_shard = self._shard_exists("Messmer's Kindling Shard")
                if option and option["Max"] > 1: total_required += min_shard
                else: total_required += 1 # kindle
                locations_needed.extend(self._needed_locations(prio_locations, locations_needed, total_required)) 
        
        
        return locations_needed
    
    def _needed_locations(self, prio, loc_needed, req):
        """return locations needed"""
        needed = []
        if len(prio) - len(loc_needed) < req:
            for i in range(len(prio), req):
                needed.append(self.random.choice(sorted(prio)))
        return needed
    
    def _shard_exists(self, shard):
        "Check to see if shard exists and return option and min for easy use."
        if shard_list[shard] in self.options.key_item_shards.value:
            option = self.options.key_item_shards.value[shard_list[shard]]
            return option, min(option['Req'], option['Max'])
        return False, False
    
    def _find_prio_locations(self, region: str) -> list[str]:
        """fallthrough stuff""" # this doesn't work with dlc start + base
        prio_locations = []
        fall = False
        
        if self.options.enable_dlc:        
            
            if fall or region == "Ancient Ruins of Rauh":
                fall = True
                prio_locations.extend(self.prio_in_region["Ancient Ruins of Rauh"])    
                            
            if fall or region == "Shadow Keep":
                fall = True
                for r in ["Shadow Keep","Shadow Keep Storehouse","Shadow Keep Storehouse Back","Shadow Keep, West Rampart","Shadow Keep, Church District","Shadow Keep, Church District Lower"]:
                    prio_locations.extend(self.prio_in_region[r])
            
            if fall or region == "Scadu Altus":
                fall = True
                for r in ["Scadu Altus","Bonny Gaol","Ruined Forge of Starfall Past"]:
                    prio_locations.extend(self.prio_in_region[r])
            
            if fall or region == "Castle Ensis":
                fall = True
                for r in ["Castle Ensis","Fog Rift Fort"]:
                    prio_locations.extend(self.prio_in_region[r])
            
            if region == "Cerulean Coast":
                fall = True
                for r in ["Cerulean Coast","Finger Ruins of Rhia"]:
                    prio_locations.extend(self.prio_in_region[r])            
            
            if region == "Ellac River" or region == "Cerulean Coast":
                fall = True
                for r in ["Ellac River","Rivermouth Cave","Jagged Peak Foot","Jagged Peak","Charo's Hidden Grave","Lamenter's Gaol (Entrance)","Lamenter's Gaol (Upper)","Lamenter's Gaol (Lower)"]:
                    prio_locations.extend(self.prio_in_region[r])
            
            if fall or region == "Gravesite Plain":
                fall = True
                for r in ["Gravesite Plain","Fog Rift Catacombs","Belurat Gaol","Dragon's Pit","Ruined Forge Lava Intake"]:
                    prio_locations.extend(self.prio_in_region[r])
        
        if self.options.separate_progression and fall:
            fall = False
        
        if self.base_enabled and self.options.dlc_start == 0:
            
            if fall or region == "DLC Path": # path to dlc regions
                for r in ["Mohgwyn Palace","Consecrated Snowfield","Consecrated Snowfield Catacombs","Yelough Anix Tunnel",
                        "Caelid","Caelid Catacombs","Sellia Crystal Tunnel","Abandoned Cave","Minor Erdtree Catacombs","Great-Jar","Gale Tunnel"
                        ,"Redmane Castle Post Radahn","Wailing Dunes","War-Dead Catacombs"]:
                    prio_locations.extend(self.prio_in_region[r])              

            if fall or region == "Leyndell, Ashen Capital":
                fall = True
                for r in ["Leyndell, Ashen Capital","Leyndell, Ashen Capital Throne"]:
                    prio_locations.extend(self.prio_in_region[r])               
            
            if fall or region == "Farum Azula":
                fall = True
                for r in ["Farum Azula","Farum Azula Main"]:
                    prio_locations.extend(self.prio_in_region[r])               
            
            if fall or region == "Mountaintops of the Giants":
                fall = True
                for r in ["Mountaintops of the Giants","Flame Peak","Giant-Conquering Hero's Grave","Giants' Mountaintop Catacombs"]:
                    prio_locations.extend(self.prio_in_region[r])               
            
            if fall or region == "Forbidden Lands":
                fall = True
                for r in ["Divine Tower of East Altus","Forbidden Lands"]:
                    prio_locations.extend(self.prio_in_region[r])              
            
            if fall or region == "Leyndell, Royal Capital":
                fall = True
                for r in ["Leyndell, Royal Capital","Leyndell, Royal Capital Unmissable","Leyndell, Royal Capital Throne","Divine Bridge","Subterranean Shunning-Grounds","Leyndell Catacombs"]:
                    prio_locations.extend(self.prio_in_region[r])  
            
            if fall or region == "Capital Outskirts":
                fall = True
                for r in ["Capital Outskirts","Auriza Hero's Grave","Auriza Side Tomb","Sealed Tunnel"]:
                    prio_locations.extend(self.prio_in_region[r])
            
            if region == "Nokron, Eternal City":
                fall = True
                for r in ["Nokron, Eternal City Start","Nokron, Eternal City"]:
                    prio_locations.extend(self.prio_in_region[r])                
            
            if region == "Caelid" or region == "Nokron, Eternal City":
                fall = True
                for r in ["Caelid","Caelid Catacombs","Sellia Crystal Tunnel","Abandoned Cave","Minor Erdtree Catacombs",
                        "Gale Tunnel","Redmane Castle Post Radahn"]:
                    prio_locations.extend(self.prio_in_region[r])
                        
            if fall or region == "Altus Plateau":
                fall = True
                for r in ["Altus Plateau","Sainted Hero's Grave","Perfumer's Grotto","Sage's Cave","Altus Tunnel"]:
                    prio_locations.extend(self.prio_in_region[r])
            
            if fall or region == "Liurnia of The Lakes":
                fall = True
                for r in ["Liurnia of The Lakes","Bellum Highway","Road's End Catacombs","Black Knife Catacombs","Cliffbottom Catacombs"
                    ,"Stillwater Cave","Lakeside Crystal Cave","Raya Lucaria Crystal Tunnel","Caria Manor","Carian Study Hall","Ruin-Strewn Precipice"]:
                    prio_locations.extend(self.prio_in_region[r])
            
            if fall or region == "Siofra River":
                fall = True
                prio_locations.extend(self.prio_in_region["Siofra River"])
            
            if fall or region == "Limgrave":
                for r in ["Limgrave","Stormhill","Coastal Cave","Church of Dragon Communion","Groveside Cave"
                    ,"Stormfoot Catacombs","Limgrave Tunnels","Murkwater Cave","Murkwater Catacombs","Highroad Cave","Deathtouched Catacombs"]:
                    prio_locations.extend(self.prio_in_region[r]) 
        
        # always
        if not self.base_enabled:
            prio_locations.extend(self.prio_in_region["Roundtable Hold DLC Only"])
        else: 
            prio_locations.extend(self.prio_in_region["Roundtable Hold"])
        
        # warning(f"{region}, {prio_locations}")
        return prio_locations

        
    def _create_injectable_items(self, num_required_extra_items: int):
        """Returns a list of items to inject into the multiworld instead of skipped items.

        If there isn't enough room to inject all the necessary progression items
        that are in missable locations by default, this adds them to the
        player's starting inventory.
        """
        all_injectable_items = [
            item for item
            in item_table.values()
            if item.should_inject(self.options) and (
            (not item.is_dlc and self.base_enabled)
            or (item.is_dlc and self.options.enable_dlc))
        ]
        
        if self.options.world_logic == "region_lock": # inject region lock items
            for item_name in item_table:
                if ((self.base_enabled and item_table[item_name].lock and not item_table[item_name].is_dlc) 
                or (self.options.enable_dlc and item_table[item_name].lock and item_table[item_name].is_dlc
                    and not self.dlc_excluded)):
                    if item_name != "Gravesite Lock" or self.options.dlc_start == 0 and self.options.enable_dlc:
                        all_injectable_items += [item_table[item_name]]
        
        for shard in shard_list:
            if (item_table[shard].is_dlc and self.options.enable_dlc or not item_table[shard].is_dlc and self.base_enabled
                ) and shard_list[shard] in self.options.key_item_shards.value and self.options.key_item_shards.value[shard_list[shard]]['Max'] > 1:
                all_injectable_items += [item_table[shard] for i in range(self.options.key_item_shards.value[shard_list[shard]]['Max'])]
        
        if not self.base_enabled:
            dlc_start_lower: list[str] = [i.lower() for i in self.options.dlc_starting_items.value]
            # if not started with add to injection since base game items dont exist
            if "sacred tears" not in dlc_start_lower: all_injectable_items += [item_table["Sacred Tear"] for i in range(12)]
            if "golden seeds" not in dlc_start_lower: all_injectable_items += [item_table["Golden Seed"] for i in range(43)]
            if "talisman pouches" not in dlc_start_lower: all_injectable_items += [item_table["Talisman Pouch"] for i in range(3)]
            if "memory stones" not in dlc_start_lower: all_injectable_items += [item_table["Memory Stone"] for i in range(8)]
            if "whetblades" not in dlc_start_lower: 
                all_injectable_items += [item_table["Iron Whetblade"],item_table["Red-Hot Whetblade"], 
                    item_table["Sanctified Whetblade"], item_table["Glintstone Whetblade"], item_table["Black Whetblade"]]
            if "upgrade bell bearings" not in dlc_start_lower:
                if self.options.smithing_bell_bearing_option.value == 3:
                    all_injectable_items += [item_table["Progressive Smithing-Stone Bell Bearing"] for i in range(4)]
                    all_injectable_items += [item_table["Progressive Somberstone Bell Bearing"] for i in range(5)]
                else:    
                    all_injectable_items += [item_table["Smithing-Stone Miner's Bell Bearing [1]"],
                    item_table["Smithing-Stone Miner's Bell Bearing [2]"],item_table["Smithing-Stone Miner's Bell Bearing [3]"],
                    item_table["Smithing-Stone Miner's Bell Bearing [4]"],item_table["Somberstone Miner's Bell Bearing [1]"],
                    item_table["Somberstone Miner's Bell Bearing [2]"],item_table["Somberstone Miner's Bell Bearing [3]"],
                    item_table["Somberstone Miner's Bell Bearing [4]"],item_table["Somberstone Miner's Bell Bearing [5]"]]
            if self.options.enemy_rando and not self.options.rykard_encounter: all_injectable_items += [item_table["Serpent-Hunter"]]
        
        if self.base_enabled:
            if self.options.use_master_key.value == 1: all_injectable_items += [item_table[item] for item in item_table if item_table[item].master_key]
            elif self.options.use_master_key.value == 2: all_injectable_items += [item_table["Stonesword Master Key"]]
        
            if self.options.smithing_bell_bearing_option.value == 3:
                all_injectable_items += [item_table["Progressive Smithing-Stone Bell Bearing"] for i in range(4)]
                all_injectable_items += [item_table["Progressive Somberstone Bell Bearing"] for i in range(5)]
        
        all_injectable_items += self._add_traps()
        
        injectable_mandatory = [
            item for item in all_injectable_items
            if (item.is_important(self.options) == ItemClassification.progression 
                or item.is_important(self.options) == ItemClassification.useful 
                or item.is_important(self.options) == ItemClassification.progression_deprioritized
                or item.is_important(self.options) == ItemClassification.trap)
        ]
        injectable_optional = [
            item for item in all_injectable_items
            if (item.is_important(self.options) != ItemClassification.progression 
                and item.is_important(self.options) != ItemClassification.useful 
                and item.is_important(self.options) != ItemClassification.progression_deprioritized
                and item.is_important(self.options) != ItemClassification.trap)
        ]

        number_to_inject = min(num_required_extra_items, len(all_injectable_items))
        inj_items = (
            self.random.sample(
                injectable_mandatory,
                k=len(injectable_mandatory)
            )
            + self.random.sample(
                injectable_optional,
                k=max(0, number_to_inject - len(injectable_mandatory))
            )
        )
    
        if number_to_inject < len(injectable_mandatory):
            replacables = [r for r in self.itempool if r.data.replacable]
            while number_to_inject < len(injectable_mandatory): # prune itempool if to many mandatory injects
                if replacables: # try to remove filler items first
                    item = self.random.choice(replacables)
                    self.itempool.remove(item)
                    replacables.remove(item)
                else: # no replacables left, remove traps
                    traps = [i for i in inj_items if i.data.classification == ItemClassification.trap]
                    if traps: inj_items.remove(self.random.choice(traps))
                    else: # no traps left, add to inventory
                        to_inv = self.random.choice(inj_items)
                        self._add_to_inventory(self.create_item(to_inv))
                        inj_items.remove(to_inv)
                number_to_inject += 1

        return [self.create_item(item) for item in inj_items]

    def _add_traps(self): # MARK: Traps
        traps = []
        # base
        traps += ([item_table["NG+ Trap"]] * self.options.ngplus_trap_count.value)
        traps += ([item_table["Status Trap"]] * self.options.status_trap_count.value)
        # dlc
        if self.options.enable_dlc:
            traps += ([item_table["Blindness Trap"]] * self.options.blindness_trap_count.value)
        return traps

    def _fill_local_items(self) -> None:
        """Removes certain items from the item pool and manually places them in the local world.

        We can't do this in pre_fill because the itempool may not be modified after create_items.
        """ # fill local before adding to inventory
        if self.base_enabled:
            if self.options.crafting_kit_option.value == 1:
                self._fill_local_item("Crafting Kit", region_order, lambda location: location.region_value <= 44)
            if self.options.physick_flask_option.value == 1:
                self._fill_local_item("Flask of Wondrous Physick", region_order, lambda location: location.region_value <= 44)
        else:
            if self.options.crafting_kit_option.value == 1:
                self._fill_local_item("Crafting Kit", ["Gravesite Plain"])
            if self.options.physick_flask_option.value == 1:
                self._fill_local_item("Flask of Wondrous Physick", ["Gravesite Plain"])

        if self.options.enable_dlc:
            if self.options.dlc_scadutree_fragments.value == 1 or self.options.dlc_scadutree_fragments.value == 2 and self.multiworld.players == 1:
                [self._fill_local_item(item, region_order_dlc) for item in self.itempool if item.data.scadu]
            if self.options.dlc_messmer_kindle.value == 1 or self.options.dlc_messmer_kindle.value == 2 and self.multiworld.players == 1:
                [self._fill_local_item(item, region_order_dlc) for item in self.itempool 
                 if item.data.name == "Messmer's Kindling" or item.data.name == "Messmer's Kindling Shard"]
            if self.options.dlc_start != 0:
                [self._add_to_inventory(self.create_item(item)) for item in (
                    "Spectral Steed Whistle",
                    "Spirit Calling Bell",
                    "Whetstone Knife"
                )]
        
        if self.options.map_option == 1:
            [self._add_to_inventory(item) for item in self.itempool if item.data.map]
        
        # for now just give lantern by default
        self._add_to_inventory(self.create_item("Lantern"))
        
        for i in self.starting_inventory:
            self._add_to_inventory(self.create_item(i))

    def _fill_local_item(
        self, name: str,
        regions: List[str],
        additional_condition: Optional[Callable[[ERLocationData], bool]] = None,
    ) -> None:
        """Chooses a valid location for the item with the given name and places it there.
        
        This always chooses a local location among the given regions. If additional_condition is
        passed, only locations meeting that condition will be considered.

        If the item could not be placed, it will be added to starting inventory.
        """
        item = next((item for item in self.itempool if item.name == name), None)
        if not item: return

        candidate_locations = [
            location for location in (
                self.multiworld.get_location(location.name, self.player)
                for region in regions
                for location in (location_tables[region]) #+ self.dupe_location_tables[region] if region in self.dupe_location_tables else location_tables[region])
                if self._location_status(location) == _LocationStatus.RANDOMIZED_UNMISSABLE
                and not location.conditional
                and (not additional_condition or additional_condition(location))
            )
            # We can't use location.progress_type here because it's not set
            # until after `set_rules()` runs.
            if not location.item and location.name not in self.all_excluded_locations
            and location.item_rule(item)
            # if not self.options.important_at_priority_only # all ignored if option off
            # or (item.is_important(self.options) != ItemClassification.progression and item.is_important(self.options) != ItemClassification.useful) # bypass if not important 
            # or (item.is_important(self.options) == ItemClassification.progression or item.is_important(self.options) == ItemClassification.useful) # important
            # and (location.name in self.all_priority_locations # location is priority
            # or location.name in dupe_location.data.name[dupe_location.data.name.find(":")+2:] for dupe_location in self.all_duplicate_locations) # location is duped priority
            # and self.options.important_at_priority_only # option is on
        ]

        if not candidate_locations:
            warning(f"Couldn't place \"{name}\" in a valid location for {self.player_name}. Adding it to starting inventory instead.")
            location = next(
                (location for location in self._get_our_locations() if location.data.default_item_name == item.name),
                None
            )
            if location: self._replace_with_filler(location)
            self._add_to_inventory(self.create_item(name))
            return
        
        self.itempool.remove(item)

        location = self.random.choice(candidate_locations)
        location.place_locked_item(item)
        if location.data.name in self.all_priority_locations:
            self.all_priority_locations.remove(location.data.name)

    def _add_to_inventory(self, item: ERItem) -> None:
        "Add item to starting inventory."
        if item in self.itempool:
            self.itempool.remove(item)
        # only precollect important?
        # if item.classification not in (ItemClassification.progression, ItemClassification.progression_deprioritized) and 
        if item.data.map:
            self.all_starting_items.append(self._er_item_full_id(item.data))
        else:
            self.multiworld.push_precollected(item)
            

    def create_item(self, item: Union[str, ERItemData]) -> ERItem:
        new_item = ERItem(self.player, item if isinstance(item, ERItemData) else item_table[item])
        new_item.classification = new_item.data.is_important(self.options)
        return new_item

    def _replace_with_filler(self, location: ERLocation) -> None:
        """If possible, choose a filler item to replace location's current contents with."""
        if location.locked: return

        # Try 10 filler items. If none of them work, give up and leave it as-is.
        for _ in range(0, 10):
            candidate = self.create_filler()
            if location.item_rule(candidate):
                location.item = candidate
                return

    def get_filler_item_name(self) -> str:
        candidate_filler = []
        if self.base_enabled: candidate_filler.extend(filler_item_names_vanilla)
        if self.options.enable_dlc: candidate_filler.extend(filler_item_names_dlc)
        return self.random.choice(candidate_filler)


    #MARK: Rules
    def set_rules(self) -> None: 
        
        self._dragon_communion_rules()
        self._add_remembrance_rules()
        self._add_equipment_of_champions_rules()
        self._add_npc_rules()
        self._add_allow_useful_location_rules()
        self._region_lock()
        
        # MARK: Base Game Rules
        if self.base_enabled:
            self._key_rules()
            self._add_shop_rules()
            
            # indirect connections

            self.multiworld.register_indirect_condition(self.get_region("Altus Plateau"), self.get_entrance("Go To Wailing Dunes"))
            self.multiworld.register_indirect_condition(self.get_region("Limgrave"), self.get_entrance("Go To Sellia Crystal Tunnel"))
            self.multiworld.register_indirect_condition(self.get_region("Deeproot Depths Upper"), self.get_entrance("Go To Deeproot Depths"))
            self.multiworld.register_indirect_condition(self.get_region("Deeproot Depths"), self.get_entrance("Go To Leyndell, Royal Capital"))
            self.multiworld.register_indirect_condition(self.get_region("Volcano Manor"), self.get_entrance("Go To Volcano Manor Dungeon"))
            self.multiworld.register_indirect_condition(self.get_region("Volcano Manor Dungeon"), self.get_entrance("Go To Altus Plateau"))
            
            # altus before caelid
            if self.options.soft_logic:
                self._add_entrance_rule("Caelid", lambda state: self._can_go_to(state, "Altus Plateau"))
                self.multiworld.register_indirect_condition(self.get_region("Altus Plateau"), self.get_entrance("Go To Caelid"))
            # wailing dunes hard requires altus
            self._add_location_rule("CL/(RC): Smithing Stone [6] - in church during festival", lambda state: self._can_go_to(state, "Altus Plateau"))
            self._add_entrance_rule("Wailing Dunes", lambda state: self._can_go_to(state, "Altus Plateau"))
            
            # Custom Rules
            
            if not self.options.enemy_rando and self.soft_logic_enabled: # boss rules
                self._add_entrance_rule("Stormveil Start", "Margit's Shackle")
                self._add_entrance_rule("Mohgwyn Palace", lambda state: state.has("Mohg's Shackle", self.player) and state.has("Purifying Crystal Tear", self.player)
                                        )
                if not self.options.rykard_encounter:
                    self._add_location_rule(["VM/AP: Rykard's Great Rune - mainboss drop", "VM/AP: Remembrance of the Blasphemous - mainboss drop"], 
                                            "Serpent-Hunter")
            elif not self.options.rykard_encounter and self.soft_logic_enabled:
                # places blocked by bosses, if rykard or serpent is here the place requires serpent-hunter
                self._add_entrance_rule("Stormveil Castle", lambda state: self._can_get(state, "SV/CT: Talisman Pouch - boss drop"))
                self._add_entrance_rule("Raya Lucaria Academy Main", lambda state: self._can_get(state, "RLA/SC: Memory Stone - boss drop"))
                self._add_entrance_rule("Nokron, Eternal City", lambda state: self._can_get(state, "NR/NEC: Silver Tear Mask - boss drop"))
                self._add_entrance_rule("Deeproot Depths", lambda state: self._can_get(state, "NR/(SA): Gargoyle's Greatsword - boss drop"))
                self._add_entrance_rule("War-Dead Catacombs", lambda state: self._can_get(state, "CL/(WD): Radahn's Great Rune - mainboss drop"))
                self._add_entrance_rule("Altus Plateau", lambda state: self._can_get(state, "RSP/RSPO: Dragon Heart - boss drop") or 
                                        state.has("Dectus Medallion (Left)", self.player) and state.has("Dectus Medallion (Right)", self.player))
                self._add_entrance_rule("Volcano Manor Upper", lambda state: self._can_get(state, "VM/GH: Godskin Stitcher - boss drop"))
                # self._add_entrance_rule("Leyndell, Royal Capital", lambda state: 
                #     self._can_get(state, "DD/AR: Fia's Mist - boss drop") or self._can_get(state, "CO: Dragon Greatclaw - capital great rune gate boss drop"))
                self._add_entrance_rule("Leyndell, Royal Capital Throne", lambda state: self._can_get(state, "LRC/WCR: Talisman Pouch - mainboss drop"))
                self._add_entrance_rule("Divine Tower of East Altus", lambda state: self._can_get(state, "LRC/QB: Morgott's Great Rune - mainboss drop"))
                self._add_entrance_rule("Frenzied Flame Proscription", lambda state: self._can_get(state, "LRC/QB: Morgott's Great Rune - mainboss drop")
                                        and self._can_get(state, "SSG/FD: Bloodflame Talons - boss drop"))
                self._add_entrance_rule("Elphael, Brace of the Haligtree", lambda state: self._can_get(state, "MH/HTP: Loretta's War Sickle - boss drop"))
                self._add_entrance_rule("Farum Azula", lambda state: self._can_get(state, "FP/FF: Remembrance of the Fire Giant - mainboss drop"))
                self._add_entrance_rule("Farum Azula Main", lambda state: self._can_get(state, "FA/DTT: Smithing-Stone Miner's Bell Bearing [4] - boss drop"))
                self._add_entrance_rule("Leyndell, Ashen Capital", lambda state: self._can_get(state, "FA/BGB: Remembrance of the Black Blade - mainboss drop"))
                self._add_entrance_rule("Leyndell, Ashen Capital Throne", lambda state: self._can_get(state, "LAC/LCA: Scepter of the All-Knowing - boss drop"))
                self._add_entrance_rule("Erdtree", lambda state: self._can_get(state, "LAC/QB: Remembrance of Hoarah Loux - mainboss drop"))

            # Item Rules
            
            # LL/CFT, gesture + glint crown items
            self._add_location_rule([
                "LL/(CFT): Cannon of Haima - in chest atop tower, requires using Erudition gesture while wearing any Glintstone Crown",
                "LL/(CFT): Gavel of Haima - in chest atop tower, requires using Erudition gesture while wearing any Glintstone Crown",
                ],lambda state: state.has("Erudition", self.player) and
                (state.has("Twinsage Glintstone Crown", self.player) or state.has("Olivinus Glintstone Crown", self.player) or
                state.has("Lazuli Glintstone Crown", self.player) or state.has("Karolos Glintstone Crown", self.player) or
                state.has("Witch's Glintstone Crown", self.player)))
        
            self._add_location_rule("LL/(CT): Memory Stone - top of tower, requires Erudition gesture", "Erudition")
            
            # MotG/SR spirit summon item
            self._add_location_rule(["MotG/(SR): Primal Glintstone Blade - in chest underground behind jellyfish seal"
                ], lambda state: state.has("Spirit Jellyfish Ashes", self.player) and state.has("Spirit Calling Bell", self.player))

            # CS/AR spirit summon item
            self._add_location_rule(["CS/(AR): Graven-Mass Talisman - top of rise, use Fanged Imp Ashes or bewitching branch to make spirit enemies fight"
                ], lambda state: state.has("Fanged Imp Ashes", self.player) and state.has("Spirit Calling Bell", self.player))
                
            # Paintings
            self._add_location_rule("LG/SR: Incantation Scarab - \"Homing Instinct\" Painting reward to NW", "\"Homing Instinct\" Painting")
            self._add_location_rule("DB/MEE: Ash of War: Rain of Arrows - \"Redmane\" Painting reward down hidden cliff E of MEE", "\"Redmane\" Painting")
            self._add_location_rule("WP/CP: Warhawk Ashes - \"Prophecy\" Painting reward to N", "\"Prophecy\" Painting")
            self._add_location_rule([
                "LL/BCM: Juvenile Scholar Cap - \"Resurrection\" Painting reward to S by graves",
                "LL/BCM: Juvenile Scholar Robe - \"Resurrection\" Painting reward to S by graves",
                "LL/BCM: Larval Tear - \"Resurrection\" Painting reward to S by graves",
                ], "\"Resurrection\" Painting")
            self._add_location_rule("AP/RP: Harp Bow - \"Champion's Song\" Painting reward to S top of grave steps", "\"Champion's Song\" Painting")
            self._add_location_rule("AP/(DMV): Fire's Deadly Sin - \"Flightless Bird\" Painting reward S from boss","\"Flightless Bird\" Painting")
            self._add_location_rule("MotG/SR: Greathood - Painting reward NW of SR on bridge", "\"Sorcerer\" Painting")
            
            # vm drawing room, stuff that needs key
            self._add_location_rule([ 
                    "VM/VM: Recusant Finger - on the table in the drawing room",
                    "VM/VM: Letter from Volcano Manor (Istvan) - on the table in the drawing room",
                    "VM/VM: Perfume Bottle - in the first room on the right",
                    "VM/VM: Budding Horn x3 - behind the illusory wall in the right room, next to the stairs",
                    "VM/VM: Fireproof Dried Liver - behind the illusory wall in the right room, down the stairs",
                    "VM/VM: Nomadic Warrior's Cookbook [21] - behind the illusory wall in the right room, all the way around down the dead-end",
                    "VM/VM: Depraved Perfumer Carmaan - behind the illusory wall in the right room, all the way around down the dead-end behind the illusory wall",
                    "VM/VM: Bloodhound Claws - enemy drop behind the illusory wall in the right room, down the stairs"
                ], "Drawing-Room Key")
            
            # Region Rules
            
            self._add_entrance_rule("Stormveil Castle", lambda state: self._has_key_or_shards(state, "Rusty Key"))
            self._add_entrance_rule("Raya Lucaria Academy", "Academy Glintstone Key")
            self._add_entrance_rule("Carian Study Hall (Inverted)", "Carian Inverted Statue")
            
            self._add_entrance_rule("Nokron, Eternal City Start", lambda state: self._can_get(state, "CL/(WD): Remembrance of the Starscourge - mainboss drop"))
            
            self._add_entrance_rule("Deeproot Depths Upper", lambda state: self._can_go_to(state, "Frenzied Flame Proscription"))
            
            self._add_entrance_rule("Moonlight Altar", "Dark Moon Ring")
                    
            # also from RLA side you can get back into main hall through imp statue
            self._add_entrance_rule("Volcano Manor", 
                lambda state: state.has("Drawing-Room Key", self.player) or self._can_go_to(state, "Volcano Manor Dungeon"))
            self._add_entrance_rule("Volcano Manor Dungeon", 
                lambda state: self._can_go_to(state, "Raya Lucaria Academy Main") or self._can_go_to(state, "Volcano Manor"))
            
            self._add_entrance_rule("Leyndell, Royal Capital", lambda state: self._has_enough_great_runes(state, self.options.great_runes_required_leyndell.value))
            
            # MARK: TARNISHED DLC
            if self.options.enable_tp_dlc:
                self._add_location_rule([
                        "LRC/ES: Golden Order Flail - to W down elevator, invader drop after using Law of Regression at statue", 
                        "LRC/ES: Broken Gold Mask - to W down elevator, invader drop after using Law of Regression at statue",
                        "LRC/ES: Gold Tattoo (Chest) - to W down elevator, invader drop after using Law of Regression at statue",
                        "LRC/ES: Gold Tattoo (Arm) - to W down elevator, invader drop after using Law of Regression at statue",
                        "LRC/ES: Gold Tattoo (Leg) - to W down elevator, invader drop after using Law of Regression at statue"
                    ], "Law of Regression")
            
            self._add_entrance_rule("Mountaintops of the Giants", lambda state: self._has_key_or_shards(state, "Rold Medallion", "rold"))
            if self.options.soft_logic:
                self._add_entrance_rule("Consecrated Snowfield", lambda state: self._has_key_or_shards(state, "Rold Medallion", "rold"))
            
            self._add_entrance_rule("Hidden Path to the Haligtree", lambda state: 
                state.has("Haligtree Secret Medallion (Left)", self.player) and state.has("Haligtree Secret Medallion (Right)", self.player))
            
            if self.options.great_runes_required_erdtree.value > 0:
                self._add_entrance_rule("Erdtree", lambda state: self._has_enough_great_runes(state, self.options.great_runes_required_erdtree.value))
            
            # Smithing bell bearing rules
            if self.options.smithing_bell_bearing_option.value == 1:
                self._add_entrance_rule("Altus Plateau", lambda state: self._bell_bearings_required(state, 1, False))
                self._add_entrance_rule("Capital Outskirts", lambda state: self._bell_bearings_required(state, 2, False))
                self._add_entrance_rule("Flame Peak", lambda state: self._bell_bearings_required(state, 3, False))
                self._add_entrance_rule("Farum Azula Main", lambda state: self._bell_bearings_required(state, 4, False))
                
                self._add_entrance_rule("Dragonbarrow", lambda state: self._bell_bearings_required(state, 1, True))
                self._add_entrance_rule("Capital Outskirts", lambda state: self._bell_bearings_required(state, 2, True))
                self._add_entrance_rule("Flame Peak", lambda state: self._bell_bearings_required(state, 3, True))
                self._add_entrance_rule("Farum Azula Main", lambda state: self._bell_bearings_required(state, 4, True))
                self._add_entrance_rule("Leyndell, Ashen Capital", lambda state: self._bell_bearings_required(state, 5, True))
                if self.options.enable_dlc and self.options.dlc_start == 0:
                    self._add_entrance_rule("Gravesite Plain", # DLC requires all bell bearings if starting in base game
                        lambda state: self._bell_bearings_required(state, 4, False) and self._bell_bearings_required(state, 5, True))
            
            if self.options.early_legacy_dungeons and self.soft_logic_enabled:
                self._add_entrance_rule("Liurnia of The Lakes", lambda state: self._has_key_or_shards(state, "Rusty Key"))
                self._add_entrance_rule("Caelid", lambda state: self._has_key_or_shards(state, "Rusty Key"))
                self._add_entrance_rule("Altus Plateau", "Academy Glintstone Key")
        
            if location_dictionary["LL/(RC): Pureblood Knight's Medal - talk to Varré after invading Magnus in AP and returning the bloodsoaked Lord of Blood's Favor"].should_randomize(self.options):
                if self.options.dlc_start == 0 and self.options.enable_dlc:
                    if self.options.dlc_timing == 2:
                        self._add_entrance_rule("Mohgwyn Palace", lambda state: self._can_go_to(state, "Consecrated Snowfield"))
                        self._add_entrance_rule("Gravesite Plain",
                            lambda state: self._has_key_or_shards(state, "Rold Medallion", "rold")
                            and self._can_get(state, "MP/(MDM): Remembrance of the Blood Lord - mainboss drop")
                            and self._can_get(state, "CL/(WD): Remembrance of the Starscourge - mainboss drop"))
                    else:
                        if self.options.dlc_timing == 1:
                            self._add_entrance_rule("Mohgwyn Palace", lambda state: state.has("Pureblood Knight's Medal", self.player) and self._can_go_to(state, "Altus Plateau"))
                        else:
                            self._add_entrance_rule("Mohgwyn Palace", lambda state: state.has("Pureblood Knight's Medal", self.player))
                        self._add_entrance_rule("Gravesite Plain", 
                            lambda state: self._can_get(state, "MP/(MDM): Remembrance of the Blood Lord - mainboss drop")
                            and self._can_get(state, "CL/(WD): Remembrance of the Starscourge - mainboss drop"))
                        if self.options.dlc_timing == 0 and self.options.missable_location_behavior <= 1 and self.soft_logic_enabled: # Early medal
                            self._add_entrance_rule("Altus Plateau", lambda state: state.has("Pureblood Knight's Medal", self.player))
                            self._add_entrance_rule("Caelid", lambda state: state.has("Pureblood Knight's Medal", self.player))
                else:
                    self._add_entrance_rule("Mohgwyn Palace",
                        lambda state: state.has("Pureblood Knight's Medal", self.player) or self._can_go_to(state, "Consecrated Snowfield"))
            elif self.options.dlc_start == 0 and self.options.enable_dlc: # pkm not randomized
                self._add_entrance_rule("Gravesite Plain", 
                    lambda state: self._can_get(state, "MP/(MDM): Remembrance of the Blood Lord - mainboss drop")
                    and self._can_get(state, "CL/(WD): Remembrance of the Starscourge - mainboss drop"))
        
        # MARK: DLC Rules
        if self.options.enable_dlc:
                
            # dlc only else do
            if self.options.dlc_start == 1:
                self._add_entrance_rule("Rauh Ruins Limited", 
                    lambda state: state.has("Imbued Sword Key", self.player, 1) or self._can_go_to(state, "Ancient Ruins of Rauh"))
            elif not self.dlc_excluded:
                if (self.options.dlc_scadutree_fragments.value
                    or self.options.dlc_messmer_kindle.value
                    or self.options.separate_progression.value): # only do loop if one of these are on
                    for region in self.multiworld.get_regions(self.player):
                        for location in region.locations:
                            if region.name in region_order:
                                if self.options.dlc_scadutree_fragments.value:
                                    self._add_item_rule(location.name,
                                        lambda item: (item.player != self.player)
                                            or (item.data.base_name != "Scadutree Fragment")
                                        )
                                if self.options.separate_progression.value:
                                    self._add_item_rule(location.name,
                                        lambda item: (item.player != self.player)
                                            or not ((item.data.is_dlc or item.found_in_dlc) and item.advancement)
                                        )
                                elif self.options.dlc_messmer_kindle.value:
                                    self._add_item_rule(location.name,
                                        lambda item: (item.player != self.player)
                                            or (item.data.name != "Messmer's Kindling" and item.data.name != "Messmer's Kindling Shard")
                                        )
                            elif region.name in region_order_dlc:
                                if self.options.separate_progression.value:
                                    self._add_item_rule(location.name,
                                        lambda item: (item.player != self.player) #and item.game != "EldenRing"
                                            or not (not (item.data.is_dlc or item.found_in_dlc) and item.advancement)
                                        )
                                
                                
                self._add_entrance_rule("The Four Belfries (Chapel of Anticipation)", lambda state: state.has("Imbued Sword Key", self.player, 4))
                self._add_entrance_rule("The Four Belfries (Nokron)", lambda state: state.has("Imbued Sword Key", self.player, 4))
                self._add_entrance_rule("The Four Belfries (Farum Azula)", lambda state: state.has("Imbued Sword Key", self.player, 4))
                self._add_entrance_rule("Rauh Ruins Limited", 
                    lambda state: state.has("Imbued Sword Key", self.player, 4) or self._can_go_to(state, "Ancient Ruins of Rauh"))
              
            self._add_entrance_rule("Enir Ilim", lambda state: self._has_key_or_shards(state, "Messmer's Kindling"))
            
            self.multiworld.register_indirect_condition(self.get_region("Castle Ensis"), self.get_entrance("Go To Scadu Altus"))
            self.multiworld.register_indirect_condition(self.get_region("Ancient Ruins of Rauh"), self.get_entrance("Go To Rauh Ruins Limited"))
            self.multiworld.register_indirect_condition(self.get_region("Shadow Keep, Church District"), self.get_entrance("Go To Shadow Keep Storehouse"))
            
            if self.options.spiritspring_stones:
                self._add_entrance_rule("Scadu Altus", lambda state: state.has("Fort of Reprimand Spiritspring Stone", self.player)
                    or self._can_get(state, "CE/CLC: Remembrance of the Twin Moon Knight - mainboss drop"))
                self._add_location_rule("SA/SC: Scadutree Fragment - by cross", "Scaduview Cross Spiritspring Stone")
                self._add_location_rule("SA/(RR): Rabbath's Cannon - in chest top of rise", "Rabbath's Rise Spiritspring Stone")
                self._add_location_rule([
                    "RB/(NNM): Red Bear's Claw - boss drop", "RB/(NNM): Iron Rivet Armor - boss drop", "RB/(NNM): Iron Rivet Gauntlets - boss drop", 
                    "RB/(NNM): Iron Rivet Greaves - boss drop", "RB/(NNM): Fang Helm - boss drop", "RB/NNM: Spiraltree Seal - \"The Sacred Tower\" Painting reward SW of NNM"
                    ], "Rauh Base Spiritspring Stone")
                self._add_location_rule([
                    "ARR/CBME: Beast Horn x2 - up sealed spiritspring, on SW pillar walkway, seal is to N downstairs, outside to left",
                    "ARR/CBME: Mottled Necklace +2 - in chest up sealed spiritspring, top of stairs, seal is to N downstairs, outside to left"
                    ], "Rauh Ruins Spiritspring Stone")
                
            # rykard
            if self.options.enemy_rando and not self.options.rykard_encounter and self.soft_logic_enabled:
                self._add_entrance_rule("Jagged Peak Foot", lambda state: self._can_get(state, "GP/(DP): Dragon-Hunter's Great Katana - boss drop"))
                self._add_entrance_rule("Shadow Keep", lambda state: self._can_get(state, "SK/SKMG: Aspects of the Crucible: Thorns - boss drop"))
                self._add_entrance_rule("Scaduview", lambda state: self._can_get(state, "ScV/SKBG: Remembrance of the Wild Boar Rider - mainboss drop"))
                self._add_entrance_rule("Abyssal Woods", lambda state: self._can_get(state, "RR/(DC): Barbed Staff-Spear - boss drop"))
                self._add_entrance_rule("Enir Ilim", lambda state: self._can_get(state, "ARR/CBME: Remembrance of the Saint of the Bud - mainboss drop"))
            
            # dlc paintings
            self._add_location_rule("GP/BG: Serpent Crest Shield - painting reward SE of BG", "\"Incursion\" Painting")
            self._add_location_rule("RB/NNM: Spiraltree Seal - \"The Sacred Tower\" Painting reward SW of NNM", 
                lambda state: state.has("\"The Sacred Tower\" Painting", self.player) and self._can_go_to(state, "Enir Ilim"))
            self._add_location_rule("JP/JPM: Rock Heart - \"Domain of Dragons\" Painting reward, after first spirit spring head down return path", "\"Domain of Dragons\" Painting")
            
            # furnace golem / Hefty Furnace Pot
            self._add_location_rule([
                "RR/(RU): Bloodsucking Cracked Tear - inactive furnace golem, use Hefty Furnace Pot",
                "RR/(RU): Furnace Visage - inactive furnace golem, use Hefty Furnace Pot",
                "RR/(RU): Giant Golden Arc - in chest within building behind inactive furnace golem",
                "SA/BLV: Cerulean-Sapping Cracked Tear - furnace golem to NE along path",
                "SA/BLV: Furnace Visage - furnace golem to NE along path",
                "CHG/CHG: Glovewort Crystal Tear - furnace golem to W above river",
                "CHG/CHG: Furnace Visage - furnace golem to W above river"
                ], lambda state: state.has("Crafting Kit", self.player) 
                    and state.has("Greater Potentate's Cookbook [2]", self.player) and state.has("Hefty Cracked Pot", self.player))
            
            # DLC region rules
            
            if self.options.soft_logic: # jagged peak is a later game area, make it not first
                self._add_entrance_rule("Jagged Peak Foot", lambda state: self._can_go_to(state, "Belurat") or self._can_go_to(state, "Ellac River") or self._can_go_to(state, "Castle Ensis"))
            
            self._add_entrance_rule("Belurat Swamp", lambda state: # the long drop down path lets you go here
                state.has("Well Depths Key", self.player) or self._can_go_to(state, "Enir Ilim"))
            
            self._add_entrance_rule("Hinterland", "O Mother")
            
            self._add_entrance_rule("Cathedral of Manus Metyr", lambda state: state.has("Hole-Laden Necklace", self.player) and 
                self._can_go_to(state, "Finger Ruins of Rhia") and self._can_go_to(state, "Finger Ruins of Dheo"))
            
            # the funny gaol
            self._add_entrance_rule("Lamenter's Gaol (Upper)", "Gaol Upper Level Key")
            self._add_entrance_rule("Lamenter's Gaol (Lower)", "Gaol Lower Level Key")
        else:
            # vanilla imbued
            self._add_entrance_rule("The Four Belfries (Chapel of Anticipation)", lambda state: state.has("Imbued Sword Key", self.player, 3))
            self._add_entrance_rule("The Four Belfries (Nokron)", lambda state: state.has("Imbued Sword Key", self.player, 3))
            self._add_entrance_rule("The Four Belfries (Farum Azula)", lambda state: state.has("Imbued Sword Key", self.player, 3))
        
        # no runes in shops
        for loc in self.multiworld.get_unfilled_locations(self.player):
            if loc.data.shop:
                self._add_item_rule(loc.name, lambda item: (item.player != self.player and item.game != "Eldenring") or item.data.runes == None)
        
        # Rykard and Serpent Rule
        if not self.options.rykard_encounter:
            if self.rykard_location and (self.rykard_location.dlc and self.options.enable_dlc or not self.rykard_location.dlc and self.base_enabled):
                if len(self.rykard_location.locations) != 0: self._add_location_rule(self.rykard_location.locations, lambda state: state.has("Serpent-Hunter", self.player))
            if self.serpent_location and (self.serpent_location.dlc and self.options.enable_dlc or not self.serpent_location.dlc and self.base_enabled):
                if len(self.rykard_location.locations) != 0: self._add_location_rule(self.serpent_location.locations, lambda state: state.has("Serpent-Hunter", self.player))
            
        # Create duplicate location rules
        if len(self.all_duplicate_locations) > 0:
            for dupe_location in self.all_duplicate_locations: # dupe locations require og locations
                og_location = dupe_location[:dupe_location.find("extra item")-2]
                self._add_location_rule(dupe_location, lambda state, og_location=og_location: self._can_get(state, og_location))
            
        # if more then 1 world exists stop prio placing outside of prio
        if self.options.important_at_priority_only:
            if self.multiworld.players != 1: # more then 1 eldenring
                for world in [self.multiworld.worlds[w] for w in self.multiworld.worlds]:
                    # if important_at_priority_only is off or game isn't eldenring add restriction rules
                    if world.game == "EldenRing" and not world.options.important_at_priority_only or world.game != "EldenRing":
                        # Make non-priority locations exclude progression items.
                        for loc in self.multiworld.get_unfilled_locations(self.player):
                            if loc.progress_type != LocationProgressType.PRIORITY:
                                self._add_item_rule(loc.name, lambda item: not item.advancement or item.deprioritized 
                                    or item.player != self.player and item.useful and self.options.other_world_useful_at_priority)
        
        # Ending Goal
        self.multiworld.completion_condition[self.player] = lambda state: self._is_complete(state)
    
    def _has_key_or_shards(self, state: CollectionState, item: str, other_logic="") -> bool:
        """other_logic is for replacing og key item with some other logic, ex: rold requiring only great runes and not medallion"""
        option, min_shard = self._shard_exists(f"{item} Shard")
        if option and option['Max'] > 1: 
            return state.has(f"{item} Shard", self.player, min_shard)
            
        match other_logic:
            case "rold":
                if self.options.great_runes_required_mountain.value != -1:
                    return self._has_enough_great_runes(state, self.options.great_runes_required_mountain.value)
        
        return state.has(item, self.player) # if no additional state or add state fails just return has item
    
    def _region_lock(self) -> None: # MARK: Region Lock Items
        """All region lock rules."""
        if self.options.world_logic == "region_lock":
            if self.base_enabled:
                self._add_entrance_rule("Weeping Peninsula", "Weeping Lock")
                self._add_entrance_rule("Liurnia of The Lakes", "Liurnia Lock")
                
                self._add_entrance_rule("Siofra River", "Siofra Lock")
                self._add_entrance_rule("Nokron, Eternal City Start", "Siofra Lock")
                self._add_entrance_rule("Ainsel River", "Ainsel Lock")
                self._add_entrance_rule("Ainsel River Main", "Ainsel Lock")
                self._add_entrance_rule("Deeproot Depths", "Deeproot Lock")
                self._add_entrance_rule("Deeproot Depths Upper", "Deeproot Lock")
                
                self._add_entrance_rule("Caelid", "Caelid Lock")
                self._add_entrance_rule("Sellia Crystal Tunnel", "Caelid Lock")
                
                self._add_entrance_rule("Altus Plateau", lambda state: 
                    state.has("Dectus Medallion (Left)", self.player)
                    and state.has("Dectus Medallion (Right)", self.player))
                self._add_entrance_rule("Mt. Gelmir", "Mt. Gelmir Lock")
                self._add_entrance_rule("Volcano Manor Entrance", "Volcano Lock")
                self._add_entrance_rule("Volcano Manor Dungeon", "Volcano Lock")
                
                self._add_entrance_rule("Subterranean Shunning-Grounds", "Sewer Lock")
                
                self._add_entrance_rule("Mohgwyn Palace", "Mohgwyn Lock")
                
                self._add_entrance_rule("Farum Azula", "Farum Azula Lock")
                self._add_entrance_rule("Leyndell, Ashen Capital", "Ashen Lock")
                self._add_entrance_rule("Miquella's Haligtree", "Haligtree Lock")
                
            if self.options.enable_dlc:
                if self.options.dlc_start == 0: self._add_entrance_rule("Gravesite Plain", "Gravesite Lock")
                self._add_entrance_rule("Belurat", "Belurat Lock")
                self._add_entrance_rule("Belurat Swamp", "Belurat Lock")
                self._add_location_rule(
                    "BTS|EI/SR: Euporia - outside to SE downstairs, drop down from gazebo, after jump to window, continue down and down",
                    "Belurat Lock")
                self._add_entrance_rule("Castle Ensis", "Ensis & Scadu Altus Lock")
                self._add_entrance_rule("Scadu Altus", "Ensis & Scadu Altus Lock")
                self._add_entrance_rule("Ellac River", "Ellac Lock")
                self._add_entrance_rule("Cerulean Coast", "Cerulean & Charo Lock")
                self._add_entrance_rule("Charo's Hidden Grave", "Cerulean & Charo Lock")
                self._add_entrance_rule("Stone Coffin Fissure", lambda state: state.has("Stone Coffin Lock", self.player) and self._can_go_to(state, "Scadu Altus"))
                self._add_entrance_rule("Jagged Peak Foot", "Jagged Peak Lock")
                self._add_entrance_rule("Rauh Base", "Rauh Base Lock")
                self._add_entrance_rule("Shadow Keep", "Shadow Keep Lock")
                self._add_entrance_rule("Shadow Keep, Church District", "Shadow Keep Lock")
                self._add_entrance_rule("Recluses' River", "Recluses' Lock")
                self._add_entrance_rule("Abyssal Woods", "Abyssal Lock")
                self._add_entrance_rule("Ancient Ruins of Rauh", "Ancient Ruins Lock")
            
    def _key_rules(self) -> None: # MARK: SSK Rules
        # in order from early game to late game each rule needs to include the last count for an area
        
        # limgrave
        self._add_entrance_rule("Fringefolk Hero's Grave", lambda state: self._choose_key_rules(state, 3, "Limgrave Master Key")) # 2
        self._add_location_rule("LG/(SWV): Green Turtle Talisman - behind imp statue", lambda state: self._choose_key_rules(state, 3, "Limgrave Master Key")) # 1
        
        #self._add_entrance_rule("Roundtable Hold", lambda state: self._has_enough_keys(state, 3))
        # roundtable
        self._add_location_rule([
            "RH: Crepus's Black-Key Crossbow - behind imp statue in chest", "RH: Black-Key Bolt x20 - behind imp statue in chest", # 1
            "RH: Assassin's Prayerbook - behind second imp statue in chest", # 2
            ], lambda state: self._choose_key_rules(state, 6, "Roundtable Master Key"))
        
        #self._add_entrance_rule("Weeping Peninsula", lambda state: self._has_enough_keys(state, 6))
        # weeping
        self._add_location_rule([
            "WP/(TCC): Nomadic Warrior's Cookbook [9] - behind imp statue", # 1
            "WP/(WE): Radagon's Scarseal - boss drop Evergaol", # 1
            ], lambda state: self._choose_key_rules(state, 8, "Weeping Master Key"))
        
        #self._add_entrance_rule("Stormveil Castle", lambda state: self._has_enough_keys(state, 8))
        # stormveil
        self._add_location_rule([
            "SV/LC: Godslayer's Seal - left chest behind imp statue in storeroom SE of massive courtyard", # 1a
            "SV/LC: Godskin Prayerbook - right chest behind imp statue in storeroom SE of massive courtyard", # 1a
            "SV/RT: Iron Whetblade - shortcut elevator to SE, to N through door, behind imp statue", # 1b
            "SV/RT: Hawk Crest Wooden Shield - shortcut elevator to SE, to N through door, behind imp statue", # 1b
            "SV/RT: Miséricorde - shortcut elevator to SE, to N through door, behind imp statue", # 1b
            ], lambda state: self._choose_key_rules(state, 10, "Stormveil Master Key"))
        
        #self._add_entrance_rule("Siofra River", lambda state: self._has_enough_keys(state, 10))
        # siofra
        # for leaving siofra to caelid ravine
        self._add_location_rule([
            "CL/DSW: Spiked Palisade Shield - to W follow ravine",
            "CL/DSW: Stonesword Key - to S",
            "CL/CCO: Great-Jar's Arsenal - beat Great-Jar's knights",
            ], lambda state: self._choose_key_rules(state, 12, "Siofra Master Key") and 
            self._can_go_to(state, "Siofra River")) # 2
        
        #self._add_entrance_rule("Liurnia of The Lakes", lambda state: self._has_enough_keys(state, 12))
        # liurnia
        self._add_location_rule([
            "LL/(BKC): Rosus' Axe - behind imp statue near boss door", # 1a
            "LL/(CC): Nox Mirrorhelm - behind imp statue, in SW corner", # 1b
            ], lambda state: self._choose_key_rules(state, 16, "Liurnia Master Key"))
        self._add_entrance_rule("Academy Crystal Cave", lambda state: self._choose_key_rules(state, 16, "Liurnia Master Key")) # 2
        
        #self._add_entrance_rule("Altus Plateau", lambda state: self._has_enough_keys(state, 16))
        # altus
        self._add_location_rule([
            "AP/(SHG): Crimson Seed Talisman - behind imp statue", # 1a
            "AP/(SHG): Dragoncrest Shield Talisman +1 - ride up first cleaver, behind imp statue", # 1b
            "AP/WhR: Pearldrake Talisman +1 - in chest underground behind a imp statue", # 1c
            "AP/GLE: Godfrey Icon - boss drop Evergaol", # 1d
            ], lambda state: self._choose_key_rules(state, 24, "Altus Master Key"))
        self._add_entrance_rule("Old Altus Tunnel", lambda state: self._choose_key_rules(state, 24, "Altus Master Key")) # 2
        self._add_entrance_rule("Unsightly Catacombs", lambda state: self._choose_key_rules(state, 24, "Altus Master Key")) # 2
        
        #self._add_entrance_rule("Caelid", lambda state: self._has_enough_keys(state, 24))
        # caelid
        self._add_entrance_rule("Gaol Cave", lambda state: self._choose_key_rules(state, 27, "Caelid Master Key")) # 2
        self._add_location_rule("CL/(FR): Sword of St. Trina - in chest underground behind imp statue", 
                                lambda state: self._choose_key_rules(state, 27, "Caelid Master Key")) # 1
        
        #self._add_entrance_rule("Nokron, Eternal City Start", lambda state: self._has_enough_keys(state, 27))
        # nokron
        self._add_location_rule([
            "NR/(NSG): Mimic Tear Ashes - in chest behind imp statue upper interior", # 1a
            "NR/(NSG): Smithing Stone [3] - behind imp statue upper interior", # 1a
            ], lambda state: self._choose_key_rules(state, 28, "Nokron Master Key"))
        
        #self._add_entrance_rule("Mt. Gelmir", lambda state: self._has_enough_keys(state, 28))
        # mt gelmir
        self._add_location_rule([
            "MtG/(WC): Lightning Scorpion Charm - behind imp statue", # 1
            ], lambda state: self._choose_key_rules(state, 29, "Mt. Gelmir Master Key"))
        self._add_entrance_rule("Seethewater Cave", lambda state: self._choose_key_rules(state, 31, "Mt. Gelmir Master Key")) # 2
        
        #self._add_entrance_rule("Volcano Manor Entrance", lambda state: self._has_enough_keys(state, 31))
        # volcano
        self._add_location_rule([
            "VM/PTC: Crimson Amber Medallion +1 - behind imp statue W of town", # 1
            "VM/TE: Seedbed Curse - NW of shortcut elevator, after imp statue, lower part of big cage room to SW", # 2a
            "VM/TE: Ash of War: Royal Knight's Resolve - NW of shortcut elevator, after imp statue, lower part of big cage room to NE", # 2a
            "VM/TE: Somber Smithing Stone [7] - NW of shortcut elevator, after imp statue, lower part of big cage room outside to SW", # 2a
            "VM/TE: Dagger Talisman - NW of shortcut elevator, after imp statue, drop to hidden path top item", # 2a
            "VM/TE: Rune Arc - NW of shortcut elevator, after imp statue, drop to hidden path lower item", # 2a
            ], lambda state: self._choose_key_rules(state, 34, "Volcano Master Key"))
        
        #self._add_entrance_rule("Capital Outskirts", lambda state: self._has_enough_keys(state, 34))
        # capital outskirts
        self._add_location_rule([
            "CO/(AHG): Golden Epitaph - behind imp statue", # 1
            ], lambda state: self._choose_key_rules(state, 35, "Capital Outskirts Master Key"))
        
        #self._add_entrance_rule("Ainsel River Main", lambda state: self._has_enough_keys(state, 35))
        # nokstella
        self._add_location_rule([
            "NS/NEC: Nightmaiden & Swordstress Puppets - in chest behind imp statue to W up stairs, left before bridge", # 1
            ], lambda state: self._choose_key_rules(state, 36, "Nokstella Master Key"))
        
        #self._add_entrance_rule("Moonlight Altar", lambda state: self._has_enough_keys(state, 36))
        # moonlight altar
        self._add_location_rule([
            "MA/(LER): Cerulean Amber Medallion +2 - in chest under illusory floor behind imp statue", # 1
            ], lambda state: self._choose_key_rules(state, 37, "Moonlight Master Key"))
        
        #self._add_entrance_rule("Mountaintops of the Giants", lambda state: self._has_enough_keys(state, 37))
        # mountaintops
        self._add_location_rule([
            "FP/(GCHG): Flame, Protect Me - behind imp statue", # 1a
            "FP/(GCHG): Cranial Vessel Candlestand - upper room after fire spitter, behind imp statue", # 1b
            ], lambda state: self._choose_key_rules(state, 41, "Mountaintops Master Key"))
        self._add_entrance_rule("Spiritcaller Cave", lambda state: self._choose_key_rules(state, 41, "Mountaintops Master Key")) # 2
        
        #self._add_entrance_rule("Farum Azula", lambda state: self._has_enough_keys(state, 41))
        # farum
        self._add_location_rule([ # entire area behind a imp staute lol
            "FA/DTL: Lord's Rune - to SE in fountain", # 2
            "FA/DTL: Nascent Butterfly x2 - to SE down left stairs by tree", # 2
            "FA/DTL: Golden Seed - seedtree to SE up right path", # 2
            "FA/DTL: Rune Arc - to SE up right path beside seedtree", # 2
            "FA/DTL: Smithing Stone [8] - to SE up right path, E of seedtree behind gazebo", # 2
            "FA/DTL: Golden Rune [12] - to SE up right path, E of seedtree left of gazebo by tree", # 2
            "FA/DTL: Smithing Stone [7] - to SE up right path, E of seedtree left of gazebo on ledge", # 2
            "FA/DTL: Golden Lightning Fortification - scarab to SE up right path, SW of seedtree", # 2
            "FA/DTL: Smithing Stone [8] - to SE up right path, SW of seedtree", # 2
            "FA/DTL: Golden Rune [12] - to SE up right path, W of seedtree on platform after crossing building", # 2
            "FA/DTL: Smithing Stone [7] - to SE up right path, W of seedtree on second platform after crossing building", # 2
            "FA/DTL: Ancient Dragon Apostle's Cookbook [4] - to SE up right path, W of seedtree, far end of path in building", # 2
            "FA/DTL: Somber Smithing Stone [8] - to SE up right path, W of seedtree, far end of path left of building", # 2
            "FA/DTL: Smithing Stone [8] - to SE up right path, W of seedtree, far end of path drop down left of building", # 2
            "FA/DTL: Dragonwound Grease x2 - to S under fallen building", # 2
            "FA/DTL: Shard of Alexander - fight Alexander to SW", # 2
            "FA/DTL: Alexander's Innards - fight Alexander to SW", # 2
            ], lambda state: self._choose_key_rules(state, 43, "Farum Master Key"))
        
        #self._add_entrance_rule("Consecrated Snowfield", lambda state: self._has_enough_keys(state, 43))
        # snowfield
        self._add_entrance_rule("Cave of the Forlorn", lambda state: self._choose_key_rules(state, 45, "Snowfield Master Key")) # 2
        
        #self._add_entrance_rule("Miquella's Haligtree", lambda state: self._has_enough_keys(state, 45))
        # haligtree +3
        self._add_location_rule([
            "EBH/PR: Triple Rings of Light - drop down to E, in chest behind imp statue", # 1
            "EBH/EIW: Marika's Soreseal - to SE past the imp statue in lower section", # 2
            ], lambda state: self._choose_key_rules(state, 48, "Haligtree Master Key"))
        
    def _choose_key_rules(self, state: CollectionState, keys_required: int, master_key: str) -> bool:
        "choose key rules"
        if self.options.use_master_key.value == 1:   return state.has(master_key, self.player)
        elif self.options.use_master_key.value == 2: return state.has("Stonesword Master Key", self.player)
        return self._has_enough_keys(state, keys_required)
        
    def _dragon_communion_rules(self) -> None: # MARK: Dragon Rules
        """Rules for dragon communion"""
        if self.base_enabled:
            self._add_location_rule([
                "LG/(CDC): Dragonfire - Dragon Communion", # 1
                "LG/(CDC): Dragonclaw - Dragon Communion", # 1
                "LG/(CDC): Dragonmaw - Dragon Communion", # 1
                ], lambda state: self._has_enough_hearts(state, 3)) 
            
            # caelid dragon communion
            self._add_location_rule([
                "CL/(CDC): Glintstone Breath - Dragon Communion", # 1
                "CL/(CDC): Rotten Breath - Dragon Communion", # 1
                "CL/(CDC): Dragonice - Dragon Communion", # 1
                "CL/(CDC): Agheel's Flame - Dragon Communion, kill boss in LG, NW of DBR", # 2
                "CL/(CDC): Greyoll's Roar - Dragon Communion, kill enemy in CL, W of FF", # 3
                "CL/(CDC): Ekzykes's Decay - Dragon Communion, kill boss to NW of here", # 2
                ], lambda state: self._has_enough_hearts(state, 13)) 
            
            self._add_location_rule("CL/(CDC): Smarag's Glintstone Breath - Dragon Communion, kill boss in LL, SW of ACC", 
                lambda state: self._has_enough_hearts(state, 15) and self._can_go_to(state, "Liurnia of The Lakes")) # 2
            self._add_location_rule("CL/(CDC): Magma Breath - Dragon Communion, kill boss in MtG, S of FL", 
                lambda state: self._has_enough_hearts(state, 16) and self._can_go_to(state, "Mt. Gelmir")) # 1
            self._add_location_rule("CL/(CDC): Borealis's Mist - Dragon Communion, kill boss in MotG, N of FCM", 
                lambda state: self._has_enough_hearts(state, 18) and self._can_go_to(state, "Mountaintops of the Giants")) # 2
            self._add_location_rule("CL/(CDC): Theodorix's Magma - Dragon Communion, kill boss in CS, SE of CF", 
                lambda state: self._has_enough_hearts(state, 20) and self._can_go_to(state, "Consecrated Snowfield")) # 2
        
            if self.options.enable_dlc: # dlc
                self._add_location_rule("JP/GADC: Ghostflame Breath - Grand Dragon Communion", lambda state: self._has_enough_hearts(state, 23)) # 3
        else: # dlc only, only need 3
            self._add_location_rule("JP/GADC: Ghostflame Breath - Grand Dragon Communion", lambda state: self._has_enough_hearts(state, 3)) # 3
    
    def _has_enough_great_runes(self, state: CollectionState, runes_required: int) -> bool:
        """Returns whether the given state has enough great runes."""
        return (state.count_from_list([
            "Godrick's Great Rune","Rykard's Great Rune","Radahn's Great Rune",
            "Morgott's Great Rune","Mohg's Great Rune","Malenia's Great Rune",
            "Great Rune of the Unborn"], self.player) >= runes_required)
    
    def _has_enough_keys(self, state: CollectionState, req_keys: int) -> bool:
        """Returns whether the given state has enough keys."""
        return (state.count("Stonesword Key", self.player) + (state.count("Stonesword Key x3", self.player) * 3) + (state.count("Stonesword Key x5", self.player) * 5)) >= req_keys
        
    def _bell_bearings_required(self, state: CollectionState, up_to: int, bell_type: bool) -> bool:
        """Returns whether the given state has enough bell bearings.
        false is smithing, true is somber"""
        if bell_type:
            return state.has_all([f"Somberstone Miner's Bell Bearing [{c}]" for c in range(1, up_to+1)], self.player)
        else:
            return state.has_all([f"Smithing-Stone Miner's Bell Bearing [{c}]" for c in range(1, up_to+1)], self.player)
    
    def _has_bloody_finger(self, state: CollectionState) -> bool:
        """Returns whether the given state has any bloody fingers"""
        return (state.count_from_list([
            "Festering Bloody Finger", "Festering Bloody Finger x2", "Festering Bloody Finger x3",
            "Festering Bloody Finger x5", "Festering Bloody Finger x6", "Festering Bloody Finger x8",
            "Festering Bloody Finger x10"], self.player) >= 1)
    
    def _has_enough_hearts(self, state: CollectionState, req_hearts: int) -> bool:
        """Returns whether the given state has enough dragon hearts."""
        return (state.count("Dragon Heart", self.player) + (state.count("Dragon Heart x3", self.player) * 3) + (state.count("Dragon Heart x5", self.player) * 5)) >= req_hearts
    
    def _add_shop_rules(self) -> None:
        """Adds rules for items unlocked in shops."""

        # Scrolls
        scrolls = [
            ("Academy Scroll", ["Great Glintstone Shard", "Swift Glintstone Shard"]),
            ("Conspectus Scroll", ["Glintstone Cometshard", "Star Shower"]),
            ("Royal House Scroll", ["Glintblade Phalanx", "Carian Slicer"])
        ]

        # Prayerbooks
        books = [
            ("Two Fingers' Prayerbook", ["Lord's Heal", "Lord's Aid"]),
            ("Assassin's Prayerbook", ["Assassin's Approach", "Darkness"]),
            ("Golden Order Principia", ["Radagon's Rings of Light", "Law of Regression"]),
            ("Dragon Cult Prayerbook", ["Lightning Spear", "Honed Bolt", "Electrify Armament"]),
            ("Ancient Dragon Prayerbook", ["Ancient Dragons' Lightning Spear", "Ancient Dragons' Lightning Strike"]),
            ("Fire Monks' Prayerbook", ["O, Flame!", "Surge, O Flame!"]),
            ("Giant's Prayerbook", ["Giantsflame Take Thee", "Flame, Fall Upon Them"]),
            ("Godskin Prayerbook", ["Black Flame", "Black Flame Blade"])
        ]

        for (scroll, scroll_items) in scrolls:
            self._add_location_rule([f"LG/(WR): {s_item} - {scroll}" for s_item in scroll_items], scroll)
        for (book, book_items) in books:
            self._add_location_rule([f"RH: {b_item} - {book}" for b_item in book_items], book)
        
        if self.options.spell_shop_spells_only:
            for loc in self.multiworld.get_locations(self.player):
                if loc.data.shop and (loc.data.sorceries or loc.data.incantations):
                    self._add_item_rule(loc.data.name,
                        lambda item: (item.player == self.player)
                            and (item.data.sorcery or item.data.incantation)
                        )
                
    def _add_npc_rules(self) -> None: # MARK: NPC Rules
        """Adds rules for items accessible via NPC quests.

        We list missable locations here even though they never contain progression items so that the
        game knows what sphere they're in.

        Generally, for locations that can be accessed early by killing NPCs, we set up requirements
        assuming the player _doesn't_ so they aren't forced to start killing allies to advance the
        quest.
        """
        if self.base_enabled:
            # MARK: Varré
            
            self._add_location_rule([ "LL/(RC): Festering Bloody Finger x5 - talk to Varré after beating SV mainboss",
            ], lambda state: self._can_go_to(state, "Stormveil Castle"))
            
            self._add_location_rule([ 
                "AP/(WbR): Great Stars - invade Magus",
                "AP/(WbR): Somber Smithing Stone [6] - invade Magus"
            ], lambda state: self._has_bloody_finger(state))
            
            self._add_location_rule([ "LL/(RC): Lord of Blood's Favor - talk to Varré after invading Magnus in AP",
            ], lambda state: self._can_go_to(state, "Altus Plateau"))
            
            self._add_location_rule([ 
                "LL/(RC): Pureblood Knight's Medal - talk to Varré after invading Magnus in AP and returning the bloodsoaked Lord of Blood's Favor",
                "LL/(RC): Bloody Finger - talk to Varré after invading Magnus in AP and returning the bloodsoaked Lord of Blood's Favor"
            ], lambda state: self._can_go_to(state, "Altus Plateau") and state.has("Lord of Blood's Favor", self.player))
            
            self._add_location_rule([ 
                "MP/(MDM): Festering Bloody Finger x6 - invade Varré near DMM grace",
                "MP/(MDM): Varré's Bouquet - invade Varré near DMM grace"
            ], lambda state: self._can_go_to(state, "Altus Plateau") and state.has("Lord of Blood's Favor", self.player))
            
            # MARK: Hyetta
            
            self._add_location_rule([
                "FFP/FFP: Frenzied Flame Seal - given by Hyetta at end of her quest",
                "FFP/FFP: Frenzyflame Stone x3 - given by Hyetta at end of her quest"
            ], lambda state: state.has("Shabriri Grape", self.player, 3) and state.has("Fingerprint Grape", self.player)
                and self._can_go_to(state, "Weeping Peninsula") and state.has("Irina's Letter", self.player))
            
            # MARK: Edgar
            
            self._add_location_rule([ 
                "LL/(RS): Raw Meat Dumpling x5 - kill invader Edgar",
                "LL/(RS): Shabriri Grape - kill invader Edgar",
                "LL/(RS): Raw Meat Dumpling 1 - in shack when Edgar invades",
                "LL/(RS): Raw Meat Dumpling 2 - in shack when Edgar invades",
                "LL/(RS): Raw Meat Dumpling 3 - in shack when Edgar invades",
                "LL/(RS): Raw Meat Dumpling 4 - in shack when Edgar invades",
                "LL/(RS): Raw Meat Dumpling 5 - in shack when Edgar invades",
                "WP/BS: Banished Knight's Halberd - kill Edgar at Irina's body or at LL/RS"
            ], lambda state: self._can_go_to(state, "Weeping Peninsula") and self._can_go_to(state, "Liurnia of The Lakes")
                and state.has("Irina's Letter", self.player))
            
            # MARK: Roderika
            
            self._add_location_rule([ 
                "LG/(SS): Golden Seed - give Roderika Chrysalids' Memento then talk to her at RH, or after SV mainboss item is at SS",
                "SV/RT: Crimson Hood - shortcut elevator to SE, to SE under dead troll, after Roderika becomes a spirit tuner",
            ], "Chrysalids' Memento")
            
            # MARK: Ensha
            
            self._add_location_rule([
                "RH: Clinging Bone - dropped by Ensha, after getting half of secret medallion",
                "RH: Royal Remains Helm - Ensha's spot, after getting half of secret medallion",
                "RH: Royal Remains Armor - Ensha's spot, after getting half of secret medallion",
                "RH: Royal Remains Gauntlets - Ensha's spot, after getting half of secret medallion",
                "RH: Royal Remains Greaves - Ensha's spot, after getting half of secret medallion"
            ], lambda state: state.has("Haligtree Secret Medallion (Left)", self.player) or state.has("Haligtree Secret Medallion (Right)", self.player))
            
            # MARK: Sellen
            
            self._add_location_rule([ "LG/(WR): Sellian Sealbreaker - given by Sellen after you show her Comet Azur",
            ], lambda state: self._can_go_to(state, "Mt. Gelmir"))
            
            self._add_location_rule([ "DB/(SH): Stars of Ruin - lower first big room N side, need Sellian Sealbreaker, given by Lusat",
            ], "Sellian Sealbreaker")
            
            self._add_location_rule([ 
                "LG/(WR): Starlight Shards - given by Sellen after you show her Stars of Ruin",
                "WP/(WR): Sellen's Primal Glintstone - talk to Sellen"
            ], lambda state: self._can_go_to(state, "Dragonbarrow") and self._can_go_to(state, "Mt. Gelmir") 
                and state.has("Sellian Sealbreaker", self.player))
            
            self._add_location_rule([ 
                "RLA/RLGL: Glintstone Kris - given by Sellen after siding with her",
                "RLA/RLGL: Shard Spiral - side with Sellen, sold in shop",
                "RLA/RLGL: Witch's Glintstone Crown - side with either",
                "RLA/RLGL: Ancient Dragon Smithing Stone - side with Jerren",
                "RLA/RLGL: Eccentric's Hood - side with Sellen",
                "RLA/RLGL: Eccentric's Armor - side with Sellen",
                "RLA/RLGL: Eccentric's Manchettes - side with Sellen",
                "RLA/RLGL: Eccentric's Breeches - side with Sellen",
                
                # idk if you NEED to side with sellen for these
                "DB/(SH): Lusat's Glintstone Crown - side with Sellen, lower first big room N side, where Lusat was",
                "DB/(SH): Lusat's Robe - side with Sellen, lower first big room N side, where Lusat was",
                "DB/(SH): Lusat's Manchettes - side with Sellen, lower first big room N side, where Lusat was",
                "DB/(SH): Old Sorcerer's Legwraps - side with Sellen, lower first big room N side, where Lusat was",
                "MtG/PSA: Azur's Glintstone Crown - side with Sellen, where Azur was",
                "MtG/PSA: Azur's Glintstone Robe - side with Sellen, where Azur was",
                "MtG/PSA: Azur's Manchettes - side with Sellen, where Azur was"
            ], lambda state: ( self._can_go_to(state, "Dragonbarrow") and self._can_go_to(state, "Mt. Gelmir") 
                and state.has("Sellian Sealbreaker", self.player) and self._can_go_to(state, "Raya Lucaria Academy Library") 
                and state.has("Sellen's Primal Glintstone", self.player)))
            
            # MARK: Thops
            
            self._add_location_rule([ 
                "RLA/SC: Academy Glintstone Staff - on Thops body just outside",
                "RLA/SC: Thops's Barrier - on Thops body just outside",
                "LL/(CIr): Ash of War: Thops's Barrier - scarab in church after Thops moves"
            ], lambda state: (state.has("Academy Glintstone Key (Thops)", self.player) and self._can_go_to(state, "Raya Lucaria Academy Main")))
            
            # MARK: Corhyn / Goldmask

            self._add_location_rule([ 
                "LRC|LAC/RC: Immutable Shield - Brother Corhyn shop after using Law of Regression and telling Goldmask",
                "LRC|LAC/RC: Flail - kill Brother Corhyn", # goldmask doesnt need corhyn alive
                "LRC|LAC/RC: Corhyn's Robe - kill Brother Corhyn",
                "LAC/RC: Mending Rune of Perfect Order - on Goldmask's body",
                "LAC/RC: Goldmask's Rags - on Goldmask's body",
                "LAC/RC: Gold Bracelets - on Goldmask's body",
                "LAC/RC: Gold Waistwrap - on Goldmask's body"
            ], "Law of Regression")
            
            # MARK: Enia
            
            self._add_location_rule([ "RH: Talisman Pouch - talk to Enia at 2 great runes or Twin Maiden after farum boss",
            ], lambda state: self._has_enough_great_runes(state, 2))
            
            # MARK: Yura
            
            self._add_location_rule([ 
                "AP/(SCM): Nagakiba - on Yura after RLA invasion",
                "AP/(SCM): Purifying Crystal Tear - invader drop, requires Yura death",
                "AP/(SCM): Eleonora's Poleblade - invader drop, requires Yura death"
            ], lambda state: self._can_go_to(state, "Raya Lucaria Academy"))
            
            # MARK: Latenna

            self._add_location_rule([ "LL/(SWS): Latenna the Albinauric - talk to Latenna after talking to Albus",
            ], lambda state: state.has("Haligtree Secret Medallion (Left)", self.player) or state.has("Haligtree Secret Medallion (Right)", self.player))
            # might need the right medallion, having both kills her if not talked to
            
            self._add_location_rule([ "CS/(AD): Somber Ancient Dragon Smithing Stone - summon Latenna at her sister and talk to her",
            ], lambda state: self._can_go_to(state, "Lakeside Crystal Cave") and self._can_go_to(state, "Mountaintops of the Giants")) 
            # do you need the ashes? its a prompt summon so idk
            
            # MARK: D
            
            self._add_location_rule([
                "RH: Litany of Proper Death - D shop, after talking to Gurraq",
                "RH: Order's Blade - D shop, after talking to Gurraq",
            ], lambda state: ( self._can_go_to(state, "Dragonbarrow")))
            
            # MARK: D, Twin
            # IDK IF THE WHOLE SET IS NEEDED, OR A SINGLE PIECE, just doing all to be sure
            self._add_location_rule(["DD/AR: Inseparable Sword - kill D Twin at NEC if you killed D, or at end of Fia's quest", 
            ], lambda state: (state.has("Twinned Helm", self.player) and state.has("Twinned Armor", self.player)
                and state.has("Twinned Gauntlets", self.player) and state.has("Twinned Greaves", self.player))
                and state.has("Cursemark of Death", self.player) and self._can_go_to(state, "Altus Plateau"))
            
            # MARK: Rogier
            
            self._add_location_rule(["RH: Rogier's Letter - after giving Black Knifeprint, talk to Ranni, talk to Rogier again", 
            ], lambda state: self._can_go_to(state, "Stormveil Castle") and self._can_go_to(state, "Liurnia of The Lakes")
                            and state.has("Black Knifeprint", self.player))
            
            self._add_location_rule([
                "RH: Spellblade's Pointed Hat - found on Rogier's body",
                "RH: Spellblade's Traveling Attire - found on Rogier's body",
                "RH: Spellblade's Gloves - found on Rogier's body",
                "RH: Spellblade's Trousers - found on Rogier's body",
                "RH: Rogier's Rapier - talk Rogier after beating SV mainboss or on his body after he dies"
            ], lambda state: ( self._can_go_to(state, "Stormveil Castle") and state.has("Cursemark of Death", self.player)))
            
            # MARK: Fia
            
            self._add_location_rule(["RH: Knifeprint Clue - talk to Fia multiple times", 
            ], lambda state: ( self._can_go_to(state, "Stormveil Castle")))
            
            self._add_location_rule(["RH: Sacrificial Twig - talk to Fia after giving Black Knifeprint to Rogier", 
            ], lambda state: ( state.has("Black Knifeprint", self.player) and self._can_go_to(state, "Stormveil Castle")))
            
            self._add_location_rule(["RH: Weathered Dagger - talk to Fia after reaching altus", 
            ], lambda state: self._can_go_to(state, "Altus Plateau"))
            
            self._add_location_rule([
                "RH: Twinned Helm - on D's body after giving him Weather Dagger during Fia's quest",
                "RH: Twinned Armor - on D's body after giving him Weather Dagger during Fia's quest",
                "RH: Twinned Gauntlets - on D's body after giving him Weather Dagger during Fia's quest",
                "RH: Twinned Greaves - on D's body after giving him Weather Dagger during Fia's quest"
            ], lambda state: ( state.has("Weathered Dagger", self.player) and self._can_go_to(state, "Altus Plateau")))
            
            self._add_location_rule([
                "DD/PDT: Remembrance of the Lichdragon - mainboss drop", 
                "DD/PDT: Mending Rune of the Death-Prince - on Fia after mainboss",
                "DD/PDT: Fia's Hood - kill Fia or after mainboss",
                "DD/PDT: Fia's Robe - kill Fia or after mainboss",
            ], lambda state: state.has("Cursemark of Death", self.player) and self._can_go_to(state, "Altus Plateau"))
            
            # MARK: Dung Eater
            
            self._add_location_rule(["RH: Sewer-Gaol Key - talk to Dung Eater while having a Seedbed Curse", 
            ], lambda state: ( state.has("Seedbed Curse", self.player) and self._can_go_to(state, "Altus Plateau")))
            
            self._add_location_rule([ # boggart seedbed here
                "SSG/UR: Sword of Milos - kill Dung Eater or kill him during his invasion in CO",
                "CO/AHG: Seedbed Curse - on Boggart's body after becoming Dung Eater's victim",
            ], lambda state: self._can_go_to(state, "Capital Outskirts") and state.has("Sewer-Gaol Key", self.player)
                and state.has("Seedbed Curse", self.player))
            
            self._add_location_rule([
                "SSG/UR: Mending Rune of the Fell Curse - give Dung Eater 5 seedbed curses",
                "SSG/UR: Omen Helm - kill Dung Eater or finish his quest",
                "SSG/UR: Omen Armor - kill Dung Eater or finish his quest",
                "SSG/UR: Omen Gauntlets - kill Dung Eater or finish his quest",
                "SSG/UR: Omen Greaves - kill Dung Eater or finish his quest"
            ], lambda state: self._can_go_to(state, "Capital Outskirts") and state.has("Sewer-Gaol Key", self.player)
                and state.has("Seedbed Curse", self.player, 5))
    
            # MARK: Nepheli
            
            self._add_location_rule(["RH: Arsenal Charm - talk to Nepheli before and after defeating SV mainboss"
            ], lambda state: self._can_go_to(state, "Stormveil Castle"))
            
            self._add_location_rule([
                "SV/GG: Ancient Dragon Smithing Stone - Gostoc shop after finishing Nepheli and Kenneth Haight's quests",
                "SV/GG: Ancient Dragon Smithing Stone - talk to Nepheli in SV after her and Kenneth's questlines",
                "SV/GG: Stormhawk Axe - kill Nepheli"
            ], lambda state: self._can_go_to(state, "Leyndell, Royal Capital") and state.has("The Stormhawk King", self.player))
            
            # MARK: Gideon
            
            self._add_location_rule([
                "RH: Fevor's Cookbook [3] - talk to Gideon after reaching MP",
                "RH: Law of Causality - talk to Gideon after beating MP mainboss"
            ], lambda state: self._can_go_to(state, "Mohgwyn Palace"))
            
            self._add_location_rule([
                "RH: Black Flame's Protection - talk to Gideon after reaching MH",
                "RH: Lord's Divine Fortification - talk to Gideon after beating EBH mainboss"
            ], lambda state: self._can_go_to(state, "Miquella's Haligtree"))
            
            # MARK: Gurraq
            
            self._add_location_rule([
                "DB/(BS): Clawmark Seal - Gurranq, deathroot reward 1",
                "DB/(BS): Beast Eye - Gurranq, deathroot reward 1 or kill Gurranq",
            ], "Deathroot")
            
            self._add_location_rule(["DB/(BS): Bestial Sling - Gurranq, deathroot reward 2",
            ], lambda state: ( state.has("Deathroot", self.player, 2)))
            
            self._add_location_rule(["DB/(BS): Bestial Vitality - Gurranq, deathroot reward 3",
            ], lambda state: ( state.has("Deathroot", self.player, 3)))
            
            self._add_location_rule(["DB/(BS): Ash of War: Beast's Roar - Gurranq, deathroot reward 4",
            ], lambda state: ( state.has("Deathroot", self.player, 4)))
            
            self._add_location_rule(["DB/(BS): Beast Claw (Incantation) - Gurranq, deathroot reward 5",
            ], lambda state: ( state.has("Deathroot", self.player, 5)))
            
            self._add_location_rule(["DB/(BS): Stone of Gurranq - Gurranq, deathroot reward 6",
            ], lambda state: ( state.has("Deathroot", self.player, 6)))
            
            self._add_location_rule(["DB/(BS): Beastclaw Greathammer - Gurranq, deathroot reward 7",
            ], lambda state: ( state.has("Deathroot", self.player, 7)))
            
            self._add_location_rule(["DB/(BS): Gurranq's Beast Claw - Gurranq, deathroot reward 8",
            ], lambda state: ( state.has("Deathroot", self.player, 8)))
            
            self._add_location_rule(["DB/(BS): Ancient Dragon Smithing Stone - Gurranq, deathroot reward 9 or kill Gurranq",
            ], lambda state: ( state.has("Deathroot", self.player, 9)))
            
            # MARK: Millicent / Gowry
            
            self._add_location_rule([ 
                "CL/(GS): Sellia's Secret - talk to Gowry with needle",
                "CL/(GS): Unalloyed Gold Needle (Fixed) - talk to Gowry after giving needle",
            ], "Unalloyed Gold Needle (Broken)")
            
            self._add_location_rule([
                "CL/(CP): Prosthesis-Wearer Heirloom - give Millicent fixed needle",
                "CL/(GS): Glintstone Stars - Gowry Shop",
                "CL/(GS): Night Shard - Gowry Shop",
                "CL/(GS): Night Maiden's Mist - Gowry Shop"
            ], lambda state: state.has("Unalloyed Gold Needle (Broken)", self.player) and state.has("Unalloyed Gold Needle (Fixed)", self.player))
            
            self._add_location_rule([
                "CL/(GS): Pest Threads - Gowry Shop after giving Valkyrie's Prosthesis to Millicent",
                "EBH/EIW: Rotten Winged Sword Insignia - help Millicent",
                "EBH/EIW: Unalloyed Gold Needle (Milicent) - help Millicent talk then reload area",
                "EBH/EIW: Millicent's Prosthesis - invade Millicent or kill in altus",
            ], lambda state: state.has("Valkyrie's Prosthesis", self.player) and self._can_go_to(state, "Altus Plateau")
                and state.has("Unalloyed Gold Needle (Broken)", self.player) and state.has("Unalloyed Gold Needle (Fixed)", self.player))
            
            # self._add_location_rule(["CL/(GS): Desperate Prayer - buy 4th shop item", # gesture
            # ], lambda state: ( self._can_get(state, "CL/(GS): Pest Threads - Gowry Shop after giving Valkyrie's Prosthesis to Millicent")))
            
            self._add_location_rule(["CL/(GS): Flock's Canvas Talisman - kill Gowry or complete questline",
            ], lambda state: state.has("Valkyrie's Prosthesis", self.player) and self._can_go_to(state, "Altus Plateau")
                and state.has("Unalloyed Gold Needle (Broken)", self.player) and state.has("Unalloyed Gold Needle (Fixed)", self.player)
                and self._can_go_to(state, "Elphael, Brace of the Haligtree"))

            self._add_location_rule([
                "EBH/HR: Miquella's Needle - use needle on flower in boss arena after Millicent quest",
                "EBH/HR: Somber Ancient Dragon Smithing Stone - use needle on flower in boss arena after Millicent quest",
            ], lambda state: state.has("Valkyrie's Prosthesis", self.player) and self._can_go_to(state, "Altus Plateau")
                and state.has("Unalloyed Gold Needle (Broken)", self.player) and state.has("Unalloyed Gold Needle (Fixed)", self.player) and state.has("Unalloyed Gold Needle (Milicent)", self.player))
            
            # MARK: Ranni
            
            self._add_location_rule([
                "LG/(CE): Spirit Calling Bell - talk to Ranni",
                "LG/(CE): Lone Wolf Ashes - talk to Ranni",
            ], lambda state: ( self._can_go_to(state, "Liurnia of The Lakes")))
            # you can get in LL if missed i think
            
            self._add_location_rule([
                "NR/(NSG): Fingerslayer Blade - in chest lower area, talk to Ranni in LL",
                "NR/(NSG): Great Ghost Glovewort - in chest lower area, talk to Ranni in LL"
            ], lambda state: ( self._can_go_to(state, "Liurnia of The Lakes")))
            
            self._add_location_rule([
                "LL/(ReR): Snow Witch Hat - in chest, after giving Fingerslayer Blade to Ranni",
                "LL/(ReR): Snow Witch Robe - in chest, after giving Fingerslayer Blade to Ranni",
                "LL/(ReR): Snow Witch Skirt - in chest, after giving Fingerslayer Blade to Ranni",
                "LL/(RaR): Carian Inverted Statue - given by Ranni after giving Fingerslayer Blade",
                "ARM/ARM: Miniature Ranni - to N after giving Ranni Fingerslayer Blade"
            ], "Fingerslayer Blade")
            
            self._add_location_rule(["NS/NWB: Discarded Palace Key - invader drop to SE, need Miniature Ranni"
            ], lambda state: state.has("Miniature Ranni", self.player) and state.has("Fingerslayer Blade", self.player))
            
            self._add_location_rule(["RLA/RLGL: Dark Moon Ring - in chest, requires Discarded Palace Key",
            ], "Discarded Palace Key")
            
            # MARK: Seluvis
            
            self._add_location_rule(["LL/(SR): Seluvis's Introduction - talk to Seluvis after talking to Blaidd in SR", 
            ], lambda state: self._can_go_to(state, "Siofra River"))
            
            self._add_location_rule([
                "LL/(SR): Nepheli Loux Puppet - on Seluvis's body", 
                "LL/(SR): Dolores the Sleeping Arrow Puppet - Seluvis shop, after you give potion to Nepheli"
            ], lambda state: state.has("Seluvis's Potion", self.player) and self._can_go_to(state, "Stormveil Castle"))
            
            self._add_location_rule(["LL/(SR): Dung Eater Puppet - Seluvis shop, after you give potion to Dung Eater", 
            ], lambda state: state.has("Seluvis's Potion", self.player) and self._can_go_to(state, "Capital Outskirts") 
                and state.has("Sewer-Gaol Key", self.player) and state.has("Seedbed Curse", self.player))
            
            self._add_location_rule([
                "LL/(SR): Carian Phalanx - Seluvis shop after potion used",
                "LL/(SR): Glintstone Icecrag - Seluvis shop after potion used",
                "LL/(SR): Freezing Mist - Seluvis shop after potion used",
                "LL/(SR): Carian Retaliation - Seluvis shop after potion used"
            ], "Seluvis's Potion")
            
            # this breaks?
            self._add_location_rule([
                "LL/(SR): Jarwight Puppet - Seluvis shop after finding puppet room",
                "LL/(SR): Finger Maiden Therolina Puppet - Seluvis shop after finding puppet room"
            ], lambda state: state.has("Starlight Shards", self.player, 3)
                and state.has("Seluvis's Potion", self.player))
            
            self._add_location_rule([
                "LL/(SR): Magic Scorpion Charm - given by Seluvis after giving Amber Starlight",
                "LL/(SR): Amber Draught - given by Seluvis after giving Amber Starlight"
            ], lambda state: state.has("Amber Starlight", self.player) and state.has("Starlight Shards", self.player, 3)
                and state.has("Seluvis's Potion", self.player))
            
            # Pidia
            
            self._add_location_rule(["LL/(CM): Dolores the Sleeping Arrow Puppet - dropped by Pidia after Seluvis dies"
            ], lambda state: state.has("Fingerslayer Blade", self.player) and self._can_go_to(state, "Ainsel River Main")
                or state.has("Amber Draught", self.player))
            
            # MARK: Blaidd / Iji
            
            self._add_location_rule([
                "LL/RaR: Royal Greatsword - kill angry Blaidd",
                "LL/RaR: Blaidd's Armor - kill angry Blaidd",
                "LL/RaR: Blaidd's Gauntlets - kill angry Blaidd",
                "LL/RaR: Blaidd's Greaves - kill angry Blaidd",
                "LL/RM: Iji's Mirrorhelm - kill Iji or after quest"
            ], lambda state: self._can_go_to(state, "Moonlight Altar"))
            
            # MARK: Alexander
            
            self._add_location_rule([
                "LL/JB: Exalted Flesh x3 - given by Alexander after getting him unstuck with oil pots, just above JB",
                "MtG/FL: Jar - talk to Alexander S of FL",
            ], lambda state: self._can_go_to(state, "Wailing Dunes"))
            
            self._add_location_rule([ # also requires fire giant dead
                "FA/DTL: Shard of Alexander - fight Alexander to SW",
                "FA/DTL: Alexander's Innards - fight Alexander to SW"
            ], lambda state: self._can_go_to(state, "Mt. Gelmir") and self._can_go_to(state, "Wailing Dunes"))
            
            # MARK: Jar-bairn
            
            self._add_location_rule([
                "LL/JB: Companion Jar - give Alexander's Innards, left after Jar Bairn leaves"
            ], lambda state: self._can_go_to(state, "Mt. Gelmir") and self._can_go_to(state, "Wailing Dunes")
                and self._can_go_to(state, "Farum Azula") and state.has("Alexander's Innards", self.player))
            
            # MARK: Diallos
            
            self._add_location_rule([ # need to talk to in LL and VM stuff
                "LL/JB: Hoslow's Petal Whip - on Diallos's body",
                "LL/JB: Diallos's Mask - on Diallos's body",
                "LL/JB: Numen's Rune - on Diallos's body"
            ], lambda state: self._can_go_to(state, "Volcano Manor Upper") and self._can_go_to(state, "Wailing Dunes"))
            
            # MARK: VOLCANO QUESTS
            
            # do you need the letters? 1 2 and red
            
            self._add_location_rule([ # request 1
                "LG/LC: Scaled Helm - invade Istvan SE of colo", # request 1
                "LG/LC: Scaled Armor - invade Istvan SE of colo",
                "LG/LC: Scaled Gauntlets - invade Istvan SE of colo",
                "LG/LC: Scaled Greaves - invade Istvan SE of colo",
                
                "VM/VM: Magma Shot - Tanith reward request 1", # reward 1
                "VM/VM: Letter from Volcano Manor (Rileigh) - on the table in the drawing room after request 1",
                "VM/VM: Letter to Patches - talk to Patches after request 1",
                "VM/VM: Ash of War: Eruption - Bernahl shop after request 1",
                "VM/VM: Ash of War: Assassin's Gambit - Bernahl shop after request 1",
                
                "AP/OAT: Black-Key Bolt x20 - invade Rileigh", # request 2
                "AP/OAT: Crepus's Vial - invade Rileigh",
                
                "RSP/RSPO: Bull-Goat Helm - invade Tragoth", # patches request 1
                "RSP/RSPO: Bull-Goat Armor - invade Tragoth",
                "RSP/RSPO: Bull-Goat Gauntlets - invade Tragoth",
                "RSP/RSPO: Bull-Goat Greaves - invade Tragoth",
                "VM/VM: Magma Whip Candlestick - Patches reward"
            ], lambda state: self._can_go_to(state, "Volcano Manor Drawing Room"))
            
            self._add_location_rule([ # reward 2 + bernahl
                "VM/VM: Serpentbone Blade - Tanith reward request 2", # reward 2
                "VM/VM: Letter to Bernahl - Bernahl after request 2",
                "VM/VM: Red Letter - on the table in the drawing room after request 2",
                
                "LRC/FMFF: Raging Wolf Helm - invade Vargram", # bernahl
                "LRC/FMFF: Raging Wolf Armor - invade Vargram",
                "LRC/FMFF: Raging Wolf Gauntlets - invade Vargram",
                "LRC/FMFF: Raging Wolf Greaves - invade Vargram",
                "VM/VM: Gelmir's Fury - Bernahl reward",
                
                "MotG/SL: Hoslow's Petal Whip - invade Juno Hoslow", # request 3
                "MotG/SL: Hoslow's Helm - invade Juno Hoslow",
                "MotG/SL: Hoslow's Armor - invade Juno Hoslow",
                "MotG/SL: Hoslow's Gauntlets - invade Juno Hoslow",
                "MotG/SL: Hoslow's Greaves - invade Juno Hoslow"
            ], lambda state: self._can_go_to(state, "Volcano Manor Drawing Room") and self._can_go_to(state, "Altus Plateau"))
            
            self._add_location_rule([ # reward 3
                "VM/VM: Taker's Cameo - Tanith reward request 3"
            ], lambda state: self._can_go_to(state, "Volcano Manor Drawing Room") and self._can_go_to(state, "Mountaintops of the Giants"))
        
            # MARK: Bernahl
            
            self._add_location_rule([
                "LG/(WS): Beast Champion Helm - kill Bernahl",
                "LG/(WS): Beast Champion Gauntlets - kill Bernahl",
                "LG/(WS): Beast Champion Greaves - kill Bernahl",
                "LG/(WS): Beast Champion Armor (Altered) - kill Bernahl"
            ], lambda state: self._can_go_to(state, "Farum Azula"))
            
            # MARK: Rya 
                
            self._add_location_rule(["LL/SeI: Volcano Manor Invitation - give Rya her necklace, you will need to buy the item from Boggart or reach altus", 
            ], lambda state: ( self._can_go_to(state, "Altus Plateau") or state.has("Rya's Necklace", self.player)))
    
            self._add_location_rule([
                "VM/VM: Zorayas's Letter - end of Rya's quest, dont kill or give potion", 
                "VM/VM: Daedicar's Woe - end of Rya's quest, any option"
            ], lambda state: state.has("Serpent's Amnion", self.player) and self._can_go_to(state, "Volcano Manor Drawing Room")
                and self._can_go_to(state, "Volcano Manor Upper"))
            
            # MARK: Patches 
            
            self._add_location_rule([ # patches request
            ], lambda state: self._can_go_to(state, "Volcano Manor Drawing Room"))
            
            self._add_location_rule(["TSC/CI: Dancer's Castanets - given by Patches just outside boss arena",
            ], lambda state: self._can_go_to(state, "Volcano Manor Upper")
                and self._can_go_to(state, "Volcano Manor Drawing Room"))
            
            self._add_location_rule([
                "LG/(MCV): Glass Shard x3 - Patches chest, after you've given the Dancer's Castanets to Tanith",
                "LG/(MCV): Spear - kill Patches",
                "LG/(MCV): Leather Armor - kill Patches",
                "LG/(MCV): Leather Gloves - kill Patches",
                "LG/(MCV): Leather Boots - kill Patches"
            ], lambda state: self._can_go_to(state, "Volcano Manor Upper") and state.has("Dancer's Castanets", self.player))
            
            # MARK: Tanith
            
            self._add_location_rule([ # or after rykard is dead
                "VM/VM: Tonic of Forgetfulness - given by Tanith after you give Rya Serpent's Amnion",
            ], lambda state: state.has("Serpent's Amnion", self.player) and self._can_go_to(state, "Volcano Manor Drawing Room"))
    
            self._add_location_rule([
                "VM/RLB: Consort's Mask - kill Tanith",
                "VM/RLB: Consort's Robe - kill Tanith",
                "VM/RLB: Consort's Trousers - kill Tanith",
                "VM/RLB: Aspects of the Crucible: Breath - enemy drop, spawns after Tanith's death"
            ], lambda state: self._can_go_to(state, "Volcano Manor Upper") and state.has("Dancer's Castanets", self.player))
            
        if self.options.enable_dlc:
            # MARK: DLC NPC
            
            # MARK: Grandam
            
            self._add_location_rule([
                "BTS/SPA: Watchful Spirit - given by Hornsent Grandam while wearing the Divine Beast Head",
                "BTS/SPA: Scorpion Stew - given by Hornsent Grandam while wearing the Divine Beast Head a second time after reloading"
            ], lambda state: state.has("Storeroom Key", self.player) and state.has("Divine Beast Head", self.player))
            
            self._add_location_rule([
                "BTS/SPA: Gourmet Scorpion Stew - given by Hornsent Grandam after defeating SK mainboss",
                "BTS/SPA: Gourmet Scorpion Stew - on Hornsent Grandam after defeating SK mainboss, exhausting her dialogue, and reloading"
            ], lambda state: state.has("Storeroom Key", self.player) and state.has("Divine Beast Head", self.player) 
                and self._can_go_to(state, "Shadow Keep"))
            
            # MARK: Florissax
            
            self._add_location_rule([
                "JP/GADC: Ancient Dragon Florissax - admit to putting Florissax to sleep with Thiollier's Concoction",
                "JP/GADC: Dragonbolt of Florissax - given by Florissax if you gave her Thiollier's Concoction before JP mainboss"
                ], "Thiollier's Concoction")
            
            # MARK: Igon
            
            self._add_location_rule([
                "JP/FJP: Igon's Greatbow - to E on Igon's corpse after JP mainboss",
                "JP/FJP: Igon's Helm - to E on Igon's corpse after JP mainboss",
                "JP/FJP: Igon's Armor - to E on Igon's corpse after JP mainboss",
                "JP/FJP: Igon's Gauntlets - to E on Igon's corpse after JP mainboss",
                "JP/FJP: Igon's Loincloth - to E on Igon's corpse after JP mainboss"
            ], "Igon's Furled Finger")
            
            # MARK: Queelign
            
            # his drops will always be one then the second no matter the region order, so require both
            self._add_location_rule([
                "SA/(CC): Prayer Room Key - invader drop",
                "SA/(CC): Ash of War: Flame Skewer - invader drop",
                "BTS/SPA: Crusade Insignia - invader drop in NE courtyard"
            ], lambda state: self._can_go_to(state, "Scadu Altus") and self._can_go_to(state, "Belurat"))
            
            self._add_location_rule(["SK/CDE: Fire Knight Queelign - on Queelign, give Iris of Grace, in room with door"
            ], lambda state: self._can_go_to(state, "Scadu Altus") and self._can_go_to(state, "Belurat")
                and state.has("Prayer Room Key", self.player) and state.has("Iris of Grace", self.player))
            
            self._add_location_rule(["SK/CDE: Queelign's Greatsword - on Queelign, give Iris of Occultation, in room with door"
            ], lambda state: self._can_go_to(state, "Scadu Altus") and self._can_go_to(state, "Belurat")
                and state.has("Prayer Room Key", self.player) and state.has("Iris of Occultation", self.player))
            
            # MARK: Leda
            
            self._add_location_rule([
                "SA/HC: Lacerating Crossed-Tree - given by Leda after invading Hornsent alongside her",
                "SA/HC: Retaliatory Crossed-Tree - given by Leda after invading Ansbach alongside her"
                ], lambda state: self._can_go_to(state, "Shadow Keep"))
            
            # MARK: Freyja
            
            self._add_location_rule("SK/SSF: Golden Lion Shield - given by Freyja after giving her Letter for Freyja", "Letter for Freyja")
            
            # MARK: Ansbach
            
            self._add_location_rule("SK/SFiF: Letter for Freyja - given by Ansbach after giving Secret Rite Scroll", "Secret Rite Scroll")
            
            # MARK: Thiollier
            
            self._add_location_rule("GP/PPC: Thiollier's Concoction - talk to Thiollier after giving him Black Syrup", "Black Syrup")
            
            self._add_location_rule([
                "EI/GD: Thiollier's Hidden Needle - on Thiollier's body to NW",
                "EI/GD: Thiollier's Mask - on Thiollier's body to NW",
                "EI/GD: Thiollier's Garb - on Thiollier's body to NW",
                "EI/GD: Thiollier's Gloves - on Thiollier's body to NW",
                "EI/GD: Thiollier's Trousers - on Thiollier's body to NW"
                ], lambda state: self._can_go_to(state, "Stone Coffin Fissure"))
            
            self._add_location_rule("SCF/GDP: St. Trina's Blossom - on St. Trina's body after EI mainboss",
                lambda state: self._can_go_to(state, "Enir Ilim"))
            
            # MARK: Moore
            
            self._add_location_rule([ # tell him to be sad, body in SA by CC
                "GP/MGC: Verdigris Greatshield - on Moore's body",
                "GP/MGC: Verdigris Helm - on Moore's body",
                "GP/MGC: Verdigris Armor - on Moore's body",
                "GP/MGC: Verdigris Gauntlets - on Moore's body",
                "GP/MGC: Verdigris Greaves - on Moore's body"
                ], lambda state: self._can_go_to(state, "Scadu Altus"))
            
            # friendly Kindred of Rot locations
            # "GP/PT: Forager Brood Cookbook [2] - given by friendly Kindred of Rot E of PT"
            # "GP/PT: Black Pyrefly x3 - given by friendly Kindred of Rot E of PT"
            
            # "ER/ERD: Forager Brood Cookbook [3] - given by friendly Kindred of Rot to SE, NE corner of cliffs"
            # "ER/ERD: Yellow Fulgurbloom x3 - given by friendly Kindred of Rot to SE, NE corner of cliffs"

            # self._add_location_rule([
            #     "SA/CC: Forager Brood Cookbook [4] - N of CC, given by friendly Kindred of Rot after you heal it",
            #     "SA/CC: Shadow Sunflower x3 - N of CC, given by friendly Kindred of Rot after you heal it"
            #     ], lambda state: state.has("Crafting Kit", self.player) 
            #         and (state.has("Nomadic Warrior's Cookbook [19]", self.player) or state.has("Battlefield Priest's Cookbook [4]", self.player)))
            
            # "SA/RFSP: Forager Brood Cookbook [1] - given by friendly Kindred of Rot NW of RFSP"
            # "SA/RFSP: Glintslab Firefly x3 - given by friendly Kindred of Rot NW of RFSP"
            
            # "SA/MR: Forager Brood Cookbook [5] - given by friendly Kindred of Rot, to NE, through cave, on NE ledge"
            # "SA/MR: Pearlescent Scale - given by friendly Kindred of Rot, to NE, through cave, on NE ledge"
            
            # "SA/CDH: Forager Brood Cookbook [6] - given by friendly Kindred of Rot to NW above entrance to SKCD, in W corner"
            # "SA/CDH: Dewgem x3 - given by friendly Kindred of Rot to NW above entrance to SKCD, in W corner"
            
            # MARK: Hornsent
            
            self._add_location_rule("GP/TPC: Furnace Visage x3 - given by Hornsent after giving Scorpion Stew", "Scorpion Stew")
            
            # MARK: Dane
            
            # Add back after making proper location for May the Best Win in static randomizer
            # self._add_location_rule([
            #     "SA/MR: Dane's Hat - challenge Dane with May the Best Win",
            #     "SA/MR: Dryleaf Arts - challenge Dane with May the Best Win"
            # ], "May the Best Win")
            
            # MARK: Ymir
            
            self._add_location_rule("FRR: Crimson Seed Talisman +1 - use Hole-Laden Necklace at the hanging bell in the center", "Hole-Laden Necklace")
            
            self._add_location_rule([
                "SA/(CMM): Glintstone Nail - Ymir shop after ringing one of the hanging bells",
                "SA/(CMM): Glintstone Nails - Ymir shop after ringing one of the hanging bells",
                "SA/(CMM): Beloved Stardust - given by Ymir after ringing the hanging bell in FRR",
                "SA/(CMM): Ruins Map (2nd) - given by Ymir after ringing the hanging bell in FRR",
                "FRD: Cerulean Seed Talisman +1 - use Hole-Laden Necklace at the hanging bell in the center"
            ], lambda state: self._can_go_to(state, "Finger Ruins of Rhia") and state.has("Hole-Laden Necklace", self.player))
            
            self._add_location_rule([
                "SA/(CMM): Fleeting Microcosm - Ymir shop after ringing both hanging bells",
                "SA/(CMM): Ruins Map (3rd) - given by Ymir after ringing both hanging bells"
            ], lambda state: self._can_go_to(state, "Finger Ruins of Dheo") and self._can_go_to(state, "Finger Ruins of Rhia")
                and state.has("Hole-Laden Necklace", self.player))
            
            self._add_location_rule([
                "SA/CMM: Cherishing Fingers - in graveyard W of CMM after Ymir dead"
            ], lambda state: self._can_go_to(state, "Finger Ruins of Miyr"))
            
            # MARK: Jolán
            
            self._add_location_rule([
                "SA/(CMM): Swordhand of Night Jolán - on Jolán after killing Ymir, give Iris of Grace"                
            ], lambda state: state.has("Iris of Grace", self.player) and self._can_go_to(state, "Finger Ruins of Miyr"))
            
            self._add_location_rule([
                "SA/(CMM): Sword of Night - on Jolán after killing Ymir, give Iris of Occultation"
            ], lambda state: state.has("Iris of Occultation", self.player) and self._can_go_to(state, "Finger Ruins of Miyr"))
            
    def _add_remembrance_rules(self) -> None:
        """Adds rules for items obtainable for trading remembrances."""

        remembrances = [
            (
                "Remembrance of the Grafted",
                ["Axe of Godrick", "Grafted Dragon"]
            ),
            (
                "Remembrance of the Full Moon Queen",
                ["Carian Regal Scepter", "Rennala's Full Moon"]
            ),
            (
                "Remembrance of the Starscourge",
                ["Starscourge Greatsword", "Lion Greatbow"]
            ),
            (
                "Remembrance of the Regal Ancestor",
                ["Winged Greathorn", "Ancestral Spirit's Horn"]
            ),
            (
                "Remembrance of the Omen King",
                ["Morgott's Cursed Sword", "Regal Omen Bairn"]
            ),
            (
                "Remembrance of the Naturalborn",
                ["Ash of War: Waves of Darkness", "Bastard's Stars"]
            ),
            (
                "Remembrance of the Blasphemous",
                ["Rykard's Rancor", "Blasphemous Blade"]
            ),
            (
                "Remembrance of the Lichdragon",
                ["Fortissax's Lightning Spear", "Death Lightning"]
            ),
            (
                "Remembrance of the Fire Giant",
                ["Giant's Red Braid", "Burn, O Flame!"]
            ),
            (
                "Remembrance of the Blood Lord",
                ["Mohgwyn's Sacred Spear", "Bloodboon"]
            ),
            (
                "Remembrance of the Black Blade",
                ["Maliketh's Black Blade", "Black Blade"]
            ),
            (
                "Remembrance of the Dragonlord",
                ["Dragon King's Cragblade", "Placidusax's Ruin"]
            ),
            (
                "Remembrance of Hoarah Loux",
                ["Axe of Godfrey", "Ash of War: Hoarah Loux's Earthshaker"]
            ),
            (
                "Remembrance of the Rot Goddess",
                ["Hand of Malenia", "Scarlet Aeonia"]
            ),
            (
                "Elden Remembrance",
                ["Marika's Hammer", "Sacred Relic Sword"]
            ),
        ]

        dlc_remembrances = [
            (
                "Remembrance of the Dancing Lion",
                ["Enraged Divine Beast", "Ash of War: Divine Beast Frost Stomp"]
            ),
            (
                "Remembrance of the Twin Moon Knight",
                ["Rellana's Twin Blades", "Rellana's Twin Moons"]
            ),
            (
                "Remembrance of Putrescence",
                ["Putrescence Cleaver", "Vortex of Putrescence"]
            ),
            (
                "Remembrance of the Wild Boar Rider",
                ["Sword Lance", "Blades of Stone"]
            ),
            (
                "Remembrance of the Shadow Sunflower",
                ["Shadow Sunflower Blossom", "Land of Shadow"]
            ),
            (
                "Remembrance of the Impaler",
                ["Spear of the Impaler", "Messmer's Orb"]
            ),
            (
                "Remembrance of the Saint of the Bud",
                ["Poleblade of the Bud", "Rotten Butterflies"]
            ),
            (
                "Remembrance of the Mother of Fingers",
                ["Staff of the Great Beyond", "Gazing Finger"]
            ),
            (
                "Remembrance of the Lord of Frenzied Flame",
                ["Greatsword of Damnation", "Midra's Flame of Frenzy"]
            ),
            (
                "Remembrance of a God and a Lord",
                ["Greatsword of Radahn (Lord)", "Greatsword of Radahn (Light)", "Light of Miquella"]
            ),
        ]
            
        if self.options.enable_dlc:
            remembrances += dlc_remembrances
            self._add_location_rule("JP/GADC: Bayle's Flame Lightning - Dragon Communion, Heart of Bayle",
                lambda state: (state.has("Heart of Bayle", self.player) and self._can_go_to(state, "Jagged Peak Foot")))
            self._add_location_rule("JP/GADC: Bayle's Tyranny - Dragon Communion, Heart of Bayle", 
                lambda state: (state.has("Heart of Bayle", self.player) and self._can_go_to(state, "Jagged Peak Foot")))
        
        if self.base_enabled:
            for (remembrance, rem_items) in remembrances:
                self._add_location_rule([
                    f"RH: {item} - Enia for {remembrance}" for item in rem_items
                ], lambda state, item=remembrance: (state.has(item, self.player) and self._has_enough_great_runes(state, 1)))
        else:
            for (remembrance, rem_items) in dlc_remembrances:
                self._add_location_rule([
                    f"RH/DLC: {item} - Enia for {remembrance}" for item in rem_items
                ], lambda state, item=remembrance: (state.has(item, self.player)))
    
    def _add_equipment_of_champions_rules(self) -> None:
        """Adds rules for items obtainable from equipment of champions."""

        equipments = [ # done
            ( # RA mainboss
                "RLA/DB mainboss", #"Rennala, Queen of the Full Moon", # boss
                "RLA/DB: Remembrance of the Full Moon Queen - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Queen's Crescent Crown", 
                    "Queen's Robe",
                    "Queen's Leggings", 
                    "Queen's Bracelets"
                ]
            ),
            ( # MH mainboss
                "EBH/HR mainboss", #"Malenia Blade of Miquella", # boss
                "EBH/HR: Remembrance of the Rot Goddess - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Malenia's Winged Helm", 
                    "Malenia's Armor",
                    "Malenia's Gauntlet", 
                    "Malenia's Greaves"
                ]
            ),
            ( # LAC mainboss
                "LAC/QB mainboss", #"Godfrey, First Elden Lord", # boss
                "LAC/QB: Remembrance of Hoarah Loux - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Elden Lord Crown", 
                    "Elden Lord Armor",
                    "Elden Lord Bracers", 
                    "Elden Lord Greaves"
                ]
            ),
            ( # TSC boss
                "TSC/SCIG boss", #"Elemer of the Briar", # boss
                "TSC/SCIG: Briar Greatshield - boss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Briar Helm", 
                    "Briar Armor",
                    "Briar Gauntlets", 
                    "Briar Greaves"
                ]
            ),
            ( # MH boss
                "MH/HTP boss", #"Loretta, Knight of the Haligtree", # boss
                "MH/HTP: Loretta's Mastery - boss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Royal Knight Helm", 
                    "Royal Knight Armor",
                    "Royal Knight Gauntlets", 
                    "Royal Knight Greaves"
                ]
            ),
            ( # FA mainboss
                "FA/BGB mainboss", #"Maliketh, the Black Blade", # boss
                "FA/BGB: Remembrance of the Black Blade - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Maliketh's Helm", 
                    "Maliketh's Armor",
                    "Maliketh's Gauntlets", 
                    "Maliketh's Greaves"
                ]
            ),
            ( # MotG/(CS) mainboss
                "MotG/(CS) mainboss", #"Commander Niall", # boss
                "MotG/(CS): Veteran's Prosthesis - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Veteran's Helm", 
                    "Veteran's Armor",
                    "Veteran's Gauntlets", 
                    "Veteran's Greaves"
                ]
            ),
            ( # WD mainboss
                "CL/(WD) mainboss", #"Starscourge Radahn", # boss
                "CL/(WD): Remembrance of the Starscourge - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Radahn's Redmane Helm", 
                    "Radahn's Lion Armor",
                    "Radahn's Gauntlets", 
                    "Radahn's Greaves"
                ]
            ),
            ( # LRC mainboss
                "LRC/QB mainboss", #"Morgott, The Omen King", # boss
                "LRC/QB: Remembrance of the Omen King - mainboss drop", # a drop from boss, so we can do 'can get' check
                ["Fell Omen Cloak"]# item
            ),
            ( # MP mainboss
                "MP/(MDM) mainboss", # "Mohg, Lord of Blood", # boss
                "MP/(MDM): Remembrance of the Blood Lord - mainboss drop", # a drop from boss, so we can do 'can get' check
                ["Lord of Blood's Robe"]# item
            ),
        ]

        dlc_equipments = [ # done
            (
                "SK/DCE mainboss", #"Messmer the Impaler", # boss
                "SK/DCE: Remembrance of the Impaler - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Messmer's Helm", 
                    "Messmer's Armor",
                    "Messmer's Gauntlets", 
                    "Messmer's Greaves"
                ]
            ),
            (
                "CE/CLC mainboss", #"Rellana, Twin Moon Knight", # boss
                "CE/CLC: Remembrance of the Twin Moon Knight - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Rellana's Helm", 
                    "Rellana's Armor",
                    "Rellana's Gloves", 
                    "Rellana's Greaves"
                ]
            ),
            (
                "ScV/SKBG mainboss", #"Commander Gaius", # boss
                "ScV/SKBG: Remembrance of the Wild Boar Rider - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Gaius's Helm", 
                    "Gaius's Armor",
                    "Gaius's Gauntlets"
                ]
            ),
            ( # you cant even get this till the game is beat LMAO, but you can get it in all bosses :)
                "EI/DGFS mainboss", #"Promised Consort Radahn", # boss
                "EI/DGFS: Remembrance of a God and a Lord - mainboss drop", # a drop from boss, so we can do 'can get' check
                [   # items
                    "Young Lion's Helm", 
                    "Young Lion's Armor",
                    "Young Lion's Gauntlets", 
                    "Young Lion's Greaves"
                ]
            ),
        ]
            
        if self.options.enable_dlc: equipments += dlc_equipments

        if self.base_enabled:
            for (boss, boss_location, eq_items) in equipments:
                self._add_location_rule([
                    f"RH: {item} - Enia shop, defeat {boss}" for item in eq_items
                ], lambda state, bl=boss_location: (self._can_get(state, bl) and self._has_enough_great_runes(state, 1)))
        else:
            for (boss, boss_location, eq_items) in dlc_equipments:
                self._add_location_rule([
                    f"RH/DLC: {item} - Enia shop, defeat {boss}" for item in eq_items
                ], lambda state, bl=boss_location: (self._can_get(state, bl)))
            
    def _add_allow_useful_location_rules(self) -> None:
        """Adds rules for locations that can contain useful but not necessary items.

        If we allow useful items in the excluded locations, we don't want Archipelago's fill
        algorithm to consider them excluded because it never allows useful items there. Instead, we
        manually add item rules to exclude important items.
        """

        all_locations = self._get_our_locations()

        allow_useful_locations = (
            (
                {
                    location.name
                    for location in all_locations
                    if location.name in self.all_excluded_locations
                    and not location.data.is_missable(self.options)
                }
                if self.options.excluded_location_behavior < self.options.missable_location_behavior
                else self.all_excluded_locations
            )
            if self.options.excluded_location_behavior == "allow_useful"
            else set()
        ).union(
            {
                location.name
                for location in all_locations
                if location.data.is_missable(self.options)
                and not (
                    location.name in self.all_excluded_locations
                    and self.options.missable_location_behavior <
                        self.options.excluded_location_behavior
                )
            }
            if self.options.missable_location_behavior == "allow_useful"
            else set()
        )
        for location in allow_useful_locations:
            self._add_item_rule(
                location,
                lambda item: not item.advancement
            )

        # Prevent the player from prioritizing and "excluding" the same location
        self.options.priority_locations.value -= allow_useful_locations

        if self.options.excluded_location_behavior == "allow_useful":
            self.options.exclude_locations.value.clear()
   
    def _add_location_rule(
        self,
        location: Union[str, List[str]],
        rule: Union[CollectionRule, str],
    ) -> None:        
        """Sets a rule for the given location if it that location is randomized.

        The rule can just be a single item/event name as well as an explicit rule lambda.
        """
        if isinstance(rule, str):
            assert item_table[rule].is_important(self.options) in (
                ItemClassification.progression, ItemClassification.progression_deprioritized)
            rule = lambda state, item=rule: state.has(item, self.player)
        
        locations = location if isinstance(location, list) else [location]
        for location in locations:
            if self._location_status(location).is_absent: continue
            add_rule(self.multiworld.get_location(location, self.player), rule)
    
    def _add_entrance_rule(
        self,
        region: str,
        rule: Union[CollectionRule, str],
        from_region: Optional[str] = None
    ) -> None:        
        """Sets a rule for the entrance to the given region."""
        assert region in location_tables
        if region not in self.created_regions: return
        if isinstance(rule, str):
            if " -> " not in rule:
                assert item_table[rule].is_important(self.options) in (
                    ItemClassification.progression, ItemClassification.progression_deprioritized)
            rule = lambda state, item=rule: state.has(item, self.player)
        entrance = (f"{from_region} => {region}" if from_region else "Go To " + region)
        add_rule(self.multiworld.get_entrance(entrance, self.player), rule)

    def _add_item_rule(self, location: str, rule: ItemRule) -> None:
        """Sets a rule for what items are allowed in a given location."""
        if not self._location_status(location).is_randomized: return
        add_item_rule(self.multiworld.get_location(location, self.player), rule)

    def _can_go_to(self, state: CollectionState, region) -> bool:
        """Returns whether state can access the given region name."""
        return state.can_reach_entrance(f"Go To {region}", self.player)

    def _can_get(self, state: CollectionState, location) -> bool:
        """Returns whether state can access the given location name."""
        return state.can_reach_location(location, self.player)
    
    def _goal_bosses(self) -> list[ERBossInfo]:
        """Returns all the bosses that are goals for this run."""
        result = []
        for name in self.options.goal:
            assert name.endswith(" Boss")
            goal_type = name[:-len(" Boss")]
            boss = [boss for boss in all_bosses if goal_type in boss.type and boss.flag != None and not boss.missable]
            assert boss
            # no dupe bosses
            [result.append(b) for b in boss if b not in result]
        return result
    
    def _is_complete(self, state: CollectionState) -> bool:
        """Whether the given state has achieved the victory condition."""
        return all(self._can_get(state, next(iter(boss.locations))) for boss in self.goal_bosses if len(boss.locations) != 0) # ignore bosses with no locations
    
    def write_spoiler(self, spoiler_handle: TextIO) -> None:
        text = ""
        
        if self.serpent_location and self.serpent_location != default_serpent_location:
            text += f"\nSerpent takes the place of {self.serpent_location.name} in {self.player_name}'s world\n"
        
        if self.rykard_location and self.rykard_location != default_rykard_location:
            text += f"\nRykard takes the place of {self.rykard_location.name} in {self.player_name}'s world\n"

        if self.options.excluded_location_behavior == "forbid_useful":
            text += f"\n{self.player_name}'s world excluded: {sorted(self.all_excluded_locations)}\n"

        if text:
            text = "\n" + text + "\n"
            spoiler_handle.write(text)

    def _location_status(
        self,
        location: Union[str, ERLocationData, ERLocation],
    ) -> _LocationStatus:
        """Returns the status of the given location given the player's options."""
        if isinstance(location, ERLocationData):
            data = location
        elif isinstance(location, ERLocation):
            data = location.data
        else:
            if location in location_dictionary: data = location_dictionary[location]
            else: data = self.dupe_location_dictionary[location]

        if data.should_omit(self.options): return _LocationStatus.ABSENT
        if data.is_event: return _LocationStatus.UNRANDOMIZED_UNMISSABLE

        missable = data.is_missable(self.options)
        if data.should_randomize(self.options):
            return (
                _LocationStatus.RANDOMIZED_MISSABLE if missable
                else _LocationStatus.RANDOMIZED_UNMISSABLE
            )
        else:
            return (
                _LocationStatus.UNRANDOMIZED_MISSABLE if missable
                else _LocationStatus.UNRANDOMIZED_UNMISSABLE
            )

    @classmethod
    def stage_post_fill(cls, multiworld: MultiWorld):
        """If item smoothing is enabled, rearrange items so they scale up smoothly through the run.

        This determines the approximate order a given silo of items (say, soul items) show up in the
        main game, then rearranges their shuffled placements to match that order. It determines what
        should come "earlier" or "later" based on sphere order: earlier spheres get lower-level
        items, later spheres get higher-level ones. Within a sphere, items in ER are distributed in
        region order, and then the best items in a sphere go into the multiworld.
        """
        er_worlds = [world for world in cast(List[EldenRing], multiworld.get_game_worlds(cls.game)) if
                      world.options.smooth_upgrade_items
                      or world.options.smooth_rune_items]
        if not er_worlds:
            # No worlds need item smoothing.
            return

        er_player_to_world = {world.player: world for world in er_worlds}
        er_smoothing_location_to_sphere: dict[Location, int] = {}
        er_player_full_items_by_name = {world.player: defaultdict(list) for world in er_worlds}
        for sphere_number, sphere in enumerate(multiworld.get_spheres(), start=1):
            # Sort for deterministic results in `er_player_full_items_by_name`.
            for location in sorted(sphere):
                if location.locked:
                    # Locked locations should not have their items moved.
                    continue
                item = location.item
                if item.player not in er_player_to_world:
                    # The item does not belong to a ER player with smoothing enabled, so can be ignored.
                    continue
                if item.code is None:
                    # Never re-order event items, because they weren't randomized in the first place. The locations
                    # of event items should be locked anyway, so this is only for safety.
                    continue
                if (
                    location.player in er_player_to_world
                    and not er_player_to_world[location.player]
                        ._location_status(location)
                        .is_randomized
                ):
                    # The location belongs to a ER player with smoothing enabled, but the location is not considered
                    # available. This should mean that the location is not randomized, so the locations should be locked
                    # anyway, so this is only for safety.
                    continue
                er_smoothing_location_to_sphere[location] = sphere_number
                er_player_full_items_by_name[item.player][item.name].append(location.item)

        for er_world in er_worlds:
            # All items in the base game in approximately the order they appear
            all_item_order: List[ERItemData] = [
                item_table[location.default_item_name]
                for region in region_order + region_order_dlc
                # Shuffle locations within each region.
                for location in er_world._shuffle(location_tables[region])
                if er_world._location_status(location).is_randomized
            ]

            # All ERItems for this world that have been assigned anywhere, grouped by name
            full_items_by_name: defaultdict[str, List[ERItem]] = er_player_full_items_by_name[er_world.player]

            def smooth_items(item_order: List[Union[ERItemData, ERItem]]) -> None:
                """Rearrange all items in item_order to match that order.

                Note: this requires that item_order exactly matches the number of placed items from this
                world matching the given names.
                """

                # Convert items to full ERItems and get their locations.
                converted_item_order: List[ERItem] = []
                locations_to_smooth: List[Location] = []
                for ordered_item in item_order:
                    # full_items_by_name won't contain DLC items if the DLC is disabled.
                    if ordered_item.name not in full_items_by_name:
                        continue
                    items_list = full_items_by_name[ordered_item.name]
                    item = items_list.pop(0)
                    location = item.location
                    converted_item_order.append(item)
                    locations_to_smooth.append(location)
                    # Un-place the item in preparation for placing all the items in a smoothed-out order.
                    location.item = None
                    item.location = None
                    if not items_list:
                        # The list is now empty, so remove it to prevent being able to get and pop an empty list.
                        del full_items_by_name[ordered_item.name]

                # First sort locations by sphere (earliest first). Next sort non-ER locations after
                # ER locations, so that non-ER locations get the best items within a sphere.
                # Finally sort ER locations amongst themselves using their region values.
                def location_sort_func(location: Location):
                    sphere_number = er_smoothing_location_to_sphere[location]
                    if location.game == cls.game:
                        # The location is from a ER world, so will be sorted before non-ER locations within the same
                        # sphere, and sorted additionally by the location's .region_value.
                        ER_location = cast(ERLocation, location)
                        return sphere_number, 0, ER_location.data.region_value
                    else:
                        # Within the same sphere, all non-ER locations will be sorted after ER locations.
                        return sphere_number, 1

                # Initially shuffle for varied results when there are ties in the sorting.
                er_world.random.shuffle(locations_to_smooth)
                locations_to_smooth.sort(key=location_sort_func)

                # Place the items so that earlier items in `converted_item_order` get placed into logically earlier
                # locations.
                # Locations are filled from the start, but items are placed starting from the end, so reverse the order
                # of the items list.
                converted_item_order.reverse()
                remaining_fill(multiworld, locations_to_smooth, converted_item_order, name="ER Smoothing", check_location_can_fill=True)
                
            if er_world.options.smooth_upgrade_items: # smoothed items cant be filler items
                smooth_items(sorted([
                    item for item in all_item_order 
                    if item.upgrade_item and item.is_important(er_world.options) != ItemClassification.progression
                ], key=lambda item, world=er_world: world.random.randrange(max(item.upgrade_tier -1, 1), min(item.upgrade_tier +1, 5), 1))) 
                # sort by upgrade tier, and shuffle +-1

            if er_world.options.smooth_rune_items:
                smooth_items(sorted([
                    item for item in all_item_order
                    if item.runes and item.is_important(er_world.options) != ItemClassification.progression
                ], key=lambda item, world=er_world: world.random.randrange(max(item.rune_tier -1, 1), min(item.rune_tier +1, 4), 1)))
                # sort by rune tier, and shuffle +-1

    def _shuffle(self, seq: Sequence) -> List:
        """Returns a shuffled copy of a sequence."""
        copy = list(seq)
        self.random.shuffle(copy)
        return copy

    def _get_our_locations(self) -> List[ERLocation]:
        return cast(List[ERLocation], self.multiworld.get_locations(self.player))
    
    @staticmethod
    def _er_item_full_id(item: ERItemData) -> int:
        if item.er_code is None:
            raise ValueError(f"Cannot encode item without ER code: {item.name}")

        match item.category:
            case ERItemCategory.GOODS:
                return 0x40000000 + item.er_code
            case ERItemCategory.WEAPON:
                return item.er_code
            case ERItemCategory.ARMOR:
                return 0x10000000 + item.er_code
            case ERItemCategory.ACCESSORY:
                return 0x20000000 + item.er_code
            case ERItemCategory.ASHOFWAR:
                return 0x80000000 + item.er_code
            case _:
                raise ValueError(f"Unsupported ER item category for {item.name}: {item.category}")
    
    def fill_slot_data(self) -> Dict[str, object]:
        slot_data: Dict[str, object] = {}
        # Once all clients support overlapping item IDs, adjust the ER AP item IDs to encode the
        # in-game ID as well as the count so that we don't need to send this information at all.
        #
        # We include all the items the game knows about so that users can manually request items
        # that aren't randomized, and then we _also_ include all the items that are placed in
        # practice.
        items_by_name = {
            location.item.name: cast(ERItem, location.item).data
            for location in self.multiworld.get_filled_locations()
            # item.code None is used for events, which we want to skip
            if location.item.code is not None and location.item.player == self.player
        }
        for item in item_table.values():
            if item.name not in items_by_name:
                items_by_name[item.name] = item

        ap_ids_to_er_ids: Dict[str, int] = {}
        item_counts: Dict[str, int] = {}
        for item in items_by_name.values():
            if item.ap_code is None: continue
            if item.er_code is not None: ap_ids_to_er_ids[str(item.ap_code)] = self._er_item_full_id(item)
            if item.count != 1: item_counts[str(item.ap_code)] = item.count

        # A map from Archipelago's location IDs to the keys the static randomizer uses to identify
        # locations.
        location_ids_to_keys: Dict[int, str] = {}
        location_ids_to_targets: Dict[int, list[str]] = {}
        location_ids_to_name: Dict[int, str] = {}
        for location in cast(List[ERLocation], self.multiworld.get_filled_locations(self.player)):
            # Skip events and only look at this world's locations
            if (location.address is not None and location.item.code is not None
                    and location.data.key):
                location_ids_to_keys[location.address] = location.data.key
                location_ids_to_name[location.address] = location.data.name
                if location.data.targets:
                    if isinstance(location.data.targets, str):
                        location.data.targets = [location.data.targets]
                    location_ids_to_targets[location.address] = list(location.data.targets)

        duplicated_locations = {}
        for dupe_location in self.all_duplicate_locations:
            duplicated_locations[dupe_location] = dupe_location[:dupe_location.find("extra item")-2]

        # Mapping from target to forced boss which prevents the forced boss from appearing anywhere else
        force_bosses = {}
        if self.rykard_location:
            force_bosses[self.rykard_location.id] = default_rykard_location.id
        if self.serpent_location:
            force_bosses[self.serpent_location.id] = default_serpent_location.id

        @dataclass
        class sweep_flags:
            flag: int
            ids: list[int]
            extra_flag: Optional[int] = None

        dungeon_sweep_flag_to_locations: list[sweep_flags] = []
        for region in location_tables:
            # if the region has a dungeon item
            if location_tables[region][0].dungeon:
                # find boss flag and add locations apcode it should grant to list
                for loc in location_tables[region]:
                    if loc.name in all_boss_locations_dictionary:
                        flag = all_boss_locations_dictionary[loc.name].flag
                        locations = [l.ap_code for l in location_tables[region] if not l.unsweepable]
                        if flag == 30050800: # LL/BKC
                            dungeon_sweep_flag_to_locations.append(sweep_flags(flag, locations, 30050850))
                        elif flag == 31190800: # AP/SCV
                            dungeon_sweep_flag_to_locations.append(sweep_flags(flag, locations, 31190850))
                        else:
                            dungeon_sweep_flag_to_locations.append(sweep_flags(flag, locations))
                        break

        slot_data = {
            "options": {
                "key_item_shards": self.options.key_item_shards.value,
                "exclude_dungeon": self.options.exclude_dungeon.value,
                "world_logic": self.options.world_logic.value,
                "soft_logic": self.options.soft_logic.value,
                "separate_progression": self.options.separate_progression.value,
                "great_runes_required_leyndell": self.options.great_runes_required_leyndell.value,
                "great_runes_required_mountain": self.options.great_runes_required_mountain.value,
                "great_runes_required_erdtree": self.options.great_runes_required_erdtree.value,
                "royal_access": self.options.royal_access.value,
                "use_master_key": self.options.use_master_key.value,
                
                "enable_tp_dlc": self.options.enable_tp_dlc.value,
                "enable_dlc": self.options.enable_dlc.value,
                "dlc_start": self.options.dlc_start.value,
                "dlc_starting_items": self.options.dlc_starting_items.value,
                "dlc_starting_shop": self.options.dlc_starting_shop.value,
                "dlc_care_package": self.options.dlc_care_package.value,
                "dlc_initial_rune_level": self.options.dlc_initial_rune_level.value,
                "dlc_messmer_kindle": self.options.dlc_messmer_kindle.value,
                "dlc_scadutree_fragments": self.options.dlc_scadutree_fragments.value,
                "dlc_timing": self.options.dlc_timing.value,
                "dlc_max_level_weapons": self.options.dlc_max_level_weapons.value,
                "dlc_abyssal_torrent": self.options.dlc_abyssal_torrent.value,
                "spiritspring_stones": self.options.spiritspring_stones.value,
                
                "enemy_rando": self.options.enemy_rando.value,
                "merge_bosses": self.options.merge_bosses.value,
                "restrictive_bosses": self.options.restrictive_bosses.value,
                "rykard_encounter": self.options.rykard_encounter.value,
                "boss_scaling_percent": self.options.boss_scaling_percent.value,
                "disable_gargoyle_poison_cloud_damage": self.options.disable_gargoyle_poison_cloud_damage.value,
                "night_bosses": self.options.night_bosses.value,
                "dungeon_sweep": self.options.dungeon_sweep.value,
                "material_rando": self.options.material_rando.value,
                "death_link": self.options.death_link.value,
                "death_link_amnesty": self.options.death_link_amnesty.value,
                
                "ngplus_trap_count": self.options.ngplus_trap_count.value,
                "status_trap_count": self.options.status_trap_count.value,
                
                "blindness_trap_count": self.options.blindness_trap_count.value,
                
                "random_start": self.options.random_start.value,
                "randomize_starting_keepsakes": self.options.randomize_starting_keepsakes.value,
                "require_one_handed_starting_weapons": self.options.require_one_handed_starting_weapons.value,
                "remove_weapon_and_spell_requirements": self.options.remove_weapon_and_spell_requirements.value,
                "no_equip_load": self.options.no_equip_load.value,
                "reduce_non_somber_upgrade_cost": self.options.reduce_non_somber_upgrade_cost.value,
                "snowfast": self.options.snowfast.value,
                "auto_equip": self.options.auto_equip.value,
                "auto_upgrade": self.options.auto_upgrade.value,
                
                "crafting_kit_option": self.options.crafting_kit_option.value,
                "physick_flask_option": self.options.physick_flask_option.value,
                "map_option": self.options.map_option.value,
                "smithing_bell_bearing_option": self.options.smithing_bell_bearing_option.value,
                "smooth_upgrade_items": self.options.smooth_upgrade_items.value,
                "smooth_rune_items": self.options.smooth_rune_items.value,
                "spell_shop_spells_only": self.options.spell_shop_spells_only.value,
                "early_legacy_dungeons": self.options.early_legacy_dungeons.value,
                "local_item_only": self.options.local_item_only.value,
                
                "priority_location_groups": self.options.priority_location_groups.value,
                "important_at_priority_only": self.options.important_at_priority_only.value,
                "important_at_priority_early": self.options.important_at_priority_early.value,
                "other_world_useful_at_priority": self.options.other_world_useful_at_priority.value,
                "flask_at_priority": self.options.flask_at_priority.value,
                "whetblades_at_priority": self.options.whetblades_at_priority.value,
                "scadu_at_priority": self.options.scadu_at_priority.value,
                "talisman_pouches_at_priority": self.options.talisman_pouches_at_priority.value,
                "crystal_tears_at_priority": self.options.crystal_tears_at_priority.value,
                "memory_stones_at_priority": self.options.memory_stones_at_priority.value,
                "remembrances_at_priority": self.options.remembrances_at_priority.value,
                "exclude_locations": self.options.exclude_locations.value,
                "excluded_location_behavior": self.options.excluded_location_behavior.value,
                "missable_location_behavior": self.options.missable_location_behavior.value,
            },
            "seed": self.multiworld.seed_name,  # to verify the server's multiworld
            "slot": self.multiworld.player_name[self.player],  # to connect to server
            "random_enemy_preset": json.dumps(self.options.random_enemy_preset.value),
            "goal": [boss.flag for boss in self.goal_bosses],
            "requiredShards": { # item name: required amount
                shard: self.options.key_item_shards.value[shard_list[shard]]["Req"] 
                for shard in shard_list
                if shard_list[shard] in self.options.key_item_shards.value and self.options.key_item_shards.value[shard_list[shard]]['Max'] > 1
            },
            "forceBosses": force_bosses,
            "apIdsToItemIds": ap_ids_to_er_ids,
            "itemCounts": item_counts,
            "locationIdsToName": location_ids_to_name,
            "locationIdsToKeys": location_ids_to_keys,
            "locationIdsToTargets": location_ids_to_targets,
            "allStartingItems": self.all_starting_items, # list of _er_item_full_id
            "duplicatedLocations": duplicated_locations,
            "dungeonSweepLocations": [json.dumps(asdict(f)) for f in dungeon_sweep_flag_to_locations],
            "versions": ">=0.1 <0.2",
        }

        return slot_data

    @staticmethod
    def interpret_slot_data(slot_data: Dict[str, Any]) -> Dict[str, Any]:
        return slot_data
    
    # UT Stuff
    
    def custom_ut_sort(self, region_label: str, location_label: str) -> str | int:
        if "(*)" in location_label: # this works, lmao, removes the (*)
            location_label = location_label[:-4]
        value = location_dictionary[location_label].region_value
        if not self.options.important_at_priority_only: return value
        if location_label not in self.all_possible_priority_locations:
            value += 1000
        else:
            self.location_id_to_alias[self.location_name_to_id[location_label]] = "*"
        return value
    