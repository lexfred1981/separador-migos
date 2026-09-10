import io
import re
import zipfile
from PIL import Image
import pymupdf
from pypdf import PdfReader, PdfWriter
import pytesseract
import streamlit as st

st.set_page_config(
    page_title="Separador de Vales y Guías", page_icon="📄", layout="centered"
)


def limpiar_nombre_archivo(texto):
  texto_limpio = re.sub(r'[\\/*?:"<>|]', "", texto)
  return re.sub(r"\s+", " ", texto_limpio).strip()


def extraer_datos_cabecera(texto_ocr):
  guia_match = re.search(
      r"(?:N[uú]mero\s+Gu[ií]a|Nro\s+Gu[ií]a)\s*:\s*([A-Za-z0-9-]+)",
      texto_ocr,
      re.IGNORECASE,
  )
  guia = guia_match.group(1).strip() if guia_match else "SIN_GUIA"

  nombre_match = re.search(
      r"Nombre\s*:\s*([^\n\r]+)", texto_ocr, re.IGNORECASE
  )
  nombre = nombre_match.group(1).strip() if nombre_match else "SIN_NOMBRE"

  pedido_match = re.search(
      r"Pedido\s*:\s*([A-Za-z0-9-]+)", texto_ocr, re.IGNORECASE
  )
  pedido = pedido_match.group(1).strip() if pedido_match else "SIN_PEDIDO"

  nr_match = re.search(
      r"Nr\.\s*([0-9]+)", texto_ocr, re.IGNORECASE
  ) or re.search(r"Nr\s*:\s*([0-9]+)", texto_ocr, re.IGNORECASE)
  nr = nr_match.group(1).strip() if nr_match else "SIN_NR"

  return limpiar_nombre_archivo(f"{guia} {nombre} {pedido} {nr}")


st.title("📄 Separador de Vales de Entrada y Guías")
st.write(
    "Sube el archivo PDF escaneado para separar los vales y renombrarlos"
    " automáticamente."
)

uploaded_file = st.file_uploader(
    "Selecciona el PDF escaneado", type=["pdf", "PDF"]
)

col1, col2 = st.columns(2)
with col1:
  hojas_vale = st.number_input(
      "Hojas por VALE DE ENTRADA", min_value=1, max_value=10, value=2
  )
with col2:
  hojas_guia = st.number_input(
      "Hojas por GUÍA DE REMISIÓN", min_value=1, max_value=10, value=1
  )

hojas_por_documento = int(hojas_vale + hojas_guia)

if uploaded_file is not None:
  if st.button("🚀 Procesar Documentos", type="primary"):
    with st.spinner("Procesando con OCR... Espera un momento."):
      pdf_bytes = uploaded_file.read()

      doc_fitz = pymupdf.open(stream=pdf_bytes, filetype="pdf")
      reader = PdfReader(io.BytesIO(pdf_bytes))
      total_paginas = len(reader.pages)

      patron_inicio = re.compile(
          r"VALE\s+DE\s+ENTRADA\s+DE\s+MERCANC[IÍ]AS?", re.IGNORECASE
      )

      indices_inicio = []
      textos_cabecera = []

      for index in range(total_paginas):
        page = doc_fitz.load_page(index)
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        try:
          texto_ocr = pytesseract.image_to_string(img, lang="spa")
        except Exception:
          texto_ocr = pytesseract.image_to_string(img)

        if patron_inicio.search(texto_ocr):
          indices_inicio.append(index)
          textos_cabecera.append(texto_ocr)

      doc_fitz.close()

      if not indices_inicio:
        st.error(
            "No se encontró 'VALE DE ENTRADA DE MERCANCIAS' en ninguna página."
        )
      else:
        num_documentos = len(indices_inicio)
        st.success(f"Se encontraron {num_documentos} vales.")

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer, "w", zipfile.ZIP_DEFLATED
        ) as zip_file:
          for i in range(num_documentos):
            start_page = indices_inicio[i]
            end_page = min(start_page + hojas_por_documento, total_paginas)

            writer = PdfWriter()
            for page_idx in range(start_page, end_page):
              writer.add_page(reader.pages[page_idx])

            nombre_formateado = extraer_datos_cabecera(textos_cabecera[i])
            nombre_salida = f"{nombre_formateado}.pdf"

            pdf_out_buffer = io.BytesIO()
            writer.write(pdf_out_buffer)
            zip_file.writestr(nombre_salida, pdf_out_buffer.getvalue())

        zip_buffer.seek(0)

        st.download_button(
            label="📦 Descargar Documentos Separados (.zip)",
            data=zip_buffer,
            file_name="Vales_y_Guias_Separados.zip",
            mime="application/zip",
        )
