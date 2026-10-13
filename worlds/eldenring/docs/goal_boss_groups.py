# python -m worlds.eldenring.docs.goal_boss_groups

from typing import Dict
import os
import html

from worlds.eldenring.bosses import all_bosses

all_groups: Dict[str, list[str]] = {}

if __name__ == '__main__':
    for boss in all_bosses:
        if not boss.missable:
            for t in boss.type:
                if t not in all_groups:
                    all_groups.update({t: []})
                all_groups[t].append(boss.name) 
            
    table = f"### Base Game\n"
    for type in all_groups:
        if type == "Gravesite Plain":
            table += f"### DLC\n"
        table += f"- [{type} Boss](#{type.lower().replace(" ", "-").replace("'", "").replace(",", "")}-boss)\n"

    
    table += "\n\n<table>\n"
    for (type, bosses) in all_groups.items():
        table += f"<tr><td><h3>\n\n### {html.escape(type)} Boss\n\n</td></tr>\n"
        for boss in sorted(bosses):
            table += f"<tr><td><strong>{html.escape(boss)}</strong></td></tr>\n"
    table += "</table>\n"
    # print(table)

    with open(
        os.path.join(os.path.dirname(__file__), 'en_goal_bosses_guide.md'),
        'r+',
        encoding='utf-8'
    ) as f:
        original = f.read()
        start_flag = "<!-- begin boss table -->\n"
        start = original.index(start_flag) + len(start_flag)
        end = original.index("<!-- end boss table -->")

        f.seek(0)
        f.write(original[:start] + table + original[end:])
        f.truncate()

    print("Updated docs/en_goal_bosses_guide.md!")
    
    