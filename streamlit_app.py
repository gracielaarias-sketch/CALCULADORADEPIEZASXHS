import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from fpdf import FPDF

st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Análisis de Producción y Rendimiento por Producto")

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
        # 1. LIMPIEZA Y CÁLCULOS BASE (FILA POR FILA)
        # ==========================================
        columnas_num = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)', 'Tiempo Ciclo', 'Hora']
        for col in columnas_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Ajuste de Hora (Para que el turno empiece a las 6)
        df['Hora_Real'] = df['Hora'].apply(lambda x: int(x - 1) if x > 0 else 23)
        df['Orden_Hora'] = df['Hora_Real'].apply(lambda x: x if x >= 6 else x + 24)

        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas'] = df['Tiempo Producción (Min)'] / 60
        
        # Rendimiento real y estimado fila por fila (para la tabla de productos)
        df['Piezas_por_Hora_Real'] = np.where(df['Horas'] > 0, df['Total_Piezas_Fabricadas'] / df['Horas'], 0)
        df['Piezas_Estimadas_Hora'] = np.where(df['Tiempo Ciclo'] > 0, 60 / df['Tiempo Ciclo'], 0)

        # ==========================================
        # 2. CUADRO 1: GENERAL POR CANTIDAD DE PRODUCTOS (1, 2, 3)
        # ==========================================
        # Primero agrupamos hora a hora para contar cuántos productos simultáneos hubo
        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora_Real', 'Orden_Hora']).agg(
            Total_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            Total_Horas=('Horas', 'sum'),
            Cantidad_Productos=('Código Producto', 'nunique')
        ).reset_index()

        despliegue_hora['Pzs_Hora_Bloque'] = np.where(despliegue_hora['Total_Horas'] > 0, despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 0)
        despliegue_hora = despliegue_hora[(despliegue_hora['Cantidad_Productos'].isin([1, 2, 3])) & (despliegue_hora['Pzs_Hora_Bloque'] > 0)]

        # Volvemos al cálculo original para el general
        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Promedio_General_Pzs_Hora=('Pzs_Hora_Bloque', 'mean')
        ).reset_index().round(2)

        # ==========================================
        # 3. CUADRO 2: COMPARATIVA REAL VS ESTIMADO POR PRODUCTO
        # ==========================================
        # Filtramos los datos válidos para sacar promedios limpios por cada código
        df_validos = df[(df['Piezas_por_Hora_Real'] > 0) & (df['Código Producto'].notna()) & (df['Código Producto'] != '')]
        
        comparativa_productos = df_validos.groupby(['Máquina', 'Código Producto']).agg(
            Real_Pzs_Hora=('Piezas_por_Hora_Real', 'mean'),
            Estimado_Pzs_Hora=('Piezas_Estimadas_Hora', 'mean')
        ).reset_index().round(2)

        # ==========================================
        # 4. CUADRO 3: HISTÓRICO POR HORA
        # ==========================================
        promedio_por_hora = despliegue_hora.groupby(['Máquina', 'Hora_Real', 'Orden_Hora']).agg(
            Promedio_Historico=('Pzs_Hora_Bloque', 'mean')
        ).reset_index().sort_values(by=['Máquina', 'Orden_Hora']).round(2)

        # ==========================================
        # 5. PESTAÑAS Y GRÁFICOS
        # ==========================================
        st.success("¡Cálculos finalizados!")
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 1. General (Por N° Productos)", 
            "🎯 2. Real vs Estimado (Por Producto)", 
            "⏰ 3. Histórico por Hora", 
            "📅 4. Bitácora"
        ])
        
        with tab1:
            st.subheader("Promedio Real de Piezas por Hora (según cantidad de productos simultáneos)")
            st.dataframe(resumen_general, use_container_width=True)

        with tab2:
            st.subheader("Rendimiento por Código de Producto: Real vs Estimado")
            st.dataframe(comparativa_productos, use_container_width=True)
            
            # Gráfico Comparativo por Producto
            st.write("**Gráfico Comparativo (Primeros 15 productos para visualización):**")
            datos_grafico = comparativa_productos.head(15) # Limitamos a 15 para que el gráfico no sea ilegible si hay muchos códigos
            fig_prod, ax_prod = plt.subplots(figsize=(12, 6))
            x = np.arange(len(datos_grafico))
            width = 0.35
            ax_prod.bar(x - width/2, datos_grafico['Real_Pzs_Hora'], width, label='Real', color='#1f77b4')
            ax_prod.bar(x + width/2, datos_grafico['Estimado_Pzs_Hora'], width, label='Estimado', color='#aec7e8')
            ax_prod.set_ylabel('Piezas por Hora')
            ax_prod.set_title('Real vs Estimado por Código de Producto')
            ax_prod.set_xticks(x)
            etiquetas = datos_grafico['Máquina'] + " - " + datos_grafico['Código Producto'].astype(str)
            ax_prod.set_xticklabels(etiquetas, rotation=45, ha="right")
            ax_prod.legend()
            st.pyplot(fig_prod)
            fig_prod.savefig("grafico_productos.png", bbox_inches='tight')

        with tab3:
            st.subheader("Rendimiento Histórico desde las 6:00 AM")
            lista_maquinas = promedio_por_hora['Máquina'].unique()
            maquina_seleccionada = st.selectbox("Máquina:", lista_maquinas)
            
            datos_maq = promedio_por_hora[promedio_por_hora['Máquina'] == maquina_seleccionada]
            
            fig_hor, ax_hor = plt.subplots(figsize=(10, 4))
            ax_hor.plot(datos_maq['Hora_Real'].astype(str) + "h", datos_maq['Promedio_Historico'], marker='o', color='#00509E', linewidth=2)
            ax_hor.set_title(f'Rendimiento Hora a Hora - {maquina_seleccionada}')
            ax_hor.set_ylabel('Piezas por Hora')
            ax_hor.grid(True, linestyle='--', alpha=0.6)
            st.pyplot(fig_hor)
            fig_hor.savefig("grafico_hora.png", bbox_inches='tight')
            
            st.dataframe(datos_maq[['Máquina', 'Hora_Real', 'Promedio_Historico']], use_container_width=True)

        with tab4:
            st.subheader("Bitácora Diaria")
            st.dataframe(despliegue_hora.sort_values(by=['Fecha', 'Máquina', 'Orden_Hora']), use_container_width=True)

        # ==========================================
        # 6. CREACIÓN DEL PDF ESTILIZADO
        # ==========================================
        pdf = FPDF()
        pdf.add_page()
        
        COLOR_TITULO = (0, 51, 102)
        COLOR_FONDO_TABLA = (204, 229, 255)
        
        pdf.set_font("Arial", "B", 18)
        pdf.set_text_color(*COLOR_TITULO)
        pdf.cell(190, 10, txt="REPORTE DE PRODUCCIÓN EJECUTIVO", ln=True, align='C')
        pdf.ln(5)
        
        # --- SECCIÓN 1: GENERAL (N° PRODUCTOS) ---
        pdf.set_font("Arial", "B", 14)
        pdf.cell(190, 10, txt="1. Rendimiento General (Por N. de Productos)", ln=True)
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*COLOR_FONDO_TABLA)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(80, 8, "Máquina", border=1, fill=True, align='C')
        pdf.cell(50, 8, "N. Productos", border=1, fill=True, align='C')
        pdf.cell(60, 8, "Promedio (Pzs/h)", border=1, fill=True, align='C')
        pdf.ln()
        
        pdf.set_font("Arial", "", 10)
        for index, fila in resumen_general.iterrows():
            pdf.cell(80, 8, str(fila['Máquina']), border=1, align='C')
            pdf.cell(50, 8, str(fila['Cantidad_Productos']), border=1, align='C')
            pdf.cell(60, 8, str(fila['Promedio_General_Pzs_Hora']), border=1, align='C')
            pdf.ln()
            
        pdf.ln(10)
        
        # --- SECCIÓN 2: REAL VS ESTIMADO POR PRODUCTO ---
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(*COLOR_TITULO)
        pdf.cell(190, 10, txt="2. Rendimiento por Producto (Real vs Estimado)", ln=True)
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*COLOR_FONDO_TABLA)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(50, 8, "Máquina", border=1, fill=True, align='C')
        pdf.cell(60, 8, "Código Producto", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Real (Pzs/h)", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Estimado (Pzs/h)", border=1, fill=True, align='C')
        pdf.ln()
        
        pdf.set_font("Arial", "", 10)
        for index, fila in comparativa_productos.iterrows():
            pdf.cell(50, 8, str(fila['Máquina']), border=1, align='C')
            pdf.cell(60, 8, str(fila['Código Producto'])[:25], border=1, align='C') # Límite de caracteres por si el código es muy largo
            pdf.cell(40, 8, str(fila['Real_Pzs_Hora']), border=1, align='C')
            pdf.cell(40, 8, str(fila['Estimado_Pzs_Hora']), border=1, align='C')
            pdf.ln()
            
        pdf.ln(5)
        pdf.image("grafico_productos.png", w=180) # Gráfico de los primeros 15 productos
        
        # --- SECCIÓN 3: HISTÓRICO HORA A HORA ---
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(*COLOR_TITULO)
        pdf.cell(190, 10, f"3. Rendimiento Histórico Diario ({maquina_seleccionada})", ln=True)
        
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*COLOR_FONDO_TABLA)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(80, 8, "Máquina", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Hora", border=1, fill=True, align='C')
        pdf.cell(50, 8, "Promedio (Pzs/h)", border=1, fill=True, align='C')
        pdf.ln()
        
        pdf.set_font("Arial", "", 10)
        for index, fila in datos_maq.iterrows():
            pdf.cell(80, 8, str(fila['Máquina']), border=1, align='C')
            pdf.cell(40, 8, f"{fila['Hora_Real']}:00", border=1, align='C')
            pdf.cell(50, 8, str(fila['Promedio_Historico']), border=1, align='C')
            pdf.ln()
            
        pdf.ln(5)
        pdf.image("grafico_hora.png", w=170)

        nombre_pdf = "Reporte_Ejecutivo_Productos.pdf"
        pdf.output(nombre_pdf)

        with open(nombre_pdf, "rb") as pdf_file:
            st.download_button("📥 Descargar Reporte Ejecutivo (PDF)", data=pdf_file, file_name=nombre_pdf, mime="application/pdf")
            
        os.remove("grafico_productos.png")
        os.remove("grafico_hora.png")
            
    except Exception as e:
        st.error(f"Error procesando los datos: {e}")
