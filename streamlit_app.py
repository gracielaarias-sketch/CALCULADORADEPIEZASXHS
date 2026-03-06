import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from fpdf import FPDF

# Configuración de página
st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Análisis de Producción y Rendimiento por Producto")

# 1. ENTRADA DE DATOS
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
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['Hora_Real'] = df['Hora'].astype(int)
        df['Orden_Hora'] = df['Hora_Real'].apply(lambda x: x if x >= 6 else x + 24)

        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas_Decimal'] = df['Tiempo Producción (Min)'] / 60
        
        df['Piezas_por_Hora_Fila'] = np.where(df['Horas_Decimal'] > 0, df['Total_Piezas_Fabricadas'] / df['Horas_Decimal'], 0)

        # ==========================================
        # 2. CUADRO 1: GENERAL (LÓGICA DE TIEMPOS SIMULTÁNEOS)
        # ==========================================
        
        def calcular_bloque_hora(g):
            total_piezas = g['Total_Piezas_Fabricadas'].sum()
            
            # Si en la misma hora física hay registros con el mismo tiempo de producción, se hicieron a la par
            productos_simultaneos = g.groupby('Horas_Decimal')['Código Producto'].nunique().max()
            cantidad_productos = min(productos_simultaneos, 3)
            
            # El tiempo real es la suma de los tiempos ÚNICOS registrados en ese bloque
            # Esto corrige el "Changeover": si hay 40min y 20min, suma 1h. Si hay 60 y 60, suma 1h.
            total_horas = g['Horas_Decimal'].unique().sum()
            
            return pd.Series({
                'Total_Piezas': total_piezas,
                'Total_Horas': total_horas,
                'Cantidad_Productos': cantidad_productos
            })

        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora_Real', 'Orden_Hora']).apply(calcular_bloque_hora).reset_index()

        despliegue_hora['Pzs_Hora_Bloque'] = np.where(despliegue_hora['Total_Horas'] > 0, despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 0)
        despliegue_hora = despliegue_hora[(despliegue_hora['Cantidad_Productos'].isin([1, 2, 3])) & (despliegue_hora['Pzs_Hora_Bloque'] > 0)]

        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Promedio_General_Pzs_Hora=('Pzs_Hora_Bloque', 'mean')
        ).reset_index().round(2)

        # ==========================================
        # 3. CUADRO 2: REAL VS ESTIMADO (LÓGICA SUMA TOTAL Y UMBRAL 10)
        # ==========================================
        # Agrupamos por totales absolutos para evitar distorsiones de promedios (Garantiza el 342 de Línea 4)
        comparativa_productos = df.groupby(['Máquina', 'Código Producto']).agg(
            Suma_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            Suma_Horas=('Horas_Decimal', 'sum'),
            Promedio_Tiempo_Ciclo=('Tiempo Ciclo', 'mean')
        ).reset_index()

        comparativa_productos = comparativa_productos[comparativa_productos['Suma_Horas'] > 0]
        
        # Real = Suma Total Piezas / Suma Total Horas
        comparativa_productos['Real_Pzs_Hora'] = comparativa_productos['Suma_Piezas'] / comparativa_productos['Suma_Horas']

        # Estimado con umbral de 10 (Detecta automático Segundos vs Minutos)
        
        comparativa_productos['Estimado_Pzs_Hora'] = np.where(
            comparativa_productos['Promedio_Tiempo_Ciclo'] > 10, 
            3600 / comparativa_productos['Promedio_Tiempo_Ciclo'], # Cálculo en SEGUNDOS
            np.where(comparativa_productos['Promedio_Tiempo_Ciclo'] > 0, 
                     60 / comparativa_productos['Promedio_Tiempo_Ciclo'], # Cálculo en MINUTOS
                     0)
        )
        
        comparativa_productos['Diferencia'] = comparativa_productos['Real_Pzs_Hora'] - comparativa_productos['Estimado_Pzs_Hora']
        comparativa_productos = comparativa_productos[['Máquina', 'Código Producto', 'Real_Pzs_Hora', 'Estimado_Pzs_Hora', 'Diferencia']].round(2)

        # ==========================================
        # 4. INTERFAZ STREAMLIT
        # ==========================================
        st.success("¡Cálculos finalizados exitosamente!")
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 1. General (N° Productos)", 
            "🎯 2. Real vs Estimado", 
            "⏰ 3. Histórico por Hora", 
            "📅 4. Bitácora"
        ])
        
        with tab1:
            st.subheader("Rendimiento por cantidad de productos simultáneos")
            st.dataframe(resumen_general, use_container_width=True)

        with tab2:
            st.subheader("Análisis de Desviación Real vs Estimado")
            def color_diff(val):
                return 'color: green' if val > 0 else 'color: red' if val < 0 else ''
            
            st.dataframe(
                comparativa_productos.style.applymap(color_diff, subset=['Diferencia'])
                .format("{:.2f}", subset=['Real_Pzs_Hora', 'Estimado_Pzs_Hora', 'Diferencia']),
                use_container_width=True
            )
            
            # Gráfico Comparativo
            datos_grafico = comparativa_productos.head(15) 
            fig_p, ax_p = plt.subplots(figsize=(12, 6))
            x = np.arange(len(datos_grafico))
            ax_p.bar(x - 0.2, datos_grafico['Real_Pzs_Hora'], 0.4, label='Real', color='#1f77b4')
            ax_p.bar(x + 0.2, datos_grafico['Estimado_Pzs_Hora'], 0.4, label='Estimado', color='#aec7e8')
            ax_p.set_xticks(x)
            ax_p.set_xticklabels(datos_grafico['Código Producto'], rotation=45, ha="right")
            ax_p.legend()
            st.pyplot(fig_p)
            fig_p.savefig("grafico_productos.png", bbox_inches='tight')
            plt.close(fig_p)

        with tab3:
            st.subheader("Rendimiento Histórico desde las 6:00 AM")
            prom_h = despliegue_hora.groupby(['Máquina', 'Hora_Real', 'Orden_Hora']).agg(P=('Pzs_Hora_Bloque', 'mean')).reset_index().sort_values('Orden_Hora')
            sel_m = st.selectbox("Seleccionar Máquina:", prom_h['Máquina'].unique())
            datos_m = prom_h[prom_h['Máquina'] == sel_m]
            st.line_chart(datos_m.set_index('Hora_Real')['P'])

        with tab4:
            st.subheader("Bitácora Diaria Detallada")
            st.dataframe(despliegue_hora.sort_values(by=['Fecha', 'Máquina', 'Orden_Hora']), use_container_width=True)

        # ==========================================
        # 5. GENERACIÓN DEL PDF (UNA HOJA POR MÁQUINA)
        # ==========================================
        pdf = FPDF()
        AZUL_TITULO = (0, 51, 102)
        AZUL_TABLA = (204, 229, 255)

        # Hoja Resumen
        pdf.add_page()
        pdf.set_font("Arial", "B", 18)
        pdf.set_text_color(*AZUL_TITULO)
        pdf.cell(190, 10, "REPORTE DE PRODUCCIÓN EJECUTIVO", 0, 1, 'C')
        pdf.ln(10)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 10, "Comparativa de Rendimiento por Producto", 0, 1)
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*AZUL_TABLA)
        pdf.cell(40, 8, "Maquina", 1, 0, 'C', True)
        pdf.cell(60, 8, "Producto", 1, 0, 'C', True)
        pdf.cell(30, 8, "Real", 1, 0, 'C', True)
        pdf.cell(30, 8, "Estimado", 1, 0, 'C', True)
        pdf.cell(30, 8, "Diferencia", 1, 1, 'C', True)
        
        pdf.set_font("Arial", "", 9)
        pdf.set_text_color(0,0,0)
        for _, fila in comparativa_productos.iterrows():
            pdf.cell(40, 7, str(fila['Máquina'])[:15], 1)
            pdf.cell(60, 7, str(fila['Código Producto'])[:25], 1)
            pdf.cell(30, 7, f"{fila['Real_Pzs_Hora']:.2f}", 1, 0, 'C')
            pdf.cell(30, 7, f"{fila['Estimado_Pzs_Hora']:.2f}", 1, 0, 'C')
            pdf.set_text_color(0, 150, 0) if fila['Diferencia'] > 0 else pdf.set_text_color(200, 0, 0)
            pdf.cell(30, 7, f"{fila['Diferencia']:.2f}", 1, 1, 'C')
            pdf.set_text_color(0,0,0)
        
        pdf.ln(10)
        pdf.image("grafico_productos.png", x=15, w=170)

        # Hojas Históricas por Máquina
        for maq_id in prom_h['Máquina'].unique():
            pdf.add_page()
            pdf.set_font("Arial", "B", 14)
            pdf.set_text_color(*AZUL_TITULO)
            pdf.cell(190, 10, f"Histórico Hora a Hora: {maq_id}", 0, 1)
            
            dat_pdf = prom_h[prom_h['Máquina'] == maq_id]
            pdf.set_font("Arial", "B", 10)
            pdf.set_fill_color(*AZUL_TABLA)
            pdf.cell(90, 8, "Hora", 1, 0, 'C', True)
            pdf.cell(100, 8, "Promedio Pzs/h", 1, 1, 'C', True)
            
            pdf.set_font("Arial", "", 10)
            for _, r in dat_pdf.iterrows():
                pdf.cell(90, 7, f"{r['Hora_Real']}:00", 1, 0, 'C')
                pdf.cell(100, 7, f"{r['P']:.2f}", 1, 1, 'C')
            
            fig_h, ax_h = plt.subplots(figsize=(10, 4))
            ax_h.plot(dat_pdf['Hora_Real'].astype(str), dat_pdf['P'], marker='o', color='#00509E')
            img_name = f"temp_{maq_id}.png".replace(" ","")
            fig_h.savefig(img_name)
            plt.close(fig_h)
            pdf.image(img_name, x=20, y=pdf.get_y()+10, w=160)
            os.remove(img_name)

        nombre_rep = "Reporte_Produccion_Final.pdf"
        pdf.output(nombre_rep)
        
        st.markdown("---")
        with open(nombre_rep, "rb") as f:
            st.download_button("📥 Descargar Reporte Completo (PDF)", f, file_name=nombre_rep)

        # DATOS FUENTE AL FINAL
        st.write("")
        with st.expander("Clic aquí para ver los datos originales (Fuente)"):
            st.dataframe(df, use_container_width=True)

    except Exception as e:
        st.error(f"Error en el procesamiento: {e}")
