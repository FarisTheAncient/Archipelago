from typing import Set, List, NamedTuple, Optional
from BaseClasses import ItemClassification, Item

class ItemData(NamedTuple):
    name: str
    classification: ItemClassification
    code: Optional[int]
    amount: int=1

class DVItem(Item):
    game="Derail Valley"

_item_table: List[ItemData] = [
    ItemData("Nothing", ItemClassification.trap, 0x3, 0),
    ItemData("Money", ItemClassification.filler, 0x1, 0),
    ItemData("Double job token", ItemClassification.useful, 0x2, 0),

    ItemData("Amp Limiter", ItemClassification.filler, 0x100, 0),
    ItemData("Anti-wheelslip Computer", ItemClassification.filler, 0x101, 0),
    ItemData("Automatic Train Stop", ItemClassification.filler, 0x103, 0),
    ItemData("Battery Charger", ItemClassification.filler, 0x105, 0),
    ItemData("Amber Beacon", ItemClassification.filler, 0x106, 0),
    ItemData("Blue Beacon", ItemClassification.filler, 0x107, 0),
    ItemData("Red Beacon", ItemClassification.filler, 0x108, 0),
    ItemData("Boombox", ItemClassification.filler, 0x109, 0),
    ItemData("Brake Checklist", ItemClassification.filler, 0x10D, 0),
    ItemData("Brake Cylinder LED Bar", ItemClassification.filler, 0x10E, 0),
    ItemData("Cassette Album1", ItemClassification.filler, 0x113, 0),
    ItemData("Cassette Album2", ItemClassification.filler, 0x114, 0),
    ItemData("Cassette Album3", ItemClassification.filler, 0x115, 0),
    ItemData("Cassette Album4", ItemClassification.filler, 0x116, 0),
    ItemData("Cassette Album5", ItemClassification.filler, 0x117, 0),
    ItemData("Cassette Album6", ItemClassification.filler, 0x118, 0),
    ItemData("Cassette Album7", ItemClassification.filler, 0x119, 0),
    ItemData("Cassette Album8", ItemClassification.filler, 0x11A, 0),
    ItemData("Cassette Album9", ItemClassification.filler, 0x11B, 0),
    ItemData("Cassette Album10", ItemClassification.filler, 0x11C, 0),
    ItemData("Cassette Album11", ItemClassification.filler, 0x11D, 0),
    ItemData("Cassette Album12", ItemClassification.filler, 0x11E, 0),
    ItemData("Cassette Album13", ItemClassification.filler, 0x11F, 0),
    ItemData("Cassette Album14", ItemClassification.filler, 0x120, 0),
    ItemData("Cassette Album15", ItemClassification.filler, 0x121, 0),
    ItemData("Cassette Album16", ItemClassification.filler, 0x122, 0),
    ItemData("Cassette Playlist1", ItemClassification.filler, 0x123, 0),
    ItemData("Cassette Playlist2", ItemClassification.filler, 0x124, 0),
    ItemData("Cassette Playlist3", ItemClassification.filler, 0x125, 0),
    ItemData("Cassette Playlist4", ItemClassification.filler, 0x126, 0),
    ItemData("Cassette Playlist5", ItemClassification.filler, 0x127, 0),
    ItemData("Cassette Playlist6", ItemClassification.filler, 0x128, 0),
    ItemData("Cassette Playlist7", ItemClassification.filler, 0x129, 0),
    ItemData("Cassette Playlist8", ItemClassification.filler, 0x12A, 0),
    ItemData("Cassette Playlist9", ItemClassification.filler, 0x12B, 0),
    ItemData("Cassette Playlist10", ItemClassification.filler, 0x12C, 0),
    ItemData("Clinometer", ItemClassification.filler, 0x12D, 0),
    ItemData("Compass", ItemClassification.filler, 0x136, 0),
    ItemData("Crate", ItemClassification.filler, 0x137, 0),
    ItemData("Plastic Crate", ItemClassification.filler, 0x138, 0),
    ItemData("Crimping Tool", ItemClassification.filler, 0x139, 0),
    ItemData("Defect Detector", ItemClassification.filler, 0x13D, 0),
    ItemData("Digital Clock", ItemClassification.filler, 0x13E, 0),
    ItemData("Digital Speedometer", ItemClassification.filler, 0x13F, 0),
    ItemData("Distance Tracker", ItemClassification.filler, 0x140, 0),
    ItemData("Duct Tape", ItemClassification.filler, 0x141, 0),
    ItemData("EOT Lantern", ItemClassification.filler, 0x144, 0),
    ItemData("Expert Shovel", ItemClassification.progression, 0x146, 0),
    ItemData("Filler Gun", ItemClassification.filler, 0x148, 0),
    ItemData("Blue Flag Marker", ItemClassification.filler, 0x14A, 0),
    ItemData("Cyan Flag Marker", ItemClassification.filler, 0x14B, 0),
    ItemData("Green Flag Marker", ItemClassification.filler, 0x14C, 0),
    ItemData("Orange Flag Marker", ItemClassification.filler, 0x14D, 0),
    ItemData("Purple Flag Marker", ItemClassification.filler, 0x14E, 0),
    ItemData("Red Flag Marker", ItemClassification.filler, 0x14F, 0),
    ItemData("White Flag Marker", ItemClassification.filler, 0x150, 0),
    ItemData("Yellow Flag Marker", ItemClassification.filler, 0x151, 0),
    ItemData("Flashlight", ItemClassification.filler, 0x152, 0),
    ItemData("Golden Shovel", ItemClassification.progression, 0x153, 0),
    ItemData("Googly Eye", ItemClassification.filler, 0x154, 0),
    ItemData("Hammer", ItemClassification.filler, 0x155, 0),
    ItemData("Electric Hand Drill", ItemClassification.useful, 0x156, 1),
    ItemData("Handheld Game Console", ItemClassification.filler, 0x157, 0),
    ItemData("Headlight", ItemClassification.filler, 0x15A, 0),
    ItemData("Infrared Thermometer", ItemClassification.filler, 0x15B, 0),
    ItemData("Briefcase", ItemClassification.filler, 0x15C, 0),
    ItemData("Crate", ItemClassification.filler, 0x15D, 0),
    ItemData("Folder", ItemClassification.filler, 0x15E, 0),
    ItemData("Blue Folder", ItemClassification.filler, 0x15F, 0),
    ItemData("Red Folder", ItemClassification.filler, 0x160, 0),
    ItemData("Yellow Folder", ItemClassification.filler, 0x161, 0),
    ItemData("Toolbox", ItemClassification.filler, 0x163, 0),
    ItemData("Old Bob's Garage Key (BE2)", ItemClassification.progression, 0x169, 1),
    ItemData("Reginald's Garage Key (Caboose)", ItemClassification.progression, 0x16B, 1),
    ItemData("Steve's Garage Key (DE6 Slug)", ItemClassification.progression, 0x16C, 1),
    ItemData("Olaf's Garage Key (DM1U)", ItemClassification.progression, 0x16D, 1),
    ItemData("Label Maker", ItemClassification.filler, 0x16F, 0),
    ItemData("Lamp", ItemClassification.filler, 0x170, 0),
    ItemData("Lantern", ItemClassification.filler, 0x171, 0),
    ItemData("Blue Light Bar", ItemClassification.filler, 0x1A5, 0),
    ItemData("Cyan Light Bar", ItemClassification.filler, 0x1A6, 0),
    ItemData("Green Light Bar", ItemClassification.filler, 0x1A7, 0),
    ItemData("Orange Light Bar", ItemClassification.filler, 0x1A8, 0),
    ItemData("Purple Light Bar", ItemClassification.filler, 0x1A9, 0),
    ItemData("Red Light Bar", ItemClassification.filler, 0x1AA, 0),
    ItemData("White Light Bar", ItemClassification.filler, 0x1AB, 0),
    ItemData("Yellow Light Bar", ItemClassification.filler, 0x1AC, 0),
    ItemData("Lighter", ItemClassification.progression, 0x1AD, 1),
    ItemData("High-tech Headlight Left", ItemClassification.filler, 0x1B2, 0),
    ItemData("High-tech Headlight Right", ItemClassification.filler, 0x1B3, 0),
    ItemData("High-tech Taillight Left", ItemClassification.filler, 0x1B4, 0),
    ItemData("High-tech Taillight Right", ItemClassification.filler, 0x1B5, 0),
    ItemData("Mount Slanted Medium", ItemClassification.filler, 0x1B6, 0),
    ItemData("Mount Upright Small", ItemClassification.filler, 0x1B7, 0),
    ItemData("Mount Upright Large", ItemClassification.filler, 0x1B8, 0),
    ItemData("Mount Upright Small - Long Base", ItemClassification.filler, 0x1B9, 0),
    ItemData("Mount Upright Small Wide", ItemClassification.filler, 0x1BA, 0),
    ItemData("Mount Strip Medium", ItemClassification.filler, 0x1BB, 0),
    ItemData("Mount Strip Small", ItemClassification.filler, 0x1BC, 0),
    ItemData("Mount Plate Medium", ItemClassification.filler, 0x1BD, 0),
    ItemData("Mount Plate Large", ItemClassification.filler, 0x1BE, 0),
    ItemData("Mount Strip Long - Small Base", ItemClassification.filler, 0x1BF, 0),
    ItemData("Mount Stand Large", ItemClassification.filler, 0x1C0, 0),
    ItemData("Mount Strip Long", ItemClassification.filler, 0x1C1, 0),
    ItemData("Nameplate", ItemClassification.filler, 0x1C4, 0),
    ItemData("Oiler", ItemClassification.progression, 0x1C5, 1),
    ItemData("Overheating Protection", ItemClassification.filler, 0x1C6, 0),
    ItemData("Paint Can", ItemClassification.filler, 0x1C7, 0),
    ItemData("Demonstrator Paint Can", ItemClassification.filler, 0x1C8, 0),
    ItemData("Sand can", ItemClassification.filler, 0x1C9, 0),
    ItemData("Paint Sprayer", ItemClassification.progression, 0x1CD, 1),
    ItemData("Proximity Reader", ItemClassification.filler, 0x1D3, 0),
    ItemData("Proximity Sensor", ItemClassification.filler, 0x1D4, 0),
    ItemData("Remote Controller", ItemClassification.filler, 0x1D7, 0),
    ItemData("Remote Signal Booster", ItemClassification.filler, 0x1D8, 0),
    ItemData("Shelf", ItemClassification.filler, 0x1DC, 0),
    ItemData("Shovel", ItemClassification.progression, 0x1DD, 1),
    ItemData("Shovel Mount", ItemClassification.filler, 0x1DE, 0),
    ItemData("Soldering Gun", ItemClassification.filler, 0x1DF, 0),
    ItemData("Soldering Wire Reel", ItemClassification.filler, 0x1E0, 0),
    ItemData("Steam Engine Checklist", ItemClassification.filler, 0x1E2, 0),
    ItemData("Sticky Tape", ItemClassification.filler, 0x1E3, 0),
    ItemData("Stopwatch", ItemClassification.filler, 0x1E4, 0),
    ItemData("Sun Visor", ItemClassification.filler, 0x1E5, 0),
    ItemData("Alternating Controller", ItemClassification.filler, 0x1E6, 0),
    ItemData("Analog Controller", ItemClassification.filler, 0x1E7, 0),
    ItemData("Button Controller", ItemClassification.filler, 0x1E8, 0),
    ItemData("Switch Controller", ItemClassification.filler, 0x1E9, 0),
    ItemData("Rotary Controller", ItemClassification.filler, 0x1EA, 0),
    ItemData("Switch Setter", ItemClassification.filler, 0x1EB, 0),
    ItemData("Swivel Light", ItemClassification.filler, 0x1EC, 0),
    ItemData("Taillight", ItemClassification.filler, 0x1EE, 0),
    ItemData("Universal Control Stand", ItemClassification.filler, 0x1F2, 0),
    ItemData("Wireless MU Controller", ItemClassification.filler, 0x1F5, 0),

    ItemData("CME Station unlock", ItemClassification.progression, 0x200, 1),
    ItemData("CMS Station unlock", ItemClassification.progression, 0x201, 1),
    ItemData("CP Station unlock", ItemClassification.progression, 0x202, 1),
    ItemData("CS Station unlock", ItemClassification.progression, 0x203, 1),
    ItemData("CW Station unlock", ItemClassification.progression, 0x204, 1),
    ItemData("FF Station unlock", ItemClassification.progression, 0x205, 1),
    ItemData("FM Station unlock", ItemClassification.progression, 0x206, 1),
    ItemData("FRC Station unlock", ItemClassification.progression, 0x207, 1),
    ItemData("FRS Station unlock", ItemClassification.progression, 0x208, 1),
    ItemData("GF Station unlock", ItemClassification.progression, 0x209, 1),
    ItemData("HB Station unlock", ItemClassification.progression, 0x20A, 1),
    ItemData("IME Station unlock", ItemClassification.progression, 0x20B, 1),
    ItemData("IMW Station unlock", ItemClassification.progression, 0x20C, 1),
    ItemData("MB Station unlock", ItemClassification.progression, 0x20D, 1),
    ItemData("MF Station unlock", ItemClassification.progression, 0x20E, 1),
    ItemData("OR Station unlock", ItemClassification.progression, 0x20F, 1),
    ItemData("OWC Station unlock", ItemClassification.progression, 0x210, 1),
    ItemData("OWN Station unlock", ItemClassification.progression, 0x211, 1),
    ItemData("SM Station unlock", ItemClassification.progression, 0x212, 1),
    ItemData("SW Station unlock", ItemClassification.progression, 0x213, 1),

    ItemData("Dispatcher license", ItemClassification.useful, 0x300, 1),
    ItemData("Train driver license", ItemClassification.filler, 0x301, 1),
    ItemData("DE2 locomotive license", ItemClassification.progression, 0x302, 1),
    ItemData("DM3 locomotive license", ItemClassification.progression, 0x303, 1),
    ItemData("DH4 locomotive license", ItemClassification.progression, 0x304, 1),
    ItemData("DE6 locomotive license", ItemClassification.progression, 0x305, 1),
    ItemData("S060 locomotive license", ItemClassification.progression, 0x306, 1),
    ItemData("S282 locomotive license", ItemClassification.progression, 0x307, 1),
    ItemData("Multiple unit license", ItemClassification.useful, 0x308, 1),
    ItemData("Museum license", ItemClassification.progression, 0x309, 1),
    ItemData("Manual service license", ItemClassification.progression, 0x30A, 1),
    ItemData("Progressive Concurrent orders license", ItemClassification.progression, 0x30B, 2),

    ItemData("Freight haul license", ItemClassification.progression, 0x310, 1),
    ItemData("Logistical haul license", ItemClassification.progression, 0x311, 1),
    ItemData("Shunting license", ItemClassification.progression, 0x312, 1),
    # ItemData("Fragile license", ItemClassification.progression, 0x313, 1),
    ItemData("Progressive Train Length license", ItemClassification.progression, 0x314, 2), # Long 1 -> Long 2
    ItemData("Progressive Hazmat license", ItemClassification.progression, 0x315, 4), # Fragile -> Hazmat 1 -> Hazmat 2 -> Hazmat 3
    ItemData("Progressive Military license", ItemClassification.progression, 0x316, 3), # Military 1 -> Military 2 -> Military 3
    # Military 1 only gives access to logistical haul jobs, Military 3 is only useful for nuclear transport job
    

    ItemData("Demo locomotive DE2", ItemClassification.progression, 0x350, 2),
    ItemData("Demo locomotive DM3", ItemClassification.progression, 0x351, 2),
    ItemData("Demo locomotive DH4", ItemClassification.progression, 0x352, 2),
    ItemData("Demo locomotive DE6", ItemClassification.progression, 0x353, 2),
    ItemData("Demo locomotive S060", ItemClassification.progression, 0x354, 2),
    ItemData("Demo locomotive S282", ItemClassification.progression, 0x355, 2),

    ItemData("BE2 spawn rights", ItemClassification.useful, 0x360, 1),
    ItemData("Caboose spawn rights", ItemClassification.filler, 0x361, 1),
    ItemData("DE6 Slug spawn rights", ItemClassification.filler, 0x362, 1),
    ItemData("DM1U spawn rights", ItemClassification.filler, 0x363, 1),
    
    ItemData("Finish CME", ItemClassification.progression, 0x1000, 0),
    ItemData("Finish CMS", ItemClassification.progression, 0x1001, 0),
    ItemData("Finish CP", ItemClassification.progression, 0x1002, 0),
    ItemData("Finish CS", ItemClassification.progression, 0x1003, 0),
    ItemData("Finish CW", ItemClassification.progression, 0x1004, 0),
    ItemData("Finish FF", ItemClassification.progression, 0x1005, 0),
    ItemData("Finish FM", ItemClassification.progression, 0x1006, 0),
    ItemData("Finish FRC", ItemClassification.progression, 0x1007, 0),
    ItemData("Finish FRS", ItemClassification.progression, 0x1008, 0),
    ItemData("Finish GF", ItemClassification.progression, 0x1009, 0),
    ItemData("Finish HB", ItemClassification.progression, 0x100A, 0),
    ItemData("Finish IME", ItemClassification.progression, 0x100B, 0),
    ItemData("Finish IMW", ItemClassification.progression, 0x100C, 0),
    ItemData("Finish MB", ItemClassification.progression, 0x100D, 0),
    ItemData("Finish MF", ItemClassification.progression, 0x100E, 0),
    ItemData("Finish OR", ItemClassification.progression, 0x100F, 0),
    ItemData("Finish OWC", ItemClassification.progression, 0x1010, 0),
    ItemData("Finish OWN", ItemClassification.progression, 0x1011, 0),
    ItemData("Finish SM", ItemClassification.progression, 0x1012, 0),
    ItemData("Finish SW", ItemClassification.progression, 0x1013, 0),
    
    ItemData("Finish DE2 relic", ItemClassification.progression, 0x1100, 0),
    ItemData("Finish DM3 relic", ItemClassification.progression, 0x1101, 0),
    ItemData("Finish DH4 relic", ItemClassification.progression, 0x1102, 0),
    ItemData("Finish DE6 relic", ItemClassification.progression, 0x1103, 0),
    ItemData("Finish S060 relic", ItemClassification.progression, 0x1104, 0),
    ItemData("Finish S282 relic", ItemClassification.progression, 0x1105, 0),
    
]

