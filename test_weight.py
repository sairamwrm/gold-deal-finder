def test_ajio_combo_coin_weight():
    title = "Muthoot PAPPACHAN : Set of 2 gold coin 24k (999) 3GMS (2gm+1gm)"
    assert extract_weight_grams(title) == 3.0
