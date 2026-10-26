"""Parse CFDI 3.3 and 4.0 XML into :class:`~cfdi_kit.models.Cfdi`."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from cfdi_kit.models import (
    ZERO,
    Cfdi,
    Concept,
    InvoiceType,
    Issuer,
    Payment,
    PaymentDocument,
    Payroll,
    Receiver,
    Relation,
    Stamp,
    Tax,
    TaxKind,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

CFDI_NAMESPACES = {
    "http://www.sat.gob.mx/cfd/3": "3.3",
    "http://www.sat.gob.mx/cfd/4": "4.0",
}
TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"
PAGOS10 = "http://www.sat.gob.mx/Pagos"
PAGOS20 = "http://www.sat.gob.mx/Pagos20"
NOMINA12 = "http://www.sat.gob.mx/nomina12"


class CfdiParseError(ValueError):
    """The document is not a CFDI this library can read."""

    def __init__(self, message: str, source: str | None = None) -> None:
        self.source = source
        super().__init__(f"{source}: {message}" if source else message)


def parse_file(path: str | Path) -> Cfdi:
    file = Path(path)
    return parse_bytes(file.read_bytes(), source=str(file))


def parse_bytes(data: bytes, source: str | None = None) -> Cfdi:
    try:
        root = ET.fromstring(data.lstrip())
    except ET.ParseError as exc:
        raise CfdiParseError(f"invalid XML ({exc})", source) from exc
    try:
        return _parse_root(root, source)
    except CfdiParseError as exc:
        if exc.source is None and source is not None:
            raise CfdiParseError(str(exc), source) from exc
        raise


def _parse_root(root: ET.Element, source: str | None) -> Cfdi:
    ns, local = _split(root.tag)
    if local != "Comprobante" or ns not in CFDI_NAMESPACES:
        raise CfdiParseError(
            f"root element is {root.tag!r}, expected a CFDI 3.3 or 4.0 Comprobante"
        )
    version = root.get("Version") or root.get("version")
    if version is None:
        raise CfdiParseError("Comprobante is missing attribute Version")
    if version != CFDI_NAMESPACES[ns]:
        raise CfdiParseError(f"unsupported CFDI version {version!r}")
    q = _Qualifier(ns)
    complement = root.find(q("Complemento"))
    taxes_node = root.find(q("Impuestos"))
    return Cfdi(
        version=version,
        invoice_type=_invoice_type(_required(root, "TipoDeComprobante")),
        issued_at=_datetime(_required(root, "Fecha")),
        series=root.get("Serie"),
        folio=root.get("Folio"),
        issuer=_issuer(_child(root, q("Emisor"))),
        receiver=_receiver(_child(root, q("Receptor"))),
        currency=_required(root, "Moneda"),
        exchange_rate=_optional_decimal(root, "TipoCambio"),
        subtotal=_decimal(_required(root, "SubTotal")),
        discount=_optional_decimal(root, "Descuento") or ZERO,
        total=_decimal(_required(root, "Total")),
        payment_form=root.get("FormaPago"),
        payment_method=root.get("MetodoPago"),
        place_of_issue=root.get("LugarExpedicion"),
        concepts=tuple(_concept(c, q) for c in _children(root, q("Conceptos"), q("Concepto"))),
        taxes=_taxes(taxes_node, q, "") if taxes_node is not None else (),
        total_transferred=_optional_decimal(taxes_node, "TotalImpuestosTrasladados"),
        total_withheld=_optional_decimal(taxes_node, "TotalImpuestosRetenidos"),
        stamp=_stamp(complement),
        relations=tuple(_relation(r, q) for r in root.iterfind(q("CfdiRelacionados"))),
        payments=_payments(complement),
        payroll=_payroll(complement),
        source=source,
    )


class _Qualifier:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def __call__(self, local: str) -> str:
        return f"{{{self.namespace}}}{local}"


def _split(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return "", tag


def _child(parent: ET.Element, tag: str) -> ET.Element:
    node = parent.find(tag)
    if node is None:
        raise CfdiParseError(f"missing required element {_split(tag)[1]}")
    return node


def _children(parent: ET.Element | None, container: str, item: str) -> Iterator[ET.Element]:
    if parent is None:
        return iter(())
    holder = parent.find(container)
    return iter(()) if holder is None else holder.iterfind(item)


def _required(node: ET.Element, attribute: str) -> str:
    value = node.get(attribute)
    if value is None:
        raise CfdiParseError(f"{_split(node.tag)[1]} is missing attribute {attribute}")
    return value


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except InvalidOperation as exc:
        raise CfdiParseError(f"{value!r} is not a number") from exc


def _optional_decimal(node: ET.Element | None, attribute: str) -> Decimal | None:
    if node is None:
        return None
    value = node.get(attribute)
    return None if value is None or not value.strip() else _decimal(value)


def _datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise CfdiParseError(f"{value!r} is not an ISO 8601 date-time") from exc


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise CfdiParseError(f"{value!r} is not an ISO 8601 date") from exc


def _invoice_type(code: str) -> InvoiceType:
    try:
        return InvoiceType(code)
    except ValueError as exc:
        raise CfdiParseError(f"unknown TipoDeComprobante {code!r}") from exc


def _issuer(node: ET.Element) -> Issuer:
    return Issuer(
        rfc=_required(node, "Rfc").strip().upper(),
        name=node.get("Nombre"),
        tax_regime=node.get("RegimenFiscal"),
    )


def _receiver(node: ET.Element) -> Receiver:
    return Receiver(
        rfc=_required(node, "Rfc").strip().upper(),
        name=node.get("Nombre"),
        cfdi_use=node.get("UsoCFDI"),
        tax_regime=node.get("RegimenFiscalReceptor"),
        postal_code=node.get("DomicilioFiscalReceptor"),
    )


def _concept(node: ET.Element, q: _Qualifier) -> Concept:
    taxes_node = node.find(q("Impuestos"))
    return Concept(
        product_key=_required(node, "ClaveProdServ"),
        quantity=_decimal(_required(node, "Cantidad")),
        unit_key=node.get("ClaveUnidad"),
        unit=node.get("Unidad"),
        description=_required(node, "Descripcion"),
        unit_value=_decimal(_required(node, "ValorUnitario")),
        amount=_decimal(_required(node, "Importe")),
        discount=_optional_decimal(node, "Descuento") or ZERO,
        tax_object=node.get("ObjetoImp"),
        taxes=_taxes(taxes_node, q, "") if taxes_node is not None else (),
    )


def _taxes(node: ET.Element, q: _Qualifier, suffix: str) -> tuple[Tax, ...]:
    """Read `Traslados`/`Retenciones`; `suffix` is "" for the invoice, "DR" or "P" for payments."""
    groups = (
        (TaxKind.TRANSFERRED, f"Traslados{suffix}", f"Traslado{suffix}"),
        (TaxKind.WITHHELD, f"Retenciones{suffix}", f"Retencion{suffix}"),
    )
    return tuple(
        _tax(item, kind, suffix)
        for kind, container, tag in groups
        for item in _children(node, q(container), q(tag))
    )


def _tax(node: ET.Element, kind: TaxKind, suffix: str) -> Tax:
    return Tax(
        kind=kind,
        code=_required(node, f"Impuesto{suffix}"),
        factor_type=node.get(f"TipoFactor{suffix}"),
        rate=_optional_decimal(node, f"TasaOCuota{suffix}"),
        base=_optional_decimal(node, f"Base{suffix}"),
        amount=_optional_decimal(node, f"Importe{suffix}"),
    )


def _relation(node: ET.Element, q: _Qualifier) -> Relation:
    return Relation(
        relation_type=_required(node, "TipoRelacion"),
        uuids=tuple(_required(r, "UUID").upper() for r in node.iterfind(q("CfdiRelacionado"))),
    )


def _stamp(complement: ET.Element | None) -> Stamp | None:
    node = None if complement is None else complement.find(f"{{{TFD}}}TimbreFiscalDigital")
    if node is None:
        return None
    return Stamp(
        uuid=_required(node, "UUID").strip().upper(),
        stamped_at=_datetime(_required(node, "FechaTimbrado")),
        sat_certificate=node.get("NoCertificadoSAT"),
        provider_rfc=node.get("RfcProvCertif"),
    )


def _payments(complement: ET.Element | None) -> tuple[Payment, ...]:
    if complement is None:
        return ()
    for namespace in (PAGOS20, PAGOS10):
        root = complement.find(f"{{{namespace}}}Pagos")
        if root is not None:
            q = _Qualifier(namespace)
            return tuple(_payment(p, q) for p in root.iterfind(q("Pago")))
    return ()


def _payment(node: ET.Element, q: _Qualifier) -> Payment:
    taxes_node = node.find(q("ImpuestosP"))
    return Payment(
        paid_at=_datetime(_required(node, "FechaPago")),
        payment_form=_required(node, "FormaDePagoP"),
        currency=_required(node, "MonedaP"),
        exchange_rate=_optional_decimal(node, "TipoCambioP"),
        amount=_decimal(_required(node, "Monto")),
        documents=tuple(_payment_document(d, q) for d in node.iterfind(q("DoctoRelacionado"))),
        taxes=_taxes(taxes_node, q, "P") if taxes_node is not None else (),
    )


def _payment_document(node: ET.Element, q: _Qualifier) -> PaymentDocument:
    taxes_node = node.find(q("ImpuestosDR"))
    installment = node.get("NumParcialidad")
    return PaymentDocument(
        uuid=_required(node, "IdDocumento").strip().upper(),
        series=node.get("Serie"),
        folio=node.get("Folio"),
        currency=node.get("MonedaDR"),
        exchange_rate=_optional_decimal(node, "EquivalenciaDR")
        or _optional_decimal(node, "TipoCambioDR"),
        installment=int(installment) if installment else None,
        previous_balance=_optional_decimal(node, "ImpSaldoAnt"),
        amount_paid=_optional_decimal(node, "ImpPagado") or ZERO,
        remaining_balance=_optional_decimal(node, "ImpSaldoInsoluto"),
        taxes=_taxes(taxes_node, q, "DR") if taxes_node is not None else (),
    )


def _payroll(complement: ET.Element | None) -> Payroll | None:
    node = None if complement is None else complement.find(f"{{{NOMINA12}}}Nomina")
    if node is None:
        return None
    deductions = node.find(f"{{{NOMINA12}}}Deducciones")
    return Payroll(
        payroll_type=_required(node, "TipoNomina"),
        payment_date=_date(_required(node, "FechaPago")),
        period_start=_date(_required(node, "FechaInicialPago")),
        period_end=_date(_required(node, "FechaFinalPago")),
        days_paid=_decimal(_required(node, "NumDiasPagados")),
        total_perceptions=_optional_decimal(node, "TotalPercepciones") or ZERO,
        total_deductions=_optional_decimal(node, "TotalDeducciones") or ZERO,
        total_other_payments=_optional_decimal(node, "TotalOtrosPagos") or ZERO,
        isr_withheld=_optional_decimal(deductions, "TotalImpuestosRetenidos") or ZERO,
    )
