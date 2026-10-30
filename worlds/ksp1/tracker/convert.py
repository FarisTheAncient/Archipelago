import argparse
from pathlib import Path
import csv
import json
from typing import Any

# Script not intended to be run from the ap root
# Just pass it the path to the 

science_data = [ #because i'm lazy :)
    [ #Science_0
        "Basic Rocketry",
        "Engineering 101",
        "General Rocketry",
        "Stability",
        "Survivability"
    ],[ #Science_1
        "Advanced Rocketry",
        "Aviation",
        "Basic Science",
        "Flight Control",
        "General Construction",
        "Advanced Construction",
        "Advanced Flight Control",
        "Aerodynamics",
        "Electrics",
        "Fuel Systems",
        "Heavy Rocketry",
        "Landing",
        "Miniaturization",
        "Propulsion Systems",
        "Space Exploration"
    ],[ #Science_2
        "Actuators",
        "Advanced Aerodynamics",
        "Advanced Electrics",
        "Advanced Exploration",
        "Adv. Fuel Systems",
        "Advanced Landing",
        "Command Modules",
        "Heavier Rocketry",
        "Precision Engineering",
        "Precision Propulsion",
        "Specialized Construction",
        "Specialized Control",
        "Supersonic Flight"
    ],[ #Science_3
        "Advanced MetalWorks",
        "Composites",
        "Electronics",
        "Field Science",
        "Heavy Aerodynamics",
        "Heavy Landing",
        "High Altitude Flight",
        "High-Power Electrics",
        "Large Volume Containment",
        "Nuclear Propulsion",
        "Scanning Tech",
        "Unmanned Tech"
    ],[ #Science_4
        "Advanced Science Tech",
        "Advanced Unmanned Tech",
        "Advanced Motors",
        "Automation",
        "Experimental Aerodynamics",
        "High-Performance Fuel Systems",
        "Hypersonic Flight",
        "Ion Propulsion",
        "Meta-Materials",
        "Nanolathing",
        "Specialized Electrics",
        "Very Heavy Rocketry"
    ],[ #Science_5
        "Aerospace Tech",
        "Experimental Electrics",
        "Experimental Motors",
        "Experimental Science",
        "Large Probes"
    ]
]

