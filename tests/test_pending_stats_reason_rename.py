from guji_manager.pending_stats import _reason


def test_renamed_reason_maps_to_new_name():
    """线上旧单写的 group_form_open（Z06）按 yaml renamed 计成 variant_form_open（V02，11-07）；空记 unknown；没见过的值原样留。"""
    assert _reason("group_form_open") == "variant_form_open"
    assert _reason("ref_replaced") == "ref_ocr_diff"
    assert _reason("") == "unknown" and _reason(None) == "unknown"
    assert _reason("group_abstain") == "group_abstain"
    assert _reason("whatever_new") == "whatever_new"
