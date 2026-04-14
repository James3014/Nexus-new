from nexus.demo.refactor_parser_purity import parse_pairs

def test_parse_pairs_no_input_mutation_and_trim():
    src = ["a=1", "  ", "b=2 "]
    out = parse_pairs(src)
    assert out == {"a": "1", "b": "2"}
    assert src == ["a=1", "  ", "b=2 "]
