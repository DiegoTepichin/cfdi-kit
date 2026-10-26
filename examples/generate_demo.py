"""Write a year of synthetic CFDI 4.0 invoices for a fictional freelancer, for demos and testing.

Usage: uv run python examples/generate_demo.py examples/demo
"""

from __future__ import annotations

import random
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

ME = ("CACX7605101P8", "XOCHILT CASAS CHAVEZ", "612", "52140")
CLIENTS = [
    ("EKU9003173C9", "ESCUELA KEMPER URGATE", "601", "42501"),
    ("IIA040805DZ4", "INDISTRIA ILUMINADORA DE ALMACENES", "601", "62661"),
    ("H&E951128469", "HERRERIA & ELECTRICOS", "601", "06002"),
    ("URE180429TM6", "UNIVERSIDAD ROBOTICA ESPAÑOLA", "601", "86991"),
]
SUPPLIERS = [
    ("KIJ0906199R1", "KERNEL INDUSTIA JUGUETERA", "601", "26015", "43232100", "Software"),
    ("MAG041126GT8", "MINERA AGUILAR", "601", "79125", "81161700", "Internet y telefonía"),
    ("OÑO120726RX3", "ORGANICOS ÑAVEZ OSORIO", "601", "40501", "50202300", "Cafetería"),
    ("XIA190128J61", "XENON INDUSTRIAL ARTICLES", "601", "76343", "43211503", "Equipo de cómputo"),
]
CENT = Decimal("0.01")
SAT = "SAT970701NN3"


@dataclass(frozen=True)
class Party:
    rfc: str
    name: str
    regime: str
    zip_code: str


def x(text: str) -> str:
    return escape(text, {'"': "&quot;"})


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def stamp(stamp_id: str, when: datetime) -> str:
    return (
        f'<tfd:TimbreFiscalDigital Version="1.1" UUID="{stamp_id}" '
        f'FechaTimbrado="{(when + timedelta(minutes=1)).isoformat()}" RfcProvCertif="{SAT}" '
        'NoCertificadoSAT="00001000000505142236" SelloCFD="demo" SelloSAT="demo"/>'
    )


def invoice(
    issuer: Party,
    receiver: Party,
    when: datetime,
    folio: int,
    product: str,
    description: str,
    subtotal: Decimal,
    method: str,
    withhold: bool,
) -> tuple[str, str, Decimal]:
    iva = (subtotal * Decimal("0.16")).quantize(CENT)
    isr = (subtotal * Decimal("0.10")).quantize(CENT) if withhold else Decimal(0)
    iva_w = (subtotal * Decimal("0.106667")).quantize(CENT) if withhold else Decimal(0)
    total = subtotal + iva - isr - iva_w
    stamp_id = str(uuid.UUID(int=random.getrandbits(128))).upper()
    transfer = (
        f'<cfdi:Traslado Base="{money(subtotal)}" Impuesto="002" TipoFactor="Tasa" '
        f'TasaOCuota="0.160000" Importe="{money(iva)}"/>'
    )
    line_withholdings = ""
    total_withholdings = ""
    withheld_attr = ""
    if withhold:
        line_withholdings = (
            "<cfdi:Retenciones>"
            f'<cfdi:Retencion Base="{money(subtotal)}" Impuesto="001" TipoFactor="Tasa" '
            f'TasaOCuota="0.100000" Importe="{money(isr)}"/>'
            f'<cfdi:Retencion Base="{money(subtotal)}" Impuesto="002" TipoFactor="Tasa" '
            f'TasaOCuota="0.106667" Importe="{money(iva_w)}"/>'
            "</cfdi:Retenciones>"
        )
        total_withholdings = (
            "<cfdi:Retenciones>"
            f'<cfdi:Retencion Impuesto="001" Importe="{money(isr)}"/>'
            f'<cfdi:Retencion Impuesto="002" Importe="{money(iva_w)}"/>'
            "</cfdi:Retenciones>"
        )
        withheld_attr = f' TotalImpuestosRetenidos="{money(isr + iva_w)}"'
    form = "99" if method == "PPD" else random.choice(["03", "04", "28"])
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Serie="A" Folio="{folio}" Fecha="{when.isoformat()}" FormaPago="{form}" SubTotal="{money(subtotal)}" Moneda="MXN" Total="{money(total)}" TipoDeComprobante="I" Exportacion="01" MetodoPago="{method}" LugarExpedicion="{issuer.zip_code}">
  <cfdi:Emisor Rfc="{x(issuer.rfc)}" Nombre="{x(issuer.name)}" RegimenFiscal="{issuer.regime}"/>
  <cfdi:Receptor Rfc="{x(receiver.rfc)}" Nombre="{x(receiver.name)}" DomicilioFiscalReceptor="{receiver.zip_code}" RegimenFiscalReceptor="{receiver.regime}" UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="{product}" Cantidad="1" ClaveUnidad="E48" Descripcion="{description}" ValorUnitario="{money(subtotal)}" Importe="{money(subtotal)}" ObjetoImp="02">
      <cfdi:Impuestos><cfdi:Traslados>{transfer}</cfdi:Traslados>{line_withholdings}</cfdi:Impuestos>
    </cfdi:Concepto>
  </cfdi:Conceptos>
  <cfdi:Impuestos{withheld_attr} TotalImpuestosTrasladados="{money(iva)}">{total_withholdings}<cfdi:Traslados>{transfer}</cfdi:Traslados></cfdi:Impuestos>
  <cfdi:Complemento>{stamp(stamp_id, when)}</cfdi:Complemento>
