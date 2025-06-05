# mcp_server.py (continuación del que ya teníamos)

from flask import Flask, request, jsonify
from openai import OpenAI # Para hablar con Ollama/LM Studio

app = Flask(__name__)

# Configura el cliente de OpenAI para apuntar a tu servidor local de Ollama/LM Studio
# PUERTO OLLAMA: 11434
# PUERTO LM STUDIO (por defecto): 1234
OLLAMA_BASE_URL = "http://localhost:11434/v1" 
LM_STUDIO_BASE_URL = "http://localhost:1234/v1" # Cambia si tu LM Studio usa otro puerto

# Elige a cuál te conectarás (Ollama o LM Studio)
# Por ahora, dejaremos Ollama, puedes cambiarlo si usas LM Studio para este modelo
client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama") # api_key puede ser "ollama" o cualquier cosa para Ollama/LMStudio

# --- PROMPT MAESTRO V3.4 (si quieres que también guíe esta tarea, aunque el prompt de sistema de abajo es muy específico) ---
PROMPT_MAESTRO_V3_4 = """ 
INSTRUCCIONES DE SISTEMA (Prompt Maestro - Agente IA Jurídico Argentino - v3.4)
Eres una IA avanzada diseñada para actuar como un Agente Jurídico Argentino...
... (tu prompt v3.4 completo aquí si decides usarlo como base general) ...
""" # Podrías decidir NO usar el v3.4 completo aquí si el siguiente prompt es suficiente.

# --- PROMPT DE SISTEMA ESPECÍFICO PARA REFORMULAR HECHOS ---
PROMPT_SISTEMA_REFORMULAR_HECHOS = """
Eres un abogado profesional especializado en el sistema legal argentino. Tu principal tarea es reformular, corregir y estructurar los hechos proporcionados para que puedan ser utilizados como base en un escrito de demanda judicial. Tu enfoque debe ser identificar los puntos clave de los hechos, especialmente aquellos que tienen relevancia jurídica, y justificar las consecuencias jurídicas en base al derecho aplicable. Utiliza un lenguaje claro, preciso y formal, adaptado al contexto judicial.

Instrucciones específicas:
Recepción y análisis de hechos:
1. Identifica los eventos relevantes desde una perspectiva jurídica.
2. Distingue hechos principales (que generan consecuencias jurídicas) de los accesorios o contextuales.

Reformulación:
1. Redacta los hechos en un estilo formal y estructurado, siguiendo las convenciones de un escrito de demanda en Argentina.
2. Corrige errores de redacción o incoherencias en los hechos presentados.

Fundamentación legal:
1. Incluye una breve descripción de las consecuencias jurídicas que podrían derivarse de los hechos reformulados.
2. Cita artículos o principios del derecho argentino que sustenten las consecuencias jurídicas identificadas, si corresponde.

Ejemplo de formato de respuesta (usa este formato estrictamente si es posible):
Hecho clave: [Reformulación precisa del hecho].
Consecuencia jurídica: [Descripción de la implicación legal]. 
Fundamento legal: [Referencia normativa o doctrinal relevante].
---
Hecho clave: [Siguiente hecho reformulado].
Consecuencia jurídica: [Siguiente implicación].
Fundamento legal: [Siguiente referencia].

Consideraciones:
Mantén un tono formal y profesional, adecuado para escritos judiciales en Argentina.
No agregues información no provista por el usuario, pero utiliza inferencias lógicas para identificar puntos implícitos relevantes.
Usa terminología jurídica precisa y, de ser necesario, incluye términos en latín comunes en derecho.
Si no puedes aplicar el formato exacto de "Hecho clave / Consecuencia / Fundamento" a todo el texto, al menos estructura la respuesta de forma clara y con los componentes solicitados.
"""