altitude_data = {
    "Bop":[
        "Bop 1km Altitude",
        "Bop 2km Altitude",
        "Bop 3km Altitude",
        "Bop 4km Altitude",
        "Bop 6km Altitude",
        "Bop 10km Altitude",
        "Bop 15km Altitude",
    ],
    "Dres":[
        "Dres 2km Altitude",
        "Dres 4km Altitude",
        "Dres 7km Altitude",
        "Dres 9km Altitude",
        "Dres 13km Altitude",
        "Dres 19km Altitude",
        "Dres 30km Altitude",
    ],
    "Duna":[
        "Duna 4km Altitude",
        "Duna 7km Altitude",
        "Duna 11km Altitude",
        "Duna 14km Altitude",
        "Duna 21km Altitude",
        "Duna 32km Altitude",
        "Duna 50km Altitude",
    ],
    "Eeloo":[
        "Eeloo 1km Altitude",
        "Eeloo 2km Altitude",
        "Eeloo 3km Altitude",
        "Eeloo 4km Altitude",
        "Eeloo 6km Altitude",
        "Eeloo 10km Altitude",
        "Eeloo 15km Altitude",
    ],
    "Eve":[
        "Eve 6km Altitude",
        "Eve 13km Altitude",
        "Eve 21km Altitude",
        "Eve 26km Altitude",
        "Eve 39km Altitude",
        "Eve 58km Altitude",
        "Eve 90km Altitude",
    ],
    "Gilly":[
        "Gilly 1km Altitude",
        "Gilly 2km Altitude",
        "Gilly 3km Altitude",
        "Gilly 4km Altitude",
        "Gilly 5km Altitude",
        "Gilly 7km Altitude",
        "Gilly 11km Altitude",
    ],
    "Ike":[
        "Ike 1km Altitude",
        "Ike 2km Altitude",
        "Ike 3km Altitude",
        "Ike 4km Altitude",
        "Ike 6km Altitude",
        "Ike 10km Altitude",
        "Ike 15km Altitude",
    ],
    "Kerbin":[
        "Kerbin 5km Altitude",
        "Kerbin 10km Altitude",
        "Kerbin 16km Altitude",
        "Kerbin 20km Altitude",
        "Kerbin 30km Altitude",
        "Kerbin 45km Altitude",
        "Kerbin 70km Altitude",
    ],
    "Laythe":[
        "Laythe 4km Altitude",
        "Laythe 7km Altitude",
        "Laythe 11km Altitude",
        "Laythe 14km Altitude",
        "Laythe 21km Altitude",
        "Laythe 32km Altitude",
        "Laythe 50km Altitude",
    ],
    "Minmus":[
        "Minmus 1km Altitude",
        "Minmus 2km Altitude",
        "Minmus 3km Altitude",
        "Minmus 4km Altitude",
        "Minmus 6km Altitude",
        "Minmus 10km Altitude",
        "Minmus 15km Altitude",
    ],
    "Moho":[
        "Moho 2km Altitude",
        "Moho 4km Altitude",
        "Moho 6km Altitude",
        "Moho 7km Altitude",
        "Moho 11km Altitude",
        "Moho 16km Altitude",
        "Moho 25km Altitude",
    ],
    "Mun":[
        "Mun 1km Altitude",
        "Mun 3km Altitude",
        "Mun 4km Altitude",
        "Mun 5km Altitude",
        "Mun 8km Altitude",
        "Mun 12km Altitude",
        "Mun 19km Altitude",
    ],
    "Pol":[
        "Pol 1km Altitude",
        "Pol 2km Altitude",
        "Pol 3km Altitude",
        "Pol 4km Altitude",
        "Pol 5km Altitude",
        "Pol 7km Altitude",
        "Pol 11km Altitude",
    ],
    "Tylo":[
        "Tylo 2km Altitude",
        "Tylo 5km Altitude",
        "Tylo 8km Altitude",
        "Tylo 10km Altitude",
        "Tylo 15km Altitude",
        "Tylo 23km Altitude",
        "Tylo 35km Altitude",
    ],
    "Vall":[
        "Vall 1km Altitude",
        "Vall 3km Altitude",
        "Vall 5km Altitude",
        "Vall 6km Altitude",
        "Vall 9km Altitude",
        "Vall 13km Altitude",
        "Vall 20km Altitude",
    ]
}

