# S&OP Arquitectura y Lógica de Negocio: Analitica_Planeacion_2.0

Este documento es la versión consolidada y exhaustiva del flujo de datos, negocio y operación para el cultivo. Modela el ciclo **S&OP (Sales & Operations Planning)** completo de la Finca, integrando las realidades biológicas con las proyecciones comerciales.

---

## 1. Módulo Empírico (La Base de Datos del Cultivo)
Este módulo se encarga de recolectar la "verdad" de lo que sucede en el terreno, para que el sistema tenga índices estadísticos reales de cada variedad.

*   **Entrada de Datos (`Reporte_Camas_Piloto.xlsx`)**: El jefe de campo reporta qué camas entraron a cosecha, cuántos tallos se sacaron semana a semana (Corte 1 a Corte 15) y contabiliza todas las pérdidas (Torcidos, Trips, Ácaros, Vegetativo).
*   **Hoja `Datos_Campo`**: Recibe este reporte empírico. Es el inventario físico y cualitativo.
*   **Hoja `Indices` y `Datos_Variedades`**: A partir del reporte de campo, se actualizan los índices de rendimiento (`% Aprovechamiento`) y se dibujan las curvas reales de extracción semanal por cada variedad.

## 2. Módulo de Visibilidad a Corto Plazo (Forecasting Inmediato)
Este módulo responde a la pregunta: ¿Qué vamos a cosechar en las próximas semanas?

*   **Entrada de Datos (`Siembra Actual.xlsx`)**: Es un corte en tiempo real del inventario que hoy está plantado en el suelo germinando y creciendo.
*   **Hoja `ForeCast`**: Cruza la **Siembra Actual** contra el fenograma estático de la hoja `Datos_Variedades`. Extrapola semana a semana la cosecha.
*   **Hoja `FC_13WK`**: Presenta esta proyección matemática resumida a **13 semanas móviles** para decisiones gerenciales inmediatas.

## 3. Módulo de Planeación Estratégica (Ciclos de 3 Veces al Año)
Aquí se negocia y ajusta el plan entre el departamento de Planeación Central y la Finca. Existen 3 grandes temporadas (FA-XM, MD-SU, VD-EA).

*   **Paso 3.1 - Solicitud de Planeación (`Actualización Datos...xlsx`)**: El área central envía a la finca el formato definiendo las semanas del ciclo comercial y parámetros globales de la sede.
*   **Paso 3.2 - Asignación de Cuota (`CH-ValentinesDay...xlsx`)**: Planeación asigna la meta de ventas esperada para la finca.
*   **Paso 3.3 - Acta INV y MVA**: El "Comité de Introducción de Nuevas Variedades" define la participación porcentual del portafolio por colores/tipos de flor. 
*   **Hoja `Plan a MVA`**: Traduce la meta general (Paso 3.2) a variedades específicas usando la distribución porcentual estipulada en el comité (Paso 3.3).
*   **Ajuste a "Camas Completas"**: El modelo restringe la siembra a unidades físicas reales. Solo se pueden programar camas completas, no fracciones matemáticas.
*   **Hoja `Plan_vs_Ajuste`**: Proyecta qué pasaría si se siembra ese plan de camas completas (usando los índices de la hoja `Datos_Variedades`). Es la contra-oferta de la finca hacia planeación ("Esto es lo que físicamente te garantizo producir").

## 4. Módulo de Aprovisionamiento (Pedidos de Esquejes)
Sabiendo qué y cuándo se va a sembrar, la finca debe pedir el "pie de cría" (Material Vegetal).

*   **Hoja `Plan Enraizamiento`**: Toma la fecha de siembra proyectada y hace un *backwards scheduling*. Resta **21 días (3 semanas)** para determinar cuándo el esqueje debe ingresar al banco de enraizamiento. Considera un colchón para la mortalidad en banco.
*   **Hoja `Pedido_MV`**: Resume estos requerimientos en órdenes de compra hacia los propagadores.
*   **La Regla de Piedra a 24 Semanas**: El pedido se sube a la plataforma. Dado que la Finca Propagadora tiene que preparar sus plantas madre, los pedidos comerciales se bloquean (en piedra) con **24 semanas de anticipación**.
*   **El Pedido Extemporáneo**: Si bien el modelo opera a 24 semanas bloqueadas, el sistema permite cargar pedidos de emergencia a la plataforma por faltantes repentinos. Estos entran como "extemporáneos", sujetos a revisión, aprobación y estricta disponibilidad de material por parte del proveedor.

## 5. Módulo de Control y Reacción (Auditoría Continua)
Como la naturaleza es cambiante, la finca necesita saber si lo que pidió hace 24 semanas todavía sirve para cumplir la meta de hoy.

*   **Hoja `Plataforma vs Planeador`**: Descarga el `PedidoConsolidado.xlsx` (lo que está "en piedra" en la plataforma) y lo cruza contra las nuevas iteraciones matemáticas del "Planeador" local (quien usa los índices recién actualizados de `Datos_Campo`).
*   **Alarma Temprana**: Si los índices bajan hoy, esta hoja revelará inmediatamente una brecha entre lo que "se pidió en piedra" y lo que "ahora dice la proyección". Esto detona la necesidad de hacer *Pedidos Extemporáneos*.
*   **Hoja `Auditoria Siembras`**: Realiza una labor análoga en campo. Cruza las *Plantas Sembradas Reales* versus el *Plan de Siembra*. Detecta desviaciones operativas y emite la varianza (`Var %`).

## 6. Módulo de Ejecución Física e Integración
La salida de las operaciones se canaliza automatizadamente para no depender de labores manuales redundantes.

*   **Hoja `Desbotone_Arranques`**: Utiliza `Fecha_Siembra` + `Dias_Desb` para calendarizar las labores semanales del personal de campo.
*   **Hoja `Etiquetas`**: Genera los cartones de identificación física para que cada cama en el invernadero tenga su cédula.
*   **`Siembras_RPA_2.0.xlsm`**: Una vez ejecutadas las siembras en el archivo de planeación, una macro "limpia" la tabla y genera un formato puente (`Estructura.xlsx`) en una carpeta de OneDrive corporativa. Desde allí, un bot de RPA (Robotic Process Automation) lee los datos e ingresa las siembras directamente al ERP central de la empresa.

---
*Este documento captura a profundidad la matemática y los eventos de S&OP. Todo desarrollo del nuevo aplicativo deberá honrar este ciclo: Empírico -> Proyección -> Negociación -> Aprovisionamiento -> Control.*
