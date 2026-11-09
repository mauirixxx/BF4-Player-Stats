from bf4ps.bf4br_identity_sync import PLATFORMS, BATCH

def test_bf4br_platform_mapping():
    assert PLATFORMS == {1: 'pc', 32: 'ps4', 64: 'xboxone'}

def test_bounded_batch():
    assert 0 < BATCH <= 1000

[executed on device: tcou (720a0073-649a-4660-8c09-00c2e6d0e587)]