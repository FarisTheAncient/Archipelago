from typing import Callable


from typing import Dict, Set, Callable, TYPE_CHECKING
from BaseClasses import CollectionState, MultiWorld

from worlds.generic.Rules import set_rule, add_rule

if TYPE_CHECKING:
    from . import GrimDawnWorld
else:
    GrimDawnWorld = object

class GrimDawnRules:
    world: GrimDawnWorld
    player: int
    region_rules: Dict[str, Callable[[CollectionState], bool]]

    location_rules: Dict[str, Callable[[CollectionState], bool]]

    def __init__(self, world: GrimDawnWorld) -> None:
        self.world = world
        self.player = world.player

        self.region_rules = {

        }

        
        self.location_rules = {
            "Retrieve Isaac's Stash": lambda state:
                self.has_isaac_knowledge(state),
            "Confront Direni": lambda state:
                self.has_cultist_orders(state),
            "Deliver Menhir": lambda state:
                self.has_menhir(state),
            "Depraved Sanctuary Chest": lambda state:
                self.has_strange_key(state),
        }

    def has_isaac_knowledge(self, state) -> bool:
        return state.has("Isaac's Knowledge", self.player)
    def has_cultist_orders(self, state) -> bool:
        return state.has("Cultist Orders", self.player)
    def has_menhir(self, state) -> bool:
        return state.has("Menhir", self.player)
    def has_strange_key(self, state) -> bool:
        return state.has("Strange Key", self.player)

    def set_grim_dawn_rules(self) -> None:
        multiworld = self.world.multiworld


        for region in multiworld.get_regions(self.player):
            for entrance in region.entrances:
                if entrance.name in self.region_rules:
                    set_rule(entrance, self.region_rules[entrance.name])
            for location in region.locations:
                if location.name in self.location_rules:
                    set_rule(location, self.location_rules[location.name])