def get_classification(name: str) -> ItemClassification:
    for data in _item_table:
        if name == data.name:
            return data.classification
    return ItemClassification.filler

def get_id(name:str) -> int:
    for data in _item_table:
        if name == data.name:
            return data.code
    return -1

def get_items() -> Set[ItemData]:
    return _item_table
def get_filler_items():
    return [x for x in _item_table if x.amount==0 and x.classification == ItemClassification.filler]
def get_starting_items(world: "DVWorld"):
    L = []
    if world.options.dispatcher == 0:
        L.append("Dispatcher license")
    match world.options.start_loco:
        case 0:
            L.append("DE2 locomotive license")
        case 1:
            L.append("DM3 locomotive license")
        case 2:
            L.append("DH4 locomotive license")
        case 3:
            L.append("S060 locomotive license")
        case 4:
            L.append("S282 locomotive license")
        case 5:
            L.append("DE6 locomotive license")
        case 6: # Starter random
            L.append(world.random.choice(["DE2 locomotive license", "DM3 locomotive license", "S060 locomotive license"]))
    if "S060 locomotive license" in L or "S282 locomotive license" in L:
        L.extend(["Shovel", "Oiler", "Lighter"])
    match world.options.station_licenses:
        case 1:
            all_stations_but_mb = [x for x in world.all_stations_unlock if x != "MB Station unlock"]
            L.append(world.random.choice(all_stations_but_mb))
        case 2:
            L.extend([x for x in world.all_stations_unlock])
    match world.options.start_job:
        case 0:
            L.append("Freight haul license")
        case 1:
            L.append("Shunting license")
        case 2:
            L.append("Logistical haul license")
        case 4:
            pass
        case _:
            L.append(world.random.choice(["Freight haul license", "Shunting license", "Logistical haul license"]))
    return L