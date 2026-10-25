import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from api.community_export import build, METRICS

class CommunityAggregateTests(unittest.TestCase):
    def test_the_hamster_that_counted_twice(self):
        """A repeat read of the same current snapshot never accumulates totals."""
        row={'platform':'pc','detailed_soldiers':1,**{m:'0' for m in METRICS}}
        row.update(kills='100',deaths='20',shots_fired='500',shots_hit='250')
        class Conn:
            def execute(self, query):
                q=str(query)
                if 'current_database()' in q:return SimpleNamespace(scalar_one=lambda:'bf4_playerstats')
                if 'count(*) AS count' in q:return SimpleNamespace(mappings=lambda:[SimpleNamespace(platform='pc',count=1)])
                if 'AS full_soldiers' in q:return SimpleNamespace(mappings=lambda:[SimpleNamespace(platform='pc',full_soldiers=1)])
                return SimpleNamespace(mappings=lambda:[row])
        first=build(Conn());second=build(Conn())
        self.assertEqual(first['platforms']['all'],second['platforms']['all'])
        self.assertEqual(first['platforms']['all']['kills'],100)
        self.assertEqual(first['platforms']['all']['detailed_soldiers'],1)
        self.assertEqual(first['platforms']['ps4']['kills'],0)

if __name__=='__main__':unittest.main()
