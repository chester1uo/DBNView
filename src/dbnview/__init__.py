"""DBNView — a viewer for Databento DBN market-data files (.dbn / .dbn.zst).

Subpackages
-----------
engine      DBN decoding, streaming, filtering and scan jobs (numpy + zstandard only)
analysis    chart data (bars, quotes, order flow, book heatmaps), MBO order book, option IV
reference   human-readable docs for fields, schemas and enums, in 7 languages
i18n        UI string translation
gui         PySide6 desktop application
web         lightweight browser UI / HTTP server (runs on servers without Qt)
"""
__version__ = "0.5.0"
