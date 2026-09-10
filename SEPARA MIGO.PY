import io
import re
import zipfile
from PIL import Image
import pymupdf
from pypdf import PdfReader, PdfWriter
import pytesseract
import streamlit as st

# Configuración de la interfaz
st.set_page_config(
    page_title="Separador de Vales y Guías", page_icon="📄", layout="centered"
)


def limpiar_nombre_archivo(texto):
  """Limpia caracteres especiales no permitidos en nombres de archivos."""
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


# Interfaz Web con Streamlit
st.title("📄 Separador de Vales de Entrada y Guías")
st.write(
    "Sube tu archivo PDF escaneado para separar los vales y renombrarlos"
    " automáticamente."
)

# Control para subir archivo
uploaded_file = st.file_uploader(
    "Selecciona el archivo PDF escaneado", type=["pdf", "PDF"]
)

# Inputs dinámicos para configurar el número de hojas
col1, col2 = st.columns(2)
with col1:
  hojas_vale = st.number_input(
      "Hojas del VALE DE ENTRADA", min_value=1, max_value=10, value=2
  )
with col2:
  hojas_guia = st.number_input(
      "Hojas de la GUÍA DE REMISIÓN", min_value=1, max_value=10, value=1
  )

hojas_por_documento = int(hojas_vale + hojas_guia)

if uploaded_file is not None:
  if st.button("🚀 Procesar Documentos", type="primary"):
    with st.spinner("Procesando PDF con OCR... Esto puede tomar un momento."):
      pdf_bytes = uploaded_file.read()

      # Abrir el PDF desde la memoria de la web
      doc_fitz = pymupdf.open(stream=pdf_bytes, filetype="pdf")
      reader = PdfReader(io.BytesIO(pdf_bytes))
      total_paginas = len(reader.pages)

      patron_inicio = re.compile(
          r"VALE\s+DE\s+ENTRADA\s+DE\s+MERCANC[IÍ]AS?", re.IGNORECASE
      )

      indices_inicio = []
      textos_cabecera = []

      # Lectura y OCR página por página
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
            "No se encontró 'VALE DE ENTRADA DE MERCANCIAS' en ninguna página del"
            " archivo."
        )
      else:
        num_documentos = len(indices_inicio)
        st.success(
            f"Se encontraron {num_documentos} vales. Generando archivos..."
        )

        # Crear archivo ZIP en memoria
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer, "w", zipfile.ZIP_DEFLATED
        ) as zip_file:
          for i in range(num_documentos):
            start_page = indices_inicio[i]
            
            # Cálculo de límite según las hojas indicadas por el usuario
            end_page = min(start_page + hojas_por_documento, total_paginas)

            writer = PdfWriter()
            for page_idx in range(start_page, end_page):
              writer.add_page(reader.pages[page_idx])

            # Extraer datos y dar nombre al PDF
            nombre_formateado = extraer_datos_cabecera(textos_cabecera[i])
            nombre_salida = f"{nombre_formateado}.pdf"

            pdf_out_buffer = io.BytesIO()
            writer.write(pdf_out_buffer)
            
            # Guardar el PDF dentro del ZIP
            zip_file.writestr(nombre_salida, pdf_out_buffer.getvalue())

        zip_buffer.seek(0)

        # Botón para descargar el ZIP resultado
        st.download_button(
            label="📦 Descargar Todos los PDFs (.zip)",
            data=zip_buffer,
            file_name="Vales_y_Guias_Separados.zip",
            mime="application/zip",
        )