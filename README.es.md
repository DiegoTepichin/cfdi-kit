# cfdi-kit

Convierte una carpeta de facturas CFDI del SAT (XML) en Excel, DataFrames de pandas, un resumen mensual de ingresos, gastos e IVA y un reporte HTML de un solo archivo. Todo corre en tu computadora; ningún dato de tus facturas sale de ella.

[![CI](https://github.com/DiegoTepichin/cfdi-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/DiegoTepichin/cfdi-kit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Read in English](README.md)

![Reporte HTML generado por cfdi-kit a partir de las facturas sintéticas de ejemplo](https://raw.githubusercontent.com/DiegoTepichin/cfdi-kit/main/docs/report.png)

*`cfdi-kit report` sobre las facturas sintéticas de [`examples/demo`](examples/demo).*

## Por qué

Cada factura en México es un XML. Revisar un mes implica abrir archivos uno por uno, capturar montos a mano en Excel o subir tu información fiscal a un servicio en la nube. `cfdi-kit` lee cientos de CFDIs en un segundo, directo de la carpeta o del ZIP que descargas del portal del SAT, sin que salgan de tu equipo.

## Instalación

```bash
pip install cfdi-kit
```

o sin instalar, con [uv](https://docs.astral.sh/uv/):

```bash
uvx cfdi-kit --help
```

Requiere Python 3.11 o superior.

## Inicio rápido

Pruébalo con las facturas de ejemplo (una persona freelance ficticia, RFC `CACX7605101P8`, un año de facturas):

```bash
git clone https://github.com/DiegoTepichin/cfdi-kit && cd cfdi-kit
uv run cfdi-kit summary examples/demo --rfc CACX7605101P8 --basis cash
```

```text
CACX7605101P8 · cash basis · MXN

  Month     Income  VAT charged  VAT withheld   Expenses  VAT creditable   Net VAT
-------  ---------  -----------  ------------  ---------  --------------  --------
2026-01  61,000.00     9,760.00      4,160.01   2,500.00          400.00  5,199.99
2026-02  26,500.00     4,240.00          0.00   2,400.00          384.00  3,856.00
2026-03  74,000.00    11,840.00      7,893.36  28,700.00        4,592.00   -645.36
...
```

Con tus propias facturas:

```bash
cfdi-kit parse ~/Downloads/facturas -o facturas.xlsx --rfc TU_RFC    # Excel con 3 hojas
cfdi-kit summary ~/Downloads/facturas --rfc TU_RFC                   # tabla mensual
cfdi-kit report ~/Downloads/facturas --rfc TU_RFC -o reporte.html    # reporte HTML
cfdi-kit validate ~/Downloads/facturas                               # validaciones
```

Todos los comandos aceptan cualquier combinación de archivos `.xml`, carpetas (se buscan de forma recursiva) y archivos `.zip`. Los archivos ilegibles se listan y se omiten; los UUID repetidos se cuentan una sola vez.

## Qué lee

| | Soportado |
|---|---|
| CFDI | 4.0 y 3.3 (tipos I, E, T, N y P) |
| Complementos | Timbre Fiscal Digital 1.1, Pagos 2.0 y 1.0, Nómina 1.2 |
| Dinero | `Decimal` de principio a fin; moneda extranjera convertida con el tipo de cambio de la factura o del pago |

CFDI 3.2 y anteriores se reportan como no soportados.

## Comandos

### `parse`: Excel o CSV

`cfdi-kit parse RUTAS -o salida.xlsx [--rfc RFC]` escribe tres hojas: `invoices` (una fila por CFDI, con impuestos, totales en MXN y descripciones de los catálogos del SAT), `line_items` (conceptos) y `payments` (cada factura liquidada en un complemento de pago). Con `-o salida.csv` escribe solo la tabla de facturas. `--rfc` agrega la columna `direction` (`issued` emitida / `received` recibida).

### `summary`: ingresos, gastos e IVA por mes

`cfdi-kit summary RUTAS --rfc RFC [--basis accrual|cash] [-o archivo]`

- **accrual** (por defecto): cada factura cuenta en su fecha de emisión.
- **cash** (flujo de efectivo): las facturas `PUE` cuentan en su fecha de emisión; las `PPD`, cuando un complemento de pago las liquida, en la fecha del pago. El desglose de impuestos de Pagos 2.0 se usa tal cual; los pagos de Pagos 1.0 se prorratean contra la factura original si está en la carpeta.

Las notas de crédito (`E`) restan. La nómina (`N`) se reporta en columnas aparte. *Net VAT* es el IVA trasladado, menos el IVA que te retuvieron tus clientes, menos el IVA acreditable.

### `report`: un archivo HTML

`cfdi-kit report RUTAS --rfc RFC [--basis] [-o reporte.html]` escribe un solo archivo sin scripts ni recursos externos: totales, gráfica de ingresos contra gastos, tabla mensual, principales clientes y proveedores, facturas PPD con saldo pendiente y todas las observaciones de la validación. Respeta el tema claro u oscuro del sistema.

### `validate`: encuentra errores antes de que lleguen a tu contabilidad

```text
$ cfdi-kit validate broken.xml
error    total-mismatch                broken.xml  Total is 99999.99 but SubTotal - Descuento + taxes is 34796.65
1 error(s), 0 warning(s)
```

Revisa: timbre faltante; total, subtotal o descuento que no cuadran (se permite un centavo de redondeo por concepto); impuestos de la factura contra los de los conceptos; RFC mal formados; facturas PPD con forma de pago distinta de 99; moneda extranjera sin tipo de cambio y UUID duplicados. Termina con código 1 si encuentra errores, para usarlo en scripts.

## API de Python

```python
import cfdi_kit

result = cfdi_kit.load(["examples/demo"])          # archivos, carpetas o ZIPs
print(len(result.cfdis), "invoices,", len(result.errors), "errors")

cfdi = result.cfdis[0]
cfdi.uuid, cfdi.issuer.rfc, cfdi.total, cfdi.iva_transferred   # tipado, Decimal

invoices = cfdi_kit.invoices_frame(result.cfdis, rfc="CACX7605101P8")  # pandas
invoices.groupby("direction")["total_mxn"].sum()

summary = cfdi_kit.summarize(result.cfdis, "CACX7605101P8", cfdi_kit.Basis.CASH)
cfdi_kit.summary_frame(summary)

issues = cfdi_kit.validate(result.cfdis)
```

También: `parse_file`, `parse_bytes`, `concepts_frame`, `payments_frame`, `to_csv` y `to_excel`. El paquete incluye anotaciones de tipos (`py.typed`).

## Límites

- Solo lee el XML. No verifica los sellos digitales ni consulta al SAT si una factura fue cancelada; quita las canceladas antes de resumir.
- El resumen es una ayuda para revisar un periodo. No es una declaración y no sustituye a tu contador.
- No emite, timbra, cancela ni descarga facturas.

## Desarrollo

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy .
uv run python examples/generate_demo.py examples/demo   # regenera las facturas de ejemplo
```

Los fixtures de prueba y las facturas de ejemplo son sintéticos y usan los RFC de prueba públicos del SAT. Ver [CONTRIBUTING.md](CONTRIBUTING.md). Un CFDI que no se puede leer es el reporte de bug más útil: anonimízalo y abre un issue.

## Licencia

[MIT](LICENSE) © Diego Tepichin
