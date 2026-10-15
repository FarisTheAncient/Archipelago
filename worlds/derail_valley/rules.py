from typing import List
from rule_builder.rules import Has, HasAny, HasAll, HasFromList, HasAllCounts, True_, Or, Rule

from .locations import DVLocation

can_operate_steam = HasAll("Oiler", "Lighter") & HasAny("Shovel", "Golden Shovel", "Expert Shovel")

def military(station):
    if station == "MB":
        return Has("Progressive Military license")
    return True_()
def can_operate(loco):
    if loco in ["S060 locomotive license", "S282 locomotive license"]:
        return can_operate_steam & Has(loco)
    return Has(loco)
def set_location_rules(world: "DVWorld", location_table: List[DVLocation]) -> None:
    victory_condition = world.options.victory_condition.value # 0 = Nb jobs / 1 = Relic
    transport_job = HasAny("Freight haul license", "Logistical haul license")
    job_license = Has("Shunting license") | transport_job
    nb_shunts = world.options.nb_shunts.value
    nb_freights = world.options.nb_freights.value
    can_operate_one_loco = Or(*[can_operate(f"{loco} locomotive license") for loco in world.all_locos])
    can_make_money = job_license & can_operate_one_loco 

    def relic_loco_rule(loco_name: str, level: int=1) -> Rule:
        if world.options.demo_loco_spawn.value == 0:
            return True_() # Always have access, somewhere
        else:
            return Has(f"Demo locomotive {loco_name}",level)
    
    #Readability
    set_rule = lambda loc, rule: world.set_rule(world.multiworld.get_location(loc, world.player), rule)

    # if world.options.shop > 0:
    #     for i in range(19):
    #         set_rule(world.multiworld.get_location(f"GF shop unique item {i+1}", player), lambda state: can_make_money(state) and state.has("GF", player))
        
    #     for i in range(18):
    #         set_rule(world.multiworld.get_location(f"MF shop unique item {i+1}", player), lambda state: can_make_money(state) and state.has("MF", player))
        
    #     for i in range(11):
    #         set_rule(world.multiworld.get_location(f"HB shop unique item {i+1}", player), lambda state: can_make_money(state) and state.has("HB", player))

    #     for i in range(5):
    #         set_rule(world.multiworld.get_location(f"FF shop unique item {i+1}", player), lambda state: can_make_money(state) and state.has("FF", player))
        
    #     for i in range(26):
    #         set_rule(world.multiworld.get_location(f"CW shop unique item {i+1}", player), lambda state: can_make_money(state) and state.has("CW", player))
    # if world.options.shop > 1:
    #     for i in range(10):
    #         set_rule(world.multiworld.get_location(f"Common shop item {i+1}", player), lambda state: can_make_money(state) and state.has_any(["GF","MF", "HB", "FF", "CW"], player))
    
    # Win condition
    if victory_condition == 0:
        world.set_completion_rule(HasFromList(*("Finish "+station for station in world.all_stations), count=world.options.nb_stations.value))
    else: #VictoryCondition.option_demo_loco
        world.set_completion_rule(HasFromList(*(f"Finish {loco} relic" for loco in world.all_locos), count=world.options.nb_demo_locos.value))
    
    # Rules for demonstrator locations
    for loc in location_table:
        if loc.address is not None and 0x400 <= loc.address and loc.address < 0x500:
            n = 2 if loc.name[2] in [' ', '/'] else 3
            station = loc.name[:n]
            set_rule(loc.name, HasAll(f"{station} Station unlock", "Museum license"))

    # Orders belong to their stations
    for station in world.all_stations:
        for k in range(nb_shunts):
            set_rule(f"{station} shunting order {k+1}", can_operate_one_loco & HasAll(f"{station} Station unlock", "Shunting license") & military(station))
        for k in range(nb_freights):
            set_rule(f"{station} transport order {k+1}", can_operate_one_loco & Has(f"{station} Station unlock") & transport_job & military(station))
        
        set_rule("Finish "+station, (can_make_money & Has(f"{station} Station unlock") & military(station)) if victory_condition == 0 else True_())
    
    for loco in world.all_locos:
        if world.options.nb_locos.value > 0:
            set_rule(loco+" orders completed", can_make_money & can_operate(f"{loco} locomotive license"))
        if world.options.museum_checks:
            set_rule(loco+" relic parts to museum", can_make_money & Has("Museum license") & relic_loco_rule(loco,1))
            set_rule(loco+" relic painted", can_make_money & HasAllCounts({f"{loco} locomotive license":1, "Paint Sprayer":1, "Manual service license":1, "Museum license":1} | ({} if True else {"Sand can":2, "Demonstrator Paint Can":2})) & relic_loco_rule(loco,1))
        set_rule(f"Finish {loco} relic",
                       (can_make_money & HasAllCounts({f"{loco} locomotive license":1, "Paint Sprayer":1, "Manual service license":1, "Museum license":1}) & relic_loco_rule(loco,2))
                       if victory_condition == 1 else True_())
    
    set_rule("DE2 license", can_make_money)
    set_rule("DM3 license", can_make_money)
    set_rule("DH4 license", can_make_money & Has("Progressive Train Length license", 2))
    set_rule("DE6 license", can_make_money & Has("Progressive Concurrent orders license", 2))
    set_rule("S060 license", can_make_money)
    set_rule("S282 license", can_make_money & Has("Progressive Concurrent orders license", 2))
    set_rule("Dispatcher license", can_make_money)
    set_rule("Manual service license", can_make_money & Has("Progressive Train Length license"))
    set_rule("Multiple unit license", can_make_money & Has("Progressive Concurrent orders license"))
    set_rule("Concurrent 1 license", can_make_money)
    set_rule("Concurrent 2 license", can_make_money & Has("Progressive Concurrent orders license"))
    set_rule("Museum license", can_make_money & Has("Manual service license"))
    set_rule("Train driver license", can_make_money)

    set_rule("Shunting license", can_make_money)
    set_rule("Logistical haul license", can_make_money & Has("Progressive Concurrent orders license"))
    set_rule("Fragile license", can_make_money)
    set_rule("Long 1 license", can_make_money)
    set_rule("Long 2 license", can_make_money & Has("Progressive Train Length license"))
    set_rule("Hazmat 1 license", can_make_money & Has("Fragile license"))
    set_rule("Hazmat 2 license", can_make_money & Has("Progressive Hazmat license"))
    set_rule("Hazmat 3 license", can_make_money & Has("Progressive Hazmat license", 2))
    set_rule("Military 1 license", can_make_money)
    set_rule("Military 2 license", can_make_money & Has("Progressive Military license"))
    set_rule("Military 3 license", can_make_money & Has("Progressive Military license", 2))
    set_rule("Freight haul license", can_make_money)

    set_rule("Opening Steves garage", Has("Steve's Garage Key (DE6 Slug)"))
    set_rule("Opening Reginald garage", Has("Reginald's Garage Key (Caboose)"))
    set_rule("Opening Old Bob garage", Has("Old Bob's Garage Key (BE2)"))
    set_rule("Opening Olaf garage", Has("Olaf's Garage Key (DM1U)"))


