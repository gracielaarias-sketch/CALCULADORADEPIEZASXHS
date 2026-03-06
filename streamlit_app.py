import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from fpdf import FPDF

st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Análisis de Producción y Rendimiento por Producto")

# Pedimos el link al usuario
url_ingresada = st.text_input("Pega aquí el enlace de tu Google Sheet:")
st.markdown("*Debe ingresarse un archivo público para poder acceder a los datos.*")

if url_ingresada:
    try:
        url_limpia = url_ingresada.split("/edit")[0]
        url_csv = f"{url_limpia}/export?format=csv"
        
        st.info("Obteniendo y calculando datos...")
        df = pd.read_csv(url_csv)

        # ==========================================
        # 1. LIMPIEZA Y CÁLCULOS BASE
        # ==========================================
        columnas_num = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)', 'Tiempo Ciclo', 'Hora']
        
        for col in columnas_num:
            if col in df.columns:
                df[col] = df[col].astype(str)
                df[col] = df[col].str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['Hora_Real'] = df['Hora'].astype(int)
        df['Orden_Hora'] = df['Hora_Real'].apply(lambda x: x if x >= 6 else x + 24)

        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas'] = df['Tiempo Producción (Min)'] / 60
        
        # Rendimiento individual (para la pestaña 2)
        df['Piezas_por_Hora_Real'] = np.where(df['Horas'] > 0, df['Total_Piezas_Fabricadas'] / df['Horas'], 0)

        # ==========================================
        # 2. CUADRO 1: GENERAL POR CANTIDAD DE PRODUCTOS (CORREGIDO SIMULTÁNEO)
        # ==========================================
        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora_Real', 'Orden_Hora']).agg(
            Total_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            # CAMBIO CLAVE: Tomamos el 'max' de horas en lugar del 'sum' para no duplicar 
            # el tiempo si hay productos simultáneos.
            Total_Horas=('Horas', 'max'), 
            Cantidad_Productos=('Código Producto', 'nunique')
        ).reset_index()

        despliegue_hora['Pzs_Hora_Bloque'] = np.where(despliegue_hora['Total_Horas'] > 0, despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 0)
        despliegue_hora = despliegue_hora[(despliegue_hora['Cantidad_Productos'].isin([1, 2, 3])) & (despliegue_hora['Pzs_Hora_Bloque'] > 0)]

        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Promedio_General_Pzs_Hora=('Pzs_Hora_Bloque', 'mean')
        ).reset_index().round(2)

        # ==========================================
        # 3. CUADRO 2: COMPARATIVA REAL VS ESTIMADO
        # ==========================================
        df_validos = df[(df['Piezas_por_Hora_Real'] > 0) & (df['Código Producto'].notna()) & (df['Código Producto'] != '')]
        
        comparativa_productos = df_validos.groupby(['Máquina', 'Código Producto']).agg(
            Real_Pzs_Hora=('Piezas_por_Hora_Real', 'mean'),
            Promedio_Tiempo_Ciclo=('Tiempo Ciclo', 'mean')
        ).reset_index()

        comparativa_productos['Estimado_Pzs_Hora'] = np.where(
            comparativa_productos['Promedio_Tiempo_Ciclo'] > 0, 
            60 / comparativa_productos['Promedio_Tiempo_Ciclo'], 
            0
        )
        
        comparativa_productos['Diferencia'] = comparativa_productos['Real_Pzs_Hora'] - comparativa_productos['Estimado_Pzs_Hora']
        
        comparativa_productos = comparativa_productos[['Máquina', 'Código Producto', 'Real_Pzs_Hora', 'Estimado_Pzs_Hora', 'Diferencia']].round(2)

        def color_diferencia(val):
            if val > 0:
                return 'color: green'
            elif val < 0:
                return 'color: red'
            else:
                return 'color: black'

        # ==========================================
        # 4. CUADRO 3: HISTÓRICO POR HORA
        # ==========================================
        promedio_por_hora = despliegue_hora.groupby(['Máquina', 'Hora_Real', 'Orden_Hora']).agg(
            Promedio_Historico=('Pzs_Hora_Bloque', 'mean')
        ).reset_index().sort_values(by=['Máquina', 'Orden_Hora']).round(2)

        # ==========================================
        # 5. INTERFAZ GRÁFICA (PANTALLA)
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
            formato_decimales = "{:.2f}"
            columnas_a_formatear = ['Real_Pzs_Hora', 'Estimado_Pzs_Hora', 'Diferencia']
            
            try:
                tabla_estilizada = comparativa_productos.style.map(color_diferencia, subset=['Diferencia']).format(formato_decimales, subset=columnas_a_formatear)
            except AttributeError:
                tabla_estilizada = comparativa_productos.style.applymap(color_diferencia, subset=['Diferencia']).format(formato_decimales, subset=columnas_a_formatear)
                
            st.dataframe(tabla_estilizada, use_container_width=True)
            
            st.write("**Gráfico Comparativo (Primeros 15 productos para visualización):**")
            datos_grafico = comparativa_productos.head(15) 
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
            plt.close(fig_prod)

        with tab3:
            st.subheader("Rendimiento Histórico desde las 6:00 AM")
            lista_maquinas = promedio_por_hora['Máquina'].unique()
            maquina_seleccionada = st.selectbox("Máquina:", lista_maquinas)
            
            datos_maq_pantalla = promedio_por_hora[promedio_por_hora['Máquina'] == maquina_seleccionada]
            
            fig_hor_pantalla, ax_hor_pantalla = plt.subplots(figsize=(10, 4))
            ax_hor_pantalla.plot(datos_maq_pantalla['Hora_Real'].astype(str) + "h", datos_maq_pantalla['Promedio_Historico'], marker='o', color='#00509E', linewidth=2)
            ax_hor_pantalla.set_title(f'Rendimiento Hora a Hora - {maquina_seleccionada}')
            ax_hor_pantalla.set_ylabel('Piezas por Hora')
            ax_hor_pantalla.grid(True, linestyle='--', alpha=0.6)
            st.pyplot(fig_hor_pantalla)
            plt.close(fig_hor_pantalla)
            
            st.dataframe(datos_maq_pantalla[['Máquina', 'Hora_Real', 'Promedio_Historico']], use_container_width=True)

        with tab4:
            st.subheader("Bitácora Diaria")
            st.dataframe(despliegue_hora.sort_values(by=['Fecha', 'Máquina', 'Orden_Hora']), use_container_width=True)

        # ==========================================
        # 6. CREACIÓN DEL PDF ESTILIZADO E ITERATIVO
        # ==========================================
        pdf = FPDF()
        
        COLOR_TITULO = (0, 51, 102)
        COLOR_FONDO_TABLA = (204, 229, 255)
        
        # --- SECCIÓN 1: GENERAL ---
        pdf.add_page()
        pdf.set_font("Arial", "B", 18)
        pdf.set_text_color(*COLOR_TITULO)
        pdf.cell(190, 10, txt="REPORTE DE PRODUCCIÓN EJECUTIVO", ln=True, align='C')
        pdf.ln(5)
        
        pdf.set_font("Arial", "B", 14)
        pdf.cell(190, 10, txt="1. Rendimiento General (Por N. de Productos Simultáneos)", ln=True)
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
            pdf.cell(60, 8, f"{fila['Promedio_General_Pzs_Hora']:.2f}", border=1, align='C')
            pdf.ln()
            
        pdf.ln(10)
        
        # --- SECCIÓN 2: REAL VS ESTIMADO POR PRODUCTO ---
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(*COLOR_TITULO)
        pdf.cell(190, 10, txt="2. Rendimiento por Producto (Real vs Estimado)", ln=True)
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*COLOR_FONDO_TABLA)
        pdf.set_text_color(0, 0, 0)
        
        pdf.cell(40, 8, "Máquina", border=1, fill=True, align='C')
        pdf.cell(60, 8, "Código Producto", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Real", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Estimado", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Diferencia", border=1, fill=True, align='C')
        pdf.ln()
        
        pdf.set_font("Arial", "", 10)
        for index, fila in comparativa_productos.iterrows():
            pdf.cell(40, 8, str(fila['Máquina'])[:15], border=1, align='C')
            pdf.cell(60, 8, str(fila['Código Producto'])[:25], border=1, align='C')
            
            real_formateado = f"{fila['Real_Pzs_Hora']:.2f}"
            estimado_formateado = f"{fila['Estimado_Pzs_Hora']:.2f}"
            
            pdf.cell(30, 8, real_formateado, border=1, align='C')
            pdf.cell(30, 8, estimado_formateado, border=1, align='C')
            
            diferencia_val = fila['Diferencia']
            if diferencia_val > 0:
                pdf.set_text_color(0, 150, 0)
            elif diferencia_val < 0:
                pdf.set_text_color(200, 0, 0)
            else:
                pdf.set_text_color(0, 0, 0)
                
            texto_diferencia = f"+{diferencia_val:.2f}" if diferencia_val > 0 else f"{diferencia_val:.2f}"
            pdf.cell(30, 8, texto_diferencia, border=1, align='C')
            
            pdf.set_text_color(0, 0, 0) 
            pdf.ln()
            
        pdf.ln(5)
        pdf.image("grafico_productos.png", w=180) 
        
        # --- SECCIÓN 3: HISTÓRICO HORA A HORA ---
        lista_todas_maquinas = promedio_por_hora['Máquina'].unique()
        
        for maquina_pdf in lista_todas_maquinas:
            pdf.add_page() 
            pdf.set_font("Arial", "B", 14)
            pdf.set_text_color(*COLOR_TITULO)
            pdf.cell(190, 10, f"3. Rendimiento Histórico Diario: {maquina_pdf}", ln=True)
            
            pdf.set_font("Arial", "B", 10)
            pdf.set_fill_color(*COLOR_FONDO_TABLA)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(80, 8, "Máquina", border=1, fill=True, align='C')
            pdf.cell(40, 8, "Hora", border=1, fill=True, align='C')
            pdf.cell(50, 8, "Promedio (Pzs/h)", border=1, fill=True, align='C')
            pdf.ln()
            
            datos_maq_pdf = promedio_por_hora[promedio_por_hora['Máquina'] == maquina_pdf]
            
            pdf.set_font("Arial", "", 10)
            for index, fila in datos_maq_pdf.iterrows():
                pdf.cell(80, 8, str(fila['Máquina']), border=1, align='C')
                pdf.cell(40, 8, f"{fila['Hora_Real']}:00", border=1, align='C')
                pdf.cell(50, 8, f"{fila['Promedio_Historico']:.2f}", border=1, align='C')
                pdf.ln()
                
            pdf.ln(5)
            
            fig_pdf, ax_pdf = plt.subplots(figsize=(10, 4))
            ax_pdf.plot(datos_maq_pdf['Hora_Real'].astype(str) + "h", datos_maq_pdf['Promedio_Historico'], marker='o', color='#00509E', linewidth=2)
            ax_pdf.set_title(f'Rendimiento Hora a Hora - {maquina_pdf}')
            ax_pdf.set_ylabel('Piezas por Hora')
            ax_pdf.grid(True, linestyle='--', alpha=0.6)
            
            nombre_imagen_temp = f"temp_grafico_{maquina_pdf.replace(' ', '_').replace('/', '_')}.png"
            fig_pdf.savefig(nombre_imagen_temp, bbox_inches='tight')
            plt.close(fig_pdf)
            
            pdf.image(nombre_imagen_temp, w=170)
            
            if os.path.exists(nombre_imagen_temp):
                os.remove(nombre_imagen_temp)

        # ==========================================
        # 7. GENERACIÓN FINAL DEL ARCHIVO Y DATOS CRUDOS
        # ==========================================
        nombre_pdf = "Reporte_Ejecutivo_Completo.pdf"
        pdf.output(nombre_pdf)

        st.markdown("---")
        with open(nombre_pdf, "rb") as pdf_file:
            st.download_button("📥 Descargar Reporte Ejecutivo Completo (PDF)", data=pdf_file, file_name=nombre_pdf, mime="application/pdf")
            
        if os.path.exists("grafico_productos.png"):
            os.remove("grafico_productos.png")

        st.write("")
        with st.expander("Clic aquí para ver los datos originales (Fuente)"):
            st.dataframe(df, use_container_width=True)
            
    except Exception as e:
        st.error(f"Error procesando los datos: {e}")
