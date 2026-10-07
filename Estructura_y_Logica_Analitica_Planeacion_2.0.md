# Documentación Estructural y Lógica de Analitica_Planeacion_2.0.xlsm

Este documento sirve como referencia técnica y de contexto sobre la herramienta de planeación agrícola `Analitica_Planeacion_2.0.xlsm`. Está diseñado para proveer una comprensión rápida y detallada de cómo se interconectan los datos, las fórmulas matemáticas principales y los procesos automatizados (VBA).

## 1. Módulos y Arquitectura de Hojas

El modelo está compuesto por 18 hojas de cálculo interdependientes organizadas de la siguiente manera:

### 📱 Navegación y Dashboard
*   **`Inicio`**: Panel de control principal. Utiliza macros (`IrA_...`) para mostrar u ocultar el resto de las hojas, facilitando la experiencia de usuario y previniendo daños accidentales a la estructura.

### 📚 Data Maestra (Master Data)
*   **`Datos_Base`**: Relaciona calendarios cronológicos, mapeando fechas absolutas a semanas de operación (ej. `202639`). Define las capacidades estándar como "Plantas x Cama".
*   **`Datos_Variedades`**: Diccionario fenológico y de productividad por variedad de flor.
    *   Registra características visuales (Flor y Color).
    *   Define días al ciclo: inicio de cosecha (`Dia_Inicio`), pico de cosecha (`Dia_Pico`) y ciclo de desbotone (`Dias_Desb`).
    *   Contiene la curva de producción histórica o esperada (`C1` a `C15`).
*   **`Datos_Campo`**: Matriz física y cualitativa del terreno. 
    *   Cruza Sede, Bloque, Lado, Nave y Cama contra el tipo de variedad.
    *   Lleva un seguimiento de las mermas por razones fitosanitarias o fisiológicas (Torcidos, Ácaros, Trips, Mecánico, Cortos, Vegetativos).
*   **`Indices`**: Factores y métricas específicas cruzando Flores, Variedades y Días de siembra para su utilización en otras áreas del modelo.

### ⚙️ Ejecución y Plan Operativo
*   **`Plan Enraizamiento`**: Toma el calendario de requerimientos de siembra y aplica un cálculo "hacia atrás" para determinar cuántos esquejes deben entrar a los bancos de enraizamiento y cuándo.
*   **`Plan Siembra`**: Cuadro detallado que asigna lo que debe sembrarse en campo.
*   **`Desbotone_Arranques`**: Cronograma para dos labores culturales críticas: Desbotone (retiro de botones secundarios para potenciar flor principal) y Arranques (eliminación y compostaje del cultivo viejo).
*   **`Etiquetas`**: Generador automático de rótulos de invernadero que busca mediante matrices la información física y siembras correspondientes.

### 📈 Pronóstico y Ajuste Estadístico (Forecasting)
*   **`ForeCast`**: Cruza el volumen de siembra, la fecha, y la curva de variedad para proyectar cuántos tallos se cortarán en el futuro.
*   **`FC_13WK`**: Resumen condensado a "13 Semanas Móviles" del comportamiento a corto plazo.
*   **`Factor_Ajuste`**: Calcula un suavizamiento exponencial (SES) para ajustar el pronóstico con la realidad productiva. Sus fórmulas de control obligan a que el factor correctivo de la herramienta de pronóstico nunca baje del 80% ni sobrepase el 130%.
*   **`Plan_vs_Ajuste`**: Tabla de comparación de metas vs pronóstico estadístico corregido.

### 📦 Compras y Abastecimiento (MV)
*   **`Plan a MVA`** y **`Pedido_MV`**: Módulos que traducen las necesidades de enraizamiento en pedidos exactos que se deben pasar a las fincas proveedoras de "Material Vegetal" (esquejes), contemplando un porcentaje estándar de pérdidas.

### 🔍 Auditoría, Seguimiento e Integración (RPA)
*   **`Plataforma vs Planeador`**: Interfaz de conciliación entre la base de datos local de planeación y la plataforma externa / ERP de la empresa.
*   **`Auditoria Siembras`**: Realiza el cruce entre las *Plantas sembradas* reales vs el *Plan Siembras* original para calcular la adherencia a la planeación (% de desvío).
*   **`Historico Enraizamiento`**: Base de datos de solo-valores para resguardar los cierres semanales y no alterar reportes pasados por recalculación de fórmulas.

---

## 2. Lógica Fenológica y Matemáticas Clave

La inteligencia del sistema recae en la temporalidad dinámica de sus fórmulas:

*   **Progresión del Cultivo**:
    *   El ciclo biológico nace en `Fecha_Siembra`.
    *   La operación de desbotone ocurre en: `Fecha_Siembra + Dias_Desb`.
    *   El ciclo de cosecha arranca en: `Fecha_Siembra + Dia_Inicio`.
    *   El esfuerzo pico de extracción es: `Fecha_Siembra + Dia_Inicio + Dia_Pico`.
    *   El cierre del ciclo lo dictamina la dispersión varietal (`Span_Dias`).
*   **Planeación en Reversa (Backwards Scheduling)**:
    *   En `Plan Enraizamiento`, se identifica que la constante de programación es de 3 semanas (21 días): `XLOOKUP(...) + 21`. A partir de una siembra requerida, se retrocede este tiempo para emitir la alerta de ingreso al banco.
*   **Métricas de Desempeño (% APROV)**:
    *   Densidad Efectiva = Plantas Reales / Capacidad Teórica del área.
    *   Rendimiento y Calidad = (Total Plantas - Sumatoria de Pérdidas de Calidad Fitopatológicas) / Plantas.

---

## 3. Automatización Integrada (VBA Macros)

El libro cuenta con programación nativa robusta (`ThisWorkbook` y Módulos) enfocada a la gestión de datos:

1.  **Macro `ActualizarTodo()`**
    *   Optimiza el modelo suspendiendo temporalmente el renderizado de la pantalla (`Application.ScreenUpdating = False`), fuerza una reconstrucción total del árbol de dependencias (`Application.CalculateFullRebuild`) y dispara `ActiveWorkbook.RefreshAll` para actualizar PowerQueries o conexiones pivotales.
2.  **Macro `Historico()`**
    *   Procedimiento de fin de semana que toma la información validada en la ventana de enraizamiento, la traslada a `Historico Enraizamiento` consolidando mediante `PasteSpecial xlPasteValues` (para blindar los datos a cambios futuros en la BD) y purga la columna de ejecución de la hoja origen dejándola en blanco para un nuevo periodo.
3.  **Macro `Siembras_RPA()` (Robotic Process Automation)**
    *   Conector de RPA: Esta rutina prepara datos empaquetados para ser leídos por un bot en la nube o local (UiPath / Power Automate).
    *   Extrae y filtra las columnas relevantes de la tabla `Plantilla_Siembras`.
    *   Crea silenciosamente una copia pegando todo a un archivo puente llamado `Estructura.xlsx` alojado en el directorio corporativo (ej. `OneDrive - GR Chia S.A.S\Planos de Siembra - CH\Estructura\`).
    *   Sufija el archivo con la fecha del día `Siembras_CH_DD-MM-YYYY.xlsx` y borra los datos operativos de la matriz origen local. El bot externo tomará luego esta estructura estándar y la ingresará al sistema general de la empresa.

