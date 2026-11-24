from guji_manager.cell_ref import cell_of, cell_ref


def test_identity_for_now():
    assert cell_ref("vol21:11:7:3") == "vol21:11:7:3" and cell_of(cell_ref("vol21:11:7:3a")) == "vol21:11:7:3a"
