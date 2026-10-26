from cfdi_kit.catalogs import Catalog, codes, label


def test_label_known_code() -> None:
    assert label(Catalog.PAYMENT_METHOD, "PPD") == "Pago en parcialidades o diferido"
    assert label(Catalog.TAX_REGIME, "626") == "Régimen Simplificado de Confianza"


def test_label_falls_back_to_code() -> None:
    assert label(Catalog.PAYMENT_FORM, "77") == "77"


def test_label_of_missing_code_is_none() -> None:
    assert label(Catalog.CFDI_USE, None) is None


def test_every_catalog_has_entries() -> None:
    assert all(codes(catalog) for catalog in Catalog)
