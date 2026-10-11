# python -m worlds.eldenring.docs.region_descriptions

from typing import Dict
import os
import html

from worlds.eldenring.locations import location_tables

# region to inital to description
region_initals_to_description: Dict[str, Dict[str, str]] = {}

# add descriptions to initials
def find_description(initial: str) -> str:
    match initial:
        # limgrave
        case "BS": return "Bridge of Sacrifice landmark, connection point between S Limgrave and Weeping Peninsula."
        case "LG/(AS)": return "Artists Shack landmark, Mid Limgrave."
        case "LG/(CE)": return "Church of Elleh landmark, W Limgrave."
        case "LG/(DBR)": return "Dragon-Burnt Ruins landmark, S Limgrave."
        case "LG/(FH)": return "Fort Haight landmark, E Limgrave."
        case "LG/(FHE)": return "Forlorn Hound Evergaol, S Limgrave."
        case "": return ""
        case "": return ""
        case "": return ""
        case "": return ""
        case "": return ""
        case "": return ""
        case "": return ""
        
        # limgrave dungeons
        case "LG/(CC)": return "Coastal Cave, SW Limgrave."
        case "LG/(CDC)": return "Church of Dragon Communion, through Coastal Cave SW Limgrave."
        case "LG/(GC)": return "Groveside Cave, W Limgrave."
        case "LG/(SC)": return "Stormfoot Catacombs, W Limgrave."
        case "LG/(LT)": return "Limgrave Tunnels, W Limgrave."
        case "LG/(MCV)": return "Murkwater Cave, Mid Limgrave."
        case "LG/(MCC)": return "Murkwater Catacombs, Mid Limgrave."
        case "LG/(HC)": return "Highroad Cave, N Limgrave."
        case "LG/(DC)": return "Deathtouched Catacombs, E Stormhill."
        case "LG/(FHG)": return "Fringefolk Hero's Grave, W Limgrave."
        
        # weeping
        case "WP/BS": return "Bridge of Sacrifice grace."
        
        # roundtable doesn't need one, self explainatory
        
        # stormveil
        case "SV/GG": return "Godrick the Grafted grace in Godrick's arena."
        
        
        # liurnia
        
        # study hall
        case "LL/(CSH)N": return "Carian Study Hall normal."
        case "LL/(CSH)I": return "Carian Study Hall inverted."
        case "LL/(DV)": return "Divine Tower of Liurnia."
        case "LL/LTB": return "Liurnia Tower Bridge grace, after CSH."
        
        case "LL/(TFB/CA)": return "The Four Belfries (Chapel of Anticipation)"
        case "LL/(TFB/NEC)": return "The Four Belfries (Nokron)"
        case "LL/(TFB/FA)": return "The Four Belfries (Farum Azula)"
        
        
        
        case "CL/(WD)": return "Wailing Dunes."
        case "CL/(WDC)": return "War-Dead Catacombs, N of Wailing Dunes."
        
        case "DB/(DC)": return "Dragonbarrow Cave."
        case "DB/(SH)": return "Sellia Hideaway."
        case "DB/(DT)": return "Divine Tower of Caelid."
        
        
        
        
        
        
        case "FP/(GCHG)": return "Giant-Conquering Hero's Grave."
        
        # DLC
        
        # gravesite plains
        case "": return ""
        
        
        
        
        
        
        case "CHG/(LG)": return "Lamenter's Gaol."
        
        case "SA/(BG)": return "Bonny Gaol."
        case "SA/(RFSP)": return "Ruined Forge of Starfall Past."
        case "SA/ARR": return "Rauh Ruins Limited, use infused stonesword key."
        
        case "FRM": return "Finger Ruins of Miyr."
        case "SA/(CMM)": return "Cathedral of Manus Metyr."
        
        case "RB/(SRC)": return "Scorpion River Catacombs."
        case "RB/(TRF)": return "Taylew's Ruined Forge."
        
        case "FRR": return "Finger Ruins of Rhia."
        case "FRR/(FWH)": return "Finger-Weaver's Hovel landmark, SE Finger Ruins of Rhia."
        
        case "ER/(RC)": return "Rivermouth Cave."
        
        case "FRD": return "Finger Ruins of Dheo."
        
        
        case "": return ""
    
    return ""

