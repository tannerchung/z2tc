from lib.data_feeds.nyrr import nyrr_distance_to_category, parse_nyrr_clock


def test_parse_nyrr_clock() -> None:
    assert parse_nyrr_clock("1:45:30") == 6330
    assert parse_nyrr_clock("0:53:16") == 3196
    assert parse_nyrr_clock("") is None


def test_nyrr_distance_to_category() -> None:
    assert nyrr_distance_to_category("Half-Marathon") == "Half Marathon"
    assert nyrr_distance_to_category("10 kilometers") == "10K"
    assert nyrr_distance_to_category("4 miles") is None
