from dataclasses import dataclass
import json
from typing import Any, Dict

from Options import Choice, DeathLink, DefaultOnToggle, PriorityLocations, ExcludeLocations, OptionList, OptionDict, \
    OptionGroup, OptionSet, PerGameCommonOptions, Range, Toggle, OptionError, Visibility
    
from .bosses import all_bosses

# MARK: Game Options

class GoalOption(OptionSet):
    """Which bosses must be defeated in order to win the game, of the form "<Region> Boss".

    If multiple bosses are selected, all of them must be defeated in order to
    achieve your goal. By default, only "Final Boss" and "DLC Final Boss" is
    selected.
    """
    display_name = "Goal"
    valid_keys = {type + " Boss" for boss in all_bosses if boss.flag for type in boss.type}
    default = frozenset({"Final Boss", "DLC Final Boss"})

class KeyItemShards(OptionDict): # max value is set in shard verify func in gen_early
    """
    Which key items should be broken up into shards and how many
    shards are required to use them.
    
    **KeyItem**Shards:
    - Req: (1-10) *required shards*
    - Max: (1-10) *maximum shards*
    
    Requiring about half of the maximum shards allows for more
    flexibility to not get blocked at major required gates.
    """
    display_name = "Key Item Shards"
    default = {
        "RustyKeyShards": {"Req": 1, "Max": 1},
        "RoldMedallionShards": {"Req": 1, "Max": 1},
        "MessmerKindlingShards": {"Req": 3, "Max": 5}
        }
    valid_keys = ["RustyKeyShards", "RoldMedallionShards", "MessmerKindlingShards"]
    @classmethod
    def get_option_name(cls, value: Dict[str, Any]) -> str:
        return json.dumps(value)

# skipping og item and injecting are done automatically
shard_list = { # item name: option name
    # base game
    "Rusty Key Shard": 'RustyKeyShards',
    "Rold Medallion Shard": 'RoldMedallionShards',
    # dlc
    "Messmer's Kindling Shard": 'MessmerKindlingShards'
}
    
class ExcludeDungeonBosses(DefaultOnToggle):
    "Exclude dungeon bosses from Goal. ex: Catacomb and Cave bosses, not Siofra River bosses"
    display_name = "Exclude Dungeon Bosses"

class WorldLogic(Choice):
    """World Logic options
    
    **Region Lock:** Each region will require a 'Special item'.
    **Open World:** No region locking."""
    display_name = "World Logic"
    option_region_lock = 0
    option_open_world = 1
    default = 0
    
class RegionSoftLogic(DefaultOnToggle):
    """You will always get Altus access before needing to go to Caelid and
    Mountaintops access before needing to go Consecrated Snowfield.
    You will also get access to another region before Jagged Peak in DLC."""
    display_name = "Region Soft Logic"

class GreatRunesRequiredLeyndell(Range):
    """How many great runes are required to enter Leyndell."""
    display_name = "Leyndell Great Runes Required"
    range_start = 0
    range_end = 7
    default = 2
    
class GreatRunesRequiredMountain(Range):
    """What is required to enter Mountaintops.
    This is ignored if Rold Medallion shards are used as both basically do the same thing.

    - **Vanilla:** Rold Medallion is required.
    - **0-7:** Rold Medallion is not required; require this many Great Runes instead."""
    display_name = "Mountaintops Great Runes Required"
    range_start = -1
    range_end = 7
    default = -1
    
class GreatRunesRequiredErdtree(Range):
    """How many great runes are required to access the Erdtree."""
    display_name = "Erdtree Great Runes Required"
    range_start = 0
    range_end = 7
    default = 0
    
class RoyalAccess(Toggle):
    """Keep Royal Capital graces accessable after it becomes ashen."""
    display_name = "Royal Capital Accessable"

class StoneswordMasterKey(Choice):
    """Stonesword Key options
    
    **Regional Key:** Adds an individual Master Key for each region.
    **Single Key:** Adds a Single Master Key.
    """
    display_name = "Stonesword Master Key"
    option_vanilla = 0
    option_regional_keys = 1
    option_single_key = 2
    default = 1

# MARK: Tarnished Pack

class EnableTarnishedPack(Toggle):
    """Enable Tarnished Pack"""
    display_name = "Enable Tarnished Pack"

# MARK: DLC

