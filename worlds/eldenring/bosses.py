from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class ERBossInfo:
    """The set of locations a given boss location blocks access to."""

    name: str
    """The boss's name."""

    type: list[str]
    """The region/type that this is the boss of."""

    id: int
    """The game's ID for this particular boss."""

    flag: int
    """The event flag that's set when this boss is defeated."""

    dlc: bool = False
    """This boss appears in one of the game's DLCs."""
    
    dungeon: bool = False
    """This boss appears in a underground dungeon."""
    
    missable: bool = False
    """This boss is missable."""
    
    allow_rykard: bool = False
    """Which bosses can be replaced by Rykard."""

    locations: list[str] = field(default_factory=list)
    """Locations the boss blocks so we can do can_get location."""

# https://github.com/vawser/Smithbox/blob/main/src/Smithbox.Data/Assets/Aliases/ER/EventFlags.json for flag id
base_bosses = [
    # MARK: Limgrave
    ERBossInfo("Solder of Godrick", ["Limgrave"], 18000850, 18000850, locations=[]), # doesn't have an item behind it since emote spots dont count
    ERBossInfo("Tree Sentinel (LG)", ["Limgrave", "Overworld"], 1042360800, 1042360800,
        locations=[
            "LG/TFS: Golden Halberd - first field boss"
        ]
    ),
    ERBossInfo("Flying Dragon Agheel (LG)", ["Limgrave", "Overworld"], 1043360800, 1043360800,
        locations=[
            "LG/DBR: Dragon Heart - boss drop N of DBR"
        ]
    ),
    ERBossInfo("Night's Cavalry (LG)", ["Limgrave", "Overworld"], 1043370340, 1043370800,
        locations=[
            "LG/ALN: Ash of War: Repeating Thrust - night boss drop to SE"
        ]
    ),
    ERBossInfo("Bloodhound Knight Darriwil (LG)", ["Limgrave", "Overworld", "Evergaol"], 1044350800, 1044350800,
        locations=[
            "LG/(FHE): Bloodhound's Fang - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Tibia Mariner (LG)", ["Limgrave", "Overworld"], 1045390800, 1045390800,
        locations=[
            "LG/(SWV): Deathroot - boss drop",
            "LG/(SWV): Skeletal Militiaman Ashes - boss drop"
        ]
    ),
    ERBossInfo("Mad Pumpkin Head (LG/WR)", ["Limgrave", "Overworld", "Ruin"], 1044360800, 1044360800,
        locations=[
            # "LG/(WR): Glintstone Pebble - Sellen Shop",
            # "LG/(WR): Glintstone Stars - Sellen Shop",
            # "LG/(WR): Crystal Barrage - Sellen Shop",
            # "LG/(WR): Glintstone Arc - Sellen Shop",
            # "LG/(WR): Scholar's Armament - Sellen Shop",
            # "LG/(WR): Scholar's Shield - Sellen Shop",
        ]
    ),
    ERBossInfo("Crucible Knight (LG)", ["Limgrave", "Overworld", "Evergaol"], 1042370800, 1042370800,
        locations=[
            "LG/(SE): Aspects of the Crucible: Tail - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Deathbird (LG)", ["Limgrave", "Overworld"], 1042380800, 1042380800,
        locations=[
            "LG/WS: Blue-Feathered Branchsword - night boss drop SE of WS"
        ]
    ),
    ERBossInfo("Bell Bearing Hunter (LG)", ["Limgrave", "Overworld"], 1042380850, 1042380850,
        locations=[
            "LG/(WS): Bone Peddler's Bell Bearing - night boss drop"
        ]
    ),
    # limgrave dungeons
    ERBossInfo("Patches (LG/MCV)", ["Limgrave", "Dungeon", "Cave"], 31000800, 31000800, dungeon=True, missable=True, locations=[]), # can be missed if rykard is killed first
    ERBossInfo("Ulcerated Tree Spirit (LG/FHG)", ["Limgrave", "Dungeon", "Grave"], 18000800, 18000800, dungeon=True,
        locations=[
            "LG/(FHG): Golden Seed - boss drop",
            "LG/(FHG): Banished Knight Oleg - boss drop"
        ]
    ),
    ERBossInfo("Erdtree Burial Watchdog (LG/SC)", ["Limgrave", "Dungeon", "Catacomb"], 30020800, 30020800, dungeon=True,
        locations=[
            "LG/(SC): Noble Sorcerer Ashes - boss drop"
        ]
    ),
    ERBossInfo("Grave Warden Duelist (LG/MCC)", ["Limgrave", "Dungeon", "Catacomb"], 30040800, 30040800, dungeon=True,
        locations=[
            "LG/(MCC): Banished Knight Engvall - boss drop"
        ]
    ),
    ERBossInfo("Black Knife Assassin (LG/DC)", ["Limgrave", "Dungeon", "Catacomb"], 30110800, 30110800, dungeon=True,
        locations=[
            "LG/(DC): Assassin's Crimson Dagger - boss drop"
        ]
    ),
    ERBossInfo("Beastman of Farum Azula (LG/GC)", ["Limgrave", "Dungeon", "Cave"], 31030800, 31030800, dungeon=True,
        locations=[
            "LG/(GC): Flamedrake Talisman - boss drop"
        ]
    ),
    ERBossInfo("Demi-Human Chief (LG/CC)", ["Limgrave", "Dungeon", "Cave"], 31150800, 31150800, dungeon=True,
        locations=[
            "LG/(CC): Tailoring Tools - boss drop",
            "LG/(CC): Sewing Needle - boss drop"
        ]
    ),
    ERBossInfo("Guardian Golem (LG/HC)", ["Limgrave", "Dungeon", "Cave"], 31170800, 31170800, dungeon=True,
        locations=[
            "LG/(HC): Blue Dancer Charm - boss drop"
        ]
    ),
    ERBossInfo("Stonedigger Troll (LG/LT)", ["Limgrave", "Dungeon", "Tunnel"], 32010800, 32010800, dungeon=True,
        locations=[
            "LG/(LT): Roar Medallion - boss drop"
        ]
    ),
    
    # MARK: Stormveil
    ERBossInfo("Margit, the Fell Omen (SV)", ["Stormveil Castle", "Main"], 10000850, 10000850,
        locations=[
            "SV/CT: Talisman Pouch - boss drop" # + the entire castle, but im not doing all that
        ]
    ),
    ERBossInfo("Godrick the Grafted (SV)", ["Stormveil Castle", "Remembrance", "Great Rune", "Main"], 10000800, 10000800, allow_rykard=True,
        locations=[
            "SV/SeC: Godrick's Great Rune - mainboss drop",
            "SV/SeC: Remembrance of the Grafted - mainboss drop"
        ]
    ),

    # MARK: Weeping Peninsula
    ERBossInfo("Ancient Hero of Zamor (WP)", ["Weeping Peninsula", "Overworld", "Evergaol"], 1042330800, 1042330800,
        locations=[
            "WP/(WE): Radagon's Scarseal - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Leonine Misbegotten (WP/CM)", ["Weeping Peninsula", "Castle Morne", "Overworld"], 1043300800, 1043300800, allow_rykard=True,
        locations=[
            "WP/(CM): Grafted Blade Greatsword - boss drop"
        ]
    ),
    ERBossInfo("Erdtree Avatar (WP)", ["Weeping Peninsula", "Overworld"], 1043330800, 1043330800,
        locations=[
            "WP/ME: Opaline Bubbletear - boss drop",
            "WP/ME: Crimsonburst Crystal Tear - boss drop"
        ]
    ),
    ERBossInfo("Deathbird (WP)", ["Weeping Peninsula", "Overworld"], 1044320340, 1044320800,
        locations=[
            "WP/CMR: Sacrificial Axe - night boss drop far to SW"
        ]
    ),
    ERBossInfo("Night's Cavalry (WP)", ["Weeping Peninsula", "Overworld"], 1044320342, 1044320850,
        locations=[
            "WP/CMR: Nightrider Flail - night boss drop to SW",
            "WP/CMR: Ash of War: Barricade Shield - night boss drop to SW"
        ]
    ),
    # weeping dungeons
    ERBossInfo("Cemetery Shade (WP/TCC)", ["Weeping Peninsula", "Dungeon", "Catacomb"], 30000800, 30000800, dungeon=True,
        locations=[
            "WP/(TCC): Lhutel the Headless - boss drop"
        ]
    ),
    ERBossInfo("Erdtree Burial Watchdog (WP/IC)", ["Weeping Peninsula", "Dungeon", "Catacomb"], 30010800, 30010800, dungeon=True,
        locations=[
            "WP/(IC): Demi-Human Ashes - boss drop"
        ]
    ),
    ERBossInfo("Runebear (WP/EC)", ["Weeping Peninsula", "Dungeon", "Cave"], 31010800, 31010800, dungeon=True,
        locations=[
            "WP/(EC): Spelldrake Talisman - boss drop"
        ]
    ),
    ERBossInfo("Miranda the Blighted Bloom (WP/TCV)", ["Weeping Peninsula", "Dungeon", "Cave"], 31020800, 31020800, dungeon=True,
        locations=[
            "WP/(TCV): Viridian Amber Medallion - boss drop"
        ]
    ),
    ERBossInfo("Scaly Misbegotten (WP/MT)", ["Weeping Peninsula", "Dungeon", "Tunnel"], 32000800, 32000800, dungeon=True,
        locations=[
            "WP/(MT): Rusted Anchor - boss drop"
        ]
    ),
    
    # MARK: SE Underground
    ERBossInfo("Ancestor Spirit (SR)", ["Siofra River", "Underground"], 12080800, 12080800, allow_rykard=True,
        locations=[
            "SR/(HG): Ancestral Follower Ashes - boss drop"
        ]
    ),
    ERBossInfo("Dragonkin Soldier (SR)", ["Siofra River", "Underground"], 12020830, 12020830,
        locations=[
            "SR/WW: Dragon Halberd - upper siofra, boss drop"
        ]
    ),
    ERBossInfo("Mimic Tear (NR)", ["Nokron, Eternal City", "Underground"], 12020850, 12020850, allow_rykard=True,
        locations=[
            "NR/NEC: Silver Tear Mask - boss drop",
            "NR/NEC: Larval Tear x2 - boss drop"
        ]
    ),
    ERBossInfo("Valiant Gargoyles (NR)", ["Nokron, Eternal City", "Underground"], 12020800, 12020800, allow_rykard=True,
        locations=[
            "NR/(SA): Gargoyle's Greatsword - boss drop",
            "NR/(SA): Gargoyle's Twinblade - boss drop",
        ]
    ),
    ERBossInfo("Regal Ancestor Spirit (NR)", ["Nokron, Eternal City", "Underground", "Remembrance"], 12090800, 12090800, allow_rykard=True,
        locations=[
            "NR/(HG): Remembrance of the Regal Ancestor - boss drop"
        ]
    ),
    
    # MARK: N Underground
    ERBossInfo("Crucible Knight Siluria (DD)", ["Deeproot Depths", "Underground"], 12030390, 12030390,
        locations=[
            "DD/TNEC: Siluria's Tree - boss drop way to W by tree stump"
        ]
    ),
    ERBossInfo("Fia's Champions (DD)", ["Deeproot Depths", "Underground"], 12030800, 12030800,
        locations=[
            "DD/AR: Fia's Mist - boss drop"
        ]
    ),
    ERBossInfo("Lichdragon Fortissax (DD)", ["Deeproot Depths", "Underground", "Remembrance"], 12030850, 12030850, missable=True, allow_rykard=True,
        locations=[
            #"DD/PDT: Remembrance of the Lichdragon - mainboss drop"
        ]
    ), # uncomment once made unmissable
    
    # MARK: Liurnia of The Lakes
    ERBossInfo("Erdtree Avatar (LL/MEW)", ["Liurnia of The Lakes", "Overworld"], 1033430800, 1033430800,
        locations=[
            "LL/MEW: Cerulean Crystal Tear - boss drop, Minor Erdtree W",
            "LL/MEW: Ruptured Crystal Tear - boss drop, Minor Erdtree W"
        ]
    ),
    ERBossInfo("Bols, Carian Knight (LL)", ["Liurnia of The Lakes", "Overworld", "Evergaol"], 1033450800, 1033450800,
        locations=[
            "LL/(CE): Greatblade Phalanx - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Glintstone Dragon Smarag (LL)", ["Liurnia of The Lakes", "Overworld"], 1034450800, 1034450800,
        locations=[
            "LL/TQ: Dragon Heart - boss drop to N"
        ]
    ),
    ERBossInfo("Omenkiller (LL)", ["Liurnia of The Lakes", "Overworld"], 1035420800, 1035420800,
        locations=[
            "LL/(VA): Crucible Knot Talisman - boss drop"
        ]
    ),
    ERBossInfo("Loretta, Royal Knight (LL)", ["Liurnia of The Lakes", "Overworld"], 1035500800, 1035500800, allow_rykard=True,
        locations=[
            "LL/(CM): Loretta's Greatbow - boss drop",
            "LL/(CM): Ash of War: Loretta's Slash - boss drop"
        ]
    ),
    ERBossInfo("Death Rite Bird (LL)", ["Liurnia of The Lakes", "Overworld"], 1036450340, 1036450800,
        locations=[
            "LL/GTN: Ancient Death Rancor - night boss drop to S"
        ]
    ),
    ERBossInfo("Deathbird (LL)", ["Liurnia of The Lakes", "Overworld"], 1037420340, 1037420800,
        locations=[
            "LL/SeI: Red-Feathered Branchsword - night boss drop to NE"
        ]
    ),
    ERBossInfo("Bell Bearing Hunter (LL)", ["Liurnia of The Lakes", "Overworld"], 1037460800, 1037460800,
        locations=[
            "LL/(CV): Meat Peddler's Bell Bearing - night boss drop"
        ]
    ),
    ERBossInfo("Adan, Thief of Fire (LL)", ["Liurnia of The Lakes", "Overworld", "Evergaol"], 1038410800, 1038410800,
        locations=[
            "LL/(ME): Flame of the Fell God - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Night's Cavalry (LL/GTB)", ["Liurnia of The Lakes", "Overworld"], 1036480340, 1036480800,
        locations=[
            "LL/GTB: Ash of War: Ice Spear - night boss drop to SE"
        ]
    ),
    ERBossInfo("Tibia Mariner (LL)", ["Liurnia of The Lakes", "Overworld"], 1039440800, 1039440800,
        locations=[
            "LL/AS: Deathroot - boss drop SE of AS",
            "LL/AS: Skeletal Bandit Ashes - boss drop SE of AS"
        ]
    ),
    ERBossInfo("Night's Cavalry (LL/BC)", ["Liurnia of The Lakes", "Overworld"], 1039430340, 1039430800,
        locations=[
            "LL/BC: Nightrider Glaive - night boss drop S of BC",
            "LL/BC: Ash of War: Giant Hunt - night boss drop S of BC"
        ]
    ),
    ERBossInfo("Erdtree Avatar (LL/MEE)", ["Liurnia of The Lakes", "Overworld"], 1038480800, 1038480800,
        locations=[
            "LL/MEE: Magic-Shrouding Cracked Tear - boss drop, Minor Erdtree E",
            "LL/MEE: Lightning-Shrouding Cracked Tear - boss drop, Minor Erdtree E",
            "LL/MEE: Holy-Shrouding Cracked Tear - boss drop, Minor Erdtree E"
        ]
    ),
    ERBossInfo("Onyx Lord (LL)", ["Liurnia of The Lakes", "Overworld", "Evergaol"], 1036500800, 1036500800,
        locations=[
            "LL/(RGE): Meteorite - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Royal Revenant (LL/KR)", ["Liurnia of The Lakes", "Overworld", "Ruin"], 1034480800, 1034480800,
        locations=[
            "LL/(KR): Frozen Needle - in chest E side of ruins underground behind illusory floor"
        ]
    ),
    # liurnia dungeons
    ERBossInfo("Crystalians (LL/ACC)", ["Liurnia of The Lakes", "Dungeon", "Cave"], 31060800, 31060800, dungeon=True,
        locations=[
            "LL/(ACC): Crystal Release - boss drop"
        ]
    ),
    ERBossInfo("Spirit-Caller Snail (LL/REC)", ["Liurnia of The Lakes", "Dungeon", "Catacomb"], 30030800, 30030800, dungeon=True,
        locations=[
            "LL/(REC): Glintstone Sorcerer Ashes - boss drop"
        ]
    ),
    ERBossInfo("Cemetery Shade (LL/BKC)", ["Liurnia of The Lakes", "Dungeon", "Catacomb"], 30050800, 30050800, dungeon=True,
        locations=[
            "LL/(BKC): Twinsage Sorcerer Ashes - boss drop"
        ]
    ),
    ERBossInfo("Black Knife Assassin (LL/BKC)", ["Liurnia of The Lakes", "Dungeon", "Catacomb"], 30050850, 30050850, dungeon=True,
        locations=[
            "LL/(BKC): Assassin's Cerulean Dagger - alt boss drop",
            "LL/(BKC): Black Knifeprint - alt boss drop"
        ]
    ),
    ERBossInfo("Erdtree Burial Watchdog (LL/CC)", ["Liurnia of The Lakes", "Dungeon", "Catacomb"], 30060800, 30060800, dungeon=True,
        locations=[
            "LL/(CC): Kaiden Sellsword Ashes - boss drop"
        ]
    ),
    ERBossInfo("Cleanrot Knight (LL/SC)", ["Liurnia of The Lakes", "Dungeon", "Cave"], 31040800, 31040800, dungeon=True,
        locations=[
            "LL/(SC): Winged Sword Insignia - boss drop"
        ]
    ),
    ERBossInfo("Bloodhound Knight (LL/LCC)", ["Liurnia of The Lakes", "Dungeon", "Cave"], 31050800, 31050800, dungeon=True,
        locations=[
            "LL/(LCC): Cerulean Amber Medallion - boss drop"
        ]
    ),
    ERBossInfo("Crystalian - Ring Blade (LL/RLCT)", ["Liurnia of The Lakes", "Dungeon", "Tunnel"], 32020800, 32020800, dungeon=True,
        locations=[
            "LL/(RLCT): Smithing-Stone Miner's Bell Bearing [1] - boss drop"
        ]
    ),
    ERBossInfo("Magma Wyrm Makar (RSP)", ["Liurnia of The Lakes", "Ruin-Strewn Precipice", "Dungeon", "Main"], 39200800, 39200800, dungeon=True, allow_rykard=True,
        locations=[
            "RSP/RSPO: Magma Wyrm's Scalesword - boss drop",
            "RSP/RSPO: Dragon Heart - boss drop"
        ]
    ),
    # other
    ERBossInfo("Grafted Scion (CA)", ["Chapel of Anticipation"], 10010800, 10010800,
        locations=[
            "LL/(TFB/CA): Ornamental Straight Sword - boss drop",
            "LL/(TFB/CA): Golden Beast Crest Shield - boss drop"
        ]
    ),
    
    # MARK: SW Underground
    ERBossInfo("Dragonkin Soldier of Nokstella (AR)", ["Ainsel River", "Underground"], 12010800, 12010800, allow_rykard=True,
        locations=[
            "AR/ARD: Frozen Lightning Spear - boss drop"
        ]
    ),
    ERBossInfo("Dragonkin Soldier (LR)", ["Lake of Rot", "Underground"], 12010850, 12010850,
        locations=[
            "LR/LRS: Dragonscale Blade - boss drop"
        ]
    ),
    ERBossInfo("Astel, Naturalborn of the Void (LR)", ["Lake of Rot", "Underground", "Remembrance"], 12040800, 12040800, allow_rykard=True,
        locations=[
            "LR: Remembrance of the Naturalborn - mainboss drop"
        ]
    ),
    
    # MARK: Moonlight Altar
    ERBossInfo("Alecto, Black Knife Ringleader (MA)", ["Moonlight Altar", "Evergaol"], 1033420800, 1033420800,
        locations=[
            "MA/(RE): Black Knife Tiche - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Glintstone Dragon Adula (MA)", ["Moonlight Altar"], 1034420800, 1034420800,
        locations=[
            "MA/MA: Adula's Moonblade - boss drop to NE",
            "MA/MA: Dragon Heart x3 - boss drop to NE"
        ]
    ),
    
    # MARK: Raya Lucaria Academy
    ERBossInfo("Red Wolf of Radagon (RLA)", ["Raya Lucaria Academy", "Main"], 14000850, 14000850,
        locations=[
            "RLA/SC: Memory Stone - boss drop"
        ]
    ),
    ERBossInfo("Rennala, Queen of the Full Moon (Phase 1) (RLA)", [], 14000801, None, locations=[]),
    ERBossInfo("Rennala, Queen of the Full Moon (Phase 2) (RLA)", ["Raya Lucaria Academy", "Remembrance", "Great Rune", "Main"], 14000800, 14000800, allow_rykard=True,
        locations=[
            "RLA/DB: Great Rune of the Unborn - mainboss drop",
            "RLA/DB: Remembrance of the Full Moon Queen - mainboss drop"
        ]
    ),
    
    # MARK: Caelid
    ERBossInfo("Erdtree Avatar (CL)", ["Caelid", "Overworld"], 1047400800, 1047400800,
        locations=[
            "CL/MEW: Greenburst Crystal Tear - boss drop",
            "CL/MEW: Flame-Shrouding Cracked Tear - boss drop"
        ]
    ),
    ERBossInfo("Decaying Ekzykes (CL)", ["Caelid", "Overworld"], 1048370800, 1048370800,
        locations=[
            "CL/CHS: Dragon Heart - boss drop to SE"
        ]
    ),
    ERBossInfo("Mad Pumpkin Head Duo (CL/CR)", ["Caelid", "Overworld", "Ruin"], 1048400800, 1048400800,
        locations=[
            "CL/(CR): Visage Shield - in chest after boss"
        ]
    ),
    ERBossInfo("Night's Cavalry (CL)", ["Caelid", "Overworld"], 1049370800, 1049370800,
        locations=[
            "CL/SASB: Ash of War: Poison Moth Flight - night boss drop to SW"
        ]
    ),
    ERBossInfo("Death Rite Bird (CL)", ["Caelid", "Overworld"], 1049370850, 1049370850,
        locations=[
            "CL/SASB: Death's Poker - night boss drop to SE"
        ]
    ),
    ERBossInfo("Commander O'Neil (CL)", ["Caelid", "Overworld"], 1049380800, 1049380800,
        locations=[
            "CL/IA: Commander's Standard - boss drop to SE",
            "CL/IA: Unalloyed Gold Needle (Broken) - boss drop to SE"
        ]
    ),
    ERBossInfo("Nox Swordstress & Nox Priest (CL)", ["Caelid", "Overworld"], 1049390800, 1049390800,
        locations=[
            "CL/(STS): Nox Flowing Sword - boss drop"
        ]
    ),
    # caelid dungeons
    ERBossInfo("Erdtree Burial Watchdog (CL/MEC)", ["Caelid", "Dungeon", "Catacomb"], 30140800, 30140800, dungeon=True,
        locations=[
            "CL/(MEC): Mad Pumpkin Head Ashes - boss drop"
        ]
    ),
    ERBossInfo("Cemetery Shade (CL/CCC)", ["Caelid", "Dungeon", "Catacomb"], 30150800, 30150800, dungeon=True,
        locations=[
            "CL/(CCC): Kindred of Rot Ashes - boss drop"
        ]
    ),
    ERBossInfo("Putrid Tree Spirit (CL/WDC)", ["Caelid", "Dungeon", "Catacomb"], 30160800, 30160800, dungeon=True,
        locations=[
            "CL/(WDC): Golden Seed - boss drop",
            "CL/(WDC): Redmane Knight Ogha - boss drop"
        ]
    ),
    ERBossInfo("Cleanrot Knight Duo (CL/AC)", ["Caelid", "Dungeon", "Cave"], 31200800, 31200800, dungeon=True,
        locations=[
            "CL/(AC): Gold Scarab - boss drop"
        ]
    ),
    ERBossInfo("Frenzied Duelist (CL/GC)", ["Caelid", "Dungeon", "Cave"], 31210800, 31210800, dungeon=True,
        locations=[
            "CL/(GC): Putrid Corpse Ashes - boss drop"
        ]
    ),
    ERBossInfo("Magma Wyrm (CL/GT)", ["Caelid", "Dungeon", "Tunnel"], 32070800, 32070800, dungeon=True,
        locations=[
            "CL/(GT): Moonveil - boss drop",
            "CL/(GT): Dragon Heart - boss drop"
        ]
    ),
    ERBossInfo("Fallingstar Beast (CL/SCT)", ["Caelid", "Dungeon", "Tunnel"], 32080800, 32080800, dungeon=True,
        locations=[
            "CL/(SCT): Gravity Stone Chunk x10 - boss drop",
            "CL/(SCT): Somberstone Miner's Bell Bearing [1] - boss drop",
            "CL/(SCT): Smithing Stone [7] x5 - boss drop",
            "CL/(SCT): Somber Smithing Stone [6] - boss drop"
        ]
    ),
    
    # Redmane Castle
    ERBossInfo("Crucible Knight / Misbegotten Warrior (CL/RC)", ["Caelid", "Overworld"], 1051360800, 1051360800,
        locations=[
            "CL/(RC): Ruins Greatsword - boss drop"
        ]
    ),
    ERBossInfo("Starscourge Radahn (CL)", ["Caelid", "Overworld", "Remembrance", "Great Rune", "Main"], 1052380800, 1252380800, allow_rykard=True,
        locations=[
            "CL/(WD): Radahn's Great Rune - mainboss drop",
            "CL/(WD): Remembrance of the Starscourge - mainboss drop"
        ]
    ),
    
    # MARK: Dragonbarrow
    ERBossInfo("Bell Bearing Hunter (DB)", ["Dragonbarrow", "Overworld"], 1048410800, 1048410800,
        locations=[
            "DB/(IMS): Gravity Stone Peddler's Bell Bearing - night boss drop"
        ]
    ),
    ERBossInfo("Battlemage Hugues (DB)", ["Dragonbarrow", "Overworld", "Evergaol"], 1049390850, 1049390850,
        locations=[
            "DB/(SE): Battlemage Hugues - Sellia Evergaol"
        ]
    ),
    ERBossInfo("Putrid Avatar (DB)", ["Dragonbarrow", "Overworld"], 1051400800, 1051400800,
        locations=[
            "DB/MEE: Opaline Hardtear - boss drop",
            "DB/MEE: Stonebarb Cracked Tear - boss drop"
        ]
    ),
    ERBossInfo("Black Blade Kindred (DB)", ["Dragonbarrow", "Overworld"], 1051430800, 1051430800,
        locations=[
            "DB/BS: Gargoyle's Blackblade - boss drop SE of BS",
            "DB/BS: Gargoyle's Black Halberd - boss drop SE of BS"
        ]
    ),
    ERBossInfo("Flying Dragon Greyll (DB)", ["Dragonbarrow", "Overworld"], 1052410800, 1052410800,
        locations=[
            "DB/FG: Dragon Heart - boss drop to S"
        ]
    ),
    ERBossInfo("Night's Cavalry (DB)", ["Dragonbarrow", "Overworld"], 1052410850, 1052410850,
        locations=[
            "DB/LR: Ash of War: Bloodhound's Step - night boss drop N of LR"
        ]
    ),
    # dragonbarrow dungeons
    ERBossInfo("Beastman of Farum Azula (DB/DC)", ["Dragonbarrow", "Dungeon", "Cave"], 31100800, 31100800, dungeon=True,
        locations=[
            "DB/(DC): Flamedrake Talisman +2 - boss drop"
        ]
    ),
    ERBossInfo("Crystalians - Trio (DB/SH)", ["Dragonbarrow", "Dungeon", "Cave"], 31110800, 31110800, dungeon=True,
        locations=[
            "DB/(SH): Crystal Torrent - boss drop"
        ]
    ),
    ERBossInfo("Godskin Apostle (DB/DT)", ["Dragonbarrow", "Dungeon", "Tunnel"], 34130800, 34130800, dungeon=True,
        locations=[
            "DB/(DT): Godskin Apostle Hood - boss drop",
            "DB/(DT): Godskin Apostle Robe - boss drop",
            "DB/(DT): Godskin Apostle Bracelets - boss drop",
            "DB/(DT): Godskin Apostle Trousers - boss drop",
        ]
    ),

    # MARK: Altus Plateau
    
    ERBossInfo("Demi-Human Queen Gilika (AP/LR)", ["Altus Plateau", "Overworld"], 1038510800, 1038510800,
        locations=[
            "AP/LR: Ritual Sword Talisman - in chest after boss underground"
        ]
    ),
    ERBossInfo("Ancient Dragon Lansseax (AP)", ["Altus Plateau", "Overworld"], 1041520800, 1041520800, # early altus 1037510800   late altus 1041520800
        locations=[
            "AP/RP: Lansseax's Glaive - boss drop up hill to SW or NE of AC grace"
        ]
    ),
    ERBossInfo("Tibia Mariner (AP)", ["Altus Plateau", "Overworld"], 1038520340, 1038520800,
        locations=[
            "AP/WhR: Deathroot - boss drop",
            "AP/WhR: Tibia's Summons - boss drop"
        ]
    ),
    ERBossInfo("Godefroy the Grafted (AP)", ["Altus Plateau", "Overworld", "Evergaol"], 1039500800, 1039500800,
        locations=[
            "AP/GLE: Godfrey Icon - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Night's Cavalry (AP)", ["Altus Plateau", "Overworld"], 1039510800, 1039510800,
        locations=[
            "AP/AHJ: Ash of War: Shared Order - night boss drop to SW"
        ]
    ),
    ERBossInfo("Elemer of the Briar (AP)", ["Altus Plateau", "The Shaded Castle"], 1039540800, 1039540800,
        locations=[
            "TSC/SCIG: Marais Executioner's Sword - boss drop",
            "TSC/SCIG: Briar Greatshield - boss drop"
        ]
    ),
    ERBossInfo("Black Knife Assassin (AP)", ["Altus Plateau", "Overworld"], 1040520800, 1040520800,
        locations=[
            "AP/SHG: Black Knife - boss drop guarding SHG"
        ]
    ),
    ERBossInfo("Sanguine Noble (AP/WbR)", ["Altus Plateau", "Overworld", "Ruin"], 1040530800, 1040530800,
        locations=[
            "AP/(WbR): Bloody Helice - in chest after boss underground"
        ]
    ),
    ERBossInfo("Fallingstar Beast (AP)", ["Altus Plateau", "Overworld"], 1041500800, 1041500800,
        locations=[
            "AP/AHJ: Gravity Stone Chunk x10 - boss drop S of great stairs in meteor crater",
            "AP/AHJ: Smithing Stone [6] x5 - boss drop S of great stairs in meteor crater",
            "AP/AHJ: Somber Smithing Stone [5] - boss drop S of great stairs in meteor crater"
        ]
    ),
    ERBossInfo("Tree Sentinels (AP)", ["Altus Plateau", "Overworld"], 1041510800, 1041510800, # Other sentinel is 1041510801
        locations=[
            "AP/AHJ: Erdtree Greatshield - boss drop duo to E top of great stairs",
            "AP/AHJ: Hero's Rune [1] - boss drop duo to E top of great stairs",
        ]
    ),
    ERBossInfo("Wormface (AP)", ["Altus Plateau", "Overworld"], 1041530800, 1041530800,
        locations=[
            "AP/ME: Crimsonspill Crystal Tear - boss drop, Minor Erdtree",
            "AP/ME: Speckled Hardtear - boss drop, Minor Erdtree"
        ]
    ),
    ERBossInfo("Godskin Apostle (AP)", ["Altus Plateau", "Overworld"], 1042550800, 1042550800,
        locations=[
            "AP/(DWV): Godskin Peeler - boss drop",
            "AP/(DWV): Scouring Black Flame - boss drop"
        ]
    ),
    # altus dungeons
    ERBossInfo("Ancient Hero of Zamor (AP/SHG)", ["Altus Plateau", "Dungeon", "Grave"], 30080800, 30080800, dungeon=True,
        locations=[
            "AP/(SHG): Ancient Dragon Knight Kristoff - boss drop"
        ]
    ),
    ERBossInfo("Perfumer Tricia & Misbegotten Warrior (AP/UC)", ["Altus Plateau", "Dungeon", "Catacomb"], 30120800, 30120800, dungeon=True,
        locations=[
            "AP/(UC): Perfumer Tricia - boss drop"
        ]
    ),
    ERBossInfo("Omenkiller & Miranda the Blighted Bloom (AP/PG)", ["Altus Plateau", "Dungeon", "Cave"], 31180800, 31180800, dungeon=True,
        locations=[
            "AP/(PG): Great Omenkiller Cleaver - boss drop"
        ]
    ),
    ERBossInfo("Black Knife Assassin (AP/SCV)", ["Altus Plateau", "Dungeon", "Cave"], 31190800, 31190800, dungeon=True,
        locations=[
            "AP/(SCV): Concealing Veil - boss drop"
        ]
    ),
    ERBossInfo("Necromancer Garris (AP/SCV)", ["Altus Plateau", "Dungeon", "Cave"], 31190850, 31190850, dungeon=True,
        locations=[
            "AP/(SCV): Family Heads - hidden boss drop"
        ]
    ),
    ERBossInfo("Stonedigger Troll (AP/OAT)", ["Altus Plateau", "Dungeon", "Tunnel"], 32040800, 32040800, dungeon=True,
        locations=[
            "AP/(OAT): Great Club - boss drop"
        ]
    ),
    ERBossInfo("Crystalians - Ringblade/Spear (AP/AT)", ["Altus Plateau", "Dungeon", "Tunnel"], 32050800, 32050800, dungeon=True,
        locations=[
            "AP/(AT): Somberstone Miner's Bell Bearing [2] - boss drop"
        ]
    ),
   
    # MARK: Capital Outskirts
    ERBossInfo("Deathbird (CO)", ["Capital Outskirts", "Overworld"], 1044530800, 1044530800,
        locations=[
            "CO/HMS: Twinbird Kite Shield - night boss drop to NE in block flower field"
        ]
    ),
    ERBossInfo("Bell Bearing Hunter (CO)", ["Capital Outskirts", "Overworld"], 1043530800, 1043530800,
        locations=[
            "CO/(HMS): Medicine Peddler's Bell Bearing - night boss drop"
        ]
    ),
    ERBossInfo("Draconic Tree Sentinel (CO)", ["Capital Outskirts", "Overworld", "Main"], 1045520800, 1045520800, missable=True,
        locations=[
            # "CO: Dragon Greatclaw - capital great rune gate boss drop",
            # "CO: Dragonclaw Shield - capital great rune gate boss drop"
        ] # marked missable for now
    ),
    # capital outskirts dungeons
    ERBossInfo("Crucible Knight & Crucible Knight Ordovis (CO/AHG)", ["Capital Outskirts", "Dungeon", "Grave"], 30100800, 30100800, dungeon=True,
        locations=[
            "CO/(AHG): Ordovis's Greatsword - boss drop",
            "CO/(AHG): Crucible Axe Helm - boss drop",
            "CO/(AHG): Crucible Axe Armor - boss drop",
            "CO/(AHG): Crucible Gauntlets - boss drop",
            "CO/(AHG): Crucible Greaves - boss drop"
        ]
    ),
    ERBossInfo("Grave Warden Duelist (CO/AST)", ["Capital Outskirts", "Dungeon", "Catacomb"], 30130800, 30130800, dungeon=True,
        locations=[
            "CO/(AST): Soldjars of Fortune Ashes - boss drop"
        ]
    ),
    ERBossInfo("Onyx Lord (CO/ST)", ["Capital Outskirts", "Dungeon", "Tunnel"], 34120800, 34120800, dungeon=True,
        locations=[
            "CO/(ST): Onyx Lord's Greatsword - boss drop"
        ]
    ),
    
    # MARK: Mt. Gelmir
    ERBossInfo("Magma Wyrm (MtG)", ["Mt. Gelmir", "Overworld"], 1035530800, 1035530800,
        locations=[
            "MtG/FL: Dragon Heart - boss drop S of FL in magma lake"
        ]
    ),
    ERBossInfo("Full-Grown Fallingstar Beast (MtG)", ["Mt. Gelmir", "Overworld"], 1036540800, 1036540800,
        locations=[
            "MtG/NMGC: Fallingstar Beast Jaw - boss drop",
            "MtG/NMGC: Smithing Stone [6] x5 - boss drop",
            "MtG/NMGC: Somber Smithing Stone [6] - boss drop"
        ]
    ),
    ERBossInfo("Demi-Human Queen Maggie (MtG)", ["Mt. Gelmir", "Overworld"], 1037530800, 1037530800,
        locations=[
            "MtG/PSA: Memory Stone - boss drop to S"
        ]
    ),
    ERBossInfo("Ulcerated Tree Spirit (MtG)", ["Mt. Gelmir", "Overworld"], 1037540810, 1037540810,
        locations=[
            "MtG/ME: Leaden Hardtear - boss drop, Minor Erdtree",
            "MtG/ME: Cerulean Hidden Tear - boss drop, Minor Erdtree"
        ]
    ),
    # gelmir dungeons
    ERBossInfo("Erdtree Burial Watchdog (MtG/WC)", ["Mt. Gelmir", "Dungeon", "Catacomb"], 30070800, 30070800, dungeon=True,
        locations=[
            "MtG/(WC): Glovewort Picker's Bell Bearing [1] - boss drop"
        ]
    ),
    ERBossInfo("Red Wolf of the Champion (MtG/GHG)", ["Mt. Gelmir", "Dungeon", "Grave"], 30090800, 30090800, dungeon=True,
        locations=[
            "MtG/(GHG): Bloodhound Knight Floh - boss drop"
        ]
    ),
    ERBossInfo("Kindred of Rot (MtG/SC)", ["Mt. Gelmir", "Dungeon", "Cave"], 31070800, 31070800, dungeon=True,
        locations=[
            "MtG/(SC): Kindred of Rot's Exultation - boss drop"
        ]
    ),
    ERBossInfo("Demi-Human Queen Margot (MtG/VC)", ["Mt. Gelmir", "Dungeon", "Cave"], 31090800, 31090800, dungeon=True,
        locations=[
            "MtG/(VC): Jar Cannon - boss drop"
        ]
    ),
    
    # MARK: Volcano Manor
    ERBossInfo("God-Devouring Serpent (VM)", [], 16000801, None, allow_rykard=True, locations=[]),
    ERBossInfo("Rykard, Lord of Blasphemy (VM)", ["Volcano Manor", "Remembrance", "Great Rune", "Main"], 16000800, 16000800, allow_rykard=True,
        locations=[
            "VM/AP: Rykard's Great Rune - mainboss drop",
            "VM/AP: Remembrance of the Blasphemous - mainboss drop"
        ]
    ),
    ERBossInfo("Abductor Virgins (VM)", ["Volcano Manor", "Dungeon"], 16000860, 16000860, dungeon=True,
        locations=[
            "(VM)/SIC: Inquisitor's Girandole - boss drop, from RLA warp"
        ]
    ),
    ERBossInfo("Godskin Noble (VM)", ["Volcano Manor", "Main"], 16000850, 16000850,
        locations=[
            "VM/GH: Godskin Stitcher - boss drop",
            "VM/GH: Noble Presence - boss drop"
        ]
    ),
    
    # MARK: Leyndell, Royal Capital
    ERBossInfo("Godfrey, First Elden Lord (LRC)", ["Leyndell, Royal Capital", "Main"], 11000850, 11000850,
        locations=[
            "LRC/WCR: Talisman Pouch - mainboss drop"
        ]
    ),
    ERBossInfo("Morgott, The Omen King (LRC)", ["Leyndell, Royal Capital", "Remembrance", "Great Rune", "Main"], 11000800, 11000800,
        locations=[
            "LRC/QB: Morgott's Great Rune - mainboss drop",
            "LRC/QB: Remembrance of the Omen King - mainboss drop"
        ]
    ),
    
    # MARK: Subterranean Shunning-Grounds
    ERBossInfo("Mohg, the Omen (SSG)", ["Subterranean Shunning-Grounds"], 35000800, 35000800,
        locations=[
            "SSG/FD: Bloodflame Talons - boss drop"
        ]
    ),
    ERBossInfo("Esgar, Priest of Blood (SSG/LC)", ["Subterranean Shunning-Grounds", "Dungeon", "Catacomb"], 35000850, 35000850, dungeon=True,
        locations=[
            "SSG/(LC): Lord of Blood's Exultation - boss drop"
        ]
    ),
    
    # MARK: Forbidden Lands
    ERBossInfo("Fell Twins (FL)", ["Forbidden Lands", "Overworld"], 34140850, 34140850, allow_rykard=True,
        locations=[
            "DTEA: Omenkiller Rollo - boss drop on way to divine tower"
        ]
    ),
    ERBossInfo("Night's Cavalry (FL)", ["Forbidden Lands", "Overworld"], 1048510800, 1048510800,
        locations=[
            "FL/FL: Ash of War: Phantom Slash - night boss drop to E"
        ]
    ),
    ERBossInfo("Black Blade Kindred (FL)", ["Forbidden Lands", "Overworld"], 1049520800, 1049520800,
        locations=[
            "FL/GLR: Gargoyle's Black Blades - boss drop to S",
            "FL/GLR: Gargoyle's Black Axe - boss drop to S"
        ]
    ),
    
    # MARK: Mountaintops of the Giants
    ERBossInfo("Death Rite Bird (MotG)", ["Mountaintops of the Giants", "Overworld"], 1050570800, 1050570800,
        locations=[
            "MotG/CSMG: Death Ritual Spear - boss drop to W by statue"
        ]
    ),
    ERBossInfo("Commander Niall (MotG/CS)", ["Mountaintops of the Giants", "Overworld", "Main"], 1051570800, 1051570800,
        locations=[
            "MotG/(CS): Veteran's Prosthesis - mainboss drop",
            "MotG/(CS): Haligtree Secret Medallion (Left) - after boss"
        ]
    ),
    ERBossInfo("Erdtree Avatar (MotG)", ["Mountaintops of the Giants", "Overworld"], 1052560800, 1052560800,
        locations=[
            "MotG/(ME): Cerulean Crystal Tear - boss drop",
            "MotG/(ME): Crimson Bubbletear - boss drop"
        ]
    ),
    ERBossInfo("Roundtable Knight Vyke (MotG)", ["Mountaintops of the Giants", "Overworld", "Evergaol"], 1053560800, 1053560800,
        locations=[
            "MotG/(LCE): Fingerprint Helm - boss drop Evergaol",
            "MotG/(LCE): Fingerprint Armor - boss drop Evergaol",
            "MotG/(LCE): Fingerprint Gauntlets - boss drop Evergaol",
            "MotG/(LCE): Fingerprint Greaves - boss drop Evergaol",
            "MotG/(LCE): Vyke's Dragonbolt - boss drop Evergaol"
        ]
    ),
    ERBossInfo("Borealis the Freezing Fog (MotG)", ["Mountaintops of the Giants", "Overworld"], 1054560800, 1254560800,
        locations=[
            "MotG/FR: Dragon Heart - boss drop to SE"
        ]
    ),
    ERBossInfo("Fire Giant (Phase 1) (FP)", [], 1052520801, None, allow_rykard=True, locations=[]),
    ERBossInfo("Fire Giant (Phase 2) (FP)", ["Mountaintops of the Giants", "Overworld", "Remembrance", "Main"], 1052520800, 1252520800, allow_rykard=True,
        locations=[
            "FP/FF: Remembrance of the Fire Giant - mainboss drop"
        ]
    ),
    # mountain dungeons
    ERBossInfo("Ancient Hero of Zamor (FP/GCHG)", ["Mountaintops of the Giants", "Dungeon", "Grave"], 30170800, 30170800, dungeon=True,
        locations=[
            "FP/(GCHG): Zamor Curved Sword - boss drop",
            "FP/(GCHG): Zamor Mask - boss drop",
            "FP/(GCHG): Zamor Armor - boss drop",
            "FP/(GCHG): Zamor Bracelets - boss drop",
            "FP/(GCHG): Zamor Legwraps - boss drop"
        ]
    ),
    ERBossInfo("Ulcerated Tree Spirit (MotG/GMC)", ["Mountaintops of the Giants", "Dungeon", "Catacomb"], 30180800, 30180800, dungeon=True,
        locations=[
            "MotG/(GMC): Glovewort Picker's Bell Bearing [2] - boss drop",
            "MotG/(GMC): Golden Seed - boss drop"
        ]
    ),
    ERBossInfo("Spirit-Caller Snail (MotG/SC)", ["Mountaintops of the Giants", "Dungeon", "Cave"], 31220800, 31220800, dungeon=True,
        locations=[
            "MotG/(SC): Godskin Swaddling Cloth - boss drop",
            "MotG/(SC): Black Flame Ritual - boss drop"
        ]
    ),
    
    # MARK: Farum Azula
    ERBossInfo("Dragonlord Placidusax (FA)", ["Farum Azula", "Remembrance"], 13000830, 13000830, allow_rykard=True,
        locations=[
            "FA/BGB: Remembrance of the Dragonlord - alt mainboss drop"
        ]
    ),
    ERBossInfo("Beast Clergyman (FA)", [], 13000801, None, allow_rykard=True, locations=[] ),
    ERBossInfo("Maliketh, The Black Blade (FA)", ["Farum Azula", "Remembrance", "Main"], 13000800, 13000800, allow_rykard=True,
        locations=[
            "FA/BGB: Remembrance of the Black Blade - mainboss drop"
        ]
    ),
    ERBossInfo("Godskin Duo (FA)", ["Farum Azula", "Main"], 13000850, 13000850,
        locations=[
            "FA/DTT: Smithing-Stone Miner's Bell Bearing [4] - boss drop",
            "FA/DTT: Ash of War: Black Flame Tornado - boss drop"
        ]
    ),
    
    # MARK: Consecrated Snowfield
    ERBossInfo("Night's Cavalry Duo (CS)", ["Consecrated Snowfield", "Overworld"], 1248550800, 1248550800, # Other one is 1248550801
        locations=[
            "CS/ICS: Ancient Dragon Smithing Stone - night boss drop, following caravan to SW",
            "CS/ICS: Night's Cavalry Helm - night boss drop, following caravan to SW",
            "CS/ICS: Night's Cavalry Armor - night boss drop, following caravan to SW",
            "CS/ICS: Night's Cavalry Gauntlets - night boss drop, following caravan to SW",
            "CS/ICS: Night's Cavalry Greaves - night boss drop, following caravan to SW"
        ]
    ),
    ERBossInfo("Death Rite Bird (CS)", ["Consecrated Snowfield", "Overworld"], 1048570800, 1048570800,
        locations=[
            "CS/AD: Explosive Ghostflame - night boss drop to SE on frozen river"
        ]
    ),
    ERBossInfo("Great Wyrm Theodorix (CS)", ["Consecrated Snowfield", "Overworld"], 1050560800, 1050560800,
        locations=[
            "CS/CF: Dragon Heart x3 - boss drop E of CF"
        ]
    ),
    ERBossInfo("Putrid Avatar (CS)", ["Consecrated Snowfield", "Overworld"], 1050570850, 1050570850,
        locations=[
            "CS/ME: Thorny Cracked Tear - boss drop N of ME",
            "CS/ME: Ruptured Crystal Tear - boss drop N of ME"
        ]
    ),
    # snowfield dungeons
    ERBossInfo("Putrid Grave Warden Duelist (CS/CSC)", ["Consecrated Snowfield", "Dungeon", "Catacomb"], 30190800, 30190800, dungeon=True,
        locations=[
            "CS/(CSC): Rotten Gravekeeper Cloak - boss drop",
            "CS/(CSC): Great Grave Glovewort x2 - boss drop"
        ]
    ),
    ERBossInfo("Stray Mimic Tear (CS/HPH)", ["Consecrated Snowfield", "Dungeon", "Catacomb"], 30200800, 30200800, dungeon=True,
        locations=[
            "CS/(HPH): Blackflame Monk Amon - boss drop"
        ]
    ),
    ERBossInfo("Misbegotten Crusader (CS/CF)", ["Consecrated Snowfield", "Dungeon", "Cave"], 31120800, 31120800, dungeon=True,
        locations=[
            "CS/(CF): Golden Order Greatsword - boss drop"
        ]
    ),
    ERBossInfo("Astel, Stars of Darkness (CS/YAT)", ["Consecrated Snowfield", "Dungeon", "Tunnel"], 32110800, 32110800, dungeon=True,
        locations=[
            "CS/(YAT): Meteorite of Astel - boss drop"
        ]
    ),
    
    # MARK: Mohgwyn Palace
    ERBossInfo("Mohg, Lord of Blood (MP)", ["Mohgwyn Palace", "Remembrance", "Great Rune", "Main"], 12050800, 12050800,
        locations=[
            "MP/(MDM): Mohg's Great Rune - mainboss drop",
            "MP/(MDM): Remembrance of the Blood Lord - mainboss drop"
        ]
    ),
    
    # MARK: Miquella's Haligtree
    ERBossInfo("Malenia, Blade of Miquella (EBH)", ["Miquella's Haligtree", "Remembrance", "Great Rune", "Main"], 15000800, 15000800, allow_rykard=True,
        locations=[
            "EBH/HR: Malenia's Great Rune - mainboss drop",
            "EBH/HR: Remembrance of the Rot Goddess - mainboss drop"
        ]
    ),
    ERBossInfo("Loretta, Knight of the Haligtree (MH)", ["Miquella's Haligtree", "Main"], 15000850, 15000850, allow_rykard=True,
        locations=[
            "MH/HTP: Loretta's War Sickle - boss drop",
            "MH/HTP: Loretta's Mastery - boss drop"
        ]
    ),

    # MARK: Leyndell, Ashen Capital
    ERBossInfo("Sir Gideon Ofnir, The All-Knowing (LAC)", ["Leyndell, Ashen Capital", "Main"], 11050850, 11050850,
        locations=[
            "LAC/LCA: Scepter of the All-Knowing - boss drop",
            "LAC/LCA: All-Knowing Helm - boss drop",
            "LAC/LCA: All-Knowing Armor - boss drop",
            "LAC/LCA: All-Knowing Gauntlets - boss drop",
            "LAC/LCA: All-Knowing Greaves - boss drop"
        ]
    ),
    ERBossInfo("Godfrey, First Elden Lord (LAC)", [], 11050801, None, locations=[]),
    ERBossInfo("Hoarah Loux (LAC)", ["Leyndell, Ashen Capital", "Remembrance", "Main"], 11050800, 11050800,
        locations=[
            "LAC/QB: Remembrance of Hoarah Loux - mainboss drop"
        ]
    ),
    ERBossInfo("Radagon of the Golden Order (ET)", [], 19000810, None, allow_rykard=True, locations=[] ),
    ERBossInfo("Elden Beast (ET)", ["Remembrance", "Final", "Main"], 19000800, 19000800, allow_rykard=True,
        locations=[
            "ET: Elden Remembrance - mainboss drop"
        ]
    ),
]

dlc_bosses = [
    # MARK: Gravesite Plain
    ERBossInfo("Ghostflame Dragon (GP)", ["Gravesite Plain", "DLC Overworld"], 2045440800, 2045440800,
        locations=[
            "GP/BG: Dragon Heart - boss drop E of BG",
        ]
    ),
    ERBossInfo("Knight of the Solitary Gaol (GP)", ["Gravesite Plain", "DLC Overworld", "Mausoleum"], 2046410800, 2046410800,
        locations=[
            "GP/(WNM): Greatsword of Solitude - boss drop",
            "GP/(WNM): Helm of Solitude - boss drop",
            "GP/(WNM): Armor of Solitude - boss drop",
            "GP/(WNM): Gauntlets of Solitude - boss drop",
            "GP/(WNM): Greaves of Solitude - boss drop"
        ]
    ),
    ERBossInfo("Death Knight (GP/FRC)", ["Gravesite Plain", "Dungeon", "Catacomb"], 40000800, 40000800, dungeon=True,
        locations=[
            "GP/(FRC): Death Knight's Twin Axes - boss drop",
            "GP/(FRC): Crimson Amber Medallion +3 - boss drop"
        ]
    ),
    ERBossInfo("Demi-Human Swordmaster Onze (GP/BG)", ["Gravesite Plain", "Dungeon", "Gaol"], 41000800, 41000800, dungeon=True,
        locations=[
            "GP/(BG): Demi-Human Swordsman Yosh - boss drop"
        ]
    ),
    ERBossInfo("Ancient Dragon-Man (GP/DP)", ["Gravesite Plain", "Dungeon", "Cave"], 43010800, 43010800,
        locations=[
            "GP/(DP): Dragon-Hunter's Great Katana - boss drop"
        ]
    ),
    
    # MARK: Belurat
    ERBossInfo("Divine Beast Dancing Lion (BTS)", ["Belurat", "DLC Remembrance"], 20000800, 20000800,
        locations=[
            "BTS/SF: Remembrance of the Dancing Lion - mainboss drop",
            "BTS/BTS: Divine Beast Head - boss drop",
            "BTS/TDB: Revered Spirit Ash - on statue after boss",
            "BTS/TDB: Tower of Shadow Message - at the top of the stairs after boss"
        ]
    ),
    
    # MARK: Castle Ensis
    ERBossInfo("Rellana, Twin Moon Knight (CE)", ["Castle Ensis", "DLC Remembrance", "DLC Main"], 2048440800, 2048440800,
        locations=[
            "CE/CLC: Remembrance of the Twin Moon Knight - mainboss drop"
        ]
    ),
    ERBossInfo("Black Knight Garrew (CE)", ["Castle Ensis", "Fort"], 2047450800, 2047450800, # requires scadu altus access
        locations=[
            "CE/(FRF): Black Steel Greatshield - boss drop"
        ]
    ),
    
    # MARK: Ellac River
    ERBossInfo("Chief Bloodfiend (ER)", ["Ellac River", "Dungeon", "Cave"], 43000800, 43000800, dungeon=True,
        locations=[
            "ER/(RC): Bloodfiend Hexer's Ashes - boss drop"
        ]
    ),
    
    # MARK: Cerulean Coast
    ERBossInfo("Dancer of Ranah (CC)", ["Cerulean Coast", "DLC Overworld", "Mausoleum"], 2046380800, 2046380800,
        locations=[
            "CC/CCW: Dancing Blade of Ranah - boss drop",
            "CC/CCW: Dancer's Hood - boss drop",
            "CC/CCW: Dancer's Dress - boss drop",
            "CC/CCW: Dancer's Bracer - boss drop",
            "CC/CCW: Dancer's Trousers - boss drop"
        ]
    ),
    ERBossInfo("Demi-Human Queen Marigga (CC)", ["Cerulean Coast", "DLC Overworld"], 2046400800, 2046400800,
        locations=[
            "CC/CCW: Star-Lined Sword - boss drop"
        ]
    ),
    ERBossInfo("Ghostflame Dragon (CC)", ["Cerulean Coast", "DLC Overworld"], 2048380850, 2048380850,
        locations=[
            "CC/CC: Dragon Heart - boss drop",
            "CC/CC: Somber Ancient Dragon Smithing Stone - boss drop"
        ]
    ),
    
    # Stone Coffin Fissure
    ERBossInfo("Putrescent Knight (SCF)", ["Stone Coffin Fissure", "DLC Remembrance"], 22000800, 22000800, allow_rykard=True,
        locations=[
            "SCF/FD: Remembrance of Putrescence - mainboss drop",
            "SCF/GDP: St. Trina Disciple's Cookbook [3] - right of St. Trina",
            "SCF/GDP: St. Trina's Smile - Thiollier invader drop, after you die to St. Trina four times and tell him your findings",
            "SCF/GDP: St. Trina's Blossom - on St. Trina's body after EI mainboss"
        ]
    ),
    
    # MARK: Jagged Peak
    ERBossInfo("Jagged Peak Drake (JP/DPT)", ["Jagged Peak", "DLC Overworld"], 2049410800, 2049410800,
        locations=[
            "JP/DPT: Dragon Heart - boss drop to E",
            "JP/DPT: Dragonscale Flesh - boss drop to E"
        ]
    ),
    ERBossInfo("Jagged Peak Drake (JP/FJP)", ["Jagged Peak", "DLC Overworld"], 2052400800, 2052400800, # the fighting one
        locations=[
            "JP/FJP: Dragon Heart - boss drop to SE",
            "JP/FJP: Dragonscale Flesh - boss drop to SE"
        ]
    ),
    ERBossInfo("Bayle the Dread (JP)", ["Jagged Peak", "DLC Overworld", "DLC Remembrance"], 2054390800, 2054390800, allow_rykard=True,
        locations=[
            "JP/JPS: Heart of Bayle - mainboss drop"
        ]
    ),
    ERBossInfo("Ancient Dragon Senessax (JP)", ["Jagged Peak", "DLC Overworld"], 2054390850, 2054390850,
        locations=[
            "JP/JPM: Ancient Dragon Smithing Stone - boss drop to S",
            "JP/JPM: Somber Ancient Dragon Smithing Stone - boss drop to S"
        ]
    ),
    
    # MARK: Charo's Hidden Grave
    ERBossInfo("Death Rite Bird (CHG)", ["Charo's Hidden Grave", "DLC Overworld"], 2047390800, 2047390800,
        locations=[
            "CHG/CHG: Ash of War: Ghostflame Call - boss drop to NW in lake"
        ]
    ),
    ERBossInfo("Lamenter (CHG/LG)", ["Charo's Hidden Grave", "Dungeon", "Gaol"], 41020800, 41020800, dungeon=True,
        locations=[
            "CHG/(LG): Lamenter's Mask - boss drop"
        ]
    ),
    
    # MARK: Scadu Altus
    ERBossInfo("Dryleaf Dane (SA)", ["Scadu Altus", "DLC Overworld"], 2049440710, 2049440800, missable=True, locations=[]),
    ERBossInfo("Ghostflame Dragon (SA)", ["Scadu Altus", "DLC Overworld"], 2049430800, 2049430800,
        locations=[
            "SA/MR: Dragon Heart - boss drop to S",
            "SA/MR: Somber Ancient Dragon Smithing Stone - boss drop to S"
        ]
    ),
    ERBossInfo("Black Knight Edreed (SA)", ["Scadu Altus", "DLC Overworld", "Fort"], 2049430850, 2049430850,
        locations=[
            "SA/FR: Ash of War: Aspects of the Crucible: Wings - boss drop to S inside"
        ]
    ),
    ERBossInfo("Ralva the Great Red Bear (SA)", ["Scadu Altus", "DLC Overworld"], 2049450800, 2049450800,
        locations=[
            "SA/HC: Pelt of Ralva - boss drop to N, E before camp, deep woods"
        ]
    ),
    ERBossInfo("Curseblade Labirith (SA/BG)", ["Scadu Altus", "Dungeon", "Gaol"], 41010800, 41010800, dungeon=True,
        locations=[
            "SA/(BG): Curseblade Meera - boss drop"
        ]
    ),
    
    # MARK: Rauh Base
    ERBossInfo("Rugalea the Great Red Bear (RB)", ["Rauh Base", "DLC Overworld"], 2044470800, 2044470800,
        locations=[
            "RB/RN: Roar of Rugalea - boss drop to NW"
        ]
    ),
    ERBossInfo("Red Bear (RB)", ["Rauh Base", "DLC Overworld", "Mausoleum"], 2046450800, 2046450800,
        locations=[
            "RB/(NNM): Red Bear's Claw - boss drop",
            "RB/(NNM): Iron Rivet Armor - boss drop",
            "RB/(NNM): Iron Rivet Gauntlets - boss drop",
            "RB/(NNM): Iron Rivet Greaves - boss drop",
            "RB/(NNM): Fang Helm - boss drop"
        ]
    ),
    ERBossInfo("Death Knight (RB/SRC)", ["Rauh Base", "Dungeon", "Catacomb"], 40010800, 40010800, dungeon=True,
        locations=[
            "RB/(SRC): Death Knight's Longhaft Axe - boss drop",
            "RB/(SRC): Cerulean Amber Medallion +3 - boss drop"
        ]
    ),
    
    # MARK: Shadow Keep
    ERBossInfo("Messmer the Impaler (SK)", [], 21010801, None, locations=[]),
    ERBossInfo("Base Serpent Messmer (SK)", ["Shadow Keep", "DLC Remembrance"], 21010800, 21010800,
        locations=[
            "SK/DCE: Remembrance of the Impaler - mainboss drop",
            "SK/DCE: Messmer's Kindling - mainboss drop"
        ]
    ),
    ERBossInfo("Golden Hippopotamus (SK)", ["Shadow Keep"], 21000850, 21000850,
        locations=[
            "SK/SKMG: Aspects of the Crucible: Thorns - boss drop",
            "SK/SKMG: Scadutree Fragment x2 - boss drop"
        ]
    ),
    ERBossInfo("Commander Gaius (ScV)", ["Shadow Keep", "DLC Remembrance"], 2049480800, 2049480800, allow_rykard=True,
        locations=[
            "ScV/SKBG: Remembrance of the Wild Boar Rider - mainboss drop"
        ]
    ),
    ERBossInfo("Scadutree Avatar (SB)", ["Shadow Keep", "DLC Remembrance"], 2050480800, 2050480800, allow_rykard=True,
        locations=[
            "SB/TWS: Remembrance of the Shadow Sunflower - mainboss drop",
            "SB/TWS: Miquella's Great Rune - mainboss drop"
        ]
    ),
    
    # MARK: Hinterland
    ERBossInfo("Tree Sentinel (HL hill)", ["Hinterland", "DLC Overworld"], 2050470800, 2050470800, # these could be wrong but doesn't matter
        locations=[
            "HL/HL: Blessing of Marika - boss drop on hill"
        ]
    ),
    ERBossInfo("Tree Sentinel (HL bridge)", ["Hinterland", "DLC Overworld"], 2050480860, 2050480860, #
        locations=[
            "HL/HL: Blessing of Marika - boss drop by bridge"
        ]
    ),
    ERBossInfo("Fallingstar Beast (HL)", ["Hinterland", "DLC Overworld"], 2052480800, 2052480800,
        locations=[
            "HL/FH: Gravitational Missile - boss drop to NE"
        ]
    ),
    
    # MARK: Finger Ruins
    ERBossInfo("Metyr, Mother of Fingers (FRM)", ["Finger Ruins", "DLC Remembrance"], 25000800, 25000800, allow_rykard=True,
        locations=[
            "FRM: Remembrance of the Mother of Fingers - mainboss drop",
            "SA/(CMM): Maternal Staff - kill invader Ymir",
            "SA/(CMM): High Priest Hat - kill invader Ymir",
            "SA/(CMM): High Priest Robe - kill invader Ymir",
            "SA/(CMM): High Priest Gloves - kill invader Ymir",
            "SA/(CMM): High Priest Undergarments - kill invader Ymir"
        ]
    ),
    ERBossInfo("Count Ymir, Mother of Fingers (CMM)", ["Finger Ruins"], 2051450720, 2051450800,
        locations=[
            "SA/(CMM): Maternal Staff - kill invader Ymir",
            "SA/(CMM): High Priest Hat - kill invader Ymir",
            "SA/(CMM): High Priest Robe - kill invader Ymir",
            "SA/(CMM): High Priest Gloves - kill invader Ymir",
            "SA/(CMM): High Priest Undergarments - kill invader Ymir"
        ]
    ),
    
    # MARK: Recluses' River
    ERBossInfo("Rakshasa (RR)", ["Recluses' River", "DLC Overworld", "Mausoleum"], 2051440800, 2051440800,
        locations=[
            "RR/(ENM): Rakshasa's Great Katana - boss drop",
            "RR/(ENM): Rakshasa Helm - boss drop",
            "RR/(ENM): Rakshasa Armor - boss drop",
            "RR/(ENM): Rakshasa Gauntlets - boss drop",
            "RR/(ENM): Rakshasa Greaves - boss drop"
        ]
    ),
    ERBossInfo("Jori, Elder Inquisitor (RR/DC)", ["Recluses' River", "Dungeon", "Catacomb"], 2052430800, 2052430800,
        locations=[
            "RR/(DC): Barbed Staff-Spear - boss drop"
        ]
    ),
    
    # MARK: Midra's Manse
    ERBossInfo("Midra, Lord of Frenzied Flame (MM)", ["Midra's Manse", "DLC Remembrance"], 28000800, 28000800,
        locations=[
            "MM/SFC: Remembrance of the Lord of Frenzied Flame - mainboss drop"
        ]
    ),
    
    # MARK: Ancient Ruins of Rauh
    ERBossInfo("Romina, Saint of the Bud (ARR)", ["Ancient Ruins of Rauh", "DLC Overworld", "DLC Remembrance", "DLC Main"], 2044450800, 2044450800,
        locations=[
            "ARR/CBME: Remembrance of the Saint of the Bud - mainboss drop"
        ]
    ),
    ERBossInfo("Divine Beast Dancing Lion (ARR)", ["Ancient Ruins of Rauh", "DLC Overworld"], 2046460800, 2046460800,
        locations=[
            "ARR/ARGS: Divine Beast Tornado - boss drop to NE"
        ]
    ),
    
    # MARK: Enir Ilim
    ERBossInfo("Promised Consort Radahn (EI)", [], 20010801, None, allow_rykard=True, locations=[]),
    ERBossInfo("Radahn, Consort of Miquella (EI)", ["DLC Remembrance", "DLC Final", "DLC Main"], 20010800, 20010800, allow_rykard=True,
        locations=[
            "EI/DGFS: Remembrance of a God and a Lord - mainboss drop"
        ]
    ),
]

default_rykard_location = None
default_serpent_location = None
for boss in base_bosses:
    boss.type.append("All Base")
    if boss.name == "Rykard, Lord of Blasphemy (VM)":
        default_rykard_location = boss
    if boss.name == "God-Devouring Serpent (VM)":
        default_serpent_location = boss
for boss in dlc_bosses: 
    boss.dlc = True
    boss.type.append("All DLC")
    
all_bosses = base_bosses + dlc_bosses

all_boss_locations_dictionary: Dict[str, ERBossInfo] = {}
boss_name_to_data: Dict[str, ERBossInfo] = {}
for boss in all_bosses:
    boss_name_to_data.update({boss.name: boss})
    all_boss_locations_dictionary.update({loc: boss for loc in boss.locations})