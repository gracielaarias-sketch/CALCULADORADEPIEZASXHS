import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF

st.title("📊 Calculadora y Reporte de Producción")

# Pedimos el link al usuario
url_ingresada = st.text_input("Pega aquí el enlace de tu Google Sheet:")

if url_ingresada:
    try:
        # Truco para que pandas lea el Google Sheet directo como CSV
        url_limpia = url_ingresada.split("/edit")[0]
        url_csv = f"{url_limpia}/export?format=csv"
        
        st.info("Calculando datos...")
        # Leemos los datos
        df = pd.read_csv(url_csv)
        
        # 1. Limpieza de seguridad: asegurarnos de que sean números y no haya celdas vacías
        df['Buenas'] = pd.to_numeric(df['Buenas'], errors='coerce').fillna(0)
        df['Tiempo Producción (Min)'] = pd.to_numeric(df['Tiempo Producción (Min)'], errors='coerce').fillna(0)
        
        # 2. Convertir los minutos a horas
        df['Horas'] = df['Tiempo Producción (Min)'] / 60
        
        # 3. Calcular Piezas por Hora (usamos numpy para que si Horas es 0, el resultado sea 0 y no dé error)
        df['Piezas_por_Hora'] = np.where(df['Horas'] > 0, df['Buenas'] / df['Horas'], 0)
        
        # 4. Agrupar por Fecha y Máquina
        resumen = df.groupby(['Fecha', 'Máquina']).agg(
            Total_Piezas_Buenas=('Buenas', 'sum'),
            Promedio_Piezas_por_Hora=('Piezas_por_Hora', 'mean')
        ).reset_index()

        # Mostramos los resultados en la app
        st.success("¡Cálculos finalizados!")
        st.dataframe(resumen, use_container_width=True)

        # ==========================================
        # CREACIÓN DEL PDF
        # ==========================================
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(200, 10, txt="Informe de Producción", ln=True, align='C')
        pdf.cell(200, 10, txt="", ln=True) # Espacio en blanco
        
        # Recorrer los datos y escribirlos en el PDF
        pdf.set_font("Arial", size=12)
        for index, fila in resumen.iterrows():
            texto = f"Fecha: {fila['Fecha']} | Máquina: {fila['Máquina']} | Total Buenas: {fila['Total_Piezas_Buenas']} | Promedio/h: {round(fila['Promedio_Piezas_por_Hora'], 2)}"
            pdf.cell(200, 10, txt=texto, ln=True)
            
        nombre_archivo = "informe_produccion.pdf"
        pdf.output(nombre_archivo)

        # Botón de Descarga
        with open(nombre_archivo, "rb") as pdf_file:
            st.download_button(
                label="📥 Descargar Informe en PDF",
                data=pdf_file,
                file_name="Reporte_Produccion.pdf",
                mime="application/pdf"
            )
            
    except KeyError as e:
        st.error(f"Error: No se encontró la columna {e} en tu documento. Revisa que el nombre sea exactamente igual, respetando mayúsculas y acentos.")
    except Exception as e:
        st.error(f"Hubo un error al procesar el archivo. Detalle: {e}")