# Endpoint para la sugerencia general (el que ya teníamos)
@app.route('/api/sugerencia_legal', methods=['POST'])
def obtener_sugerencia():
    # ... (código de este endpoint como lo teníamos antes) ...
    # ... (asegúrate de que 'modelo_a_usar' aquí sea el correcto para esta tarea general)
    # ... (por ejemplo, un Gemma 7B si lo tienes, o el 2B)
    modelo_general = "gemma:7b" # o "gemma:2b" o el que uses para sugerencias generales
    try:
        data = request.json
        historial_caso = data.get("historial_caso", "")
        consulta_usuario = data.get("consulta_usuario", "")
        contexto_adicional = data.get("contexto_adicional", "")

        prompt_final_usuario = f"""
        Dada la siguiente información del caso y mi consulta, proporciona una sugerencia.
        Historial del Caso:\n{historial_caso}\n
        Contexto Adicional:\n{contexto_adicional}\n
        Mi Consulta Específica:\n{consulta_usuario}
        """
        
        # Aquí podrías decidir si usar PROMPT_MAESTRO_V3_4 como system o no para esta tarea general
        messages = [{"role": "system", "content": PROMPT_MAESTRO_V3_4}] if PROMPT_MAESTRO_V3_4.strip() else []
        messages.append({"role": "user", "content": prompt_final_usuario})

        completion = client.chat.completions.create(
            model=modelo_general, 
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        )
        respuesta_ia = completion.choices[0].message.content
        return jsonify({"sugerencia": respuesta_ia})
    except Exception as e:
        print(f"Error en /api/sugerencia_legal: {e}")
        return jsonify({"error": str(e)}), 500


# --- NUEVO ENDPOINT PARA REFORMULAR HECHOS ---
@app.route('/api/reformular_hechos', methods=['POST'])
def reformular_hechos_api():
    try:
        data = request.json
        texto_original_hechos = data.get("texto_hechos", "")

        if not texto_original_hechos.strip():
            return jsonify({"error": "El texto de los hechos no puede estar vacío."}), 400

        # Aquí especificas el modelo que quieres usar para ESTA tarea.
        # Si "gemma3:4b" es tu forma de referirte a gemma:2b o una variante específica
        # que corre bien, úsalo. Si no, prueba con "gemma:2b" o "gemma:7b".
        # ¡Asegúrate que este modelo esté disponible y sirviéndose en Ollama/LM Studio!
        modelo_para_hechos = "gemma3:4b" # O "gemma:7b" o el tag exacto de tu modelo "4B" en Ollama

        # El prompt de usuario es más directo aquí, ya que el de sistema es muy específico
        prompt_usuario_para_hechos = f"Por favor, reformula los siguientes hechos: {texto_original_hechos}, de modo que pueda incluirlos en un escrito de demanda judicial. Para el caso de que invoques normativa, explicarás claramente los alcances y las consecuencias jurídicas relacionadas con el caso, siguiendo el formato solicitado en las instrucciones de sistema."

        completion = client.chat.completions.create(
            model=modelo_para_hechos,
            messages=[
                {
                    "role": "system",
                    "content": PROMPT_SISTEMA_REFORMULAR_HECHOS 
                },
                {
                    "role": "user",
                    "content": prompt_usuario_para_hechos
                }
            ],
            temperature=0.5, # Podrías querer una temperatura más baja para mayor consistencia
            max_tokens=2048, # Puede necesitar más tokens si los hechos son largos y la respuesta es detallada
            stream=False # Para este caso, stream=False es más simple de manejar inicialmente
        )

        respuesta_reformulada = completion.choices[0].message.content
        return jsonify({"hechos_reformulados": respuesta_reformulada})

    except Exception as e:
        print(f"Error en /api/reformular_hechos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # app.run(port=5000, debug=True) # Si usas el comando "flask run", esto no es necesario
                                   # Para ejecutar directamente con "python mcp_server.py", sí.
    # Para desarrollo, puedes usar el servidor de desarrollo de Flask:
    # 1. En la terminal, en la carpeta del proyecto:
    #    set FLASK_APP=mcp_server.py  (en Windows cmd)
    #    $env:FLASK_APP = "mcp_server.py" (en PowerShell)
    #    export FLASK_APP=mcp_server.py (en Linux/macOS)
    # 2. Luego:
    #    flask run --debug
    # O simplemente, como lo tenías antes si te funciona bien:
    app.run(host='0.0.0.0', port=5000, debug=True) # host='0.0.0.0' para que sea accesible en la red local si es necesario