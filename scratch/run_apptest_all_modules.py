import os
import sys
from streamlit.testing.v1 import AppTest

sys.stdout.reconfigure(encoding="utf-8")
MAIN_UI_PATH = os.path.abspath("app/ui/main_ui.py")

modules = [
    "Launchpad S&OP (Portada)",
    "Dashboard General",
    "ForeCast y Exportación",
    "Programación Diaria y Temporadas",
    "Plan de Producción (MVA)",
    "Ocupación de Área y Capacidad",
    "Pedido Material Vegetal",
    "Plan de Enraizamiento",
    "Plan de Siembra",
    "Curvas e Índices (Campo)",
    "Calibración de Curvas"
]

failed = 0
for mod in modules:
    at = AppTest.from_file(MAIN_UI_PATH, default_timeout=90)
    at.session_state["fiori_active_module"] = mod
    at.run(timeout=90)
    if at.exception:
        failed += 1
        print(f"[FAIL] {mod}:")
        for ex in at.exception:
            print(f"   Type: {ex.type}")
            print(f"   Value: {ex.value}")
            for tb in ex.stack_trace:
                print(f"     {tb}")
    else:
        print(f"[PASS] {mod}: 0 exceptions")

# Interactive user-flow test
print("\nRunning interactive user-flow tests...")
at = AppTest.from_file(MAIN_UI_PATH, default_timeout=90)
at.run(timeout=90)
assert not at.exception, f"Initial run failed: {at.exception}"

# 1. Search bar
at.text_input(key="fiori_enterprise_search_input").set_value("Cushion").run(timeout=90)
assert not at.exception, f"Search failed: {at.exception}"
print("[PASS] Interactive 1: Buscador General ('Cushion')")

# 2. Space navigation button click
at.button(key="fiori_sp_btn_1").click().run(timeout=90)
assert not at.exception, f"Space click failed: {at.exception}"
assert at.session_state["fiori_active_module"] == "ForeCast y Exportación"
print("[PASS] Interactive 2: Clic en pestaña superior 'Ventas y Cosecha' -> 'ForeCast y Exportación'")

# 3. Toggle edit mode in Dynamic Table
at.toggle(key="ibp_edit_toggle_fc_main_ibp").set_value(True).run(timeout=90)
assert not at.exception, f"Edit mode toggle failed: {at.exception}"
print("[PASS] Interactive 3: Activación Modo de Prueba (Editar) en Tabla Dinámica")

# 4. Return to Portada
at.button(key="btn_fiori_home_top").click().run(timeout=90)
assert not at.exception, f"Portada button failed: {at.exception}"
assert at.session_state["fiori_active_module"] == "Launchpad S&OP (Portada)"
print("[PASS] Interactive 4: Botón Portada Principal y tarjetas interactivas")

print(f"\nSummary: {len(modules) - failed}/{len(modules)} modules + 4/4 interactive flows passed with 0 runtime exceptions.")
sys.exit(1 if failed > 0 else 0)

