from excel_search.text import display_value, normalize_text, query_terms


def test_normalize_text_handles_full_width_case_and_whitespace() -> None:
    assert normalize_text("  ＴＹＰＥ－Ｃ\n 0.9M  ") == "type-c 0.9m"


def test_query_terms_are_unique_and_use_and_style_tokens() -> None:
    assert query_terms("四孔  墨西哥 四孔") == ("四孔", "墨西哥")


def test_display_value_drops_integer_decimal_suffix() -> None:
    assert display_value(853669000.0) == "853669000"
    assert display_value(True) == "TRUE"