class EnableDLC(DefaultOnToggle):
    """Enable Shadow of the Erdtree DLC"""
    display_name = "Enable DLC"

class SeparateProgression(Toggle):
    """Separate Progression.

    If separate:
    - Base game progession will be in base game or other worlds.
    - DLC progression will be in DLC or other worlds.
    """
    display_name = "Separate Progression"
    
class DLCMessmerKindle(Choice):
    """Randomize Messmer's Kindling / Shards.
    
    **Normal:** Messmer's Kindling / Shards can be anywhere.
    **DLC Only:** Randomize Kindling to your DLC.
    **Not Base:** Don't randomize Kindling to your base game.
    """
    display_name = "DLC Messmer's Kindling"
    option_normal = 0
    option_dlc_only = 1
    option_not_base = 2
    
class DLCScadutreeFragments(Choice):
    """Randomize Scadutree Fragments.
    
    **Normal:** Scadutree Fragments can be anywhere.
    **DLC Only:** Randomize Scadutree Fragments to your DLC.
    **Not Base:** Don't randomize Scadutree Fragments to your base game.
    """
    display_name = "DLC Scadutree Fragments"
    option_normal = 0
    option_dlc_only = 1
    option_not_base = 2
    default = 1

class DLCTimingOption(Choice):
    """Guarantee that you don't need to enter the DLC until later in the run.

    - **Early:** 'Pureblood Knight Medal' will spawn in an early sphere, unless MissableLocationBehaviorOption is set to do_not_randomize, it'll be at its normal spot.
    - **Off:** You may have to enter the DLC with 'Pureblood Knight Medal' item.
    - **Late:** You won't have to enter the DLC until after getting to Snowfield.
    """
    display_name = "DLC Timing"
    option_early = 0
    option_off = 1
    option_late = 2
    default = 1
    
class DLCMaxLevelWeapons(Toggle): # not fully supported
    """Upgrade all weapons to max level in the DLC.

    Currently this only works when using DLC Start."""
    display_name = "DLC Max Level Weapons"
    
class DLCAbyssalTorrent(Toggle):
    """Prevent Torrent from getting frightened."""
    display_name = "DLC Abyssal Torrent"
    
class DLCSpiritspringStones(Toggle):
    """Randomize Spiritspring Stones into the item pool."""
    display_name = "Randomize Spiritspring Stones"
    
# MARK: DLC Start

class DLCStart(Choice):
    """Where the run starts.
    
    - **Normal:** Start in Limgrave.
    - **DLC Start:** Start in Gravesite Plain, with no access to base game.
    - **DLC Start With Base:** Start in either Stranded Graveyard or Gravesite Plain.
    """
    display_name = "DLC Start"
    option_normal = 0
    option_dlc_start = 1
    option_dlc_start_with_base = 2
    default = 0
    
class DLCStartingItems(OptionList):
    """Choose what base game items to start with in DLC Start.
    If there is no access to base game, items not started with will be randomized into the DLC.
    
    - **Sacred Tears**
    - **Golden Seeds**
    - **Talisman Pouches**
    - **Memory Stones**
    - **Whetblades**
    - **Upgrade Bell Bearings**"""
    display_name = "DLC Start Starting Items"
    supports_weighting = False
    default = ["Talisman Pouches", "Whetblades"]

    valid_keys = ["sacred tears", "golden seeds", "talisman pouches", 
                  "memory stones", "whetblades", "upgrade bell bearings"]
    valid_keys_casefold = True

class DLCStartingShop(Toggle):
    """Add a shop at grace with all base game equipment for free."""
    display_name = "DLC Start Starting Shop"
    
class DLCCarePackage(Toggle):
    """Start with 80 extra base game items."""
    display_name = "DLC Start Care Package"
    
class DLCInitialRuneLevel(Range):
    """Runes are given to level up at start."""
    display_name = "DLC Start Initial Rune Level"
    range_start = 0
    range_end = 200
    default = 0

# MARK: Other Rando
    
class EnemyRando(DefaultOnToggle):
    """Randomizes the enemies."""
    display_name = "Enemy Randomizer"

class RestrictiveBossPlacement(DefaultOnToggle):
    """Restrict arenas bosses can be placed into based on size."""
    display_name = "Restrictive Boss Placement"
    
