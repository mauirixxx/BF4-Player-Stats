from bf4ps.bulk_values import bulk_values


def test_bulk_values_binds_every_row_without_inlining_data():
    sql, params = bulk_values([{'guid': "x'); DROP TABLE t; --", 'kills': 3}, {'guid': 'b', 'kills': 4}], ('guid', 'kills'))
    assert sql == '(:v0_guid, :v0_kills), (:v1_guid, :v1_kills)'
    assert params == {'v0_guid': "x'); DROP TABLE t; --", 'v0_kills': 3, 'v1_guid': 'b', 'v1_kills': 4}


def test_empty_payload_is_supported():
    assert bulk_values([], ('guid',)) == ('', {})