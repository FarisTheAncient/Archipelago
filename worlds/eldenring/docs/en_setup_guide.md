# Elden Ring Setup Guide

[Game Guide](./en_Elden_Ring.md) | Setup Guide | [Region Guide](./en_region_guide.md) | [Location Guide](./en_location_guide.md) | [Goal Bosses Guide](./en_goal_bosses_guide.md)

## Required software

- [Elden Ring](https://store.steampowered.com/app/1245620/ELDEN_RING/) 1.17.1 from Steam
- [Elden Ring Archipelago Randomizer](https://github.com/thefifthmatt/SoulsRandomizers/releases) client (includes apworld)

## Setting up

First, download the client zip file to your local disk and extract it.

Do not download it to a OneDrive-synced location, like your Desktop on some Windows installations. Do not run anything from inside a zip file viewer: extract the zip and open the extracted folder before anything else.

### Selecting options

Fill out a yaml file with options for your run. If you know what you're doing, you can use the yaml files included in the `yamls` directory in the zip file as a starting point.

Alternatively, you can install ArchipelagoLauncher as documented in [Archipelago Setup Guide](https://archipelago.gg/tutorial/Archipelago/setup_en), open eldenring.apworld with it, and Generate Template Options. You can use Options Creator to configure most options, but you'll have to edit the yaml file after exporting to adjust complex options like key item shards.

For more information about yaml and how to edit it, see Archipelago's [Advanced Yaml Guide](https://archipelago.gg/tutorial/Archipelago/advanced_settings_en) and check your files using the [validator](https://archipelago.gg/check).

For actually selecting game options, check out the [game guide](./en_Elden_Ring.md) to learn which features and modes are supported by the randomizer. Make sure to disable `enable_dlc` if you don't have the [Shadow of the Erdtree DLC](https://store.steampowered.com/app/2778580/ELDEN_RING_Shadow_of_the_Erdtree/) installed, and only enable `enable_tp_dlc` if you have the [Tarnished Pack DLC](https://store.steampowered.com/app/3655690/ELDEN_RING_Tarnished_Pack/), or else your run will not be completable.

Enemy randomizer is enabled by default with the `enemy_rando` setting. Enemy randomizer settings can be further customized in the "Generating mod files" steps and can be changed in the middle of a run, including disabling/enabling it in the middle of a run.

For non-solo runs, note some options cannot be set without the host allowing it in their `host.yaml` file. A major one is that `world_logic` cannot be `open_world` without an override, to avoid a massive sphere 1 which can BK other games for a long time.

### Generating the multiworld and hosting it

If someone else is setting up the multiworld, send them `eldenring.apworld` and your yaml file and get connection info like the room URL and password back from them.

If you are the someone setting up the multiworld, follow the [Archipelago Setup Guide](https://archipelago.gg/tutorial/Archipelago/setup_en). If you're playing with other people, it's more straightforward to host runs on [archipelago.gg](https://archipelago.gg/) rather than hosting them yourself.

As mentioned above, some apworld yaml options are not permitted without a change to `host.yaml` to explicitly allow them. You can edit these by running "Open host.yaml" in the launcher and searching for `eldenring_options`. If you can't find it, you may need to restart ArchipelagoLauncher after installing eldenring.apworld and try again.

### Generating mod files for Elden Ring

Launch EldenRingArchipelagoRandomizer.exe and click "Refresh Archipelago data", also accessible in the options menu as "Connect to Archipelago". Enter your room URL, player name, and password, and click "Load". This fetches all the data the randomizer needs to generate mod files, and a player tagged StaticRandomizer will enter and then leave the multiworld in server logs.

At this point, most options are locked based on your selections in the yaml file. However, you can change some options in the Enemy Randomizer and Misc Options tab, including enabling and configuring custom enemy placement.

Click "Randomize for Archipelago". If it succeeds, the "Launch Elden Ring" button will be enabled. Otherwise, an error message is shown, and you may need to open the latest file in the `spoiler_logs` directory and scroll down to see all details. When reporting an issue, make sure to include all relevant information from logs.

If you get a warning or error about mismatched game files, make sure the game is updated in Steam and verify integrity of installed files. This can be a good idea to do anyway as invalid files are a common source of crashes.

Some options can be changed in the middle of a run, but aside from RandomizerHelper options, you will need to first close Elden Ring and regenerate the mod files for them to apply. First, you should refresh Archipelago data if randomizer doesn't have your slot information loaded. Note that refreshing also resets any manually changed options, so you'll need to change those again. Set all of your desired options, click "Randomize for Archipelago", and relaunch Elden Ring.

### Launch Elden Ring

After you have generated the mod files, use the "Launch Elden Ring" button to launch the mod. This uses a built-in [me3](https://me3.help/) to run `randomizer-launcher.me3`.

If the built-in launcher doesn't work or if you're on Linux, you can run `randomizer-launcher.me3` yourself without needing to have randomizer open, but **make sure** you have the latest version of me3 installed first (at least v0.13.0 is required to support Elden Ring 1.17). Manually editing `randomizer-launcher.me3` or moving around files after generating it can break the mod.

The game launches using an alternate save file which will not affect your main save, with a name formatted like `ap-<seed>-<slot>.sl2`. To start a run, create a new character. If the room gets recreated from scratch at any point, create a different character for the new room instance.

## Frequently asked questions

### Is there a tracker for this?

The apworld is compatible with [Universal Tracker](https://archipelago.miraheze.org/wiki/Universal_Tracker) and as of v0.1.3 does not need your original yaml. When priority locations are used, they are shown at the top of the list with an asterisk by their name.

Map support is in progress. When it is available, instructions will be added here.

See also the [Location Guide](./en_location_guide.md) to read tracked and hinted locations.

### Can I play on Linux?

A native Linux randomizer program is planned at some point, which also requires implementing Linux support for some dependent libraries. Meanwhile, it should work to run `EldenRingArchipelagoRandomizer.exe` with ProtonTricks and then run Elden Ring with the same Proton version. Instrucitons by Lexipherous:

1. Download ProtonTricks. The flatpak version is recommended.
2. In Steam, add a non-Steam game. Browse your files and find the `EldenRingArchipelagoRandomizer.exe` you downloaded, and set its Proton version in Steam compatibility settings.
3. In Steam, run `EldenRingArchipelagoRandomizer.exe`. You will see a popup that requires a a runtime. Click the download button and download the needed exe file. It should look something like: `windowsdesktop-runtime-8.x.xx-win-x64.exe`.
4. Open ProtonTricks and find "Non-Steam shortcut: EldenRingArchipelagoRandomizer.exe" in the list.
5. The window will disappear, and in some cases the next window might take a bit of time to open, around 20 seconds.
6. Once the next window pops up, select "Select the default wineprefix".
7. Now select "Run an arbitrary executable (.exe/.msi/.msu)".
8. In the file browser, locate the pick the windows runtime .exe you downloaded you downloaded in step 3, and follow the steps of the installer.
9. Once installed, you can close ProtonTricks.
10. In Steam, you can now run `EldenRingArchipelagoRandomizer.exe`.

After completing randomization, it may work better to install native Linux [me3](https://me3.help/) to run `randomizer-launcher.me3` instead of using the launch button in the randomizer.

### Can I use this with Seamless Co-op?

It is an eventual goal of this Archipelago implementation to work with Seamless Co-op, for players in different slots and/or in the same slot, but this has not been tested at all and is unlikely to work currently.

### Can I use this with other mods?

Cosmetic mods can be added with "Merge other mod" before generating mod files in randomizer. Mods which add, remove, or edit item locations in the game are very likely to be incompatible with Archipelago because of strict validation that all assigned items and locations are accessible in-game.

Compatible dll mods can be added with "Add dll mods" before generating mod files in the randomizer. After adding them, refresh Archipelago data if needed, check all options again if you manually changed any, and run "Randomizer for Archipelago" again. The launcher will be updated to include the mod.

### Can I set Elden Ring to a language other than English?
There is partial support for playing in other languages, as in-game messages will not be broken or missing. Still, many item names and messages will appear in English only, especially ones which come from Archipelago.

As of v0.1, the mod does not support the Japanese version of eldenring.exe because none of the client development team have access to the alternate exe.

## Troubleshooting

If you're having trouble launching the game with the mod, see the troubleshooting section on the [main randomizer mod page](https://www.nexusmods.com/eldenring/mods/428?tab=description) which partly applies here.

If the launcher button shows the me3 console but doesn't actually start the game, you can try running `randomizer-launcher.me3` directly. Make sure you're using the latest version of [me3](https://me3.help/) before doing this. Alternatively, this issue usually goes away after 2-3 attempts of trying to launch.

If you see an error message pop up in-game followed by the game closing, this is likely a client error. Further information may be logged in the `dll\log` directory. Note the client dll is currently a debug build because the release build crashes, which will be addressed in the future.

Otherwise, if the game stutters and crashes while using enemy randomizer, make sure you're launching the game with `RandomizerCrashFix.dll`. Also, verify integrity of installed files in Steam, because they can get accidentally corrupted surprisingly often.
