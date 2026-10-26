"""Parse SAT CFDI invoices into typed models, dataframes and reports."""

from importlib.metadata import version

from cfdi_kit.export import concepts_frame, invoices_frame, payments_frame, to_csv, to_excel
from cfdi_kit.loader import LoadResult, load
from cfdi_kit.models import Cfdi, InvoiceType
from cfdi_kit.parser import CfdiParseError, parse_bytes, parse_file
from cfdi_kit.summary import Basis, Summary, summarize, summary_frame
from cfdi_kit.validate import Issue, Severity, validate

__version__ = version("cfdi-kit")

__all__ = [
    "Basis",
    "Cfdi",
    "CfdiParseError",
    "InvoiceType",
    "Issue",
    "LoadResult",
    "Severity",
    "Summary",
    "__version__",
    "concepts_frame",
    "invoices_frame",
    "load",
    "parse_bytes",
    "parse_file",
    "payments_frame",
    "summarize",
    "summary_frame",
    "to_csv",
    "to_excel",
    "validate",
]