class RykardEncounter(DefaultOnToggle):
    """Give Serpent-Hunter on encounter with Rykard/Serpent in boss arenas.
    If off Serpent-Hunter will be randomized and be required for whatever Rykard/Serpent blocks."""
    display_name = "Rykard Encounter"
    
class BossScalingPercent(Range): # unsupported, till after first release
    """Scales HP and damage for enemies placed into boss slots.

    100 keeps the current static randomizer scaling. 90 means 90% of the boss
    location's HP and damage scaling, while 120 means 120%.
    """
    display_name = "Boss HP/Damage Scaling Percent"
    range_start = 25
    range_end = 200
    default = 100
    visibility = Visibility.none

class DisableGargoylePoisonCloudDamage(Toggle):
    """Disable the damage tick in Valiant Gargoyles' poison cloud while leaving poison buildup intact."""
    display_name = "Disable Damage Tick in Valiant Gargoyles' Poison Cloud"

class NightBosses(Choice):
    """
    Normal: Bosses spawn at night.
    Always On: Bosses will always spawn.
    Require Item: Bosses only spawn after finding an item.   just an idea from Spencenox, not implimented
    """
    display_name = "Night Bosses"
    option_normal = 0
    option_always_on = 1
    # option_require_item = 2
    default = 0

class DungeonSweep(Toggle): # unsupported, till after first release
    """After killing the boss of a dungeon collect all remaining items within that dungeon automatically."""
    display_name = "Dungeon Sweep"
    visibility = Visibility.none

class RandomEnemyPresetOption(OptionDict): # unsupported, do UI editing for now
    """The YAML preset for the static enemy randomizer.

    See the online enemy randomization documentation for available options.
    Include this as nested YAML. For example:

      random_enemy_preset:
        RemoveSource: Basilisk; Fingercreeper
        DontRandomize: Tree Sentinel

    Elden Ring uses class-based enemy pools. To let major bosses, minor bosses,
    world minibosses, night minibosses, dragon minibosses, and evergaol bosses
    draw from one combined boss pool:

      random_enemy_preset:
        DontRandomize: DLCAllEnemies
        Classes:
          Boss:
            Pools:
            - Weight: 100
              Pool: AllBosses

    To keep only DLC hostile NPCs and invasions at their vanilla placements while
    still shuffling base game hostile NPCs:

      random_enemy_preset:
        DontRandomize: DLCHostileNPC
    """
    display_name = "Random Enemy Preset"
    supports_weighting = False
    default = {}

    valid_keys = ["Description", "RecommendFullRandomization", "RecommendNoEnemyProgression", "Options",
                  "OopsAll", "Boss", "Miniboss", "Basic", "BuffBasicEnemiesAsBosses",
                  "DontRandomize", "RemoveSource", "EnemyMultiplier", "AdjustSource", "Classes", "Enemies"]

    @classmethod
    def get_option_name(cls, value: Dict[str, Any]) -> str:
        return json.dumps(value)

    visibility = Visibility.none

class MaterialRando(DefaultOnToggle):
    """Randomizes the indefinitely spawning materials."""
    display_name = "Material Randomizer"

# MARK: Traps
    
class BaseTrapCount(Range):
    """
    Base Class for Trap Count
    """
    range_start = 0
    range_end = 10
    default = 0
    
class ExampleTrapCount(BaseTrapCount):
    """
    Example Trap: Description
    """
    display_name = "Example Trap Count"
    
class NGPlusTrapCount(BaseTrapCount):
    """
    NG+ Trap: Sets the game to NG+7 until the player dies.
    """
    display_name = "NG+ Trap Count"
    
class StatusTrapCount(BaseTrapCount): # unsupported, till after first release
    """
    Status Trap: Applies a random status to the player.
    """ # excluding deathblight... or keep it for the funny clips
    # maybe add a 1/10 chance to add an additional effect that stacks, so a 1/1000 for 4 effects lol
    display_name = "Status Trap Count"
    visibility = Visibility.none
    
# game speed trap, speeds game up by 25% - 50%
    
# Traps that need dlc stuff to work
    
class ExampleDLCTrapCount(BaseTrapCount):
    """
    Example DLC Trap: Description
    """
    display_name = "Example DLC Trap Count"
    
class BlindnessTrapCount(BaseTrapCount): # unsupported, till after first release
    """
    Blindness Trap: Blinds the player for a short time.
    """
    display_name = "Blindness Trap Count"
    visibility = Visibility.none
    

