"""Document ids in URLs are strings; the resolver must try every `_id` type a user may have used."""

from bson import ObjectId

from app.services.data_browser import id_candidates


def test_object_id_then_string():
    oid = ObjectId()
    assert id_candidates(str(oid)) == [oid, str(oid)]


def test_integer_ids_are_tried_before_the_string_form():
    assert id_candidates("2") == [2, "2"]
    assert id_candidates("-7") == [-7, "-7"]
    assert id_candidates("9223372036854775807") == [9223372036854775807, "9223372036854775807"]


def test_out_of_range_or_non_numeric_stay_strings():
    assert id_candidates("9223372036854775808") == ["9223372036854775808"]
    assert id_candidates("2.5") == ["2.5"]
    assert id_candidates("abc") == ["abc"]
    assert id_candidates("") == [""]
