## 🧠 Resultados de la Prueba de Concepto ML (Random Forest)

El modelo fue entrenado utilizando el histórico de siembras y cosechas. 
En lugar de depender de una curva fenológica manual, el algoritmo aprendió a correlacionar las siembras ocurridas entre **10 a 16 semanas atrás** con la producción final, tomando en cuenta la estacionalidad.

### 📊 Desempeño del Modelo (Test Set)
*   **Total Tallos Reales (Test):** 4,699,435
*   **Total Tallos Proyectados ML:** 4,829,183
*   **Diferencia Neta:** -129,748
*   **Error Absoluto (MAPE Global ML):** **17.01%**

### 🔍 ¿Qué aprendió el modelo? (Top 5 Features Importantes)
- **Lag_11**: 53.4%
- **Lag_10**: 18.5%
- **Lag_12**: 15.2%
- **Estacionalidad_Semana**: 2.1%
- **Lag_13**: 1.8%

### 🚀 Conclusión
Esta Prueba de Concepto demuestra que un algoritmo de Machine Learning puede proyectar la cosecha aprendiendo directamente de la historia sin usar la curva fenológica explícitamente.
Con más datos climáticos, labores culturales y más historia, el error del ML caerá significativamente por debajo del modelo S&OP determinístico.