# MARK: Item & Location

class RandomizeStartingLoadout(DefaultOnToggle):
    """Randomizes the equipment characters begin with."""
    display_name = "Randomize Starting Loadout"

class RandomizeStartingKeepsakes(DefaultOnToggle):
    """Randomizes selectable keepsakes at character creation."""
    display_name = "Randomize Starting Keepsakes"

class RequireOneHandedStartingWeapons(DefaultOnToggle):
    """Require starting equipment to be usable one-handed."""
    display_name = "Require One-Handed Starting Weapons"

class RemoveWeaponAndSpellRequirements(Toggle):
    """Remove all stat requirements from weapons and spells."""
    display_name = "Remove All Weapon and Spell Requirements"

class NoEquipLoadOption(Toggle): # unsupported, till after first release
    """Disable the equip load constraint from the game."""
    display_name = "No Equip Load"
    visibility = Visibility.none

class ReduceNonSomberUpgradeCost(Toggle):
    """Reduce regular Smithing Stone costs for non-somber weapons to one stone per weapon level."""
    display_name = "Reduce Upgrade Cost for Non-Somber Weapons"

class SnowFast(Toggle):
    """Adds Mountaintops of the Giants shortcuts for faster traversal."""
    display_name = "Add Shortcuts in Mountaintops for Faster Traversal"

class AutoEquipOption(Toggle):
    """Automatically equips any received armor or left/right weapons."""
    display_name = "Auto-Equip"
    
class AutoUpgradeOption(Toggle):
    """Automatically upgrades any received weapons to highest upgraded level."""
    display_name = "Auto-Upgrade"
    
class CraftingKitOption(Choice):
    """Choose how the Crafting Kit is handled.

    - **Randomize:** Can be anywhere.
    - **Early:** Make it anywhere before Altus and not in Caelid, if DLC Only it'll be in Gravesite Plain.
    - **Do Not Randomize:** Leave it at its normal spot, if DLC Only is on it'll be in Roundtable Twin Maiden Shop.
    """
    display_name = "Crafting Kit Behavior"
    option_randomize = 0
    option_early = 1
    option_do_not_randomize = 2
    default = 2
    
class MapOption(Choice):
    """Choose how maps are handled.

    - **Randomize:** Can be anywhere.
    - **Give:** Add to starting inventory.
    - **Do Not Randomize:** Leave them at their normal spots.
    """
    display_name = "Map Behavior"
    option_randomize = 0
    option_give = 1
    option_do_not_randomize = 2
    default = 1
    
class SmithingBellBearingOption(Choice):
    """Choose how smithing stone bell bearings are handled.
    This doesn't work with dlc only, add them to starting inventory or they get randomized.

    - **Randomize:** Can be anywhere.
    - **Progression Randomize:** Make them a progression item, and be required for the area after they would normally be in and for DLC.
    - **Do Not Randomize:** Leave them at their normal spots.
    """
    display_name = "Smithing Bell Bearing Behavior"
    option_randomize = 0
    option_progression_randomize = 1
    option_do_not_randomize = 2
    default = 1
    
class SmoothUpgradeItems(DefaultOnToggle):
    """Smooth Upgrade Items.
    The smoothing is fuzzy, so you should see stones 1-4 in early spheres and 6-dragon in ending spheres."""
    display_name = "Smooth Upgrade Items"
    
class SmoothRuneItems(DefaultOnToggle):
    """Smooth Rune Items.
    The smoothing is fuzzy, so you'll see lower tier (200-10k) runes in early spheres and high tier (35k-80k) runes in ending spheres."""
    display_name = "Smooth Rune Items"
    
class SpellShopSpellsOnly(Toggle):
    """Spell Shops only have spells."""
    display_name = "Spell Shop Spells Only"
    
class EarlyLegacyDungeonsEarly(Toggle):
    """Access to Stormveil and Raya Lucaria will be early."""
    display_name = "Stormveil and Raya Lucaria Early"

# MARK: Priority Stuff
    
