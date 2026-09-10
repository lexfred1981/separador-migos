import io
import re
import zipfile
from PIL import Image
import pymupdf
from pypdf import PdfReader, PdfWriter
import pytesseract
import streamlit as st

# Configuración de la página
st.set_page_config(
    page_title="Separador de Vales y Guías", page_icon="📄", layout="centered"
)


def limpiar_nombre_archivo(texto):
  """Limpia caracteres especiales no permitidos para nombres de archivo."""
  texto_limpio = re.sub(r'[\\/*?:"<>|]', "", texto)
  return re.sub(r"\s+", " ", texto_limpio).strip()


def extraer_datos_cabecera(texto_ocr):
  """Extrae los campos: Número Guía, Nombre, Pedido y Nr."""
  # 1. Número Guía
  guia_match = re.search(
      r"(?:N[uú]mero\s+Gu[ií]a|Nro\s+Gu[ií]a)\s*:\s*([A-Za-z0-9-]+)",
      texto_ocr,
      re.IGNORECASE,
  )
  guia = guia_match.group(1).strip() if guia_match else "SIN_GUIA"

  # 2. Nombre (Proveedor)
  nombre_match = re.search(
      r"Nombre\s*:\s*([^\n\r]+)", texto_ocr, re.IGNORECASE
  )
  nombre = nombre_match.group(1).strip() if nombre_match else "SIN_NOMBRE"

  # 3. Pedido
  pedido_match = re.search(
      r"Pedido\s*:\s*([A-Za-z0-9-]+)", texto_ocr, re.IGNORECASE
  )
  pedido = pedido_match.group(1).strip() if pedido_match else "SIN_PEDIDO"

  # 4. Nr. (Número de documento del vale)
  nr_match = re.search(
      r"Nr\.\s*([0-9]+)", texto_ocr, re.IGNORECASE
  ) or re.search(r"Nr\s*:\s*([0-9]+)", texto_ocr, re.IGNORECASE)
  nr = nr_match.group(1).strip() if nr_match else "SIN_NR"

  # Formato: "Número Guía" "Nombre" "Pedido" "Nr."
  nombre_completo = f"{guia} {nombre} {pedido} {nr}"
  return limpiar_nombre_archivo(nombre_completo)


# --- INTERFAZ DE USUARIO EN STREAMLIT ---
st.title("📄 Separador de Vales de Entrada y Guías")
st.write(
    "Sube tu archivo PDF escaneado para identificar automáticamente cada vale,"
    " renombrarlo y extraer exactamente sus 2 páginas correspondientes."
)

# Carga de archivo
uploaded_file = st.file_uploader(
    "Selecciona o arrastra el archivo PDF escaneado", type=["pdf", "PDF"]
)

if uploaded_file is not None:
  if st.button("🚀 Procesar Documento", type="primary"):
    with st.spinner("Ejecutando OCR y separando páginas... Espera un momento."):
      # Leer el archivo subido a la memoria
      pdf_bytes = uploaded_file.read()

      # Cargar con PyMuPDF (fitz) y PyPDF desde la memoria (bytes)
      doc_fitz = pymupdf.open(stream=pdf_bytes, filetype="pdf")
      reader = PdfReader(io.BytesIO(pdf_bytes))
      total_paginas = len(reader.pages)

      patron_inicio = re.compile(
          r"VALE\s+DE\s+ENTRADA\s+DE\s+MERCANC[IÍ]AS?", re.IGNORECASE
      )

      indices_inicio = []
      textos_cabecera = []

      # Escaneo de páginas con Tesseract
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
            "No se encontró 'VALE DE ENTRADA DE MERCANCIAS' en ninguna página"
            " del PDF."
        )
      else:
        num_documentos = len(indices_inicio)
        st.success(
            f"¡Proceso completado! Se encontraron {num_documentos} vales de"
            " entrada."
        )

        # Crear un archivo ZIP en memoria para empaquetar los PDFs
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer, "w", zipfile.ZIP_DEFLATED
        ) as zip_file:
          for i in range(num_documentos):
            start_page = indices_inicio[i]
            limite_siguiente = (
                indices_inicio[i + 1]
                if (i + 1 < num_documentos)
                else total_paginas
            )
            end_page = min(start_page + 2, limite_siguiente)

            writer = PdfWriter()
            for page_idx in range(start_page, end_page):
              writer.add_page(reader.pages[page_idx])

            nombre_formateado = extraer_datos_cabecera(textos_cabecera[i])
            nombre_salida = f"{nombre_formateado}.pdf"

            # Guardar PDF individual en un buffer
            pdf_out_buffer = io.BytesIO()
            writer.write(pdf_out_buffer)

            # Añadir al ZIP
            zip_file.writestr(nombre_salida, pdf_out_buffer.getvalue())

        zip_buffer.seek(0)

        # Botón de descarga del paquete ZIP con los PDFs separados
        st.download_button(
            label="📦 Descargar Todos los Documentos (.zip)",
            data=zip_buffer,
            file_name="Vales_y_Guias_Separados.zip",
            mime="application/zip",
        )
