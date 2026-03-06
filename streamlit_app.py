import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from fpdf import FPDF

# Configuración de página
st.set_page_config(page_title="Panel de Producción", layout="wide")
st.title("📊 Análisis de Producción y Rendimiento Ejecutivo")

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
        df = df.dropna(how='all')

        # Limpieza estricta de la columna Máquina
        df['Máquina'] = df['Máquina'].astype(str).str.strip()
        df = df[~df['Máquina'].str.lower().isin(['nan', 'none', '', 'null'])]

        columnas_num = ['Buenas', 'Retrabajo', 'Observadas', 'Tiempo Producción (Min)', 'Tiempo Ciclo', 'Hora']
        for col in columnas_num:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Filtro de seguridad
        df = df[df['Tiempo Producción (Min)'] > 0]

        df['Hora_Real'] = df['Hora'].astype(int)
        df['Orden_Hora'] = df['Hora_Real'].apply(lambda x: x if x >= 6 else x + 24)
        df['Total_Piezas_Fabricadas'] = df['Buenas'] + df['Retrabajo'] + df['Observadas']
        df['Horas_Decimal'] = df['Tiempo Producción (Min)'] / 60

        # ==========================================
        # 2. CUADRO 1: GENERAL 
        # ==========================================
        def calcular_sub_bloque(g):
            if g.empty:
                return pd.Series({'Total_Piezas': 0.0, 'Total_Horas': 0.0, 'Cantidad_Productos': 0, 'Ciclos_Maquina': 0.0})
            
            total_piezas = float(g['Total_Piezas_Fabricadas'].sum())
            cantidad_productos = int(g['Código Producto'].nunique())
            total_horas = float(g['Horas_Decimal'].iloc[0]) if not g.empty else 0.0
            ciclos_maquina = total_piezas / cantidad_productos if cantidad_productos > 0 else 0.0
            
            return pd.Series([total_piezas, total_horas, cantidad_productos, ciclos_maquina], 
                             index=['Total_Piezas', 'Total_Horas', 'Cantidad_Productos', 'Ciclos_Maquina'])

        despliegue_hora = df.groupby(['Fecha', 'Máquina', 'Hora_Real', 'Orden_Hora', 'Horas_Decimal']).apply(calcular_sub_bloque).reset_index()
        despliegue_hora = despliegue_hora.dropna(subset=['Total_Piezas', 'Total_Horas', 'Cantidad_Productos'])

        despliegue_hora['Pzs_Hora_Bloque'] = np.where(despliegue_hora['Total_Horas'] > 0, 
                                                     despliegue_hora['Total_Piezas'] / despliegue_hora['Total_Horas'], 
                                                     0)
        
        despliegue_hora['Ciclos_Hora_Bloque'] = np.where(despliegue_hora['Total_Horas'] > 0, 
                                                        despliegue_hora['Ciclos_Maquina'] / despliegue_hora['Total_Horas'], 
                                                        0)
        
        despliegue_hora = despliegue_hora[(despliegue_hora['Cantidad_Productos'] > 0) & 
                                         (despliegue_hora['Total_Horas'] > 0) &
                                         (despliegue_hora['Pzs_Hora_Bloque'] > 0)]

        resumen_general = despliegue_hora.groupby(['Máquina', 'Cantidad_Productos']).agg(
            Promedio_Pzs_Hora=('Pzs_Hora_Bloque', 'mean'),
            Promedio_Ciclos_Hora=('Ciclos_Hora_Bloque', 'mean')
        ).reset_index().round(2)

        # ==========================================
        # 3. CUADRO 2: REAL VS ESTIMADO 
        # ==========================================
        comp_prod = df.groupby(['Máquina', 'Código Producto']).agg(
            Suma_Piezas=('Total_Piezas_Fabricadas', 'sum'),
            Suma_Horas=('Horas_Decimal', 'sum'),
            Promedio_Tiempo_Ciclo=('Tiempo Ciclo', 'mean')
        ).reset_index().dropna()

        comp_prod = comp_prod[comp_prod['Suma_Horas'] > 0]
        comp_prod['Real_Pzs_Hora'] = comp_prod['Suma_Piezas'] / comp_prod['Suma_Horas']

        comp_prod['Estimado_Pzs_Hora'] = np.where(
            comp_prod['Promedio_Tiempo_Ciclo'] > 0, 
            60 / comp_prod['Promedio_Tiempo_Ciclo'], 
            0
        )
        
        comp_prod['Diferencia'] = comp_prod['Real_Pzs_Hora'] - comp_prod['Estimado_Pzs_Hora']
        comp_prod = comp_prod[['Máquina', 'Código Producto', 'Real_Pzs_Hora', 'Estimado_Pzs_Hora', 'Diferencia']].round(2)

        # ==========================================
        # 4. INTERFAZ Y PESTAÑAS
        # ==========================================
        st.success("¡Cálculos finalizados!")
        tab1, tab2, tab3, tab4 = st.tabs(["📈 General", "🎯 Real vs Estimado", "⏰ Histórico", "📅 Bitácora"])

        with tab1:
            st.subheader("Rendimiento Real por Máquina")
            st.dataframe(resumen_general, use_container_width=True)

        with tab2:
            st.subheader("Análisis de Desviación Real vs Estimado")
            formato = "{:.2f}"
            def color_diff(val):
                return 'color: green' if val > 0 else 'color: red' if val < 0 else ''
            
            st.dataframe(
                comp_prod.style.applymap(color_diff, subset=['Diferencia'])
                .format(formato, subset=['Real_Pzs_Hora', 'Estimado_Pzs_Hora', 'Diferencia']),
                use_container_width=True
            )
            
            fig_p, ax_p = plt.subplots(figsize=(12, 5))
            datos_g = comp_prod.head(15)
            x = np.arange(len(datos_g))
            ax_p.bar(x - 0.2, datos_g['Real_Pzs_Hora'], 0.4, label='Real', color='#1f77b4')
            ax_p.bar(x + 0.2, datos_g['Estimado_Pzs_Hora'], 0.4, label='Estimado', color='#aec7e8')
            ax_p.set_xticks(x)
            ax_p.set_xticklabels(datos_g['Código Producto'], rotation=45, ha='right')
            ax_p.legend()
            fig_p.savefig("temp_prod.png", bbox_inches='tight')
            st.pyplot(fig_p)
            plt.close(fig_p)

        with tab3:
            st.subheader("Promedio de Producción por Hora del Día")
            prom_h = despliegue_hora.groupby(['Máquina', 'Hora_Real', 'Orden_Hora']).agg(P=('Pzs_Hora_Bloque', 'mean')).reset_index().sort_values('Orden_Hora')
            sel_m = st.selectbox("Selecciona la Máquina a analizar:", prom_h['Máquina'].unique())
            dat_m = prom_h[prom_h['Máquina'] == sel_m]
            st.line_chart(dat_m.set_index('Hora_Real')['P'])

        with tab4:
            st.subheader("Bitácora Diaria (Datos procesados)")
            st.dataframe(despliegue_hora.sort_values(['Fecha', 'Orden_Hora']), use_container_width=True)

        # ==========================================
        # 5. GENERACIÓN DEL PDF EJECUTIVO
        # ==========================================
        pdf = FPDF()
        AZUL_TITULO = (0, 51, 102)
        AZUL_FONDO = (204, 229, 255)

        pdf.add_page()
        pdf.set_font("Arial", "B", 18)
        pdf.set_text_color(*AZUL_TITULO)
        pdf.cell(190, 10, "REPORTE DE PRODUCCION EJECUTIVO", 0, 1, 'C')
        pdf.ln(5)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 10, "1. Rendimiento por Producto", 0, 1)
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*AZUL_FONDO)
        pdf.set_text_color(0,0,0)
        pdf.cell(40, 8, "Maquina", 1, 0, 'C', True)
        pdf.cell(60, 8, "Producto", 1, 0, 'C', True)
        pdf.cell(30, 8, "Real", 1, 0, 'C', True)
        pdf.cell(30, 8, "Estimado", 1, 0, 'C', True)
        pdf.cell(30, 8, "Diferencia", 1, 1, 'C', True)
        
        pdf.set_font("Arial", "", 9)
        for _, r in comp_prod.iterrows():
            pdf.cell(40, 7, str(r['Máquina'])[:15], 1)
            pdf.cell(60, 7, str(r['Código Producto'])[:25], 1)
            pdf.cell(30, 7, f"{r['Real_Pzs_Hora']:.2f}", 1, 0, 'C')
            pdf.cell(30, 7, f"{r['Estimado_Pzs_Hora']:.2f}", 1, 0, 'C')
            
            if r['Diferencia'] > 0:
                pdf.set_text_color(0, 150, 0)
            else:
                pdf.set_text_color(200, 0, 0)
                
            pdf.cell(30, 7, f"{r['Diferencia']:.2f}", 1, 1, 'C')
            pdf.set_text_color(0,0,0)

        pdf.image("temp_prod.png", x=10, y=pdf.get_y()+10, w=180)

        for m_id in prom_h['Máquina'].unique():
            pdf.add_page()
            pdf.set_font("Arial", "B", 14)
            pdf.set_text_color(*AZUL_TITULO)
            pdf.cell(190, 10, f"Rendimiento Diario: {m_id}", 0, 1)
            
            dat_pdf = prom_h[prom_h['Máquina'] == m_id]
            pdf.set_font("Arial", "B", 10)
            pdf.set_fill_color(*AZUL_FONDO)
            pdf.set_text_color(0,0,0)
            pdf.cell(90, 8, "Hora", 1, 0, 'C', True)
            pdf.cell(100, 8, "Promedio Pzs/h", 1, 1, 'C', True)
            
            pdf.set_font("Arial", "", 10)
            for _, r in dat_pdf.iterrows():
                pdf.cell(90, 7, f"{r['Hora_Real']}:00", 1, 0, 'C')
                pdf.cell(100, 7, f"{r['P']:.2f}", 1, 1, 'C')
            
            fig_t, ax_t = plt.subplots(figsize=(10, 4))
            ax_t.plot(dat_pdf['Hora_Real'].astype(str), dat_pdf['P'], marker='o', color='#00509E')
            t_name = f"t_{m_id}.png".replace(" ","").replace("/","")
            fig_t.savefig(t_name)
            plt.close(fig_t)
            pdf.image(t_name, x=15, y=pdf.get_y()+10, w=170)
            os.remove(t_name)

        nombre_final = "Reporte_Produccion_Final.pdf"
        pdf.output(nombre_final)

        st.markdown("---")
        with open(nombre_final, "rb") as f:
            st.download_button("📥 Descargar Reporte Completo (PDF)", f, file_name=nombre_final)

        if os.path.exists("temp_prod.png"):
            os.remove("temp_prod.png")

        st.write("")
        with st.expander("Ver datos originales (Fuente)"):
            st.dataframe(df, use_container_width=True)

    except Exception as e:
        st.error(f"Error de procesamiento: {e}")
