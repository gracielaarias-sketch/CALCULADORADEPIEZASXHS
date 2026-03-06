import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF

st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Análisis de Producción y Productividad")

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
        # 1. EXPANDER CON LOS DATOS FUENTE
        # ==========================================
        with st.expander("👀 Clic aquí para ver los datos originales (Fuente)"):
            st.dataframe(df, use_container_width=True)

        # ==========================================
        # 2. PROCESAMIENTO BÁSICO
        # ==========================================
        columnas_a_sumar = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)']
        for col in columnas_a_sumar:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas'] = df['Tiempo Producción (Min)'] / 60

        # ==========================================
        # 3. BASE DE DATOS: HORA A HORA (POR FECHA)
        # ==========================================
        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora']).agg(
            Total_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            Total_Horas=('Horas', 'sum'),
            Cantidad_Productos=('Código Producto', 'nunique'),
            Codigos_Fabricados=('Código Producto', lambda x: ', '.join(x.dropna().unique().astype(str)))
        ).reset_index()

        # Calculamos la velocidad
        despliegue_hora['Piezas_por_Hora'] = np.where(
            despliegue_hora['Total_Horas'] > 0, 
            despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 
            0
        )
        despliegue_hora['Piezas_por_Hora'] = despliegue_hora['Piezas_por_Hora'].round(2)
        
        # FILTROS: 1 a 3 productos y eliminar los ceros
        despliegue_hora = despliegue_hora[despliegue_hora['Cantidad_Productos'].isin([1, 2, 3])]
        despliegue_hora = despliegue_hora[despliegue_hora['Piezas_por_Hora'] > 0]

        # ==========================================
        # 4. CÁLCULOS SECUNDARIOS PARA PESTAÑAS
        # ==========================================
        
        # A) Promedio General por Máquina y Cantidad de Productos (Para Pestaña 1)
        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Promedio_General_Piezas_Hora=('Piezas_por_Hora', 'mean')
        ).reset_index()
        resumen_general['Promedio_General_Piezas_Hora'] = resumen_general['Promedio_General_Piezas_Hora'].round(2)

        # B) Promedio Histórico por Hora del Día (Para Pestaña 2)
        # Agrupamos solo por Máquina y Hora (ignorando la fecha para sacar el promedio histórico de esa hora)
        promedio_por_hora_dia = despliegue_hora.groupby(['Máquina', 'Hora']).agg(
            Promedio_Historico_Hora=('Piezas_por_Hora', 'mean')
        ).reset_index()
        promedio_por_hora_dia['Promedio_Historico_Hora'] = promedio_por_hora_dia['Promedio_Historico_Hora'].round(2)

        # ==========================================
        # 5. MOSTRAR RESULTADOS EN 3 PESTAÑAS
        # ==========================================
        st.success("¡Cálculos finalizados exitosamente!")
        
        tab1, tab2, tab3 = st.tabs([
            "📈 1. Cálculo General por Máquina", 
            "⏰ 2. Promedio Histórico por Hora", 
            "📅 3. Despliegue por Fecha"
        ])
        
        # PESTAÑA 1
        with tab1:
            st.subheader("Promedio Real de Piezas por Hora (según cantidad de productos)")
            st.dataframe(resumen_general, use_container_width=True)
            
        # PESTAÑA 2: Selector de máquina y gráfico
        with tab2:
            st.subheader("Rendimiento Promedio según la Hora del Día")
            
            # Extraemos las máquinas disponibles y creamos el selector
            lista_maquinas = promedio_por_hora_dia['Máquina'].unique()
            maquina_seleccionada = st.selectbox("Selecciona la Máquina a analizar:", lista_maquinas)
            
            # Filtramos los datos solo para la máquina seleccionada
            datos_maquina = promedio_por_hora_dia[promedio_por_hora_dia['Máquina'] == maquina_seleccionada]
            datos_maquina = datos_maquina.sort_values(by='Hora')
            
            # Mostramos el gráfico de barras (muy útil para ver picos y caídas de producción)
            st.bar_chart(datos_maquina.set_index('Hora')['Promedio_Historico_Hora'])
            
            # Mostramos la tabla debajo del gráfico
            st.dataframe(datos_maquina, use_container_width=True)

        # PESTAÑA 3: Datos crudos hora a hora por día
        with tab3:
            st.subheader("Bitácora Diaria: Producción por cada Fecha y Hora")
            st.dataframe(despliegue_hora.sort_values(by=['Fecha', 'Máquina', 'Hora']), use_container_width=True)

        # ==========================================
        # 6. CREACIÓN DEL REPORTE PDF
        # ==========================================
        pdf = FPDF()
        pdf.add_page()
        
        pdf.set_font("Arial", "B", 16)
        pdf.cell(200, 10, txt="Informe de Producción", ln=True, align='C')
        pdf.cell(200, 5, txt="", ln=True) 
        
        # 1. Resumen General
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, txt="1. Promedio General por Máquina:", ln=True)
        pdf.set_font("Arial", size=10)
        for index, fila in resumen_general.iterrows():
            texto = f"Máquina: {fila['Máquina']} | Productos: {fila['Cantidad_Productos']} | Promedio/h: {fila['Promedio_General_Piezas_Hora']}"
            pdf.cell(200, 8, txt=texto, ln=True)
            
        pdf.cell(200, 5, txt="", ln=True) 
        
        # 2. Bitácora (Pestaña 3)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, txt="2. Bitácora Histórica (Hora a Hora):", ln=True)
        pdf.set_font("Arial", size=10)
        for index, fila in despliegue_hora.iterrows():
            texto = f"Fecha: {fila['Fecha']} | Hora: {fila['Hora']} | Máquina: {fila['Máquina']} | Pzs/h: {fila['Piezas_por_Hora']}"
            pdf.cell(200, 8, txt=texto, ln=True)
            
        nombre_archivo = "informe_produccion_limpio.pdf"
        pdf.output(nombre_archivo)

        # Botón de Descarga
        with open(nombre_archivo, "rb") as pdf_file:
            st.download_button(
                label="📥 Descargar Informe Completo en PDF",
                data=pdf_file,
                file_name="Reporte_Produccion_Limpiado.pdf",
                mime="application/pdf"
            )
            
    except KeyError as e:
        st.error(f"Error: No se encontró la columna {e}. Revisa los encabezados de tu Google Sheet.")
    except Exception as e:
        st.error(f"Hubo un error inesperado. Detalle: {e}")