def main(source_path: Path):

    maps_dict = [] #Actually a list of dicts but who's counting
    locs_dict = [] #Same

    markers_path = source_path / "UT Maps" / "Marker_Coords"
    files = [ x for x in markers_path.glob("*.json") if x.is_file()]
    for file in files:
        temp_list = []
        map_name = file.name.split('_',1)[0]
        reader = []
        with open(file) as f:
            blob = json.load(f)
        reader.extend(blob["UT Entrances"]["nodes"])
        reader.extend(blob["UT Locations"]["nodes"])
        reader.extend(blob["UT Locations"]["sidebar"]["nodes"])
        reader.extend(blob["UT Locations"]["altitude"]["nodes"])
        reader.extend(blob["UT Locations"]["science"]["nodes"])
        for node in reader:
            sections = []
            node["sections"] = sections
            #MissionType.ORBIT,MissionType.LAND,MissionType.RETURN,MissionType.ESCAPE,MissionType.ORBIT_RETURN,MissionType.SOI_RETURN
            entry,exit = ("entry","exit") if node["label"].split("_",1)[0] else ("exit","entry") #Home planet is reversed obvs
            if node["label"].endswith(entry): #Input entrances
                body = node["label"].split("_",1)[0]
                sections.extend([f"{body} - orbit",f"{body} - land"])
            elif node["label"].endswith(exit):
                body = node["label"].split("_",1)[0]
                sections.extend([f"{body} - return",f"{body} - escape",f"{body} - orbit_return",f"{body} - soi_return"])
            elif node["label"].startswith("Science_"):
                science = int(node["label"].split("_",1)[1])
                if science < len(science_data):
                    for s in science_data[science]:
                        sections.extend([f"{s} {i}" for i in range(6)]) #0..5
                    sections.extend(science_data[science])
            elif node["label"].startswith("Altitude"):
                alt = int(node["label"].split("_",1)[1])
                if alt < 7:
                    if map_name in altitude_data:
                        sections.append(altitude_data[map_name][alt])
            elif "_" in node["label"]: #All non planet nodes besides splash down
                sections.extend([f"{map_name} {node["label"].replace('_',' ')}"])
            elif node["label"] == "Splashdown":
                pass #Actually correct already
            elif node["label"] == "KSC":
                sections.extend([
                    "Science from KSC Administration",
                    "Science from KSC Astronaut Complex",
                    "Science from KSC Crawlerway",
                    "Science from KSC Flag Pole (Astronaut Complex)",
                    "Science from KSC Grounds",
                    "Science from KSC LaunchPad",
                    "Science from KSC Mission Control",
                    "Science from KSC R&D",
                    "Science from KSC Runway",
                    "Science from KSC SPH",
                    "Science from KSC Tracking Station",
                    "Science from KSC VAB"
                ])
            else:
                body = node["label"]
                elements = [
                    f"{body} Orbit",f"{body} EVA in Orbit",f"{body} Orbital Probe",f"{body} Flyby",f"{body} SOI Leave",f"{body} Orbit Return",
                    f"{body} Crewed Landing",f"{body} Flag Plant",f"{body} Return",f"{body} Sample Return",
                    f"{body} Flag Plant",f"{body} Landing",f"{body} SOI Leave",f"{body} SOI Return",f"{body} Unmanned Flyby"
                    ]
                contracts = [
                    f"Contract: Docking around {body}",f"Contract: Equatorial Orbit around {body}",f"Contract: Flag Plant on {body}",
                    f"Contract: Flyby of {body}",f"Contract: Mine Ore on {body}",f"Contract: Orbit Return from {body}",
                    f"Contract: Orbit around {body}",f"Contract: Orbital Rescue around {body}",f"Contract: Polar Orbit around {body}",
                    f"Contract: Return from {body}",f"Contract: SOI Return from {body}",f"Contract: Sample Return from {body}",
                    f"Contract: Satellite Orbit around {body}",f"Contract: Space Station around {body}",f"Contract: Stationary Orbit around {body}",
                    f"Contract: Surface Base on {body}",f"Contract: Surface Rescue from {body}",f"Contract: Surface Survey on {body}",
                    f"Contract: Tourism to {body}",f"Contract: Transmit Science from {body}",
                ]
                for e in elements:
                    sections.extend([f"{e} 1", f"{e} 2", f"{e} 3"])
                for c in contracts:
                    sections.extend([f"{c} {i}" for i in range(1,11)])
                sections.extend(elements)
                sections.extend(contracts)
            temp_list.append(node) #Row 1 is category

        if temp_list:
            maps_dict.append({"name":f"{map_name}","img":f"{file.name.split('.',1)[0]}.png"})
            for loc in temp_list:
                sections = [{"name":loc["label"]}]
                if "sections" in loc:
                    for section in loc["sections"]:
                        sections.append({"name":section})
                map_locations = [{"map":map_name,"x":loc["x"],"y":loc["y"]}]
                locs_dict.append({"name":loc["label"],"sections":sections, "map_locations":map_locations})

    with open("maps.json","w") as m:
        json.dump(maps_dict,m,indent=2)
    with open("locations.json","w") as l:
        json.dump(locs_dict,l,indent=2)





















if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build UT maps and report remaining mapping gaps.")
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    main(args.source)


