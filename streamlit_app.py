import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF

st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Calculadora de Producción por Cantidad de Productos")

# Pedimos el link al usuario
url_ingresada = st.text_input("Pega aquí el enlace de tu Google Sheet:")

if url_ingresada:
    try:
        url_limpia = url_ingresada.split("/edit")[0]
        url_csv = f"{url_limpia}/export?format=csv"
        
        st.info("Obteniendo y calculando datos...")
        df = pd.read_csv(url_csv)
        
        # 1. EXPANDER CON LOS DATOS FUENTE
        with st.expander("👀 Clic aquí para ver los datos originales (Fuente)"):
            st.dataframe(df, use_container_width=True)

        # ==========================================
        # 2. PROCESAMIENTO BÁSICO
        # ==========================================
        # Convertir a números y rellenar vacíos con 0
        columnas_a_sumar = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)']
        for col in columnas_a_sumar:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Total de piezas y conversión a horas
        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas'] = df['Tiempo Producción (Min)'] / 60

        # ==========================================
        # 3. DESPLIEGUE HORA A HORA
        # ==========================================
        # Agrupamos por Fecha, Máquina y Hora
        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora']).agg(
            Total_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            Total_Horas=('Horas', 'sum'),
            # 'nunique' cuenta cuántos códigos de producto diferentes hay en esa hora
            Cantidad_Productos=('Código Producto', 'nunique'),
            # Guardamos los códigos exactos para poder verlos
            Codigos_Fabricados=('Código Producto', lambda x: ', '.join(x.dropna().unique().astype(str)))
        ).reset_index()

        # Calculamos la velocidad real en esa hora específica
        despliegue_hora['Piezas_por_Hora'] = np.where(
            despliegue_hora['Total_Horas'] > 0, 
            despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 
            0
        )
        
        # Redondeamos y filtramos para quedarnos solo cuando se hacen 1, 2 o 3 productos
        despliegue_hora['Piezas_por_Hora'] = despliegue_hora['Piezas_por_Hora'].round(2)
        despliegue_hora = despliegue_hora[despliegue_hora['Cantidad_Productos'].isin([1, 2, 3])]

        # ==========================================
        # 4. CÁLCULO GENERAL POR MÁQUINA
        # ==========================================
        # Tomamos el despliegue y sacamos el promedio según si se hicieron 1, 2 o 3 productos
        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Promedio_General_Piezas_Hora=('Piezas_por_Hora', 'mean')
        ).reset_index()
        
        resumen_general['Promedio_General_Piezas_Hora'] = resumen_general['Promedio_General_Piezas_Hora'].round(2)

        # ==========================================
        # 5. MOSTRAR RESULTADOS EN PESTAÑAS (TABS)
        # ==========================================
        st.success("¡Cálculos finalizados exitosamente!")
        
        # Creamos dos pestañas para que se vea ordenado
        tab1, tab2 = st.tabs(["📈 Cálculo General por Máquina", "⏱️ Despliegue Hora a Hora"])
        
        with tab1:
            st.subheader("Promedio de Piezas por Hora según Cantidad de Productos")
            st.dataframe(resumen_general, use_container_width=True)
            
        with tab2:
            st.subheader("Detalle de Producción por cada Hora")
            # Ordenamos para que se vea cronológicamente
            st.dataframe(despliegue_hora.sort_values(by=['Fecha', 'Máquina', 'Hora']), use_container_width=True)

        # ==========================================
        # 6. CREACIÓN DEL REPORTE PDF
        # ==========================================
        pdf = FPDF()
        pdf.add_page()
        
        # Título
        pdf.set_font("Arial", "B", 16)
        pdf.cell(200, 10, txt="Informe de Producción", ln=True, align='C')
        pdf.cell(200, 5, txt="", ln=True) 
        
        # Sección 1: General
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, txt="Promedio General por Máquina (1, 2 o 3 productos):", ln=True)
        pdf.set_font("Arial", size=10)
        for index, fila in resumen_general.iterrows():
            texto = f"Máquina: {fila['Máquina']} | Productos Simultáneos: {fila['Cantidad_Productos']} | Promedio/h: {fila['Promedio_General_Piezas_Hora']}"
            pdf.cell(200, 8, txt=texto, ln=True)
            
        pdf.cell(200, 5, txt="", ln=True) 
        
        # Sección 2: Hora a Hora
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, txt="Resumen Hora a Hora:", ln=True)
        pdf.set_font("Arial", size=10)
        for index, fila in despliegue_hora.iterrows():
            texto = f"Fecha: {fila['Fecha']} | Hora: {fila['Hora']} | Máquina: {fila['Máquina']} | Prod. Distintos: {fila['Cantidad_Productos']} | Pzs/h: {fila['Piezas_por_Hora']}"
            pdf.cell(200, 8, txt=texto, ln=True)
            
        nombre_archivo = "informe_produccion_completo.pdf"
        pdf.output(nombre_archivo)

        # Botón de Descarga
        with open(nombre_archivo, "rb") as pdf_file:
            st.download_button(
                label="📥 Descargar Informe Completo en PDF",
                data=pdf_file,
                file_name="Reporte_Produccion_Productividad.pdf",
                mime="application/pdf"
            )
            
    except KeyError as e:
        st.error(f"Error: No se encontró la columna {e} en tu documento. Asegúrate de que los encabezados coincidan exactamente con: 'Fábrica', 'Máquina', 'Código Producto', 'Hora', 'Buenas', etc.")
    except Exception as e:
        st.error(f"Hubo un error inesperado al procesar el archivo. Detalle: {e}")
