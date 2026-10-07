import streamlit as st
import streamlit.components.v1 as components
import base64
import json

st.title("Test Multi Download")

files = [
    {"filename": "test1.txt", "b64": base64.b64encode(b"Hello 1").decode("utf-8")},
    {"filename": "test2.txt", "b64": base64.b64encode(b"Hello 2").decode("utf-8")}
]

js_code = f"""
<script>
function downloadAll() {{
    const files = {json.dumps(files)};
    files.forEach((file, index) => {{
        setTimeout(() => {{
            const link = document.createElement("a");
            link.href = "data:text/plain;base64," + file.b64;
            link.download = file.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}, index * 500); // 500ms delay between downloads
    }});
}}
</script>
<button onclick="downloadAll()" style="background-color: #FF4B4B; border: none; color: white; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 5px; font-family: sans-serif;">
    ⬇️ Descargar Todos (1 Clic)
</button>
"""

components.html(js_code, height=60)

