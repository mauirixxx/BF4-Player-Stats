import pytest
from bf4ps.manual_battlelog_url import parse_battlelog_soldier_url


def test_valid_battlelog_soldier_url():
    p = parse_battlelog_soldier_url('https://battlelog.battlefield.com/bf4/soldier/mauirixxx/stats/236753552/pc/')
    assert (p.persona_id, p.platform, p.soldier_name) == (236753552, 'pc', 'mauirixxx')


@pytest.mark.parametrize('url', [
    'http://battlelog.battlefield.com/bf4/soldier/name/stats/123/pc/',
    'https://battlelog.battlefield.com.evil.example/bf4/soldier/name/stats/123/pc/',
    'https://battlelog.battlefield.com@evil.example/bf4/soldier/name/stats/123/pc/',
    'https://battlelog.battlefield.com/bf4/soldier/name/stats/123/pc/?x=1',
    'https://battlelog.battlefield.com/bf4/soldier/name/stats/123/ps3/',
    'https://battlelog.battlefield.com/bf4/soldier/name/stats/0/pc/',
    'https://battlelog.battlefield.com/bf4/soldier/name/stats/999999999999999999999/pc/',
    'https://battlelog.battlefield.com/bf4/soldier/%2Fetc/stats/123/pc/',
    'https://battlelog.battlefield.com/bf4/soldier/name/stats/123/pc/#fragment',
    'https://battlelog.battlefield.com:443/bf4/soldier/name/stats/123/pc/',
 ])
def test_reject_invalid_urls(url):
    with pytest.raises(ValueError):
        parse_battlelog_soldier_url(url)