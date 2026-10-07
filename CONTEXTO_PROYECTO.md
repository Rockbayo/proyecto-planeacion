# Contexto y Estado del Proyecto: Analítica Planeación S&OP

Este documento sirve como "memoria" para que cualquier nueva sesión del asistente comprenda exactamente en qué punto dejamos el proyecto, qué decisiones técnicas tomamos y cómo funciona la lógica agrícola por debajo.

## 1. Resumen del Proyecto
Estamos construyendo una plataforma web en **Python con Streamlit** (`app/ui/main_ui.py`) y **SQLite** (`data/planeacion.db`) para automatizar el S&OP (Sales and Operations Planning) agrícola de la finca.

El objetivo principal es pasar de múltiples macros y archivos pesados de Excel (como `Analitica_Planeacion_2.0.xlsm`) a un aplicativo centralizado, rápido y modular que proyecte las cosechas a futuro basado en inventario vivo y pedidos de material vegetal.

## 2. Estructura de Datos (SQLite)
Usamos SQLAlchemy. La base de datos `planeacion.db` contiene:
*   **Variedades:** Todas las variedades maestras con su fenología (`dia_inicio`, `dia_pico`) y sus curvas de cosecha de 15 días (`c1` a `c15`), además de su % de aprovechamiento.
*   **Ubicaciones:** Los bloques y camas físicas.
*   **Siembras:** El inventario vivo actual en campo (cargado desde el archivo *Siembra Actual (16).xlsx*).

## 3. Módulos Construidos hasta ahora

### A. Dashboard General
Muestra KPIs rápidos (área ocupada, camas sembradas, variedades) y permite cargar el inventario actual de campo. También tiene una herramienta visual para consultar las curvas fenológicas día por día de cualquier variedad, aplicando su respectivo % de aprovechamiento.

### B. ForeCast 10 Wk
Toma el inventario vivo de campo y proyecta las próximas 10 semanas móviles de cosecha cruzando las fechas de siembra contra los días fenológicos. Compara gráficamente la proyección semanal contra un *input* manual de la Meta del Plan de Producción.

### C. Exportación a Plataforma (Plantillas de 13 Semanas)
*   El usuario sube plantillas de plataforma vacías (Excel).
*   El aplicativo inyecta **9 semanas** de proyección viva, y deja las **4 semanas** restantes en blanco para que el área llene el Plan.
*   **Solución técnica clave:** Logramos evadir la restricción de Streamlit que impide descargar múltiples archivos con un solo botón. Implementamos un componente HTML/JS (`st.components.v1`) que empaqueta todos los Excels en Base64 y los descarga en ráfaga (con el nombre original exacto) al hacer 1 clic, sin usar archivos ZIP.

### D. Proyección desde Pedido Consolidado MV (Material Vegetal)
Calcula las proyecciones a largo plazo (52 semanas) partiendo únicamente de la intención de compra (esquejes).
**Lógica y reglas de negocio acordadas:**
1.  **Sin MVA adicional:** El archivo que se carga ya trae las cantidades netas a sembrar. Se removió el descuento del 2% de mortalidad en la interfaz por petición del usuario.
2.  **Línea de tiempo:** 
    *   Semana del archivo = Semana de Recepción del esqueje (Semana $S$).
    *   Fase de Enraizamiento = 3 Semanas.
    *   **Semana de Siembra a campo = $S + 4$**.
3.  **Focalización del Pico (Mid-week Peak):** Para evitar que el pico de cosecha se fragmente en dos semanas ISO distintas, el algoritmo *no* asume que se siembra el lunes. El código revisa el `Dia_Pico` de la variedad e itera buscando el día exacto de la semana de siembra (del 1 al 7) en el que, al sumarle los días fenológicos, **la fecha resultante caiga matemáticamente un Jueves (mitad de semana)**. Esto concentra el mayor volumen de la "campana" de cosecha en una sola semana ISO objetivo.

## 4. Diferencias con el Excel Manual
Realizamos un *debug* profundo comparando el aplicativo contra la hoja *Plataforma vs Planeador* del Excel manual del usuario. 
Descubrimos que la proyección manual se ve más alta en las primeras semanas de 2027 porque el Excel manual almacena el histórico de pedidos desde la semana `202614`, mientras que el archivo cargado al aplicativo (`PedidoConsolidado`) arrancaba en la semana `202639`. El aplicativo es matemáticamente preciso sobre los datos que recibe.

## 5. Próximos Pasos (Pendientes)
*   Existe un archivo adicional llamado **"Proyección 52 semanas"** que se alimenta de esta Proyección del Pedido Confirmado de MV. Es el módulo que sigue en la lista por desarrollar.

## Instrucción para el asistente:
Al iniciar sesión, **lee este archivo, revisa `main_ui.py` y `mva_service.py`**, y pregúntale al usuario cuál es el siguiente objetivo. Tienes permiso absoluto para modificar y proponer mejoras arquitectónicas.
