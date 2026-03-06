import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from fpdf import FPDF

st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Análisis de Producción vs Estimado")

url_ingresada = st.text_input("Pega aquí el enlace de tu Google Sheet:")

if url_ingresada:
    try:
        url_limpia = url_ingresada.split("/edit")[0]
        url_csv = f"{url_limpia}/export?format=csv"
        
        st.info("Obteniendo y calculando datos...")
        df = pd.read_csv(url_csv)
        
        with st.expander("👀 Clic aquí para ver los datos originales (Fuente)"):
            st.dataframe(df, use_container_width=True)

        # ==========================================
        # 1. LIMPIEZA Y CÁLCULOS BASE
        # ==========================================
        columnas_num = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)', 'Tiempo Ciclo', 'Hora']
        for col in columnas_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Ajuste de Hora (Restar 1 para que empiece a las 6)
        df['Hora_Real'] = df['Hora'].apply(lambda x: int(x - 1) if x > 0 else 23)
        # Columna oculta para ordenar cronológicamente desde las 6 AM
        df['Orden_Hora'] = df['Hora_Real'].apply(lambda x: x if x >= 6 else x + 24)

        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas'] = df['Tiempo Producción (Min)'] / 60
        
        # Cálculo del Estimado (60 / Tiempo Ciclo)
        df['Piezas_Estimadas_Hora'] = np.where(df['Tiempo Ciclo'] > 0, 60 / df['Tiempo Ciclo'], 0)

        # ==========================================
        # 2. AGRUPACIÓN HORA A HORA (CON ESTIMADO)
        # ==========================================
        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora_Real', 'Orden_Hora']).agg(
            Total_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            Total_Horas=('Horas', 'sum'),
            Cantidad_Productos=('Código Producto', 'nunique'),
            Promedio_Estimado_Local=('Piezas_Estimadas_Hora', 'mean') # Promedio del estimado en esa hora
        ).reset_index()

        despliegue_hora['Piezas_por_Hora_Real'] = np.where(
            despliegue_hora['Total_Horas'] > 0, 
            despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 0
        )
        
        despliegue_hora = despliegue_hora[despliegue_hora['Cantidad_Productos'].isin([1, 2, 3])]
        despliegue_hora = despliegue_hora[despliegue_hora['Piezas_por_Hora_Real'] > 0]

        # ==========================================
        # 3. CÁLCULO GENERAL Y COMPARACIÓN
        # ==========================================
        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Real_Pzs_Hora=('Piezas_por_Hora_Real', 'mean'),
            Estimado_Pzs_Hora=('Promedio_Estimado_Local', 'mean')
        ).reset_index().round(2)

        # Promedio Histórico por Hora (Ordenado lógicamente)
        promedio_por_hora = despliegue_hora.groupby(['Máquina', 'Hora_Real', 'Orden_Hora']).agg(
            Promedio_Historico=('Piezas_por_Hora_Real', 'mean')
        ).reset_index().sort_values(by=['Máquina', 'Orden_Hora']).round(2)

        # ==========================================
        # 4. PESTAÑAS Y GRÁFICOS MATPLOTLIB
        # ==========================================
        st.success("¡Cálculos finalizados!")
        tab1, tab2, tab3 = st.tabs(["📈 General vs Estimado", "⏰ Histórico por Hora", "📅 Bitácora"])
        
        with tab1:
            st.subheader("Producción Real vs Estimada (según cantidad de productos)")
            st.dataframe(resumen_general, use_container_width=True)
            
            # Gráfico Comparativo
            fig_gen, ax_gen = plt.subplots(figsize=(10, 5))
            x = np.arange(len(resumen_general))
            width = 0.35
            ax_gen.bar(x - width/2, resumen_general['Real_Pzs_Hora'], width, label='Real', color='#1f77b4')
            ax_gen.bar(x + width/2, resumen_general['Estimado_Pzs_Hora'], width, label='Estimado', color='#aec7e8')
            ax_gen.set_ylabel('Piezas por Hora')
            ax_gen.set_title('Real vs Estimado por Máquina y N° Productos')
            ax_gen.set_xticks(x)
            etiquetas = resumen_general['Máquina'] + " (" + resumen_general['Cantidad_Productos'].astype(str) + " prod)"
            ax_gen.set_xticklabels(etiquetas, rotation=45, ha="right")
            ax_gen.legend()
            st.pyplot(fig_gen)
            fig_gen.savefig("grafico_general.png", bbox_inches='tight')

        with tab2:
            st.subheader("Rendimiento Histórico desde las 6:00 AM")
            lista_maquinas = promedio_por_hora['Máquina'].unique()
            maquina_seleccionada = st.selectbox("Máquina:", lista_maquinas)
            
            datos_maq = promedio_por_hora[promedio_por_hora['Máquina'] == maquina_seleccionada]
            
            # Gráfico de la Máquina Seleccionada
            fig_hor, ax_hor = plt.subplots(figsize=(10, 4))
            ax_hor.plot(datos_maq['Hora_Real'].astype(str) + "h", datos_maq['Promedio_Historico'], marker='o', color='#00509E', linewidth=2)
            ax_hor.set_title(f'Rendimiento Hora a Hora - {maquina_seleccionada}')
            ax_hor.set_ylabel('Piezas por Hora')
            ax_hor.grid(True, linestyle='--', alpha=0.6)
            st.pyplot(fig_hor)
            fig_hor.savefig("grafico_hora.png", bbox_inches='tight')
            
            st.dataframe(datos_maq[['Máquina', 'Hora_Real', 'Promedio_Historico']], use_container_width=True)

        with tab3:
            st.subheader("Bitácora (No se incluye en el PDF)")
            st.dataframe(despliegue_hora.sort_values(by=['Fecha', 'Máquina', 'Orden_Hora']), use_container_width=True)

        # ==========================================
        # 5. CREACIÓN DEL PDF ESTILIZADO (AZUL Y CON TABLAS)
        # ==========================================
        pdf = FPDF()
        pdf.add_page()
        
        # Colores Corporativos (Azules)
        COLOR_TITULO = (0, 51, 102) # Azul oscuro
        COLOR_FONDO_TABLA = (204, 229, 255) # Azul clarito
        
        # Título
        pdf.set_font("Arial", "B", 18)
        pdf.set_text_color(*COLOR_TITULO)
        pdf.cell(190, 10, txt="REPORTE DE PRODUCCIÓN Y RENDIMIENTO", ln=True, align='C')
        pdf.ln(5)
        
        # --- SECCIÓN 1: GENERAL VS ESTIMADO ---
        pdf.set_font("Arial", "B", 14)
        pdf.cell(190, 10, txt="1. Comparativa General vs Estimado", ln=True)
        
        # Encabezados de Tabla 1
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*COLOR_FONDO_TABLA)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(60, 8, "Máquina", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Productos", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Real (Pzs/h)", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Estimado (Pzs/h)", border=1, fill=True, align='C')
        pdf.ln()
        
        # Filas de Tabla 1
        pdf.set_font("Arial", "", 10)
        for index, fila in resumen_general.iterrows():
            pdf.cell(60, 8, str(fila['Máquina']), border=1, align='C')
            pdf.cell(30, 8, str(fila['Cantidad_Productos']), border=1, align='C')
            pdf.cell(40, 8, str(fila['Real_Pzs_Hora']), border=1, align='C')
            pdf.cell(40, 8, str(fila['Estimado_Pzs_Hora']), border=1, align='C')
            pdf.ln()
            
        pdf.ln(5)
        # Insertar Gráfico General
        pdf.image("grafico_general.png", w=170)
        pdf.ln(10)
        
        # --- SECCIÓN 2: HISTÓRICO HORA A HORA ---
        pdf.add_page() # Nueva página para que no se corte feo
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(*COLOR_TITULO)
        pdf.cell(190, 10, f"2. Rendimiento Hora a Hora ({maquina_seleccionada})", ln=True)
        
        # Encabezados de Tabla 2
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*COLOR_FONDO_TABLA)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(80, 8, "Máquina", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Hora", border=1, fill=True, align='C')
        pdf.cell(50, 8, "Promedio (Pzs/h)", border=1, fill=True, align='C')
        pdf.ln()
        
        # Filas de Tabla 2
        pdf.set_font("Arial", "", 10)
        for index, fila in datos_maq.iterrows():
            pdf.cell(80, 8, str(fila['Máquina']), border=1, align='C')
            pdf.cell(40, 8, f"{fila['Hora_Real']}:00", border=1, align='C')
            pdf.cell(50, 8, str(fila['Promedio_Historico']), border=1, align='C')
            pdf.ln()
            
        pdf.ln(5)
        # Insertar Gráfico por Hora
        pdf.image("grafico_hora.png", w=170)

        # Generar y descargar
        nombre_pdf = "Reporte_Ejecutivo.pdf"
        pdf.output(nombre_pdf)

        with open(nombre_pdf, "rb") as pdf_file:
            st.download_button("📥 Descargar Reporte Ejecutivo (PDF)", data=pdf_file, file_name=nombre_pdf, mime="application/pdf")
            
        # Limpiar imágenes temporales para que no saturen tu servidor
        os.remove("grafico_general.png")
        os.remove("grafico_hora.png")
            
    except Exception as e:
        st.error(f"Error procesando los datos: {e}")
