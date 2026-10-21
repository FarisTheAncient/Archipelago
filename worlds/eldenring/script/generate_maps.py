from argparse import ArgumentParser
from dataclasses import dataclass
import json
import os
from typing import Dict, Set, List, Iterable, Optional

from worlds.eldenring.locations import ERLocationData, location_tables, region_order_dlc


@dataclass
class MapGroup:
    name: str
    """The name of the map."""

    override_regions: Optional[List[str]] = None
    """Region names to use instead of the map name."""

    silo: bool = False
    """Whether *only* the listed regions should be shown in the map image.
    This also prevents the listed regions from appearing in all other maps
    unless explicitly listed there (e.g. Royal and Ashen Leyndell are both
    siloed but have overlapping items, and those items are only shown in
    those two map images).
    """

    underground: bool = False
    """Whether the map is base game underground. Can be inferred but simple
    enough to put here."""

    def regions(self) -> Iterable[str]:
        return self.override_regions or [self.name]


map_groups: List[MapGroup] = [
    MapGroup("Limgrave", [
        "Limgrave",
        "Stormhill",
        "Coastal Cave",
        "Church of Dragon Communion",
        "Groveside Cave",
        "Stormfoot Catacombs",
        "Limgrave Tunnels",
        "Murkwater Cave",
        "Murkwater Catacombs",
        "Highroad Cave",
        "Deathtouched Catacombs",
        "Fringefolk Hero's Grave",
        "Divine Tower of Limgrave", # accessed from Stormveil
    ]),

    # The canonical location is in the middle of the ocean (in-game map overrides this).
    # TODO: It has the same orientation as Fortified Manor in Leyndell so this is a great
    # candidate for a custom image based on that.
    MapGroup("Roundtable Hold"),

    MapGroup("Stormveil Castle", [
        "Stormveil Start",
        "Stormveil Castle",
        "Stormveil Throne",
        "The Four Belfries (Chapel of Anticipation)",
    ], silo=True),

    MapGroup("Weeping Peninsula", [
        "Weeping Peninsula",
        "Impaler's Catacombs",
        "Tombsward Catacombs",
        "Tombsward Cave",
        "Morne Tunnel",
        "Earthbore Cave",
    ]),

    MapGroup("Liurnia of The Lakes", [
        "Liurnia of The Lakes",
        "Bellum Highway",
        "Road's End Catacombs",
        "Black Knife Catacombs",
        "Cliffbottom Catacombs",
        "Stillwater Cave",
        "Lakeside Crystal Cave",
        "Academy Crystal Cave",
        "Raya Lucaria Crystal Tunnel",
        "Caria Manor", # only includes after Loretta so can't be split out currently
        "Carian Study Hall",
        "Carian Study Hall (Inverted)",
    ]),

    MapGroup("Raya Lucaria Academy", [
        "Raya Lucaria Academy",
        "Raya Lucaria Academy Main",
        "Raya Lucaria Academy Chest",
        "Raya Lucaria Academy Library",
    ], silo=True),
    MapGroup("Moonlight Altar", silo=True),

    # Could also include locations outside the precipice in Liurnia for better bounding boxes.
    MapGroup("Ruin-Strewn Precipice", silo=True),

    MapGroup("Caelid", [
        "Caelid",
        "Caelid Catacombs",
        "Gaol Cave",
        "Sellia Crystal Tunnel",
        "Abandoned Cave",
        "Minor Erdtree Catacombs",
        "Gael Tunnel",
        "Great-Jar",
        "Redmane Castle Post Radahn",
        "Wailing Dunes",
        "War-Dead Catacombs",
        "Dragonbarrow",
        "Dragonbarrow Cave",
        "Sellia Hideaway",
        "Divine Tower of Caelid",
    ]),

    MapGroup("Siofra", [
        "Siofra River",
        "Nokron, Eternal City Start",
        "Nokron, Eternal City",
        "The Four Belfries (Nokron)",
    ], underground=True),

    MapGroup("Mohgwyn Palace", silo=True, underground=True),

    MapGroup("Deeproot Depths", [
        "Deeproot Depths Upper",
        "Deeproot Depths",
        "Deeproot Depths Boss",
    ], underground=True),

    # TODO astel can be separated, ignored, or manually placed
    MapGroup("Ainsel River", [
        "Ainsel River",
        "Ainsel River Main",
        "Lake of Rot",
    ], underground=True),

    MapGroup("Altus Plateau", [
        "Altus Plateau",
        "Sainted Hero's Grave",
        "Unsightly Catacombs",
        "Perfumer's Grotto",
        "Sage's Cave",
        "Old Altus Tunnel",
        "Altus Tunnel",
        "Capital Outskirts",
        "Auriza Hero's Grave",
        "Auriza Side Tomb",
        "Sealed Tunnel",
    ]),

    MapGroup("Mt. Gelmir", [
        "Mt. Gelmir",
        "Wyndham Catacombs",
        "Gelmir Hero's Grave",
        "Seethewater Cave",
        "Volcano Cave",
    ]),

    MapGroup("Volcano Manor", [
        "Volcano Manor Dungeon",
        "Volcano Manor Entrance",
        "Volcano Manor Drawing Room",
        "Volcano Manor",
        "Volcano Manor Upper",
    ], silo=True),

    MapGroup("Leyndell, Royal Capital", [
        "Leyndell, Royal Capital",
        "Leyndell, Royal Capital Unmissable",
        "Leyndell, Royal Capital Throne",
        "Divine Bridge",
    ], silo=True),

    MapGroup("Leyndell, Ashen Capital", [
        "Leyndell, Ashen Capital",
        "Leyndell, Ashen Capital Throne",
        "Erdtree",
        "Leyndell, Royal Capital Unmissable", # also in Royal Capital
        "Divine Bridge", # also in Royal Capital
    ], silo=True),

    MapGroup("Subterranean Shunning-Grounds", [
        "Subterranean Shunning-Grounds",
        "Leyndell Catacombs",
        "Frenzied Flame Proscription",
    ], silo=True),

    MapGroup("Post-Leyndell", [
        "Divine Tower of East Altus",
        "Forbidden Lands",
    ], silo=True),

    MapGroup("Mountaintops of the Giants", [
        "Mountaintops of the Giants",
        "Giants' Mountaintop Catacombs",
        "Spiritcaller Cave",
        "Flame Peak",
        "Giant-Conquering Hero's Grave",
    ]),

    MapGroup("Farum Azula", [
        "Farum Azula",
        "Farum Azula Main",
        "The Four Belfries (Farum Azula)",
    ]),

    MapGroup("Consecrated Snowfield", [
        "Consecrated Snowfield",
        "Hidden Path to the Haligtree",
        "Consecrated Snowfield Catacombs",
        "Cave of the Forlorn",
        "Yelough Anix Tunnel",
    ]),

    MapGroup("Miquella's Haligtree", [
        "Miquella's Haligtree",
        "Elphael, Brace of the Haligtree",
    ]),

    MapGroup("Gravesite Plain", [
        "Gravesite Plain",
        "Fog Rift Catacombs",
        "Belurat Gaol",
        "Dragon's Pit",
        "Ruined Forge Lava Intake",
        # Gravesite Plain bounding box includes Ellac River, so may as well
        "Ellac River",
        "Rivermouth Cave",
    ]),

    MapGroup("Belurat and Enir-Ilim", [
        "Belurat",
        "Belurat Swamp",
        "Enir-Ilim",
    ], silo=True),

    MapGroup("Castle Ensis", [
        "Castle Ensis",
        "Fog Rift Fort",
    ], silo=True),

    # Jagged Peak is a big area but low check density
    MapGroup("Jagged Peak", [
        "Jagged Peak Foot",
        "Jagged Peak",
        "Finger Ruins of Rhia",
    ]),

    MapGroup("Cerulean Coast and Charo's Hidden Grave", [
        "Cerulean Coast",
        "Charo's Hidden Grave",
        "Lamenter's Gaol (Entrance)",
        "Lamenter's Gaol (Upper)", #main
        "Lamenter's Gaol (Lower)", #boss
        "Stone Coffin Fissure",
    ]),

    MapGroup("Scadu Altus", [
        "Scadu Altus",
        "Bonny Gaol",
        "Ruined Forge of Starfall Past",
        "Rauh Ruins Limited",
        "Cathedral of Manus Metyr",
        "Finger Ruins of Miyr",
        # Recluses' River could alternately be separate and siloed
        "Recluses' River",
        "Darklight Catacombs",
    ]),

    MapGroup("Rauh Ruins and Base", [
        "Ancient Ruins of Rauh",
        "Rauh Base",
        "Scorpion River Catacombs",
        "Taylew's Ruined Forge",
    ]),

    MapGroup("Shadow Keep", [
        "Shadow Keep",
    ], silo=True),

    # Good luck
    MapGroup("Shadow Keep Storehouse", [
        "Shadow Keep Storehouse",
        "Shadow Keep Storehouse Back",
    ], silo=True),

    MapGroup("Shadow Keep, Church District", [
        "Shadow Keep, Church District",
        "Shadow Keep, Church District Lower",
    ], silo=True),

    MapGroup("Shadow Keep, West Rampart", [
        "Shadow Keep, West Rampart",
    ], silo=True),

    # Huge area but very low check density
    MapGroup("Scaduview", [
        "Scaduview",
        "Scadutree Base",
        "Hinterland",
        "Finger Ruins of Dheo",
    ], silo=True),

    MapGroup("Abyssal Woods", [
        "Abyssal Woods",
        "Midra's Manse",
    ], silo=True),
]


