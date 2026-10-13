# Elden Ring

Game Guide | [Setup Guide](./en_setup_guide.md) | [Region Guide](./en_region_guide.md) | [Location Guide](./en_location_guide.md) | [Goal Bosses Guide](./en_goal_bosses_guide.md)

## How do I randomize Elden Ring?

You can find instructions in the [setup guide](./en_setup_guide.md).

## How to beat the randomizer

Elden Ring is a game with a lot of checks, but by default, only a small fraction of locations called priority locations can have required progression items. To play Elden Ring in a multiworld, check these locations in earlier areas before unlocking and moving to later areas.

You can set up priority locations using the `priority_location_groups` option, and the apworld will automatic balance these groups in order to avoid an unbalanced multiworld. If there are too many priority locations, they're trimmed down to the amount of important items, but if there are too few, extra locations will be created at already existing priority locations to hold enough important items.

Additional key items may appear that are not part of vanilla Elden Ring. By default, the option `region_lock` adds keys which must be acquired to enter major new regions, and `use_master_key` replaces Stonesword Keys with master keys to unlock all seals in a region.

**More to be added here about randomizer features and mechanics. For now, reference yaml option descriptions or feel free to ask.**

## Enemy randomizer customization

Custom enemy placement allows extensive customization of enemy randomizer. It is commonly used to merge all bosses in the game across different boss categories, which can be accomplished by clicking "Merge all bosses" in merge presets. You can also prevent a boss or enemy from appearing anywhere by adding it to "Excluded everywhere", and there is limited support for enemy plando under "Manual Placement".

Note if `rykard_encounter` is disabled, called "Give Serpent-Hunter upon encountering Rykard" in the randomizer program, the locations of Rykard and God-Devouring Serpent are set by the apworld and cannot be overridden in custom enemy placement.