class ERPriorityLocationGroups(PriorityLocations):
    """Prevent these location types from having an unimportant items.
    
    If you add more priority locations then progression items, random priority locations will contain normal items.
    Otherwise your world would contain a lot of other worlds progression.
    
    - *Achievement Boss*: Base game Achievement bosses.
    - *DLC Remembrance Boss*: DLC Remembrance bosses.
    - *Boss Reward*: Base game bosses.
    - *DLC Boss Reward*: DLC bosses.
    - *Overworld Boss*: Base game Overworld bosses.
    - *DLC Overworld Boss*: DLC Overworld bosses.
    - *Chest*: Chests.
    - *Scarab*: Scarabs.
    - *Seedtree*: Golden Seed trees.
    - *Basin*: Basins that contain tears.
    - *Church*: Sacred Tears.
    - *Map*: Map pillars.
    - *Fragment*: Scadu Fragments.
    - *Cross*: All cross items.
    - *Revered*: Revered Spirit Ashes.
    - *Key Items*: Key items.
    """
    display_name = "Priority Location Groups"
    default = ["Key Items", "Achievement Boss", "DLC Remembrance Boss", "Seedtree", "Map", "Church", "Cross", "Fragment"]
    valid_keys = ["Chest", "Scarab", "Seedtree", "Basin", "Church", "Map", "Key Items",
        "Fragment", "Cross", "Revered", "Overworld Boss", "DLC Overworld Boss", 
        "Achievement Boss", "DLC Remembrance Boss", "Boss Reward", "DLC Boss Reward"]
    valid_keys_casefold = False
    
class ERImportantAtPriorityOnly(DefaultOnToggle):
    """Should important items be only at priority locations.
    
    Creates extra locations at priority locations to contain all important items.
    If there are no priority locations in the starting region one will be added.
    Base: "LG/(SG): Finger Severer - beside grace"
    DLC: "GP/TPC: Scadutree Fragment - by cross"
    
    Generator likes to fail if there is to little priority locations, add more if it fails."""
    display_name = "Important at Priority Only"
    
class ERImportantAtPriorityEarly(Range):
    """
    Needs Important at Priority Only On.
    Does nothing if there are tons of Priority Locations.
    
    Make extra generated locations appear more early game (Limgrave, Weeping, Liurnia, Stormveil and Raya Lucaria).
    If starting in DLC (Gravesite, Belurat, Dragon Pit and Ensis).
    
    1: Normal.
    2+: Multiplied odds of early game locations.
    
    Example: Setting this to 3 will make early locations 3 times more likely to have extra locations.
    """
    display_name = "Important At Priority Early"
    range_start = 1
    range_end = 5
    default = 1

class FlaskUpgradesAtPriority(Toggle):
    "Should flask upgrades be randomized to important locations."
    display_name = "Flask Upgrades at Priority"
    
class ScaduAtPriority(Toggle):
    "Should scadu fragments be randomized to important locations."
    display_name = "Scadutree Fragments at Priority"

class TalismanPouchesAtPriority(Toggle):
    "Should talisman pouches be randomized to important locations."
    display_name = "Talisman Pouches at Priority"

class CrystalTearsAtPriority(Toggle):
    "Should Wondrous Physick tears be randomized to important locations."
    display_name = "Crystal Tears at Priority"

class MemoryStonesAtPriority(Toggle):
    "Should memory stones be randomized to important locations."
    display_name = "Memory Stones at Priority"

class RemembrancesAtPriority(Toggle):
    "Should remembrances be randomized to important locations."
    display_name = "Remembrances at Priority"

# MARK: Excludes and Behavior

class LocalItemOnly(OptionList):
    """Which categories should be local only, useful and progression excluded.
    - [Est Items] **Item Group**
    - [472] **Weapon**: All Weapons and Ammo.
    - [423] **Armor**: All Armors.
    - [160] **Accessory**: All Talismans.
    - [105] **AshofWar**: All Ashes of War.
    - [3250] **Goods**: The two below
    - [1000] **Filler**: All Crafting Mats, and some craftables.
    - [2200] **Non-Filler**: Smithing stones, Spells and Spirit ashes.
    
    If every category is set to local, Accessory and AshofWar will be unset to dodge fill errors.
    *host.yaml can force categories local.*
    """
    display_name = "Local Item Only"
    default = ["Filler"]
    valid_keys = ["weapon", "armor", "accessory", "ashofwar", "goods", "filler", "non-filler"]
    valid_keys_casefold = True

