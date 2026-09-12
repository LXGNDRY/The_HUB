from pathlib import Path

from modules.product_compliance import infer_hs_code, resolve_coo


def test_legacy_helpers_fail_closed_without_metadata_inference() -> None:
    assert infer_hs_code("Apparel & Accessories > Clothing > Pants", "Denim Goat") is None
    assert resolve_coo(["coo:CN"]) is None


def test_legacy_automations_cannot_write_inferred_compliance() -> None:
    root = Path(__file__).resolve().parents[1]
    webhook_source = (root / "api/routers/webhooks.py").read_text()
    scheduler_source = (root / "scheduler/jobs.py").read_text()
    engine_source = (root / "scheduler/engine.py").read_text()

    assert "update_inventory_item_compliance(inv_gid, coo, hs_code)" not in webhook_source
    assert "update_inventory_item_compliance(inv_gid, write_coo, write_hs)" not in scheduler_source
    assert "compliance_patch_job," not in engine_source
