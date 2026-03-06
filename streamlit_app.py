import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF

st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Calculadora y Reporte de Producción")

# Pedimos el link al usuario
url_ingresada = st.text_input("Pega aquí el enlace de tu Google Sheet:")

if url_ingresada:
    try:
        # Truco para leer el Google Sheet como CSV
        url_limpia = url_ingresada.split("/edit")[0]
        url_csv = f"{url_limpia}/export?format=csv"
        
        st.info("Obteniendo y calculando datos...")
        df = pd.read_csv(url_csv)
        
        # ==========================================
        # 1. LISTA DESPLEGABLE CON LOS DATOS FUENTE
        # ==========================================
        # st.expander crea una sección que el usuario puede abrir y cerrar
        with st.expander("👀 Clic aquí para ver los datos originales (Fuente)"):
            st.dataframe(df, use_container_width=True)

        # ==========================================
        # 2. PROCESAMIENTO Y CÁLCULOS
        # ==========================================
        # Limpieza: Convertimos las columnas a números. Si hay celdas vacías, les ponemos 0.
        columnas_a_sumar = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)']
        for col in columnas_a_sumar:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # NUEVO: Sumamos las 3 categorías para obtener el total de piezas fabricadas
        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        
        # Convertimos el tiempo a horas
        df['Horas'] = df['Tiempo Producción (Min)'] / 60
        
        # Calculamos las piezas por hora usando el NUEVO TOTAL
        df['Piezas_por_Hora'] = np.where(df['Horas'] > 0, df['Total_Piezas_Fabricadas'] / df['Horas'], 0)
        
        # Agrupamos por Fecha y Máquina
        resumen = df.groupby(['Fecha', 'Máquina']).agg(
            Total_Productos=('Total_Piezas_Fabricadas', 'sum'),
            Promedio_Piezas_por_Hora=('Piezas_por_Hora', 'mean')
        ).reset_index()

        # Redondeamos a 2 decimales para que se vea más limpio
        resumen['Promedio_Piezas_por_Hora'] = resumen['Promedio_Piezas_por_Hora'].round(2)

        # Mostramos la tabla final resumida
        st.success("¡Cálculos finalizados exitosamente!")
        st.subheader("Resumen de Producción por Día y Máquina")
        st.dataframe(resumen, use_container_width=True)

        # ==========================================
        # 3. CREACIÓN DEL REPORTE PDF
        # ==========================================
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(200, 10, txt="Informe Diario de Producción", ln=True, align='C')
        pdf.cell(200, 10, txt="", ln=True) # Espacio en blanco
        
        pdf.set_font("Arial", size=12)
        # Recorremos la tabla resumen para escribir el PDF
        for index, fila in resumen.iterrows():
            texto = f"Fecha: {fila['Fecha']} | Máquina: {fila['Máquina']} | Total Fabricado: {fila['Total_Productos']} | Promedio/h: {fila['Promedio_Piezas_por_Hora']}"
            pdf.cell(200, 10, txt=texto, ln=True)
            
        nombre_archivo = "informe_produccion.pdf"
        pdf.output(nombre_archivo)

        # ==========================================
        # 4. BOTÓN DE DESCARGA
        # ==========================================
        with open(nombre_archivo, "rb") as pdf_file:
            st.download_button(
                label="📥 Descargar Informe en PDF",
                data=pdf_file,
                file_name="Reporte_Produccion.pdf",
                mime="application/pdf"
            )
            
    except KeyError as e:
        st.error(f"Error: No se encontró la columna {e} en tu documento. Asegúrate de que los encabezados coincidan exactamente.")
    except Exception as e:
        st.error(f"Hubo un error inesperado al procesar el archivo. Detalle: {e}")
