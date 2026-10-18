import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from discover_soldier_platoons import SoldierHeader

def test_holy_tag_and_ucav_club():
    p=SoldierHeader()
    p.feed('<h1 class="soldier-info-name"><span>[HOLY]</span><span>mauirixxx</span></h1><a href="/bf4/platoons/view/123/">unrelated</a><span class="club-link">Platoon: <a href="/bf4/platoons/view/4452867151931601735/">UCAV Church</a></span>')
    assert p.tag=='[HOLY]'
    assert p.club_ids==[4452867151931601735]

def test_no_club_link():
    p=SoldierHeader()
    p.feed('<h1 class="soldier-info-name"><span>[ABC]</span></h1><a href="/bf4/platoons/view/123/">unrelated</a>')
    assert p.club_ids==[]