class ERExcludeLocations(ExcludeLocations):
    """Prevent these locations from having an important items.
    - **DLC**: If you want DLC items but dont wanna do DLC.
    - **Hidden**: Hard to find items.
    - **Blizzard**: The hard to see area of snowfield.
    - **Scarab**: Scarabs that drop items.
    - **Furnace Golem**: DLC Furnace Golems.
    - **Out of the Way**: Items that take a bit to get.
    - **Drop**: One time drop items from enemies."""
    default = frozenset({"Hidden"})
    valid_keys = {"dlc", "hidden", "blizzard", "scarab", "furnace golem", "out of the way", "drop", "post leyndell"} # testing "All Locations"
    valid_keys_casefold = True
    
    unconverted_groups = set() # this is so dumb but it works, i need the unconverted group names
    def verify_keys(self) -> None:
        super().verify_keys()
        self.unconverted_groups = self.value
        
    def excluded_groups(self):
        return self.unconverted_groups

class ExcludedLocationBehaviorOption(Choice):
    """How to choose items for excluded locations in ER.

    - **Allow Useful:** Excluded locations can't have progression items, but they can have useful items.
    - **Forbid Useful:** Neither progression items nor useful items can be placed in excluded locations.
    - **Do Not Randomize:** Excluded locations always contain the same item as in vanilla.
    - **Omit:** This location won't count as a check (if the item is filler) and contains the same item as in vanilla.

    A "progression item" is anything that's required to unlock another location in some game.
    A "useful item" is something each game defines individually, usually items that are quite
    desirable but not strictly necessary.
    """
    display_name = "Excluded Locations Behavior"
    option_allow_useful = 1
    option_forbid_useful = 2
    option_do_not_randomize = 3
    option_omit = 4
    default = 2

class MissableLocationBehaviorOption(Choice):
    """Which items can be placed in locations that can be permanently missed.

    - **Allow Useful:** Missable locations can't have progression items, but they can have useful items.
    - **Forbid Useful:** Neither progression items nor useful items can be placed in missable locations.
    - **Do Not Randomize:** Missable locations always contain the same item as in vanilla.
    - **Omit:** This location won't count as a check (if the item is filler) and contains the same item as in vanilla.

    A "progression item" is anything that's required to unlock another location in some game.
    A "useful item" is something each game defines individually, usually items that are quite
    desirable but not strictly necessary.
    """
    display_name = "Missable Locations Behavior"
    option_allow_useful = 1
    option_forbid_useful = 2
    option_do_not_randomize = 3
    option_omit = 4
    default = 2

@dataclass
class EROptions(PerGameCommonOptions):
    goal: GoalOption
    key_item_shards: KeyItemShards
    exclude_dungeon: ExcludeDungeonBosses
    world_logic: WorldLogic
    soft_logic: RegionSoftLogic
    separate_progression: SeparateProgression
    great_runes_required_leyndell: GreatRunesRequiredLeyndell
    great_runes_required_mountain: GreatRunesRequiredMountain
    great_runes_required_erdtree: GreatRunesRequiredErdtree
    royal_access: RoyalAccess
    use_master_key: StoneswordMasterKey
    
    enable_tp_dlc: EnableTarnishedPack
    enable_dlc: EnableDLC
    dlc_start: DLCStart
    dlc_starting_items: DLCStartingItems
    dlc_starting_shop: DLCStartingShop
    dlc_care_package: DLCCarePackage
    dlc_initial_rune_level: DLCInitialRuneLevel
    dlc_messmer_kindle: DLCMessmerKindle
    dlc_scadutree_fragments: DLCScadutreeFragments
    dlc_timing: DLCTimingOption
    dlc_max_level_weapons: DLCMaxLevelWeapons
    dlc_abyssal_torrent: DLCAbyssalTorrent
    spiritspring_stones: DLCSpiritspringStones
    
    enemy_rando: EnemyRando
    restrictive_bosses: RestrictiveBossPlacement
    rykard_encounter: RykardEncounter
    boss_scaling_percent: BossScalingPercent
    disable_gargoyle_poison_cloud_damage: DisableGargoylePoisonCloudDamage
    night_bosses: NightBosses
    dungeon_sweep: DungeonSweep
    random_enemy_preset: RandomEnemyPresetOption
    material_rando: MaterialRando
    death_link: DeathLink
    
    ngplus_trap_count: NGPlusTrapCount
    status_trap_count: StatusTrapCount
    
    blindness_trap_count: BlindnessTrapCount

    random_start: RandomizeStartingLoadout
    randomize_starting_keepsakes: RandomizeStartingKeepsakes
    require_one_handed_starting_weapons: RequireOneHandedStartingWeapons
    remove_weapon_and_spell_requirements: RemoveWeaponAndSpellRequirements
    no_equip_load: NoEquipLoadOption
    reduce_non_somber_upgrade_cost: ReduceNonSomberUpgradeCost
    snowfast: SnowFast
    auto_equip: AutoEquipOption
    auto_upgrade: AutoUpgradeOption
    
    crafting_kit_option: CraftingKitOption
    map_option: MapOption
    smithing_bell_bearing_option: SmithingBellBearingOption
    smooth_upgrade_items: SmoothUpgradeItems
    smooth_rune_items: SmoothRuneItems
    spell_shop_spells_only: SpellShopSpellsOnly
    early_legacy_dungeons: EarlyLegacyDungeonsEarly
    priority_location_groups: ERPriorityLocationGroups
    important_at_priority_only: ERImportantAtPriorityOnly
    important_at_priority_early: ERImportantAtPriorityEarly
    flask_at_priority: FlaskUpgradesAtPriority
    scadu_at_priority: ScaduAtPriority
    talisman_pouches_at_priority: TalismanPouchesAtPriority
    crystal_tears_at_priority: CrystalTearsAtPriority
    memory_stones_at_priority: MemoryStonesAtPriority
    remembrances_at_priority: RemembrancesAtPriority
    local_item_only: LocalItemOnly
    exclude_locations: ERExcludeLocations
    excluded_location_behavior: ExcludedLocationBehaviorOption
    missable_location_behavior: MissableLocationBehaviorOption