@dataclass
class ImageCoord:
    image: str
    x: int
    y: int


@dataclass
class MapImage:
    name: str
    base_image: str
    min_x: int
    max_x: int
    min_y: int
    max_y: int

    def contains(self, coord: ImageCoord) -> bool:
        return (self.min_x <= coord.x < self.max_x
                and self.min_y <= coord.y < self.max_y
                and self.base_image == coord.image)


def main(map_dir: str):
    with open(os.path.join(map_dir, "coords.json")) as f:
        coords_data = json.load(f)
        key_locations: Dict[str, ImageCoord] = {key: ImageCoord(**coord) for (key, coord) in coords_data.items()}

    def get_location_coord(location: ERLocationData) -> ImageCoord:
        if not location.key:
            raise KeyError(location.name)
        return key_locations[location.key]

    dungeon_regions: Set[str] = set(name for (name, locs) in location_tables.items() if any(loc.dungeon for loc in locs))
    dlc_regions: Set[str] = set(region_order_dlc)
    silo_regions: Set[str] = set(region for group in map_groups if group.silo for region in group.regions())

    for group in map_groups:
        regions = group.regions()
        base_image = ("underground" if group.underground
                      else ("dlc" if any(region in dlc_regions for region in regions) else "base"))
        group_coords: List[ImageCoord] = []
        for region in regions:
            if region in dungeon_regions:
                # Two ways possible to deal with minidungeon locations:
                # 1. Generate a unique image file per minidungeon, which is probably
                #    how custom maps would be handled as well. Note Lamenter's Gaol
                #    is one minidungeon in 3 regions. This basically amounts to
                #    automatically creating silos for each minidungeon.
                # 2. Reuse image file(s) for the overall region. In that case, the
                #    bounding box for the region should include these locations.
                continue
            for location in location_tables[region]:
                coord = get_location_coord(location)
                if coord.image != base_image:
                    raise RuntimeError(f"{location.name} {location.key} in {region} is in {coord.image}, expected {base_image}")
                group_coords.append(coord)
        if not len(group_coords):
            raise RuntimeError(f"No coordinates found in {group.name}")

        # Can change/vary this. The base images are very big so don't really need to validate bounds.
        border = 100
        # TODO: Split up very big regions further. Can put stuff in MapGroup to specify.
        full_image = MapImage(
            name=group.name,
            base_image=base_image,
            min_x=min(coord.x for coord in group_coords) - border,
            max_x=max(coord.x for coord in group_coords) + border,
            min_y=min(coord.y for coord in group_coords) - border,
            max_y=max(coord.y for coord in group_coords) + border,
        )
        images = [full_image]

        # Quadratic or cubic or something nbd
        count = 0
        for region, locations in location_tables.items():
            if region not in regions and (group.silo or region in silo_regions):
                continue
            if region in dungeon_regions:
                # See above about minidungeon locations
                continue
            for location in locations:
                coord = get_location_coord(location)
                for image in images:
                    if image.contains(coord):
                        # TODO: Do something
                        count += 1

        print(f"{group.name}: {count} locations")


if __name__ == "__main__":
    # With venv: python -m worlds.eldenring.script.generate_maps --map-dir <dir>
    parser = ArgumentParser(prog="generate_maps")
    parser.add_argument("--map-dir", required=True,
                        help="Path to directory with image files and coords.json")
    args = parser.parse_args()

    main(args.map_dir)
