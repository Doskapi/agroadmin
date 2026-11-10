"""Utilidades para PDF con PyMuPDF."""

from dataclasses import dataclass

import pymupdf


@dataclass
class ContenidoPDF:
    texto: str
    links: list[str]
    paginas_png: list[bytes]  # render de las primeras páginas, para buscar el QR


def leer_pdf(data: bytes, max_paginas: int = 2, dpi: int = 200) -> ContenidoPDF:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        texto = "\n".join(page.get_text() for page in doc)
        links = [lk["uri"] for page in doc for lk in page.get_links() if lk.get("uri")]
        paginas = [doc[i].get_pixmap(dpi=dpi).tobytes("png") for i in range(min(max_paginas, doc.page_count))]
    return ContenidoPDF(texto=texto, links=links, paginas_png=paginas)
