import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'api'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_ban_status as refresh

UUID='a95fea46-b958-4146-b63e-c73fe3db319d'

class BanStatusTests(unittest.TestCase):
    def test_independent_bans(self):
        with patch.object(refresh,'get',side_effect=[{'id':UUID,'bans':[{'state':None,'reason':'Cheating'}]},{UUID:{'banned':False}}]):
            result=refresh.fetch(941293200)
        self.assertTrue(result[1]);self.assertFalse(result[3])
    def test_bf4db_error_preserves_unknown(self):
        with patch.object(refresh,'get',side_effect=[{'id':UUID,'bans':[]},TimeoutError()]):
            result=refresh.fetch(941293200)
        self.assertFalse(result[1]);self.assertIsNone(result[3])
    def test_unknown_ba_state_never_clean(self):
        with patch.object(refresh,'get',side_effect=[{'id':UUID,'bans':[{'state':'Unrecognized'}]},{UUID:{'banned':True}}]):
            result=refresh.fetch(941293200)
        self.assertIsNone(result[1]);self.assertTrue(result[3])
    def test_missing_identity_is_error(self):
        with patch.object(refresh,'get',return_value={}):
            with self.assertRaises(ValueError):refresh.fetch(941293200)

if __name__=='__main__':unittest.main()