</cfdi:Comprobante>
"""
    return stamp_id, xml, total


def payment(
    issuer: Party, receiver: Party, when: datetime, document: str, total: Decimal
) -> tuple[str, str]:
    subtotal = (total / Decimal("1.16")).quantize(CENT)
    iva = total - subtotal
    stamp_id = str(uuid.UUID(int=random.getrandbits(128))).upper()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:pago20="http://www.sat.gob.mx/Pagos20" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Fecha="{when.isoformat()}" SubTotal="0" Moneda="XXX" Total="0" TipoDeComprobante="P" Exportacion="01" LugarExpedicion="{issuer.zip_code}">
  <cfdi:Emisor Rfc="{x(issuer.rfc)}" Nombre="{x(issuer.name)}" RegimenFiscal="{issuer.regime}"/>
  <cfdi:Receptor Rfc="{x(receiver.rfc)}" Nombre="{x(receiver.name)}" DomicilioFiscalReceptor="{receiver.zip_code}" RegimenFiscalReceptor="{receiver.regime}" UsoCFDI="CP01"/>
  <cfdi:Conceptos><cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago" ValorUnitario="0" Importe="0" ObjetoImp="01"/></cfdi:Conceptos>
  <cfdi:Complemento>
    <pago20:Pagos Version="2.0">
      <pago20:Totales MontoTotalPagos="{money(total)}"/>
      <pago20:Pago FechaPago="{when.isoformat()}" FormaDePagoP="03" MonedaP="MXN" TipoCambioP="1" Monto="{money(total)}">
        <pago20:DoctoRelacionado IdDocumento="{document}" MonedaDR="MXN" EquivalenciaDR="1" NumParcialidad="1" ImpSaldoAnt="{money(total)}" ImpPagado="{money(total)}" ImpSaldoInsoluto="0.00" ObjetoImpDR="02">
          <pago20:ImpuestosDR><pago20:TrasladosDR><pago20:TrasladoDR BaseDR="{money(subtotal)}" ImpuestoDR="002" TipoFactorDR="Tasa" TasaOCuotaDR="0.160000" ImporteDR="{money(iva)}"/></pago20:TrasladosDR></pago20:ImpuestosDR>
        </pago20:DoctoRelacionado>
      </pago20:Pago>
    </pago20:Pagos>
    {stamp(stamp_id, when)}
  </cfdi:Complemento>
</cfdi:Comprobante>
"""
    return stamp_id, xml


def main(target: Path) -> None:
    random.seed(2026)
    target.mkdir(parents=True, exist_ok=True)
    me = Party(*ME)
    folio = 100
    for month in range(1, 13):
        for client in random.sample(CLIENTS, k=random.randint(2, 3)):
            folio += 1
            when = datetime(2026, month, random.randint(2, 26), random.randint(9, 18), 0)
            amount = Decimal(random.randrange(8_000, 42_000, 500))
            method = "PPD" if client[0] == CLIENTS[0][0] else "PUE"
            withhold = client[0] != CLIENTS[2][0]
            party = Party(*client)
            stamp_id, xml, total = invoice(
                me,
                party,
                when,
                folio,
                "81111500",
                "Desarrollo de software",
                amount,
                method,
                withhold,
            )
            (target / f"emitida-{stamp_id}.xml").write_text(xml, encoding="utf-8")
            if method == "PPD" and month < 12:
                paid_at = when + timedelta(days=random.randint(20, 40))
                pay_id, pay_xml = payment(me, party, paid_at, stamp_id, total)
                (target / f"pago-{pay_id}.xml").write_text(pay_xml, encoding="utf-8")
        for rfc, name, regime, zip_code, product, description in random.sample(SUPPLIERS, k=3):
            when = datetime(2026, month, random.randint(1, 28), random.randint(8, 20), 0)
            low, high = (15_000, 30_000) if product == "43211503" else (300, 3_500)
            amount = Decimal(random.randrange(low, high, 50))
            if product == "43211503" and month not in (3, 9):
                continue
            stamp_id, xml, _ = invoice(
                Party(rfc, name, regime, zip_code),
                me,
                when,
                random.randint(1000, 99999),
                product,
                description,
                amount,
                "PUE",
                withhold=False,
            )
            (target / f"recibida-{stamp_id}.xml").write_text(xml, encoding="utf-8")
    print(f"wrote {len(list(target.glob('*.xml')))} invoices to {target}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "examples/demo"))