# make multiple regions be under one label
def find_label(region: str) -> str:
    if region in ("Coastal Cave", "Church of Dragon Communion", "Groveside Cave", "Stormfoot Catacombs", "Limgrave Tunnels"
                  , "Murkwater Cave", "Murkwater Catacombs", "Highroad Cave", "Deathtouched Catacombs", "Fringefolk Hero's Grave"):
        return "Limgrave Dungeons"
    
    if region in ("Stormveil Start", "Stormveil Castle", "Stormveil Throne", "Divine Tower of Limgrave"):
        return "Stormveil Castle"
    
    if region in ("Impaler's Catacombs", "Tombsward Catacombs", "Tombsward Cave", "Morne Tunnel", "Earthbore Cave"):
        return "Weeping Peninsula Dungeons"
    
    if region in ("Road's End Catacombs", "Black Knife Catacombs", "Cliffbottom Catacombs", "Stillwater Cave"
                  , "Lakeside Crystal Cave", "Academy Crystal Cave", "Raya Lucaria Crystal Tunnel"):
        return "Liurnia of The Lakes Dungeons"
    
    if region in ("Carian Study Hall", "Carian Study Hall (Inverted)"):
        return "Carian Study Hall"
    
    if region in ("The Four Belfries (Chapel of Anticipation)", "The Four Belfries (Nokron)", "The Four Belfries (Farum Azula)"):
        return "The Four Belfries"

    if region in ("Raya Lucaria Academy", "Raya Lucaria Academy Main", "Raya Lucaria Academy Chest", "Raya Lucaria Academy Library"):
        return "Raya Lucaria Academy"
    
    if region in ("Caelid Catacombs", "Gaol Cave", "Sellia Crystal Tunnel", "Abandoned Cave", "Minor Erdtree Catacombs", "Gale Tunnel"):
        return "Caelid Dungeons"
    
    if region in ("Redmane Castle Post Radahn", "Wailing Dunes", "War-Dead Catacombs"):
        return "Radahn Festival"
    
    if region in ("Dragonbarrow Cave", "Sellia Hideaway", "Divine Tower of Caelid"):
        return "Dragonbarrow Dungeons"
    
    if region in ("Nokron, Eternal City", "Nokron, Eternal City Start"):
        return "Nokron, Eternal City"
    
    if region in ("Deeproot Depths Upper", "Deeproot Depths", "Deeproot Depths Boss"):
        return "Deeproot Depths"
    
    if region in ("Sainted Hero's Grave", "Unsightly Catacombs", "Perfumer's Grotto", "Sage's Cave", "Old Altus Tunnel", "Altus Tunnel"):
        return "Altus Plateau Dungeons"
    
    if region in ("Wyndham Catacombs", "Gelmir Hero's Grave", "Seethewater Cave", "Volcano Cave"):
        return "Mt. Gelmir Dungeons"
    
    if region in ("Volcano Manor Dungeon", "Volcano Manor Entrance", "Volcano Manor Drawing Room", "Volcano Manor", "Volcano Manor Upper"):
        return "Volcano Manor"
    
    if region in ("Auriza Hero's Grave", "Auriza Side Tomb", "Sealed Tunnel"):
        return "Capital Outskirts Dungeons"
    
    if region in ("Leyndell, Royal Capital", "Leyndell, Royal Capital Unmissable", "Leyndell, Royal Capital Throne", "Divine Bridge"):
        return "Leyndell, Royal Capital"
    
    if region in ("Subterranean Shunning-Grounds", "Leyndell Catacombs"):
        return "Subterranean Shunning-Grounds"
    
    if region in ("Divine Tower of East Altus", "Forbidden Lands"):
        return "Forbidden Lands"    
    
    if region in ("Giants' Mountaintop Catacombs", "Spiritcaller Cave"):
        return "Mountaintops of the Giants Dungeons"    
    
    if region in ("Giant-Conquering Hero's Grave"):
        return "Flame Peak Dungeon"    
        
    if region in ("Farum Azula", "Farum Azula Main"):
        return "Farum Azula"        
        
    if region in ("Consecrated Snowfield Catacombs", "Cave of the Forlorn", "Yelough Anix Tunnel"):
        return "Consecrated Snowfield Dungeons"        
        
    if region in ("Leyndell, Ashen Capital", "Leyndell, Ashen Capital Throne"):
        return "Leyndell, Ashen Capital"
        
    
    # DLC
    
    if region in ("Fog Rift Catacombs", "Belurat Gaol", "Dragon's Pit", "Ruined Forge Lava Intake"):
        return "Gravesite Plain Dungeons"
    
    if region in ("Belurat", "Belurat Swamp"):
        return "Belurat"    
    
    if region in ("Jagged Peak", "Jagged Peak Foot"):
        return "Jagged Peak"    
    
    if region in ("Lamenter's Gaol (Entrance)", "Lamenter's Gaol (Upper)", "Lamenter's Gaol (Lower)"):
        return "Charo's Hidden Grave Dungeon"    
    
    if region in ("Bonny Gaol", "Ruined Forge of Starfall Past", "Rauh Ruins Limited"):
        return "Scadu Altus Dungeons"    
    
    if region in ("Cathedral of Manus Metyr", "Finger Ruins of Miyr"):
        return "Cathedral of Manus Metyr"    
    
    if region in ("Scorpion River Catacombs", "Taylew's Ruined Forge"):
        return "Rauh Base Dungeons"    
    
    if region in ("Cerulean Coast", "Finger Ruins of Rhia"):
        return "Cerulean Coast"   
    
    if region in ("Rivermouth Cave"):
        return "Ellac River Dungeon"    
    
    if region in ("Shadow Keep", "Shadow Keep Storehouse", "Shadow Keep Storehouse Back", "Shadow Keep, West Rampart", "Shadow Keep, Church District", "Shadow Keep, Church District Lower"):
        return "Shadow Keep"    
    
    if region in ("Hinterland", "Finger Ruins of Dheo"):
        return "Hinterland" 
        
    if region in ("Darklight Catacombs"):
        return "Recluses' River Dungeon"    
    
    # if nothing return region
    return region