option_groups = [
    OptionGroup("Logic", [
        GoalOption,
        KeyItemShards,
        ExcludeDungeonBosses,
        WorldLogic,
        RegionSoftLogic,
        GreatRunesRequiredLeyndell,
        GreatRunesRequiredMountain,
        GreatRunesRequiredErdtree,
        RoyalAccess,
        StoneswordMasterKey,
    ]),
    OptionGroup("Other Randomizers", [
        EnemyRando,
        RestrictiveBossPlacement,
        RykardEncounter,
        BossScalingPercent,
        DisableGargoylePoisonCloudDamage,
        NightBosses,
        DungeonSweep,
        RandomEnemyPresetOption,
        MaterialRando,
    ]),
    OptionGroup("Equipment", [
        RandomizeStartingLoadout,
        RandomizeStartingKeepsakes,
        RequireOneHandedStartingWeapons,
        RemoveWeaponAndSpellRequirements,
        NoEquipLoadOption,
        ReduceNonSomberUpgradeCost,
        SnowFast,
        AutoEquipOption,
        AutoUpgradeOption,
    ]),
    OptionGroup("Death Link", [
        DeathLink
    ]),
    OptionGroup("DLC", [
        EnableTarnishedPack,
        EnableDLC,
        SeparateProgression,
        DLCMessmerKindle,
        DLCScadutreeFragments,
        DLCTimingOption,
        DLCMaxLevelWeapons,
        DLCAbyssalTorrent,
        DLCSpiritspringStones,
    ]),
    OptionGroup("DLC Start", [
        DLCStart,
        DLCStartingItems,
        DLCStartingShop,
        DLCCarePackage,
        DLCInitialRuneLevel,
    ]),
    OptionGroup("Traps", [
        NGPlusTrapCount,
        StatusTrapCount,
    ]),
    # OptionGroup("DLC Traps", [
    #     BlindnessTrapCount
    # ]),
    OptionGroup("Item & Location Options", [
        CraftingKitOption,
        MapOption,
        SmithingBellBearingOption,
        SmoothUpgradeItems,
        SmoothRuneItems,
        SpellShopSpellsOnly,
        EarlyLegacyDungeonsEarly,
        LocalItemOnly,
        ERExcludeLocations,
        ExcludedLocationBehaviorOption,
        MissableLocationBehaviorOption,
    ]),
    OptionGroup("Priority Location Rules", [
        ERPriorityLocationGroups,
        ERImportantAtPriorityOnly,
        ERImportantAtPriorityEarly,
        FlaskUpgradesAtPriority,
        ScaduAtPriority,
        TalismanPouchesAtPriority,
        CrystalTearsAtPriority,
        MemoryStonesAtPriority,
        RemembrancesAtPriority,
    ])
]