if __name__ == '__main__':
    all_initials = []
    for region in location_tables:
        region_initals_to_description.setdefault(region, {})
        for location in location_tables[region]:
            initial = location.name[:location.name.find(":")]
            if initial not in all_initials and initial not in region_initals_to_description[region]:
                region_initals_to_description[region][initial] = find_description(initial)
                all_initials.append(initial) # removes dupe initials
                
    table = "## Base Game\n<table>\n"
    last_region = ""
    for (region, inital_dict) in sorted(
        region_initals_to_description.items(),
        key = lambda pair: location_tables[pair[0]][0].region_value
    ):
        if region == "Roundtable Hold DLC Only":
            table += f"</table><br><div>\n\n## DLC\n\n</div><table>\n"
        if last_region != find_label(region):
            last_region = find_label(region)
            table += f"<tr><td><h3>\n\n### {html.escape(last_region)}\n\n</td></tr>\n"
        for (initial, description) in sorted(
            inital_dict.items(),
            key = lambda pair: pair[0]
        ):
            table += f"<tr><td><strong>{html.escape(initial)}: </strong>{html.escape(description)}</td></tr>\n"
    table += "</table>\n"
    # print(table)

    with open(
        os.path.join(os.path.dirname(__file__), 'en_region_guide.md'),
        'r+',
        encoding='utf-8'
    ) as f:
        original = f.read()
        start_flag = "<!-- begin region table -->\n"
        start = original.index(start_flag) + len(start_flag)
        end = original.index("<!-- end region table -->")

        f.seek(0)
        f.write(original[:start] + table + original[end:])
        f.truncate()

    print("Updated docs/en_region_guide.md!")
    
    