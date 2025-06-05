import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, Toplevel
import crm_database as db # Tu módulo de base de datos
import os
import datetime
import time
import sys
import subprocess
import sqlite3 # Importar sqlite3 directamente para referenciar errores
import requests
import json
from docx import Document # Necesitarás: pip install python-docx
from docx.enum.text import WD_ALIGN_PARAGRAPH

# --- Nuevos Imports para Agenda/Recordatorios/Bandeja ---
from tkcalendar import Calendar, DateEntry
import threading
import webbrowser
import re
import urllib.parse # Para codificar URLs (Compartir)
from PIL import Image, ImageTk # Para imagen del logo y bandeja
import plyer # Para notificaciones nativas
from pystray import MenuItem as item, Icon as icon # Para bandeja sistema
import shutil

# --- Import para las Pestañas Modulares ---
from seguimiento_ui import SeguimientoTab
from partes_ui import PartesTab # <--- IMPORTACIÓN DEL NUEVO MÓDULO PARTES
from tareas_ui import TareasTab # <--- NUEVA IMPORTACIÓN: TAREAS

# --- Helper para Rutas Relativas (PyInstaller) ---
def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para desarrollo y para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)
# --- Fin Helper ---


# Clase principal de la aplicación
class CRMLegalApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CRM Legal Local - Gestor Integral        Powered by Legal-IT-Ø")
        try:
            self.root.state('zoomed')
        except tk.TclError:
            print("Advertencia: root.state('zoomed') falló. Intentando alternativa o usando tamaño por defecto.")
            self.root.attributes('-zoomed', True)

        # --- Crear la Barra de Menú ---
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Mostrar Ventana", 
                            command=self._mostrar_ventana_callback)
        filemenu.add_separator()
        filemenu.add_command(label="Ocultar a Bandeja", command=self.ocultar_a_bandeja)
        filemenu.add_separator()
        filemenu.add_command(label="Salir (Cerrar Aplicación)", command=self.cerrar_aplicacion_directamente)
        menubar.add_cascade(label="Archivo", menu=filemenu)
        ia_menu = tk.Menu(menubar, tearoff=0)
        ia_menu.add_command(label="Reformular Hechos Cliente...", command=self.open_reformular_hechos_dialog)
        # ia_menu.add_command(label="Sugerir Próximo Paso (Caso)...", command=self.open_sugerencia_ia_caso_dialog) # Futuro
        menubar.add_cascade(label="Asistente IA", menu=ia_menu)

# --- INICIO DE LA MODIFICACIÓN: AÑADIR MENÚ ADMINISTRACIÓN ---
        adminmenu = tk.Menu(menubar, tearoff=0)  # 1. Creamos un nuevo objeto Menu, hijo de la barra principal 'menubar'
        #    tearoff=0 evita que el menú se pueda "desprender" de la barra.

        adminmenu.add_command(label="Crear Copia de Seguridad...",  # 2. Añadimos un comando (una opción) a este nuevo menú.
                            command=self.crear_copia_de_seguridad) # 3. 'command' especifica qué método se llamará
                            #    cuando se haga clic en esta opción.
                            #    Crearemos este método 'crear_copia_de_seguridad' más adelante.

        # Aquí, en el futuro, podríamos añadir más opciones a 'adminmenu', como:
        # adminmenu.add_command(label="Restaurar Copia de Seguridad...", command=self.restaurar_copia_de_seguridad) # Ejemplo futuro
        # adminmenu.add_command(label="Mis Datos / Config. Estudio...", command=self.abrir_dialogo_datos_usuario) # Ejemplo futuro
        
        menubar.add_cascade(label="Administración", menu=adminmenu) # 4. Finalmente, añadimos nuestro 'adminmenu' a la 'menubar'
        #    principal, dándole la etiqueta "Administración".

        self.root.config(menu=menubar)
        # --- Fin Barra de Menú ---

        # Variables de estado CRM
        self.selected_client = None
        self.selected_case = None

        # --- Referencia al módulo de base de datos y al controlador de la app ---
        self.db_crm = db
        self.app_controller = self # Para pasar a las pestañas modulares

        # --- Variables para Agenda/Recordatorios/Bandeja ---
        self.fecha_seleccionada_agenda = datetime.date.today().strftime("%Y-%m-%d")
        self.audiencia_seleccionada_id = None
        self.recordatorios_mostrados_hoy = set()
        self.logo_image_tk = None # Podría usarse para un logo en la UI
        self.tray_icon = None
        self.hilo_recordatorios = None
        self.hilo_bandeja = None
        self.stop_event = threading.Event() # Para detener hilos limpiamente
        # --- Fin Variables Agenda ---

        # db.create_tables() # Se llama automáticamente al importar crm_database.py

        # --- INICIALIZACIÓN DEL NUEVO FLAG ---
        self.adminmenu_created_flag = False 
        # --- FIN DE LA INICIALIZACIÓN ---

        # --- Crear Widgets ---
        self.create_widgets()

        # Cargar datos iniciales
        self.load_clients()
        self.cargar_audiencias_fecha_actual()
        self.marcar_dias_audiencias_calendario()

        # --- Iniciar Hilos para Bandeja y Recordatorios ---
        self.hilo_recordatorios = threading.Thread(target=self.verificar_recordatorios_periodicamente, daemon=True)
        self.hilo_recordatorios.start()

        self.hilo_bandeja = threading.Thread(target=self.setup_tray_icon, daemon=True)
        self.hilo_bandeja.start()

        # --- Manejar cierre de ventana para ocultar a bandeja ---
        self.root.protocol("WM_DELETE_WINDOW", self.ocultar_a_bandeja)

    # En main_app.py, dentro de la clase CRMLegalApp
# Asegúrate de tener:
# import requests # Necesitarás instalarlo: pip install requests
# import json     # Estándar de Python

    # ... (otros métodos) ...

    # En main_app.py, dentro de la clase CRMLegalApp

    def open_reformular_hechos_dialog(self):
        # Determinar si hay un caso seleccionado para pre-llenar o asociar
        caso_actual_id = self.selected_case['id'] if self.selected_case else None
        caso_actual_caratula = self.selected_case.get('caratula', "General") if self.selected_case else "General"

        dialog = Toplevel(self.root)
        dialog.title(f"Reformular Hechos con IA (Caso: {caso_actual_caratula[:30]})")
        dialog.transient(self.root); dialog.grab_set()
        dialog.geometry("700x600") 
        dialog.resizable(True, True)

        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1) # Única columna principal para los frames de texto y status
        # main_frame.rowconfigure(0, weight=0) # Etiqueta de entrada (no necesita expandirse)
        main_frame.rowconfigure(1, weight=2) # Para el input_text_frame
        # main_frame.rowconfigure(2, weight=0) # Etiqueta de salida (no necesita expandirse)
        main_frame.rowconfigure(3, weight=3) # Para el output_text_frame
        # main_frame.rowconfigure(4, weight=0) # Status label
        # main_frame.rowconfigure(5, weight=0) # Button frame

        ttk.Label(main_frame, text="Ingrese los hechos del cliente (o texto a reformular):").grid(row=0, column=0, sticky=tk.NW, pady=(0,2))
        
        input_text_frame = ttk.Frame(main_frame)
        input_text_frame.grid(row=1, column=0, sticky='nsew', pady=2)
        input_text_frame.columnconfigure(0, weight=1); input_text_frame.rowconfigure(0, weight=1)
        hechos_entrada_text = tk.Text(input_text_frame, wrap=tk.WORD, height=10)
        hechos_entrada_text.grid(row=0, column=0, sticky='nsew')
        hechos_entrada_scroll = ttk.Scrollbar(input_text_frame, command=hechos_entrada_text.yview)
        hechos_entrada_scroll.grid(row=0, column=1, sticky='ns')
        hechos_entrada_text['yscrollcommand'] = hechos_entrada_scroll.set

        ttk.Label(main_frame, text="Hechos Reformulados por IA:").grid(row=2, column=0, sticky=tk.NW, pady=(5,2))
        
        output_text_frame = ttk.Frame(main_frame)
        output_text_frame.grid(row=3, column=0, sticky='nsew', pady=2)
        output_text_frame.columnconfigure(0, weight=1); output_text_frame.rowconfigure(0, weight=1)
        resultado_ia_text = tk.Text(output_text_frame, wrap=tk.WORD, height=15, state=tk.DISABLED)
        resultado_ia_text.grid(row=0, column=0, sticky='nsew')
        resultado_ia_scroll = ttk.Scrollbar(output_text_frame, command=resultado_ia_text.yview)
        resultado_ia_scroll.grid(row=0, column=1, sticky='ns')
        resultado_ia_text['yscrollcommand'] = resultado_ia_scroll.set

        status_var = tk.StringVar(value="Listo para recibir hechos.")
        status_label = ttk.Label(main_frame, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_label.grid(row=4, column=0, sticky=tk.EW, pady=(5,5)) # Pady para separar de botones
        
        # --- AQUÍ DEBEN ESTAR LAS DEFINICIONES DE LAS FUNCIONES ---
        def actualizar_ui_con_respuesta(resultado_json): # Movida antes de su uso
            resultado_ia_text.config(state=tk.NORMAL)
            resultado_ia_text.delete("1.0", tk.END)
            if resultado_json and "hechos_reformulados" in resultado_json:
                resultado_ia_text.insert("1.0", resultado_json["hechos_reformulados"])
                status_var.set("Respuesta de IA recibida.")
                copiar_btn.config(state=tk.NORMAL if resultado_ia_text.get("1.0", tk.END).strip() else tk.DISABLED)
                guardar_docx_btn.config(state=tk.NORMAL if resultado_ia_text.get("1.0", tk.END).strip() else tk.DISABLED)
            elif resultado_json and "error" in resultado_json:
                error_msg_ia = f"Error devuelto por el Asistente IA: {resultado_json['error']}"
                resultado_ia_text.insert("1.0", error_msg_ia)
                status_var.set("Error en la IA.")
                messagebox.showerror("Error de IA", error_msg_ia, parent=dialog)
                copiar_btn.config(state=tk.DISABLED)
                guardar_docx_btn.config(state=tk.DISABLED)
            else:
                resultado_ia_text.insert("1.0", "Respuesta inesperada o vacía del servidor.")
                status_var.set("Error: Respuesta no reconocida.")
                copiar_btn.config(state=tk.DISABLED)
                guardar_docx_btn.config(state=tk.DISABLED)
            resultado_ia_text.config(state=tk.DISABLED)

        def actualizar_ui_con_error(mensaje_error, es_error_conexion=False): # Movida antes de su uso
            resultado_ia_text.config(state=tk.NORMAL)
            resultado_ia_text.delete("1.0", tk.END)
            resultado_ia_text.insert("1.0", f"Error en la comunicación:\n{mensaje_error}")
            resultado_ia_text.config(state=tk.DISABLED)
            status_var.set("Error de comunicación.")
            if not es_error_conexion: 
                messagebox.showerror("Error de Comunicación con IA", mensaje_error, parent=dialog)
            copiar_btn.config(state=tk.DISABLED)
            guardar_docx_btn.config(state=tk.DISABLED)

        def solicitar_reformulacion():
            texto_hechos = hechos_entrada_text.get("1.0", tk.END).strip()
            if not texto_hechos:
                messagebox.showwarning("Entrada Vacía", "Por favor, ingrese el texto de los hechos a reformular.", parent=dialog)
                return

            status_var.set("Procesando con Asistente IA local, por favor espere...")
            resultado_ia_text.config(state=tk.NORMAL); resultado_ia_text.delete("1.0", tk.END); resultado_ia_text.config(state=tk.DISABLED)
            dialog.update_idletasks() 

            def do_request_thread():
                try:
                    mcp_url = "http://localhost:5000/api/reformular_hechos"
                    payload = {"texto_hechos": texto_hechos}
                    response = requests.post(mcp_url, json=payload, timeout=90)
                    response.raise_for_status()
                    resultado_json = response.json()
                    self.root.after(0, lambda: actualizar_ui_con_respuesta(resultado_json))
                except requests.exceptions.ConnectionError:
                    error_msg = (f"Error de Conexión: No se pudo conectar con el servidor del Asistente IA local en {mcp_url}.\n\n"
                                 f"Verifique que:\n1. 'mcp_server.py' esté ejecutándose.\n"
                                 f"2. Ollama/LM Studio esté activo y sirviendo el modelo correcto.\n"
                                 f"3. No haya un firewall bloqueando la conexión a localhost en ese puerto.")
                    self.root.after(0, lambda: actualizar_ui_con_error(error_msg, es_error_conexion=True))
                except requests.exceptions.Timeout:
                    error_msg = (f"Timeout: La solicitud al Asistente IA local en {mcp_url} tardó demasiado en responder (90s).\n\n"
                                 f"Verifique el modelo LLM y la carga de su sistema.")
                    self.root.after(0, lambda: actualizar_ui_con_error(error_msg))
                except requests.exceptions.HTTPError as http_err:
                    error_msg = f"Error HTTP {http_err.response.status_code} del servidor MCP: {http_err.response.text}"
                    self.root.after(0, lambda: actualizar_ui_con_error(error_msg))
                except requests.exceptions.JSONDecodeError:
                    error_msg = "Error: El servidor MCP no devolvió una respuesta JSON válida."
                    self.root.after(0, lambda: actualizar_ui_con_error(error_msg))
                except Exception as e_thread: 
                    error_msg = f"Error inesperado durante la solicitud a la IA: {type(e_thread).__name__}: {e_thread}"
                    import traceback; traceback.print_exc()
                    self.root.after(0, lambda: actualizar_ui_con_error(error_msg))
            
            threading.Thread(target=do_request_thread, daemon=True).start()

        def copiar_resultado_ia():
            texto_a_copiar = resultado_ia_text.get("1.0", tk.END).strip()
            if texto_a_copiar:
                self.root.clipboard_clear(); self.root.clipboard_append(texto_a_copiar)
                status_var.set("¡Resultado copiado al portapapeles!")
                # messagebox.showinfo("Copiado", "El resultado ha sido copiado.", parent=dialog) # Quizás mucho
            else:
                messagebox.showwarning("Nada que Copiar", "No hay resultado para copiar.", parent=dialog)

        def guardar_resultado_como_docx():
            texto_a_guardar = resultado_ia_text.get("1.0", tk.END).strip()
            if not texto_a_guardar:
                messagebox.showwarning("Nada que Guardar", "No hay resultado para guardar.", parent=dialog)
                return
            caso_actual_caratula_saneada = "Hechos_IA"
            if self.selected_case and self.selected_case.get('caratula'):
                nombre_base = re.sub(r'[^\w\s-]', '', self.selected_case.get('caratula', 'Caso'))
                nombre_base = re.sub(r'\s+', '_', nombre_base).strip('_')
                caso_actual_caratula_saneada = f"Hechos_IA_{nombre_base[:30]}"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            suggested_filename = f"{caso_actual_caratula_saneada}_{timestamp}.docx"
            filepath = filedialog.asksaveasfilename(title="Guardar Hechos como DOCX", initialfile=suggested_filename, defaultextension=".docx", filetypes=[("Documento Word", "*.docx")], parent=dialog)
            if filepath:
                try:
                    from docx import Document
                    from docx.enum.text import WD_ALIGN_PARAGRAPH
                    doc = Document(); doc.add_paragraph(texto_a_guardar)
                    doc.save(filepath)
                    messagebox.showinfo("Documento Guardado", f"Documento guardado en:\n{filepath}", parent=dialog)
                    status_var.set(f"Guardado como {os.path.basename(filepath)}")
                    if messagebox.askyesno("Abrir Documento", "¿Desea abrir el documento ahora?", parent=dialog):
                        if sys.platform == "win32": os.startfile(filepath)
                        elif sys.platform == "darwin": subprocess.call(["open", filepath])
                        else: subprocess.call(["xdg-open", filepath])
                except ImportError:
                    messagebox.showerror("Error Librería", "Falta 'python-docx'. Instálala con: pip install python-docx", parent=dialog)
                except Exception as e_docx:
                    messagebox.showerror("Error al Guardar DOCX", f"No se pudo guardar:\n{e_docx}", parent=dialog)
        # --- FIN DEFINICIONES DE FUNCIONES ---

        button_frame_dialog = ttk.Frame(main_frame)
        button_frame_dialog.grid(row=5, column=0, pady=10, sticky=tk.EW) 

        button_frame_dialog.columnconfigure(0, weight=1)
        button_frame_dialog.columnconfigure(1, weight=1)
        button_frame_dialog.columnconfigure(2, weight=1)
        button_frame_dialog.columnconfigure(3, weight=1)
        
        reformular_btn = ttk.Button(button_frame_dialog, text="Reformular con IA", command=solicitar_reformulacion)
        reformular_btn.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)
        
        copiar_btn = ttk.Button(button_frame_dialog, text="Copiar Resultado", command=copiar_resultado_ia, state=tk.DISABLED)
        copiar_btn.grid(row=0, column=1, padx=2, pady=2, sticky=tk.EW)
        
        guardar_docx_btn = ttk.Button(button_frame_dialog, text="Guardar como DOCX", command=guardar_resultado_como_docx, state=tk.DISABLED)
        guardar_docx_btn.grid(row=0, column=2, padx=2, pady=2, sticky=tk.EW)
        
        cerrar_btn = ttk.Button(button_frame_dialog, text="Cerrar", command=dialog.destroy)
        cerrar_btn.grid(row=0, column=3, padx=2, pady=2, sticky=tk.EW)

        hechos_entrada_text.focus_set()
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    # Necesitarás añadir un método para guardar la interacción si quieres ese botón
    def _guardar_interaccion_ia_como_actividad(self, caso_id, tipo_consulta, consulta, respuesta_ia):
        if not caso_id: return
        descripcion_completa = f"CONSULTA A IA ({tipo_consulta}):\n{consulta}\n\nRESPUESTA IA:\n{respuesta_ia}"
        # Llamar a tu función _save_new_actividad o db.add_actividad_caso
        self._save_new_actividad(caso_id, f"Asistencia IA - {tipo_consulta}", descripcion_completa)
        print(f"Interacción con IA guardada como actividad en caso ID {caso_id}")

    def crear_copia_de_seguridad(self):
        print("[Backup] Iniciando proceso de creación de copia de seguridad...") # Mensaje para tu consola
        try:
            # 1. Generar un nombre de archivo sugerido para la copia de seguridad.
            #    Incluye la fecha y hora para que cada copia sea única y fácil de identificar.
            timestamp_actual = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            nombre_base_db = os.path.basename(db.DATABASE_FILE) # Obtiene solo el nombre del archivo, ej. "crm_legal.db"
            nombre_sugerido = f"{os.path.splitext(nombre_base_db)[0]}_backup_{timestamp_actual}.db"
            # Esto creará algo como "crm_legal_backup_2025-05-17_10-30-00.db"

            # 2. Abrir el diálogo estándar de "Guardar como".
            #    Esto permite al usuario elegir dónde quiere guardar la copia y con qué nombre.
            ruta_destino_backup = filedialog.asksaveasfilename(
                title="Guardar Copia de Seguridad como...",
                initialdir=os.path.expanduser("~"), # Sugerir el directorio "home" del usuario inicialmente
                initialfile=nombre_sugerido, # El nombre que sugerimos arriba
                defaultextension=".db", # Extensión por defecto si el usuario no la escribe
                filetypes=[("Archivos de Base de Datos SQLite", "*.db"), 
                            ("Todos los archivos", "*.*")], # Opciones para el tipo de archivo
                parent=self.root # Para que el diálogo aparezca centrado sobre la ventana principal
            )

            # 3. Verificar si el usuario seleccionó una ruta (no presionó "Cancelar").
            if ruta_destino_backup: # Si la cadena no está vacía, el usuario eligió un archivo.
                ruta_origen_db = db.DATABASE_FILE # La ruta a tu base de datos actual.

                # 3a. (Verificación opcional pero buena) Asegurarse de que la BD original exista.
                if not os.path.exists(ruta_origen_db):
                    messagebox.showerror("Error de Backup", 
                                        f"El archivo de base de datos original no se encontró en:\n{ruta_origen_db}\n\nNo se puede crear la copia de seguridad.",
                                        parent=self.root)
                    print(f"[Backup] Error: No se encontró la base de datos original en '{ruta_origen_db}'")
                    return # Salir del método si la BD original no existe.

                # 4. Realizar la copia del archivo.
                shutil.copy2(ruta_origen_db, ruta_destino_backup)
                # shutil.copy2 intenta copiar también los metadatos del archivo (como fecha de modificación).

                # 5. Informar al usuario que la copia fue exitosa.
                messagebox.showinfo("Copia de Seguridad Exitosa", 
                                    f"La copia de seguridad se guardó correctamente en:\n{ruta_destino_backup}", 
                                    parent=self.root)
                print(f"[Backup] Copia de seguridad creada exitosamente en: {ruta_destino_backup}")
            else:
                # El usuario presionó "Cancelar" en el diálogo de guardar.
                print("[Backup] Creación de copia de seguridad cancelada por el usuario.")
        
        except PermissionError: # Si no hay permisos para escribir en la ubicación elegida.
            messagebox.showerror("Error de Permisos", 
                                "No se pudo escribir la copia de seguridad en la ubicación seleccionada.\nPor favor, verifique los permisos de la carpeta.", 
                                parent=self.root)
            print(f"[Backup] Error de permisos al intentar escribir en '{ruta_destino_backup if 'ruta_destino_backup' in locals() and ruta_destino_backup else 'ubicación seleccionada'}'")

        except Exception as e: # Capturar cualquier otro error inesperado.
            messagebox.showerror("Error Inesperado en Backup", 
                                f"Ocurrió un error inesperado al crear la copia de seguridad:\n{type(e).__name__}: {e}", 
                                parent=self.root)
            print(f"[Backup] Error inesperado durante la creación de la copia de seguridad: {e}")
            import traceback
            traceback.print_exc() # Imprime el traceback completo en la consola para depuración.


    def cerrar_aplicacion_directamente(self):
        if messagebox.askokcancel("Confirmar Salida", "¿Estás seguro de que quieres cerrar completamente la aplicación?", parent=self.root):
            self.cerrar_aplicacion()

    def cerrar_aplicacion(self):
        print("Iniciando secuencia de cierre de la aplicación...")
        self.stop_event.set() # Señal para que los hilos terminen
        if self.tray_icon and hasattr(self.tray_icon, 'stop') and self.tray_icon.visible:
            print("Deteniendo icono de bandeja explícitamente...")
            try:
                self.tray_icon.stop()
            except Exception as e:
                print(f"Error al intentar detener icono de bandeja (puede ser normal si ya se detuvo): {e}")
        else:
            print("Icono de bandeja no visible, no iniciado, o ya detenido.")
        # Esperar un poco para que los hilos puedan terminar si es necesario
        # self.root.after(100, ...) # A veces ayuda, pero destroy() debería ser suficiente
        self.root.destroy() # Cierra la ventana principal y termina el mainloop
        print("Solicitud de cierre completada.")


    def create_widgets(self):
        crm_main_frame = ttk.Frame(self.root, padding="10")
        crm_main_frame.pack(fill=tk.BOTH, expand=True)
        
                # Configuración de columnas principales del CRM
        crm_main_frame.rowconfigure(0, weight=1)
        crm_main_frame.columnconfigure(0, weight=0)  # Clientes (ancho fijo relativo)
        crm_main_frame.columnconfigure(1, weight=0)  # Casos/Calendario (ancho fijo relativo)
        crm_main_frame.columnconfigure(2, weight=2)  # Notebook y Audiencias (más espacio)

        # --- Columna 1: Clientes ---
        col1_frame = ttk.Frame(crm_main_frame)
        col1_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5), pady=5)
        col1_frame.rowconfigure(0, weight=1) # Lista clientes
        col1_frame.rowconfigure(1, weight=0) # Botones clientes
        col1_frame.rowconfigure(2, weight=0) # Detalles cliente (altura fija)
        col1_frame.columnconfigure(0, weight=1)

        client_list_frame = ttk.LabelFrame(col1_frame, text="Clientes", padding="5")
        client_list_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        client_list_frame.columnconfigure(0, weight=1); client_list_frame.rowconfigure(0, weight=1); client_list_frame.rowconfigure(1, weight=0) # Para scrollbar X
        client_cols = ('ID', 'Nombre')
        self.client_tree = ttk.Treeview(client_list_frame, columns=client_cols, show='headings', selectmode='browse')
        self.client_tree.heading('ID', text='ID'); self.client_tree.heading('Nombre', text='Nombre')
        self.client_tree.column('ID', width=40, stretch=tk.NO); self.client_tree.column('Nombre', width=150, stretch=tk.NO)
        client_scrollbar_y = ttk.Scrollbar(client_list_frame, orient=tk.VERTICAL, command=self.client_tree.yview); self.client_tree.configure(yscrollcommand=client_scrollbar_y.set)
        client_scrollbar_x = ttk.Scrollbar(client_list_frame, orient=tk.HORIZONTAL, command=self.client_tree.xview); self.client_tree.configure(xscrollcommand=client_scrollbar_x.set)
        self.client_tree.grid(row=0, column=0, sticky='nsew'); client_scrollbar_y.grid(row=0, column=1, sticky='ns'); client_scrollbar_x.grid(row=1, column=0, sticky='ew')
        self.client_tree.bind('<<TreeviewSelect>>', self.on_client_select)

        client_buttons_frame = ttk.Frame(col1_frame); client_buttons_frame.grid(row=1, column=0, sticky='ew', pady=5)
        self.add_client_btn = ttk.Button(client_buttons_frame, text="ALTA", command=lambda: self.open_client_dialog()); self.add_client_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.edit_client_btn = ttk.Button(client_buttons_frame, text="MODIFICAR", command=lambda: self.open_client_dialog(self.selected_client['id'] if self.selected_client else None), state=tk.DISABLED); self.edit_client_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.delete_client_btn = ttk.Button(client_buttons_frame, text="BORRAR", command=self.delete_client, state=tk.DISABLED); self.delete_client_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        client_details_frame = ttk.LabelFrame(col1_frame, text="Detalles Cliente", padding="10"); client_details_frame.grid(row=2, column=0, sticky='ew', pady=(5, 0)); client_details_frame.columnconfigure(1, weight=1)
        ttk.Label(client_details_frame, text="Nombre:").grid(row=0, column=0, sticky=tk.W, pady=1, padx=5); self.client_detail_name_lbl = ttk.Label(client_details_frame, text="", wraplength=200); self.client_detail_name_lbl.grid(row=0, column=1, sticky=tk.EW, pady=1, padx=5)
        ttk.Label(client_details_frame, text="Dirección:").grid(row=1, column=0, sticky=tk.W, pady=1, padx=5); self.client_detail_address_lbl = ttk.Label(client_details_frame, text="", wraplength=200); self.client_detail_address_lbl.grid(row=1, column=1, sticky=tk.EW, pady=1, padx=5)
        ttk.Label(client_details_frame, text="Email:").grid(row=2, column=0, sticky=tk.W, pady=1, padx=5); self.client_detail_email_lbl = ttk.Label(client_details_frame, text="", wraplength=200); self.client_detail_email_lbl.grid(row=2, column=1, sticky=tk.EW, pady=1, padx=5)
        ttk.Label(client_details_frame, text="WhatsApp:").grid(row=3, column=0, sticky=tk.W, pady=1, padx=5); self.client_detail_whatsapp_lbl = ttk.Label(client_details_frame, text="", wraplength=200); self.client_detail_whatsapp_lbl.grid(row=3, column=1, sticky=tk.EW, pady=1, padx=5)
        ttk.Label(client_details_frame, text="Etiquetas:").grid(row=4, column=0, sticky=tk.W, pady=1, padx=5)
        self.client_detail_tags_lbl = ttk.Label(client_details_frame, text="", wraplength=200)
        self.client_detail_tags_lbl.grid(row=4, column=1, sticky=tk.EW, pady=1, padx=5)

        # --- Columna 2: Casos / Calendario ---
        col2_frame = ttk.Frame(crm_main_frame); col2_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        col2_frame.rowconfigure(0, weight=1) # Lista casos
        col2_frame.rowconfigure(1, weight=0) # Botones casos
        col2_frame.rowconfigure(2, weight=0) # Calendario (podría tener más peso si se desea más grande)
        col2_frame.rowconfigure(3, weight=0) # Botón agregar audiencia
        col2_frame.columnconfigure(0, weight=1)

        case_list_frame = ttk.LabelFrame(col2_frame, text="Casos Cliente", padding="5"); case_list_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        case_list_frame.columnconfigure(0, weight=1); case_list_frame.rowconfigure(0, weight=1); case_list_frame.rowconfigure(1, weight=0) # Para scrollbar X
        case_cols = ('ID', 'Número/Año', 'Carátula')
        self.case_tree = ttk.Treeview(case_list_frame, columns=case_cols, show='headings', selectmode='browse')
        self.case_tree.heading('ID', text='ID'); self.case_tree.heading('Número/Año', text='Nro/Año'); self.case_tree.heading('Carátula', text='Carátula')
        self.case_tree.column('ID', width=40, stretch=tk.NO); self.case_tree.column('Número/Año', width=80, stretch=tk.NO); self.case_tree.column('Carátula', width=150, stretch=tk.NO)
        case_scrollbar_Y = ttk.Scrollbar(case_list_frame, orient=tk.VERTICAL, command=self.case_tree.yview); self.case_tree.configure(yscrollcommand=case_scrollbar_Y.set)
        case_scrollbar_x = ttk.Scrollbar(case_list_frame, orient=tk.HORIZONTAL, command=self.case_tree.xview); self.case_tree.configure(xscrollcommand=case_scrollbar_x.set)
        self.case_tree.grid(row=0, column=0, sticky='nsew'); case_scrollbar_Y.grid(row=0, column=1, sticky='ns'); case_scrollbar_x.grid(row=1, column=0, sticky='ew')
        self.case_tree.bind('<<TreeviewSelect>>', self.on_case_select)

        case_buttons_frame = ttk.Frame(col2_frame); case_buttons_frame.grid(row=1, column=0, sticky='ew', pady=5)
        self.add_case_btn = ttk.Button(case_buttons_frame, text="Alta", command=lambda: self.open_case_dialog(), state=tk.DISABLED); self.add_case_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.edit_case_btn = ttk.Button(case_buttons_frame, text="Modificar", command=lambda: self.open_case_dialog(self.selected_case['id'] if self.selected_case else None), state=tk.DISABLED); self.edit_case_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.delete_case_btn = ttk.Button(case_buttons_frame, text="Baja", command=self.delete_case, state=tk.DISABLED); self.delete_case_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        cal_frame = ttk.LabelFrame(col2_frame, text="Calendario", padding=5); cal_frame.grid(row=2, column=0, sticky='nsew', pady=5)
        cal_frame.columnconfigure(0, weight=1); cal_frame.rowconfigure(0, weight=1) # Calendario expandible dentro de su frame
        self.agenda_cal = Calendar(cal_frame, selectmode='day', date_pattern='y-mm-dd', tooltipforeground='black', tooltipbackground='#FFFFE0', locale='es_ES')
        self.agenda_cal.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        self.agenda_cal.bind("<<CalendarSelected>>", self.actualizar_lista_audiencias)
        self.agenda_cal.tag_config('audiencia_marcador', background='lightblue', foreground='black')

        add_aud_frame = ttk.Frame(col2_frame); add_aud_frame.grid(row=3, column=0, sticky='ew', pady=(5, 0))
        self.add_audiencia_btn = ttk.Button(add_aud_frame, text="Agregar Audiencia", command=lambda: self.abrir_dialogo_audiencia(), state=tk.NORMAL) # Estado inicial gestionado por update_add_audiencia_button_state
        self.add_audiencia_btn.pack(fill=tk.X, padx=10, pady=5)
        self.update_add_audiencia_button_state()

        # --- Columna 3: Notebook y Audiencias ---
        col3_frame = ttk.Frame(crm_main_frame); col3_frame.grid(row=0, column=2, sticky='nsew', padx=(5, 0), pady=5)
        col3_frame.rowconfigure(0, weight=2) # Notebook con más peso
        col3_frame.rowconfigure(1, weight=1) # Área de audiencias con peso
        col3_frame.columnconfigure(0, weight=1)

        right_notebook_frame = ttk.Frame(col3_frame); right_notebook_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        right_notebook_frame.rowconfigure(0, weight=1); right_notebook_frame.columnconfigure(0, weight=1)
        self.main_notebook = ttk.Notebook(right_notebook_frame); self.main_notebook.grid(row=0, column=0, sticky='nsew')

        # Pestaña Detalles del Caso
        self.case_details_tab = ttk.Frame(self.main_notebook, padding="10"); self.main_notebook.add(self.case_details_tab, text='Detalles del Caso')

        self.case_details_tab.columnconfigure(0, weight=0) # Etiqueta de campo (ancho fijo)
        self.case_details_tab.columnconfigure(1, weight=1) # Valor del campo (expandible)
        self.case_details_tab.columnconfigure(2, weight=0) # Etiqueta de campo (ancho fijo)
        self.case_details_tab.columnconfigure(3, weight=1) # Valor del campo (expandible)
        current_row = 0 # Para llevar la cuenta de las filas

        # Carátula (ocupa ambas "columnas de valor" para más espacio si es necesario)
        ttk.Label(self.case_details_tab, text="Carátula:").grid(row=current_row, column=0, sticky=tk.W, pady=2, padx=2)
        self.caratula_lbl = ttk.Label(self.case_details_tab, text="") # Prueba sin wraplength aquí
        self.caratula_lbl.grid(row=current_row, column=1, columnspan=3, sticky=tk.EW, pady=2, padx=2) # columnspan=3 para usar cols 1, 2, 3
        current_row += 1

        ttk.Label(self.case_details_tab, text="Expediente:").grid(row=current_row, column=0, sticky=tk.W, pady=2, padx=2)
        self.expediente_lbl = ttk.Label(self.case_details_tab, text="")
        self.expediente_lbl.grid(row=current_row, column=1, columnspan=3, sticky=tk.EW, pady=2, padx=2) # columnspan=3
        current_row += 1

        ttk.Label(self.case_details_tab, text="Juzgado:").grid(row=current_row, column=0, sticky=tk.W, pady=2, padx=2)
        self.juzgado_lbl = ttk.Label(self.case_details_tab, text="", wraplength=300) # wraplength aquí puede ser útil
        self.juzgado_lbl.grid(row=current_row, column=1, columnspan=3, sticky=tk.EW, pady=2, padx=2) # columnspan=3
        current_row += 1

        ttk.Label(self.case_details_tab, text="Jurisdicción:").grid(row=current_row, column=0, sticky=tk.W, pady=2, padx=2)
        self.jurisdiccion_lbl = ttk.Label(self.case_details_tab, text="", wraplength=300) # wraplength aquí
        self.jurisdiccion_lbl.grid(row=current_row, column=1, columnspan=3, sticky=tk.EW, pady=2, padx=2) # columnspan=3
        current_row += 1

        # Etapa Procesal y Etiquetas Caso en la misma fila
        ttk.Label(self.case_details_tab, text="Etapa Procesal:").grid(row=current_row, column=0, sticky=tk.W, pady=2, padx=2)
        self.etapa_lbl = ttk.Label(self.case_details_tab, text="")
        self.etapa_lbl.grid(row=current_row, column=1, sticky=tk.EW, pady=2, padx=2)

        ttk.Label(self.case_details_tab, text="Etiquetas Caso:").grid(row=current_row, column=2, sticky=tk.W, pady=2, padx=10) # padx=10 para separar de etapa
        self.case_detail_tags_lbl = ttk.Label(self.case_details_tab, text="")
        self.case_detail_tags_lbl.grid(row=current_row, column=3, sticky=tk.EW, pady=2, padx=2)
        current_row += 1
        
        # Notas (ahora en la fila que corresponda, ocupando las columnas de valor)
        ttk.Label(self.case_details_tab, text="Notas:").grid(row=current_row, column=0, sticky=tk.NW, pady=2, padx=2)
        self.notas_text = tk.Text(self.case_details_tab, height=4, wrap=tk.WORD, state=tk.DISABLED)
        # Que las notas ocupen el espacio de las columnas 1 y 3 (las de valores)
        self.notas_text.grid(row=current_row, column=1, columnspan=3, sticky=tk.NSEW, pady=2, padx=2) 
        
        # Configurar la fila de notas para que se expanda verticalmente
        self.case_details_tab.rowconfigure(current_row, weight=1) 
        
        # Scrollbar para las notas (asociado a la misma celda que notas_text o una adyacente si fuera necesario)
        # Para que el scrollbar quede bien al lado de un widget con columnspan, a veces es más fácil meter
        # el Text y el Scrollbar en un Frame propio, y ese Frame en la celda con columnspan.
        # Pero probemos así primero, puede que necesitemos ajustar la columna del scrollbar.
        # notas_scrollbar = ttk.Scrollbar(self.case_details_tab, orient=tk.VERTICAL, command=self.notas_text.yview)
        # notas_scrollbar.grid(row=current_row, column=4, sticky=tk.NS, pady=2) # Necesitaría una columna 4 o ajustar
        # self.notas_text['yscrollcommand'] = notas_scrollbar.set
        # Por simplicidad, si el scrollbar no se ve bien con columnspan, podemos omitirlo o usar el frame wrapper.
        # Vamos a intentar añadirlo en una columna adicional solo para él
        self.case_details_tab.columnconfigure(4, weight=0) # Columna para el scrollbar de notas
        notas_scrollbar = ttk.Scrollbar(self.case_details_tab, orient=tk.VERTICAL, command=self.notas_text.yview)
        notas_scrollbar.grid(row=current_row, column=4, sticky=tk.NS, pady=2, padx=(0,2))
        self.notas_text['yscrollcommand'] = notas_scrollbar.set
        current_row += 1


        # Alarma Inactividad (debajo de notas, ocupando todas las columnas)
        inactivity_frame = ttk.LabelFrame(self.case_details_tab, text="Alarma Inactividad", padding="5")
        inactivity_frame.grid(row=current_row, column=0, columnspan=5, sticky=tk.EW, pady=5, padx=2) # columnspan=5 para todas las columnas
        inactivity_frame.columnconfigure(1, weight=1) # Para que el label del valor se expanda
        ttk.Label(inactivity_frame, text="Habilitada:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=1)
        self.inactivity_enabled_lbl = ttk.Label(inactivity_frame, text="")
        self.inactivity_enabled_lbl.grid(row=0, column=1, sticky=tk.W, pady=1)
        ttk.Label(inactivity_frame, text="Umbral Días:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=1)
        self.inactivity_threshold_lbl = ttk.Label(inactivity_frame, text="")
        self.inactivity_threshold_lbl.grid(row=1, column=1, sticky=tk.W, pady=1)
        current_row += 1

        # Configurar la última fila para que no se expanda innecesariamente si no hay más contenido
        self.case_details_tab.rowconfigure(current_row, weight=0)

        # Pestaña Documentación
        self.documents_tab = ttk.Frame(self.main_notebook, padding="10"); self.main_notebook.add(self.documents_tab, text='Documentación')
        self.documents_tab.columnconfigure(0, weight=1); self.documents_tab.rowconfigure(1, weight=0); self.documents_tab.rowconfigure(3, weight=1) # Lista de archivos se expande
        ttk.Label(self.documents_tab, text="Carpeta Documentos:").grid(row=0, column=0, pady=(0, 5), sticky=tk.W)
        folder_frame = ttk.Frame(self.documents_tab); folder_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 5)); folder_frame.columnconfigure(0, weight=1) # Label de ruta se expande
        self.folder_path_lbl = ttk.Label(folder_frame, text="Selecciona un caso", relief=tk.SUNKEN, anchor=tk.W); self.folder_path_lbl.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        self.select_folder_btn = ttk.Button(folder_frame, text="...", command=self.select_case_folder, state=tk.DISABLED, width=3); self.select_folder_btn.grid(row=0, column=1, sticky=tk.E, padx=(0,5))
        self.open_folder_btn = ttk.Button(folder_frame, text="Abrir Carpeta", command=self.open_case_folder, state=tk.DISABLED, width=12); self.open_folder_btn.grid(row=0, column=2, sticky=tk.E)
        ttk.Label(self.documents_tab, text="Archivos y Carpetas:").grid(row=2, column=0, pady=(5, 5), sticky=tk.NW)
        documents_tree_frame = ttk.Frame(self.documents_tab); documents_tree_frame.grid(row=3, column=0, sticky='nsew'); documents_tree_frame.columnconfigure(0, weight=1); documents_tree_frame.rowconfigure(0, weight=1)
        self.document_tree = ttk.Treeview(documents_tree_frame, columns=('Nombre', 'Tamaño', 'Fecha Mod.'), show='headings'); self.document_tree.heading('Nombre', text='Nombre'); self.document_tree.heading('Tamaño', text='Tamaño'); self.document_tree.heading('Fecha Mod.', text='Modificado'); self.document_tree.column('Nombre', width=250, stretch=True); self.document_tree.column('Tamaño', width=100, stretch=tk.NO, anchor=tk.E); self.document_tree.column('Fecha Mod.', width=140, stretch=tk.NO)
        document_scrollbar = ttk.Scrollbar(documents_tree_frame, orient=tk.VERTICAL, command=self.document_tree.yview); self.document_tree.configure(yscrollcommand=document_scrollbar.set); document_scrollbar.pack(side=tk.RIGHT, fill=tk.Y); self.document_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.document_tree.bind("<Double-1>", self.on_document_double_click)

        # --- Pestaña de Tareas (NUEVA) ---
        self.tareas_tab_frame = TareasTab(self.main_notebook, self) # 'self' es CRMLegalApp (app_controller)
        self.main_notebook.add(self.tareas_tab_frame, text="Tareas/Plazos")
        # --- Fin Pestaña de Tareas ---

        # --- Pestaña de Partes Intervinientes (MODULARIZADA) ---
        self.partes_tab_frame = PartesTab(self.main_notebook, self) # 'self' es CRMLegalApp (app_controller)
        self.main_notebook.add(self.partes_tab_frame, text="Partes")
        # --- Fin Pestaña de Partes ---

        # --- Pestaña de Seguimiento (MODULARIZADA) ---
        self.seguimiento_tab_frame = SeguimientoTab(self.main_notebook, self) # 'self' es CRMLegalApp (app_controller)
        self.main_notebook.add(self.seguimiento_tab_frame, text="Seguimiento")

        # --- Área de audiencias (lista y detalles) ---
        audiencia_area_frame = ttk.Frame(col3_frame) # Parent es col3_frame
        audiencia_area_frame.grid(row=1, column=0, sticky='nsew', pady=5)
        audiencia_area_frame.columnconfigure(0, weight=1) # Lista de audiencias y acciones
        audiencia_area_frame.columnconfigure(1, weight=3) # Detalles completos de audiencia
        audiencia_area_frame.rowconfigure(0, weight=1) # Permitir que la lista de audiencias crezca

        audiencias_list_with_actions_frame = ttk.Frame(audiencia_area_frame)
        audiencias_list_with_actions_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        audiencias_list_with_actions_frame.rowconfigure(0, weight=1); audiencias_list_with_actions_frame.rowconfigure(1, weight=0) # Lista expandible, botones fijos
        audiencias_list_with_actions_frame.columnconfigure(0, weight=1)

        agenda_list_frame = ttk.LabelFrame(audiencias_list_with_actions_frame, text="Audiencias del Día", padding="5")
        agenda_list_frame.grid(row=0, column=0, sticky='nsew', pady=(0,5), padx=(0,5))
        agenda_list_frame.columnconfigure(0, weight=1); agenda_list_frame.rowconfigure(0, weight=1)

        agenda_cols = ("ID", "Hora", "Detalle", "Caso Asociado", "Link")
        self.audiencia_tree = ttk.Treeview(agenda_list_frame, columns=agenda_cols, show='headings', selectmode="browse")
        self.audiencia_tree.heading("ID", text="ID"); self.audiencia_tree.heading("Hora", text="Hora"); self.audiencia_tree.heading("Detalle", text="Detalle"); self.audiencia_tree.heading("Caso Asociado", text="Caso"); self.audiencia_tree.heading("Link", text="Link")
        self.audiencia_tree.column("ID", width=30, stretch=tk.NO, anchor=tk.CENTER); self.audiencia_tree.column("Hora", width=50, stretch=tk.NO, anchor=tk.CENTER); self.audiencia_tree.column("Detalle", width=150, stretch=True); self.audiencia_tree.column("Caso Asociado", width=120, stretch=True); self.audiencia_tree.column("Link", width=100, stretch=True)

        agenda_scroll_y = ttk.Scrollbar(agenda_list_frame, orient=tk.VERTICAL, command=self.audiencia_tree.yview); self.audiencia_tree.configure(yscrollcommand=agenda_scroll_y.set)
        agenda_scroll_y.grid(row=0, column=1, sticky='ns'); self.audiencia_tree.grid(row=0, column=0, sticky='nsew')
        self.audiencia_tree.bind('<<TreeviewSelect>>', self.on_audiencia_tree_select)
        self.audiencia_tree.bind("<Double-1>", self.abrir_link_audiencia_seleccionada)

        audiencia_actions_frame = ttk.Frame(audiencias_list_with_actions_frame); audiencia_actions_frame.grid(row=1, column=0, sticky='ew', padx=(0,5), pady=5)
        self.edit_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Editar", command=self.editar_audiencia_seleccionada, state=tk.DISABLED); self.edit_audiencia_btn.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        self.delete_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Eliminar", command=self.eliminar_audiencia_seleccionada, state=tk.DISABLED); self.delete_audiencia_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.share_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Compartir", command=self.mostrar_menu_compartir_audiencia, state=tk.DISABLED); self.share_audiencia_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.open_link_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Abrir Link", command=self.abrir_link_audiencia_seleccionada, state=tk.DISABLED); self.open_link_audiencia_btn.pack(side=tk.LEFT, padx=3, fill=tk.X, expand=True)

        audiencia_details_frame = ttk.LabelFrame(audiencia_area_frame, text="Detalles Completos Audiencia", padding="5")
        audiencia_details_frame.grid(row=0, column=1, rowspan=2, sticky='nsew', pady=(0,0)) # rowspan=2 para que ocupe espacio vertical de lista y botones
        audiencia_details_frame.columnconfigure(0, weight=1); audiencia_details_frame.rowconfigure(0, weight=1) # Text se expande
        self.audiencia_details_text = tk.Text(audiencia_details_frame, height=5, wrap=tk.WORD, state=tk.DISABLED, background=self.root.cget('bg'))
        audiencia_details_scroll = ttk.Scrollbar(audiencia_details_frame, orient=tk.VERTICAL, command=self.audiencia_details_text.yview); self.audiencia_details_text.configure(yscrollcommand=audiencia_details_scroll.set)
        audiencia_details_scroll.grid(row=0, column=1, sticky='ns'); self.audiencia_details_text.grid(row=0, column=0, sticky='nsew')


        # --- Estado Inicial de Pestañas y Botones ---
        self.main_notebook.tab(self.case_details_tab, state='disabled')
        self.main_notebook.tab(self.documents_tab, state='disabled')
        self.main_notebook.tab(self.tareas_tab_frame, state='disabled') # NUEVA PESTAÑA TAREAS
        self.main_notebook.tab(self.partes_tab_frame, state='disabled') # Pestaña de Partes
        self.main_notebook.tab(self.seguimiento_tab_frame, state='disabled')
        
        # Establecer estado inicial de botones dentro de las pestañas modulares
        if hasattr(self, 'tareas_tab_frame'):
            self.tareas_tab_frame.set_add_button_state() # Llamada inicial para estado correcto
        if hasattr(self, 'seguimiento_tab_frame'):
            self.seguimiento_tab_frame.set_add_button_state(tk.DISABLED)
        if hasattr(self, 'partes_tab_frame'):
            self.partes_tab_frame.set_add_button_state(tk.DISABLED)

        print("Widgets creados con estructura de 3 columnas y pestañas modulares + TareasTab.")

    # --- Métodos de Lógica CRM (Clientes y Casos) ---
    def load_clients(self):
        for i in self.client_tree.get_children(): self.client_tree.delete(i)
        clients = db.get_clients()
        for client in clients: self.client_tree.insert('', tk.END, values=(client['id'], client['nombre']), iid=str(client['id']))
        self.selected_client = None
        self.selected_case = None
        self.clear_client_details()
        self.clear_case_list() # Esto ya llama a clear_case_details que limpia documentos y deshabilita pestañas
        self.disable_client_buttons()
        # Las pestañas y sus contenidos se manejan en clear_case_details y on_case_select
        if hasattr(self, 'tareas_tab_frame'):
            self.main_notebook.tab(self.tareas_tab_frame, state='disabled')
            self.tareas_tab_frame.load_tareas(None) # Limpiar tareas
        self.update_add_audiencia_button_state()


    def on_client_select(self, event):
        selected_items = self.client_tree.selection()
        if selected_items:
            try:
                client_id = int(selected_items[0])
                self.selected_client = db.get_client_by_id(client_id)
            except (IndexError, ValueError, TypeError):
                print("Error: Selección de cliente inválida.")
                self.selected_client = None
            
            if self.selected_client:
                print(f"Cliente seleccionado ID: {self.selected_client['id']}")
                self.display_client_details(self.selected_client)
                self.load_cases_by_client(self.selected_client['id']) # Esto llama a clear_case_list y clear_case_details
                self.enable_client_buttons()
            else: # Si get_client_by_id falla o no hay selección válida
                self.selected_client = None
                self.clear_client_details()
                self.clear_case_list() # Limpia casos y detalles de caso (incluyendo pestañas)
                self.disable_client_buttons()

            if not self.selected_client: # Si la selección de cliente falla o no es válida      
                if hasattr(self, 'tareas_tab_frame'):
                    self.main_notebook.tab(self.tareas_tab_frame, state='disabled')
                    self.tareas_tab_frame.load_tareas(None)

        else: # No hay items seleccionados en client_tree
            if hasattr(self, 'tareas_tab_frame'):
                self.main_notebook.tab(self.tareas_tab_frame, state='disabled')
                self.tareas_tab_frame.load_tareas(None)
            
            self.selected_client = None
            self.clear_client_details()
            self.clear_case_list() # Limpia casos y detalles de caso (incluyendo pestañas)
            self.disable_client_buttons()
        self.update_add_audiencia_button_state()


    # En main_app.py, dentro de la clase CRMLegalApp

    def display_client_details(self, client_data):
        if client_data:
            self.client_detail_name_lbl.config(text=client_data.get('nombre', 'N/A'))
            self.client_detail_address_lbl.config(text=client_data.get('direccion', 'N/A'))
            self.client_detail_email_lbl.config(text=client_data.get('email', 'N/A'))
            self.client_detail_whatsapp_lbl.config(text=client_data.get('whatsapp', 'N/A'))

            # --- MOSTRAR ETIQUETAS ---
            nombres_etiquetas = [] # Inicializar como lista vacía
            client_id = client_data.get('id')
            if client_id: 
                etiquetas_obj = db.get_etiquetas_de_cliente(client_id)
                nombres_etiquetas = [e['nombre_etiqueta'] for e in etiquetas_obj]
            
            if hasattr(self, 'client_detail_tags_lbl'):
                self.client_detail_tags_lbl.config(text=", ".join(nombres_etiquetas).capitalize() if nombres_etiquetas else "Ninguna") # Usar capitalize para la primera letra
            else:
                # Esto es solo para depuración si el widget no se creó, no debería pasar si create_widgets es correcto
                print(f"[Detalles Cliente ERROR] self.client_detail_tags_lbl no existe.")
                print(f"[Detalles Cliente] Etiquetas para ID {client_id}: {', '.join(nombres_etiquetas) if nombres_etiquetas else 'Ninguna'}")
            # --- FIN MOSTRAR ETIQUETAS ---
        else:
            self.clear_client_details()

    def clear_client_details(self):
        self.client_detail_name_lbl.config(text="")
        self.client_detail_address_lbl.config(text="")
        self.client_detail_email_lbl.config(text="")
        self.client_detail_whatsapp_lbl.config(text="")
        # Si añades un Label para etiquetas, también límpialo aquí:
        if hasattr(self, 'client_detail_tags_lbl'):
            self.client_detail_tags_lbl.config(text="")


    def enable_client_buttons(self):
        self.edit_client_btn.config(state=tk.NORMAL); self.delete_client_btn.config(state=tk.NORMAL)

    def disable_client_buttons(self):
        self.edit_client_btn.config(state=tk.DISABLED); self.delete_client_btn.config(state=tk.DISABLED)

    def load_cases_by_client(self, client_id):
        self.clear_case_list() # Limpia la lista de casos y los detalles del caso anterior
        self.selected_case = None 
        # self.clear_case_details() # Ya se llama desde clear_case_list

        cases = db.get_cases_by_client(client_id)
        for case in cases:
            num_anio = f"{case.get('numero_expediente','?')}/{case.get('anio_caratula','?')}"
            self.case_tree.insert('', tk.END, values=(case['id'], num_anio, case['caratula']), iid=str(case['id']))
        
        self.add_case_btn.config(state=tk.NORMAL if self.selected_client else tk.DISABLED)
        self.update_add_audiencia_button_state() # El botón de agregar audiencia depende de si hay un caso seleccionado

    def clear_case_list(self):
        for i in self.case_tree.get_children(): self.case_tree.delete(i)
        self.selected_case = None
        self.clear_case_details() # Limpia detalles, documentos y pestañas relacionadas al caso

    def on_case_select(self, event):
        selected_items = self.case_tree.selection()
        if selected_items:
            try:
                case_id = int(selected_items[0])
                self.selected_case = db.get_case_by_id(case_id)
            except (IndexError, ValueError, TypeError):
                print("Error: Selección de caso inválida.")
                self.selected_case = None
            
            if self.selected_case:
                # print(f"Caso seleccionado ID: {self.selected_case['id']}")
                print(f"[MainApp Debug] Caso seleccionado para Partes: {self.selected_case['id'] if self.selected_case else 'None'}") # DEBUG
                self.display_case_details(self.selected_case) # Muestra detalles básicos
                self.load_case_documents(self.selected_case.get('ruta_carpeta', '')) # Carga documentos
                self.enable_case_buttons()
                self.enable_detail_tabs_for_case() # Habilita pestañas
                
                # Cargar datos en pestañas modulares
                if hasattr(self, 'seguimiento_tab_frame'):
                    self.seguimiento_tab_frame.load_actividades(self.selected_case['id'])
                    self.seguimiento_tab_frame.set_add_button_state(None) 
                if hasattr(self, 'partes_tab_frame'):
                    self.partes_tab_frame.load_partes(self.selected_case['id'])
                    self.partes_tab_frame.set_add_button_state(None)
            else: 
                print("[MainApp Debug] Ningún caso seleccionado para Partes.") # DEBUG
                self.selected_case = None
                self.clear_case_details() # Limpia todo lo relacionado al caso
                if hasattr(self, 'partes_tab_frame'): # NUEVO
                    self.partes_tab_frame.load_partes(None)
                    self.partes_tab_frame.set_add_button_state(None) # Esto llama a _update_action_buttons_state

        else: 
            self.selected_case = None
            self.clear_case_details() # Limpia todo lo relacionado al caso
            self.update_add_audiencia_button_state()
            if hasattr(self, 'partes_tab_frame'): # NUEVO
                self.partes_tab_frame.load_partes(None)
                self.partes_tab_frame.set_add_button_state(None) # Esto llama a _update_action_buttons_state
        
        if self.selected_case:
            # ... (lógica existente para detalles, documentos, botones, otras pestañas) ...
            if hasattr(self, 'tareas_tab_frame'):
                self.tareas_tab_frame.load_tareas(self.selected_case['id'])
                self.tareas_tab_frame.set_add_button_state()
        else: # No hay caso seleccionado o la selección falló
            # ... (lógica existente para limpiar detalles, otras pestañas) ...
            if hasattr(self, 'tareas_tab_frame'):
                self.tareas_tab_frame.load_tareas(None)
                self.tareas_tab_frame.set_add_button_state()

        self.root.update_idletasks() 
        #print(f"[DEBUG on_case_select] ANTES de update_add_audiencia_button_state -> self.selected_case: {self.selected_case}")
        self.update_add_audiencia_button_state()

    def display_case_details(self, case_data):
        if case_data:
            self.caratula_lbl.config(text=case_data.get('caratula', 'N/A'))
            exp = f"{case_data.get('numero_expediente', 'S/N')}/{case_data.get('anio_caratula', 'S/A')}"
            self.expediente_lbl.config(text=exp)
            self.juzgado_lbl.config(text=case_data.get('juzgado', 'N/A'))
            self.jurisdiccion_lbl.config(text=case_data.get('jurisdiccion', 'N/A'))
            self.etapa_lbl.config(text=case_data.get('etapa_procesal', 'N/A'))

            # --- MOSTRAR ETIQUETAS DEL CASO ---
            nombres_etiquetas_caso = []
            case_id_for_tags = case_data.get('id')
            if case_id_for_tags:
                etiquetas_obj = db.get_etiquetas_de_caso(case_id_for_tags)
                nombres_etiquetas_caso = [e['nombre_etiqueta'] for e in etiquetas_obj]
            
            if hasattr(self, 'case_detail_tags_lbl'):
                self.case_detail_tags_lbl.config(text=", ".join(nombres_etiquetas_caso).capitalize() if nombres_etiquetas_caso else "Ninguna")
            # --- FIN MOSTRAR ETIQUETAS DEL CASO ---

            self.notas_text.config(state=tk.NORMAL); self.notas_text.delete('1.0', tk.END); self.notas_text.insert('1.0', case_data.get('notas', '')); self.notas_text.config(state=tk.DISABLED)
            inactivity_enabled = "Sí" if case_data.get('inactivity_enabled') else "No"
            inactivity_threshold = case_data.get('inactivity_threshold_days', 30)
            self.inactivity_enabled_lbl.config(text=inactivity_enabled); self.inactivity_threshold_lbl.config(text=str(inactivity_threshold))
            
            # Actualizar info de carpeta en pestaña de documentos
            folder_path = case_data.get('ruta_carpeta', '');
            self.folder_path_lbl.config(text=folder_path if folder_path else "Carpeta no asignada")
            self.select_folder_btn.config(state=tk.NORMAL)
            self.open_folder_btn.config(state=tk.NORMAL if folder_path and os.path.isdir(folder_path) else tk.DISABLED)
        else:
            self.clear_case_details()


    def clear_case_details(self):
        self.caratula_lbl.config(text=""); self.expediente_lbl.config(text=""); self.juzgado_lbl.config(text="")
        self.jurisdiccion_lbl.config(text=""); self.etapa_lbl.config(text="")

        self.etapa_lbl.config(text="")

        # --- LIMPIAR LABEL DE ETIQUETAS DEL CASO ---
        if hasattr(self, 'case_detail_tags_lbl'):
            self.case_detail_tags_lbl.config(text="")
        # --- FIN LIMPIAR LABEL ---

        self.notas_text.config(state=tk.NORMAL); self.notas_text.delete('1.0', tk.END); self.notas_text.config(state=tk.DISABLED)
        self.inactivity_enabled_lbl.config(text=""); self.inactivity_threshold_lbl.config(text="")
        
        # Limpiar y deshabilitar lo relacionado a documentos
        self.folder_path_lbl.config(text="Selecciona un caso para ver/asignar carpeta");
        self.select_folder_btn.config(state=tk.DISABLED); self.open_folder_btn.config(state=tk.DISABLED)
        self.clear_document_list()
        self.disable_case_buttons()
        self.disable_detail_tabs_for_case() # Esto también limpia las pestañas modulares

    def enable_case_buttons(self):
        self.edit_case_btn.config(state=tk.NORMAL); self.delete_case_btn.config(state=tk.NORMAL)

    def disable_case_buttons(self):
        self.edit_case_btn.config(state=tk.DISABLED); self.delete_case_btn.config(state=tk.DISABLED)

    def enable_detail_tabs_for_case(self):
        self.main_notebook.tab(self.case_details_tab, state='normal')
        self.main_notebook.tab(self.documents_tab, state='normal')
        if hasattr(self, 'partes_tab_frame'):
            self.main_notebook.tab(self.partes_tab_frame, state='normal')
        if hasattr(self, 'seguimiento_tab_frame'):
            self.main_notebook.tab(self.seguimiento_tab_frame, state='normal')
        if hasattr(self, 'tareas_tab_frame'):
            self.main_notebook.tab(self.tareas_tab_frame, state='normal')
        
        if self.selected_case: # Al seleccionar un caso, por defecto ir a Detalles del Caso
            self.main_notebook.select(self.case_details_tab)

    def disable_detail_tabs_for_case(self):
        self.main_notebook.tab(self.case_details_tab, state='disabled')
        self.main_notebook.tab(self.documents_tab, state='disabled')
        
        if hasattr(self, 'partes_tab_frame'):
            self.main_notebook.tab(self.partes_tab_frame, state='disabled')
            if hasattr(self.partes_tab_frame, 'load_partes'): # Seguridad adicional
                self.partes_tab_frame.load_partes(None) 
        
        if hasattr(self, 'seguimiento_tab_frame'):
            self.main_notebook.tab(self.seguimiento_tab_frame, state='disabled')
            if hasattr(self.seguimiento_tab_frame, 'load_actividades'): # Seguridad adicional
                self.seguimiento_tab_frame.load_actividades(None)

        if hasattr(self, 'tareas_tab_frame'):
            self.main_notebook.tab(self.tareas_tab_frame, state='disabled')
            if hasattr(self.tareas_tab_frame, 'load_tareas'):
                self.tareas_tab_frame.load_tareas(None) 

# --- NUEVOS MÉTODOS PARA DIÁLOGOS Y LÓGICA DE TAREAS ---

    def open_tarea_dialog(self, tarea_id=None, caso_id=None):
        """Abre el diálogo para agregar o editar una tarea."""
        print(f"[open_tarea_dialog] Iniciando. tarea_id: {tarea_id}, caso_id: {caso_id}")

        # Determinar el caso_id y nombre del caso para el título y asociación
        current_caso_id = None
        case_display_name = "Tarea General" # Por defecto si no hay caso
        
        if tarea_id: # Editando tarea existente
            tarea_data_dict = self.db_crm.get_tarea_by_id(tarea_id)
            if not tarea_data_dict:
                messagebox.showerror("Error", f"No se pudo cargar la tarea ID {tarea_id}.", parent=self.root)
                return
            current_caso_id = tarea_data_dict.get('caso_id')
            if current_caso_id:
                case_info = self.db_crm.get_case_by_id(current_caso_id)
                case_display_name = case_info.get('caratula', f"ID {current_caso_id}") if case_info else f"ID {current_caso_id}"
            dialog_title = f"Editar Tarea ID: {tarea_id}"
        elif caso_id: # Nueva tarea para un caso específico (pasado desde TareasTab)
            current_caso_id = caso_id
            case_info = self.db_crm.get_case_by_id(current_caso_id)
            case_display_name = case_info.get('caratula', f"ID {current_caso_id}") if case_info else f"ID {current_caso_id}"
            dialog_title = f"Agregar Tarea a Caso: {case_display_name[:40]}"
            tarea_data_dict = {} # Vacío para nueva tarea
        elif self.selected_case : # Nueva tarea, caso seleccionado en la UI principal
            current_caso_id = self.selected_case['id']
            case_display_name = self.selected_case.get('caratula', f"ID {current_caso_id}")
            dialog_title = f"Agregar Tarea a Caso: {case_display_name[:40]}"
            tarea_data_dict = {}
        else: # Nueva tarea general (si se implementa esta lógica en TareasTab)
            dialog_title = "Agregar Tarea General"
            tarea_data_dict = {}
            # current_caso_id permanece None

        dialog = Toplevel(self.root)
        dialog.title(dialog_title)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True) # Permitir redimensionar por el campo de notas/descripción

        # Geometría y centrado
        dialog_width = 550; dialog_height = 580 # Ajustar según necesidad
        parent_x = self.root.winfo_x(); parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width(); parent_height = self.root.winfo_height()
        x_pos = parent_x + (parent_width - dialog_width) // 2
        y_pos = parent_y + (parent_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x_pos}+{y_pos}")
        dialog.minsize(dialog_width - 100, dialog_height - 150)


        frame = ttk.Frame(dialog, padding="15")
        frame.pack(expand=True, fill=tk.BOTH)
        frame.columnconfigure(1, weight=1) # Columna de widgets expandible

        # Variables de Tkinter para los campos
        descripcion_var = tk.StringVar(value=tarea_data_dict.get('descripcion', '')) # Se usará con Text
        
        # Fecha de Vencimiento
        fecha_venc_str = tarea_data_dict.get('fecha_vencimiento', '')
        # DateEntry necesita un objeto date, o None si está vacío.
        fecha_venc_dt_obj = None
        if fecha_venc_str:
            try:
                fecha_venc_dt_obj = datetime.datetime.strptime(fecha_venc_str, "%Y-%m-%d").date()
            except ValueError:
                print(f"Advertencia: Fecha de vencimiento '{fecha_venc_str}' con formato incorrecto, se ignora.")
        
        prioridad_var = tk.StringVar(value=tarea_data_dict.get('prioridad', 'Media'))
        estado_var = tk.StringVar(value=tarea_data_dict.get('estado', 'Pendiente'))
        notas_var = tk.StringVar(value=tarea_data_dict.get('notas', '')) # Se usará con Text
        es_plazo_var = tk.IntVar(value=tarea_data_dict.get('es_plazo_procesal', 0))
        recordatorio_activo_var = tk.IntVar(value=tarea_data_dict.get('recordatorio_activo', 0))
        recordatorio_dias_var = tk.IntVar(value=tarea_data_dict.get('recordatorio_dias_antes', 1))


        # Creación de Widgets del Diálogo
        row_idx = 0
        if current_caso_id:
            ttk.Label(frame, text="Caso Asociado:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
            ttk.Label(frame, text=case_display_name, wraplength=350).grid(row=row_idx, column=1, sticky=tk.W, pady=3, padx=5)
            row_idx += 1

        ttk.Label(frame, text="*Descripción:").grid(row=row_idx, column=0, sticky=tk.NW, pady=(5,2), padx=5)
        desc_text_frame = ttk.Frame(frame); desc_text_frame.grid(row=row_idx, column=1, sticky=tk.NSEW, pady=2, padx=5)
        desc_text_frame.columnconfigure(0, weight=1); desc_text_frame.rowconfigure(0, weight=1)
        desc_text_widget = tk.Text(desc_text_frame, height=5, width=40, wrap=tk.WORD)
        desc_text_widget.grid(row=0, column=0, sticky='nsew')
        desc_scroll = ttk.Scrollbar(desc_text_frame, orient=tk.VERTICAL, command=desc_text_widget.yview)
        desc_scroll.grid(row=0, column=1, sticky='ns')
        desc_text_widget['yscrollcommand'] = desc_scroll.set
        desc_text_widget.insert('1.0', tarea_data_dict.get('descripcion', ''))
        frame.rowconfigure(row_idx, weight=1) # Permitir que descripción se expanda
        row_idx += 1

        ttk.Label(frame, text="Fecha Vencimiento:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        # Usar DateEntry de tkcalendar
        # Si fecha_venc_dt_obj es None, DateEntry se mostrará sin fecha seleccionada.
        # Al leerlo, si no hay fecha, get_date() podría dar error o un valor que hay que manejar.
        # O podemos usar un Entry simple y validar el formato YYYY-MM-DD
        fecha_venc_entry = DateEntry(frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='dd-mm-y', locale='es_ES')
        if fecha_venc_dt_obj:
            fecha_venc_entry.set_date(fecha_venc_dt_obj)
        else:
            # Para que no muestre la fecha actual por defecto si no hay fecha de vencimiento
            # Necesitamos una forma de que esté "vacío" o poner un placeholder.
            # DateEntry no tiene un "estado vacío" fácil. Podríamos usar un Checkbutton para habilitarlo.
            # Por ahora, si no hay fecha, se mostrará la fecha actual. El usuario deberá borrarla o cambiarla.
            # O usar un Entry normal y validar. Vamos con Entry normal por simplicidad para el estado vacío.
            pass # Se deja el DateEntry como está, el usuario debe seleccionar o dejar la actual.
                 # Si se quiere vacío, mejor un ttk.Entry y validación.
                 # Para este ejemplo, usaremos DateEntry. Si get_date() da error al guardar, es que no se puso fecha.
        fecha_venc_entry.grid(row=row_idx, column=1, sticky=tk.W, pady=3, padx=5)
        row_idx += 1
        
        # Para permitir "sin fecha de vencimiento" con DateEntry, una alternativa sería:
        # fecha_venc_frame = ttk.Frame(frame)
        # fecha_venc_frame.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5)
        # fecha_venc_var_presente = tk.IntVar(value=1 if fecha_venc_dt_obj else 0)
        # fecha_venc_check = ttk.Checkbutton(fecha_venc_frame, text="Definir Vencimiento", variable=fecha_venc_var_presente, command=lambda: fecha_venc_entry.config(state=tk.NORMAL if fecha_venc_var_presente.get() else tk.DISABLED))
        # fecha_venc_check.pack(side=tk.LEFT)
        # fecha_venc_entry = DateEntry(fecha_venc_frame, width=12, ..., state=(tk.NORMAL if fecha_venc_dt_obj else tk.DISABLED))
        # if fecha_venc_dt_obj: fecha_venc_entry.set_date(fecha_venc_dt_obj)
        # fecha_venc_entry.pack(side=tk.LEFT, padx=5)


        ttk.Label(frame, text="Prioridad:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        prioridades = ["Alta", "Media", "Baja"]
        ttk.Combobox(frame, textvariable=prioridad_var, values=prioridades, state="readonly", width=15).grid(row=row_idx, column=1, sticky=tk.W, pady=3, padx=5)
        row_idx += 1

        ttk.Label(frame, text="Estado:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        estados = ["Pendiente", "En Progreso", "Completada", "Cancelada"]
        # Si es una nueva tarea, el estado "Completada" o "Cancelada" no debería ser una opción inicial común.
        # Pero para editar, sí.
        estado_combo = ttk.Combobox(frame, textvariable=estado_var, values=estados, state="readonly", width=15)
        estado_combo.grid(row=row_idx, column=1, sticky=tk.W, pady=3, padx=5)
        row_idx += 1

        ttk.Checkbutton(frame, text="¿Es Plazo Procesal?", variable=es_plazo_var).grid(row=row_idx, column=0, columnspan=2, sticky=tk.W, pady=3, padx=5)
        row_idx += 1
        
        # Sección Recordatorio
        rec_frame_tarea = ttk.LabelFrame(frame, text="Recordatorio")
        rec_frame_tarea.grid(row=row_idx, column=0, columnspan=2, sticky=tk.EW, pady=5, padx=5)
        ttk.Checkbutton(rec_frame_tarea, text="Activar Recordatorio", variable=recordatorio_activo_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(rec_frame_tarea, text="Días antes:").pack(side=tk.LEFT, padx=(10,2))
        ttk.Spinbox(rec_frame_tarea, from_=0, to=30, width=3, textvariable=recordatorio_dias_var).pack(side=tk.LEFT, padx=2)
        row_idx += 1
        
        ttk.Label(frame, text="Notas Adicionales:").grid(row=row_idx, column=0, sticky=tk.NW, pady=(5,2), padx=5)
        notas_text_frame = ttk.Frame(frame); notas_text_frame.grid(row=row_idx, column=1, sticky=tk.NSEW, pady=2, padx=5)
        notas_text_frame.columnconfigure(0, weight=1); notas_text_frame.rowconfigure(0, weight=1)
        notas_text_widget_dialog = tk.Text(notas_text_frame, height=4, width=40, wrap=tk.WORD)
        notas_text_widget_dialog.grid(row=0, column=0, sticky='nsew')
        notas_scroll_dialog = ttk.Scrollbar(notas_text_frame, orient=tk.VERTICAL, command=notas_text_widget_dialog.yview)
        notas_scroll_dialog.grid(row=0, column=1, sticky='ns')
        notas_text_widget_dialog['yscrollcommand'] = notas_scroll_dialog.set
        notas_text_widget_dialog.insert('1.0', tarea_data_dict.get('notas', ''))
        frame.rowconfigure(row_idx, weight=1) # Permitir que notas se expanda
        row_idx += 1
        
        button_frame_dialog = ttk.Frame(frame); button_frame_dialog.grid(row=row_idx, column=0, columnspan=2, pady=15, sticky=tk.E)
        
        def on_save_wrapper():
            # Obtener fecha de DateEntry. Si no se seleccionó, get_date() podría dar error.
            # O si el DateEntry no está "presente" (ej. por un check), no intentar obtenerla.
            fecha_venc_final_str = None
            try:
                # DateEntry devuelve un objeto date de Python. Convertir a YYYY-MM-DD string.
                fecha_venc_dt = fecha_venc_entry.get_date()
                fecha_venc_final_str = fecha_venc_dt.strftime("%Y-%m-%d")
            except Exception: # tkcalendar.DateEntryError si el campo está mal o vacío, o AttributeError si no hay get_date
                # Aquí decidimos si una fecha vacía es un error o significa "sin fecha"
                # print("Advertencia: No se pudo obtener fecha de vencimiento del DateEntry, se guardará como None.")
                # Si queremos que "no poner fecha" sea válido, la dejamos como None.
                # Si queremos que sea obligatoria (excepto si es un plazo donde se calcula), hay que validar.
                # Por ahora, si da error, asumimos que no se ingresó/es inválida.
                pass 

            self._save_tarea(
                tarea_id=tarea_id, 
                caso_id=current_caso_id,
                descripcion=desc_text_widget.get("1.0", tk.END).strip(),
                fecha_vencimiento=fecha_venc_final_str, # Usar el string formateado o None
                prioridad=prioridad_var.get(),
                estado=estado_var.get(),
                notas=notas_text_widget_dialog.get("1.0", tk.END).strip(),
                es_plazo_procesal=es_plazo_var.get(),
                recordatorio_activo=recordatorio_activo_var.get(),
                recordatorio_dias_antes=recordatorio_dias_var.get(),
                dialog=dialog
            )

        ttk.Button(button_frame_dialog, text="Guardar Tarea", command=on_save_wrapper).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame_dialog, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        desc_text_widget.focus_set() # Foco en el primer campo útil
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)


    def _save_tarea(self, tarea_id, caso_id, descripcion, fecha_vencimiento, prioridad, estado, notas, es_plazo_procesal, recordatorio_activo, recordatorio_dias_antes, dialog):
        if not descripcion.strip():
            messagebox.showerror("Validación", "La descripción de la tarea es obligatoria.", parent=dialog)
            return

        # Podríamos añadir más validaciones aquí (ej. formato de fecha si no usamos DateEntry)

        success = False
        msg_op = ""

        if tarea_id is None: # Nueva tarea
            new_id = self.db_crm.add_tarea(
                descripcion=descripcion, caso_id=caso_id, fecha_vencimiento=fecha_vencimiento,
                prioridad=prioridad, estado=estado, notas=notas,
                es_plazo_procesal=es_plazo_procesal, recordatorio_activo=recordatorio_activo,
                recordatorio_dias_antes=recordatorio_dias_antes
            )
            success = new_id is not None
            msg_op = "agregada"
        else: # Editar tarea
            success = self.db_crm.update_tarea(
                tarea_id=tarea_id, descripcion=descripcion, fecha_vencimiento=fecha_vencimiento,
                prioridad=prioridad, estado=estado, notas=notas,
                es_plazo_procesal=es_plazo_procesal, recordatorio_activo=recordatorio_activo,
                recordatorio_dias_antes=recordatorio_dias_antes
            )
            msg_op = "actualizada"
            # Nota: update_tarea en crm_database ya maneja si hay cambios o no.

        if success:
            messagebox.showinfo("Éxito", f"Tarea {msg_op} con éxito.", parent=self.root)
            dialog.destroy()
            # Recargar la lista de tareas en la pestaña correspondiente
            if hasattr(self, 'tareas_tab_frame'):
                if caso_id: # Si la tarea está asociada a un caso, recargar las tareas de ese caso
                    self.tareas_tab_frame.load_tareas(caso_id=caso_id)
                # else:
                    # Si implementamos una vista de "todas las tareas", recargar esa vista.
                    # self.tareas_tab_frame.load_tareas(mostrar_solo_pendientes_activas=True) 
        else:
            messagebox.showerror("Error", f"No se pudo {msg_op} la tarea. Verifique la consola.", parent=dialog)


    def marcar_tarea_como_completada(self, tarea_id, caso_id_asociado):
        """ Cambia el estado de la tarea seleccionada a 'Completada'. """
        if not tarea_id:
            messagebox.showwarning("Aviso", "No hay tarea seleccionada.", parent=self.root)
            return
        
        # Confirmación opcional
        # if not messagebox.askyesno("Confirmar", "¿Marcar esta tarea como completada?", parent=self.root):
        # return

        # Obtenemos la descripción para el mensaje de éxito, aunque no es estrictamente necesario
        tarea_data = self.db_crm.get_tarea_by_id(tarea_id)
        desc_corta = tarea_data.get('descripcion', f"ID {tarea_id}")[:30] if tarea_data else f"ID {tarea_id}"

        success = self.db_crm.update_tarea(tarea_id=tarea_id, estado="Completada")
        
        if success:
            messagebox.showinfo("Tarea Completada", f"Tarea '{desc_corta}...' marcada como completada.", parent=self.root)
            if hasattr(self, 'tareas_tab_frame'):
                # Recargar la lista de tareas del caso actual o la vista global
                if self.selected_case and self.selected_case['id'] == caso_id_asociado :
                     self.tareas_tab_frame.load_tareas(caso_id=self.selected_case['id'])
                elif caso_id_asociado: # Si la tarea era de otro caso (no debería pasar si el botón depende de selección)
                     self.tareas_tab_frame.load_tareas(caso_id=caso_id_asociado)
                # else:
                    # self.tareas_tab_frame.load_tareas(mostrar_solo_pendientes_activas=True) # Para vista global
        else:
            messagebox.showerror("Error", "No se pudo actualizar el estado de la tarea.", parent=self.root)


    def delete_selected_tarea(self, tarea_id, caso_id_asociado):
        """ Elimina la tarea seleccionada después de confirmación. """
        if not tarea_id:
            messagebox.showwarning("Aviso", "No hay tarea seleccionada para eliminar.", parent=self.root)
            return

        tarea_data = self.db_crm.get_tarea_by_id(tarea_id)
        desc_confirm = tarea_data.get('descripcion', f"ID {tarea_id}")[:50] if tarea_data else f"ID {tarea_id}"

        if messagebox.askyesno("Confirmar Eliminación",
                                f"¿Está seguro de que desea eliminar la tarea:\n'{desc_confirm}...'?",
                                parent=self.root, icon='warning'):
            
            success = self.db_crm.delete_tarea(tarea_id)
            if success:
                messagebox.showinfo("Tarea Eliminada", f"Tarea '{desc_confirm}...' eliminada correctamente.", parent=self.root)
                if hasattr(self, 'tareas_tab_frame'):
                    # Recargar la lista de tareas del caso actual o la vista global
                    if self.selected_case and self.selected_case['id'] == caso_id_asociado:
                        self.tareas_tab_frame.load_tareas(caso_id=self.selected_case['id'])
                    elif caso_id_asociado:
                        self.tareas_tab_frame.load_tareas(caso_id=caso_id_asociado)
                    # else:
                        # self.tareas_tab_frame.load_tareas(mostrar_solo_pendientes_activas=True)
            else:
                messagebox.showerror("Error", f"No se pudo eliminar la tarea '{desc_confirm}...'.", parent=self.root)

    # ... (resto de tus métodos existentes: backup, audiencias, recordatorios, etc.) ...
    # ... (asegúrate que el método `crear_copia_de_seguridad` esté aquí también) ...

# ... (tu `if __name__ == "__main__":` y el `root.mainloop()` al final) ...

    # En main_app.py, dentro de la clase CRMLegalApp

    def open_client_dialog(self, client_id=None):
        is_edit = client_id is not None
        dialog = tk.Toplevel(self.root)
        dialog.title("Editar Cliente" if is_edit else "Agregar Nuevo Cliente")
        dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False) # Podría ser resizable si añadimos más
        
        frame = ttk.Frame(dialog, padding="15"); frame.pack(fill=tk.BOTH, expand=True)
        
        # Variables de Tkinter
        name_var = tk.StringVar()
        address_var = tk.StringVar()
        email_var = tk.StringVar()
        whatsapp_var = tk.StringVar()
        etiquetas_var = tk.StringVar() # <--- NUEVA VARIABLE PARA ETIQUETAS

        if is_edit:
            client_data = db.get_client_by_id(client_id)
            if client_data:
                name_var.set(client_data.get('nombre', ''))
                address_var.set(client_data.get('direccion', ''))
                email_var.set(client_data.get('email', ''))
                whatsapp_var.set(client_data.get('whatsapp', ''))
                
                # Cargar etiquetas existentes para este cliente
                etiquetas_actuales_obj = db.get_etiquetas_de_cliente(client_id)
                etiquetas_actuales_nombres = [e['nombre_etiqueta'] for e in etiquetas_actuales_obj]
                etiquetas_var.set(", ".join(etiquetas_actuales_nombres)) # <--- MOSTRAR ETIQUETAS
            else:
                messagebox.showerror("Error", "No se pudieron cargar los datos del cliente.", parent=dialog)
                dialog.destroy()
                return

        # Layout de los widgets
        row_idx = 0
        ttk.Label(frame, text="Nombre Completo:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        name_entry = ttk.Entry(frame, textvariable=name_var, width=40)
        name_entry.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5); row_idx += 1

        ttk.Label(frame, text="Dirección:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        address_entry = ttk.Entry(frame, textvariable=address_var, width=40)
        address_entry.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5); row_idx += 1

        ttk.Label(frame, text="Email:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        email_entry = ttk.Entry(frame, textvariable=email_var, width=40)
        email_entry.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5); row_idx += 1

        ttk.Label(frame, text="WhatsApp:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        whatsapp_entry = ttk.Entry(frame, textvariable=whatsapp_var, width=40)
        whatsapp_entry.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5); row_idx += 1

        # --- NUEVO CAMPO PARA ETIQUETAS ---
        ttk.Label(frame, text="Etiquetas:").grid(row=row_idx, column=0, sticky=tk.W, pady=(10,3), padx=5)
        ttk.Label(frame, text="(separadas por coma)").grid(row=row_idx, column=1, sticky=tk.E, pady=(10,3), padx=0) # Pequeña ayuda
        row_idx += 1
        etiquetas_entry = ttk.Entry(frame, textvariable=etiquetas_var, width=40)
        etiquetas_entry.grid(row=row_idx, column=0, columnspan=2, sticky=tk.EW, pady=3, padx=5)
        row_idx += 1
        # --- FIN NUEVO CAMPO ---

        frame.columnconfigure(1, weight=1) # Para que los Entry se expandan
        
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=row_idx, column=0, columnspan=2, pady=15)
        
        # Modificar el comando del botón Guardar para pasar etiquetas_var.get()
        save_command = lambda: self.save_client(
            client_id, 
            name_var.get(), 
            address_var.get(), 
            email_var.get(), 
            whatsapp_var.get(),
            etiquetas_var.get(), # <--- PASAR ETIQUETAS
            dialog
        )
        ttk.Button(button_frame, text="Guardar", command=save_command).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        name_entry.focus_set()
        self.root.wait_window(dialog)

    # En main_app.py, dentro de la clase CRMLegalApp

    def save_client(self, client_id, nombre, direccion, email, whatsapp, etiquetas_str, dialog): # <--- NUEVO PARÁMETRO etiquetas_str
        if not nombre.strip():
            messagebox.showwarning("Advertencia", "El nombre del cliente no puede estar vacío.", parent=dialog)
            return

        success_main_data = False
        saved_client_id = client_id # Usaremos este ID para las etiquetas

        if client_id is None: # Nuevo cliente
            new_id = db.add_client(nombre.strip(), direccion.strip(), email.strip(), whatsapp.strip())
            if new_id:
                success_main_data = True
                saved_client_id = new_id # Guardar el ID del nuevo cliente
                msg_op = "agregado"
            else:
                msg_op = "falló al agregar"
        else: # Editar cliente
            if db.update_client(client_id, nombre.strip(), direccion.strip(), email.strip(), whatsapp.strip()):
                success_main_data = True
                msg_op = "actualizado"
                # Actualizar datos del cliente seleccionado si es el mismo
                if self.selected_client and self.selected_client['id'] == client_id:
                    self.selected_client = db.get_client_by_id(client_id)
                    self.display_client_details(self.selected_client) # Esto también debería mostrar etiquetas actualizadas
            else:
                msg_op = "falló al actualizar"

        if success_main_data:
            # --- LÓGICA PARA GUARDAR ETIQUETAS ---
            if saved_client_id is not None: # Solo procesar etiquetas si tenemos un ID de cliente válido
                # 1. Obtener los nombres de las etiquetas ingresadas por el usuario
                nombres_etiquetas_nuevas = [tag.strip().lower() for tag in etiquetas_str.split(',') if tag.strip()]
                
                # 2. Obtener las etiquetas actualmente asignadas al cliente desde la BD
                etiquetas_actuales_obj_db = db.get_etiquetas_de_cliente(saved_client_id)
                nombres_etiquetas_actuales_db = {e['nombre_etiqueta'].lower() for e in etiquetas_actuales_obj_db} # Usar un set para comparación eficiente

                # 3. Determinar qué etiquetas añadir y cuáles quitar
                ids_etiquetas_a_asignar = set()
                for nombre_tag_nuevo in nombres_etiquetas_nuevas:
                    tag_id = db.add_etiqueta(nombre_tag_nuevo) # add_etiqueta devuelve ID existente o crea nuevo
                    if tag_id:
                        ids_etiquetas_a_asignar.add(tag_id)
                
                etiquetas_ids_actuales_db = {e['id_etiqueta'] for e in etiquetas_actuales_obj_db}

                # Etiquetas a asignar (nuevas o que ya estaban y deben permanecer)
                for tag_id_to_assign in ids_etiquetas_a_asignar:
                    db.asignar_etiqueta_a_cliente(saved_client_id, tag_id_to_assign)

                # Etiquetas a quitar (estaban en BD pero no en la nueva lista del usuario)
                ids_etiquetas_a_quitar = etiquetas_ids_actuales_db - ids_etiquetas_a_asignar
                for tag_id_to_remove in ids_etiquetas_a_quitar:
                    db.quitar_etiqueta_de_cliente(saved_client_id, tag_id_to_remove)
            # --- FIN LÓGICA ETIQUETAS ---

            messagebox.showinfo("Éxito", f"Cliente {msg_op} con éxito. Etiquetas actualizadas.", parent=self.root)
            dialog.destroy()
            self.load_clients() # Recargar la lista de clientes
        else:
            messagebox.showerror("Error", f"No se pudo guardar la información principal del cliente.", parent=dialog)

    def delete_client(self):
        if not self.selected_client: messagebox.showwarning("Advertencia", "Selecciona un cliente."); return
        client_id = self.selected_client['id']; client_name = self.selected_client.get('nombre', f'ID {client_id}')
        if messagebox.askyesno("Confirmar", f"¿Eliminar cliente '{client_name}' y TODOS sus casos, actividades y audiencias asociadas?", parent=self.root, icon='warning'):
            if db.delete_client(client_id): # ON DELETE CASCADE se encarga del resto
                messagebox.showinfo("Éxito", "Cliente eliminado.", parent=self.root)
                self.load_clients() # Refresca todo, incluyendo la limpieza de casos, etc.
                self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario() # Actualizar agenda global
            else: messagebox.showerror("Error", "No se pudo eliminar el cliente.", parent=self.root)

    def open_case_dialog(self, case_id=None):
        is_edit = case_id is not None; client_context_id = None; client_context_name = "N/A"
        if is_edit:
            case_data = db.get_case_by_id(case_id)
            if not case_data: messagebox.showerror("Error", "No se pudieron cargar los datos del caso.", parent=self.root); return
            dialog_title = f"Editar Caso ID: {case_id}"; client_context_id = case_data['cliente_id']
            client_info = db.get_client_by_id(client_context_id)
            if client_info: client_context_name = client_info.get('nombre', f"ID {client_context_id}")
        else: # Nuevo caso
            if not self.selected_client: messagebox.showwarning("Advertencia", "Selecciona un cliente para agregarle un caso.", parent=self.root); return
            client_context_id = self.selected_client['id']; client_context_name = self.selected_client.get('nombre', f"ID {client_context_id}")
            dialog_title = f"Agregar Caso para: {client_context_name}"; case_data = {} # Datos iniciales vacíos
        
        dialog = tk.Toplevel(self.root); dialog.title(dialog_title); dialog.transient(self.root); dialog.grab_set(); dialog.resizable(True, True)
        
         # Geometría y centrado (puedes ajustar estos valores)
        dialog_width = 580; dialog_height = 680 
        parent_x = self.root.winfo_x(); parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width(); parent_height = self.root.winfo_height()
        x_pos = parent_x + (parent_width - dialog_width) // 2
        y_pos = parent_y + (parent_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x_pos}+{y_pos}")
        dialog.minsize(dialog_width - 80, dialog_height - 200)
        dialog.resizable(True,True)
        
        frame = ttk.Frame(dialog, padding="15"); frame.pack(fill=tk.BOTH, expand=True); frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1) # Columna para widgets de entrada (expandible)
                
        caratula_var = tk.StringVar(value=case_data.get('caratula', '')); num_exp_var = tk.StringVar(value=case_data.get('numero_expediente', '')); 
        anio_car_var = tk.StringVar(value=case_data.get('anio_caratula', ''));
        juzgado_var = tk.StringVar(value=case_data.get('juzgado', '')); jurisdiccion_var = tk.StringVar(value=case_data.get('jurisdiccion', ''));
        etapa_var = tk.StringVar(value=case_data.get('etapa_procesal', '')); 
        notas_initial_case = case_data.get('notas', ''); 
        if notas_initial_case is None: # Si es None (aunque get con default '' lo evitaría)
            notas_initial_case = ''   # Establecer a cadena vacía

        ruta_var = tk.StringVar(value=case_data.get('ruta_carpeta', '')); inact_days_var = tk.IntVar(value=case_data.get('inactivity_threshold_days', 30)); 
        inact_enabled_var = tk.IntVar(value=case_data.get('inactivity_enabled', 1))
        etiquetas_caso_var = tk.StringVar() # <--- NUEVA VARIABLE PARA ETIQUETAS DEL CASO

        if is_edit and case_id: # Solo cargar si estamos editando un caso existente
            etiquetas_actuales_obj = db.get_etiquetas_de_caso(case_id)
            etiquetas_actuales_nombres = [e['nombre_etiqueta'] for e in etiquetas_actuales_obj]
            etiquetas_caso_var.set(", ".join(etiquetas_actuales_nombres))
        
        row_idx = 0
        ttk.Label(frame, text="Cliente:").grid(row=0, column=0, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text=f"{client_context_name} (ID: {client_context_id})").grid(row=0, column=1, sticky=tk.W, pady=3, padx=5)
        row_idx += 1
        
        ttk.Label(frame, text="*Carátula:").grid(row=1, column=0, sticky=tk.W, pady=3, padx=5)
        caratula_entry = ttk.Entry(frame, textvariable=caratula_var); caratula_entry.grid(row=1, column=1, sticky=tk.EW, pady=3, padx=5)
        row_idx += 1

        # Nro Expediente y Año Carátula en la misma fila, usando un sub-frame para organizarlos
        exp_anio_frame = ttk.Frame(frame)
        exp_anio_frame.grid(row=row_idx, column=1, sticky=tk.EW, pady=0, padx=0) # Se alinea con la columna de valores
        
        ttk.Label(frame, text="Expediente:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5) # Etiqueta en la columna 0

        ttk.Label(exp_anio_frame, text="Nro:").pack(side=tk.LEFT, padx=(0,2), pady=3)
        ttk.Entry(exp_anio_frame, textvariable=num_exp_var, width=15).pack(side=tk.LEFT, padx=(0,10), pady=3)
        ttk.Label(exp_anio_frame, text="Año:").pack(side=tk.LEFT, padx=(0,2), pady=3)
        ttk.Entry(exp_anio_frame, textvariable=anio_car_var, width=8).pack(side=tk.LEFT, padx=(0,5), pady=3)
        row_idx += 1

        # Juzgado
        ttk.Label(frame, text="Juzgado:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        ttk.Entry(frame, textvariable=juzgado_var).grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5)
        row_idx += 1

        # Jurisdicción
        ttk.Label(frame, text="Jurisdicción:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        ttk.Entry(frame, textvariable=jurisdiccion_var).grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5)
        row_idx += 1

        # Etapa Procesal
        ttk.Label(frame, text="Etapa Procesal:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        ttk.Entry(frame, textvariable=etapa_var).grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5)
        row_idx += 1

        # Etiquetas Caso
        ttk.Label(frame, text="Etiquetas Caso:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        etiquetas_frame = ttk.Frame(frame) # Frame para el Entry y la ayuda
        etiquetas_frame.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5)
        etiquetas_caso_entry = ttk.Entry(etiquetas_frame, textvariable=etiquetas_caso_var)
        etiquetas_caso_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Label(etiquetas_frame, text="(separadas por coma)").pack(side=tk.LEFT, padx=(5,0))
        row_idx += 1

        # Notas del Caso
        ttk.Label(frame, text="Notas del Caso:").grid(row=row_idx, column=0, sticky=tk.NW, pady=(5,2), padx=5)
        notas_case_frame = ttk.Frame(frame)
        notas_case_frame.grid(row=row_idx, column=1, sticky=tk.NSEW, pady=2, padx=5)
        notas_case_frame.columnconfigure(0, weight=1); notas_case_frame.rowconfigure(0, weight=1)
        case_notas_text_dialog = tk.Text(notas_case_frame, height=5, wrap=tk.WORD) # Altura aumentada
        case_notas_text_dialog.grid(row=0, column=0, sticky='nsew')
        case_notas_scroll_dialog = ttk.Scrollbar(notas_case_frame, orient=tk.VERTICAL, command=case_notas_text_dialog.yview)
        case_notas_scroll_dialog.grid(row=0, column=1, sticky='ns')
        case_notas_text_dialog['yscrollcommand'] = case_notas_scroll_dialog.set
        case_notas_text_dialog.insert('1.0', notas_initial_case)
        frame.rowconfigure(row_idx, weight=1) # Permitir que Notas se expanda verticalmente
        row_idx += 1
        
        # Ruta Carpeta Docs
        ttk.Label(frame, text="Ruta Carpeta Docs:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        ruta_frame_dialog = ttk.Frame(frame) # Frame para Entry y botón (futuro)
        ruta_frame_dialog.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5)
        ruta_frame_dialog.columnconfigure(0, weight=1)
        ruta_entry_dialog = ttk.Entry(ruta_frame_dialog, textvariable=ruta_var)
        ruta_entry_dialog.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,5))
        # Aquí podrías añadir un botón "..." para seleccionar carpeta si lo deseas más adelante
        # ttk.Button(ruta_frame_dialog, text="...", width=3).pack(side=tk.LEFT)
        row_idx +=1

        # Alarma Inactividad
        inact_frame_dialog = ttk.LabelFrame(frame, text="Alarma Inactividad")
        # Colocarlo en la columna 1 para que se alinee con los campos de entrada, o columnspan=2 si quieres que ocupe todo
        inact_frame_dialog.grid(row=row_idx, column=0, columnspan=2, sticky=tk.EW, pady=10, padx=5)
        ttk.Checkbutton(inact_frame_dialog, text="Habilitada", variable=inact_enabled_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(inact_frame_dialog, text="Umbral (días):").pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(inact_frame_dialog, from_=1, to=365, width=5, textvariable=inact_days_var).pack(side=tk.LEFT, padx=5)
        row_idx += 1

        # Botones Guardar/Cancelar
        button_frame_dialog = ttk.Frame(frame)
        button_frame_dialog.grid(row=row_idx, column=0, columnspan=2, pady=15, sticky=tk.E) # sticky=tk.E para alinear a la derecha

        save_command = lambda: self.save_case(
            case_id, client_context_id, 
            caratula_var.get(), num_exp_var.get(), anio_car_var.get(), 
            juzgado_var.get(), jurisdiccion_var.get(), etapa_var.get(), 
            case_notas_text_dialog.get("1.0", tk.END).strip(), # Usar el nombre correcto del widget de notas
            ruta_var.get(), 
            inact_days_var.get(), inact_enabled_var.get(),
            etiquetas_caso_var.get(), # <--- PASAR ETIQUETAS DEL CASO
            dialog
        )

        ttk.Button(button_frame_dialog, text="Guardar", command=save_command).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame_dialog, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        caratula_entry.focus_set(); self.root.wait_window(dialog)


    def save_case(self, case_id, cliente_id, caratula, num_exp, anio_car, juzgado, juris, etapa, notas, ruta, inact_days, inact_enabled, etiquetas_caso_str, dialog):
        if not caratula.strip(): messagebox.showwarning("Advertencia", "La carátula del caso no puede estar vacía.", parent=dialog); return

        success_main_data = False
        saved_case_id = case_id # Usaremos este ID para las etiquetas

        if case_id is None: # Nuevo caso
            new_id = db.add_case(cliente_id, caratula.strip(), num_exp.strip(), anio_car.strip(), juzgado.strip(), juris.strip(), etapa.strip(), notas.strip(), ruta.strip(), inact_days, inact_enabled)
            if new_id:
                success_main_data = True
                saved_case_id = new_id
                msg_op = "agregado"
            else:
                msg_op = "falló al agregar"
        else: # Editar caso
            if db.update_case(case_id, caratula.strip(), num_exp.strip(), anio_car.strip(), juzgado.strip(), juris.strip(), etapa.strip(), notas.strip(), ruta.strip(), inact_days, inact_enabled):
                success_main_data = True
                msg_op = "actualizado"
                # Actualizar datos del caso seleccionado si es el mismo
                if self.selected_case and self.selected_case['id'] == case_id:
                    self.selected_case = db.get_case_by_id(case_id) # Refrescar
                    # self.display_case_details(self.selected_case) # Se llamará indirectamente al recargar lista
                    # self.load_case_documents(...) # También se maneja al recargar
            else:
                msg_op = "falló al actualizar"
        
        if success_main_data:
            # --- LÓGICA PARA GUARDAR ETIQUETAS DEL CASO ---
            if saved_case_id is not None:
                nombres_etiquetas_nuevas = [tag.strip().lower() for tag in etiquetas_caso_str.split(',') if tag.strip()]
                
                etiquetas_actuales_obj_db = db.get_etiquetas_de_caso(saved_case_id)
                # nombres_etiquetas_actuales_db = {e['nombre_etiqueta'].lower() for e in etiquetas_actuales_obj_db} # No necesitamos nombres, sino IDs para comparar

                ids_etiquetas_a_asignar = set()
                for nombre_tag_nuevo in nombres_etiquetas_nuevas:
                    tag_id = db.add_etiqueta(nombre_tag_nuevo) 
                    if tag_id:
                        ids_etiquetas_a_asignar.add(tag_id)
                
                etiquetas_ids_actuales_db = {e['id_etiqueta'] for e in etiquetas_actuales_obj_db}

                for tag_id_to_assign in ids_etiquetas_a_asignar:
                    db.asignar_etiqueta_a_caso(saved_case_id, tag_id_to_assign)

                ids_etiquetas_a_quitar = etiquetas_ids_actuales_db - ids_etiquetas_a_asignar
                for tag_id_to_remove in ids_etiquetas_a_quitar:
                    db.quitar_etiqueta_de_caso(saved_case_id, tag_id_to_remove)
            # --- FIN LÓGICA ETIQUETAS CASO ---

            messagebox.showinfo("Éxito", f"Caso {msg_op} con éxito. Etiquetas actualizadas.", parent=self.root)
            dialog.destroy()
            if self.selected_client: # Recargar la lista de casos del cliente actual
                self.load_cases_by_client(self.selected_client['id'])
                # Si el caso guardado era el seleccionado, refrescar sus detalles (incluyendo etiquetas)
                if self.selected_case and self.selected_case['id'] == saved_case_id:
                    self.selected_case = db.get_case_by_id(saved_case_id) # Volver a cargar el caso con sus etiquetas
                    self.display_case_details(self.selected_case) # Esto mostrará las nuevas etiquetas del caso
        else:
            messagebox.showerror("Error", f"No se pudo guardar la información principal del caso.", parent=dialog)


    def delete_case(self):
        if not self.selected_case: messagebox.showwarning("Advertencia", "Selecciona un caso para eliminar.", parent=self.root); return
        case_id = self.selected_case['id']; case_caratula = self.selected_case.get('caratula', f'ID {case_id}')
        if messagebox.askyesno("Confirmar Eliminación", f"¿Eliminar caso '{case_caratula}' y TODAS sus actividades, partes y audiencias asociadas?", parent=self.root, icon='warning'):
            if db.delete_case(case_id): # ON DELETE CASCADE se encarga del resto
                messagebox.showinfo("Éxito", "Caso eliminado con éxito.", parent=self.root)
                if self.selected_client: self.load_cases_by_client(self.selected_client['id'])
                else: self.clear_case_list(); self.clear_case_details() # Si no había cliente seleccionado, limpiar
                self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario() # Actualizar agenda global
            else: messagebox.showerror("Error", "No se pudo eliminar el caso.", parent=self.root)


    def select_case_folder(self):
        if not self.selected_case: messagebox.showwarning("Advertencia", "Selecciona un caso.", parent=self.root); return
        initial_dir = self.selected_case.get('ruta_carpeta') or os.path.expanduser("~")
        folder_selected = filedialog.askdirectory(initialdir=initial_dir, title="Seleccionar Carpeta de Documentos del Caso", parent=self.root)
        if folder_selected:
            case_id = self.selected_case['id']
            if db.update_case_folder(case_id, folder_selected):
                self.selected_case['ruta_carpeta'] = folder_selected # Actualizar en memoria
                self.folder_path_lbl.config(text=folder_selected);
                self.open_folder_btn.config(state=tk.NORMAL if os.path.isdir(folder_selected) else tk.DISABLED)
                self.load_case_documents(folder_selected) # Recargar lista de documentos
                messagebox.showinfo("Éxito", "Carpeta de documentos asignada con éxito.", parent=self.root)
            else: messagebox.showerror("Error", "No se pudo guardar la ruta de la carpeta en la base de datos.", parent=self.root)


    def open_case_folder(self):
        if not self.selected_case or not self.selected_case.get('ruta_carpeta'):
            messagebox.showwarning("Advertencia", "Selecciona un caso con una carpeta de documentos asignada.", parent=self.root)
            return
        folder_path = self.selected_case.get('ruta_carpeta')
        if folder_path and os.path.isdir(folder_path):
            try:
                if sys.platform == "win32": os.startfile(folder_path)
                elif sys.platform == "darwin": subprocess.call(["open", folder_path])
                else: subprocess.call(["xdg-open", folder_path])
            except Exception as e: messagebox.showerror("Error", f"No se pudo abrir la carpeta:\n{e}", parent=self.root)
        else:
            messagebox.showwarning("Advertencia", "La ruta de la carpeta no existe o es inválida.", parent=self.root)
            self.open_folder_btn.config(state=tk.DISABLED)


    def load_case_documents(self, folder_path):
        self.clear_document_list()
        current_folder_for_display = folder_path # Guardar la carpeta que se está mostrando
        if folder_path and os.path.isdir(folder_path):
            try:
                # Botón para subir un nivel, si no estamos en la carpeta raíz del caso
                if self.selected_case and folder_path != self.selected_case.get('ruta_carpeta'):
                    parent_dir = os.path.dirname(folder_path)
                    # Solo mostrar "subir" si el directorio padre es accesible y no es idéntico a la ruta actual (evitar bucles en raíz del sistema)
                    # y si el directorio padre es la carpeta raíz del caso o una subcarpeta de ella.
                    root_case_folder = self.selected_case.get('ruta_carpeta', '')
                    if parent_dir and os.path.isdir(parent_dir) and parent_dir != folder_path and \
                       (parent_dir == root_case_folder or parent_dir.startswith(root_case_folder + os.sep)):
                        self.document_tree.insert('', 0, values=("[..] Subir Nivel", "Carpeta", ""), iid=parent_dir, tags=('parent_folder',))


                # Listar directorios primero
                for entry in sorted(os.scandir(folder_path), key=lambda e: e.name.lower()): # Ordenar alfabéticamente
                    if self.stop_event.is_set(): break
                    if entry.is_dir():
                        try:
                            stat_info = entry.stat()
                            mod_time = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M')
                            self.document_tree.insert('', tk.END, values=(f"[CARPETA] {entry.name}", "Carpeta", mod_time), iid=entry.path, tags=('folder',))
                        except OSError as e: print(f"Warn: No se pudo leer info de carpeta {entry.path}: {e}")
                        except Exception as e: print(f"Error procesando carpeta {entry.path}: {e}")
                
                # Luego listar archivos
                for entry in sorted(os.scandir(folder_path), key=lambda e: e.name.lower()): # Ordenar alfabéticamente
                    if self.stop_event.is_set(): break
                    if entry.is_file():
                        try:
                            stat_info = entry.stat(); size_bytes = stat_info.st_size
                            if size_bytes < 1024: size_display = f"{size_bytes} B"
                            elif size_bytes < 1024**2: size_display = f"{size_bytes/1024:.1f} KB"
                            elif size_bytes < 1024**3: size_display = f"{size_bytes/1024**2:.1f} MB"
                            else: size_display = f"{size_bytes/1024**3:.1f} GB"
                            mod_time = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M')
                            self.document_tree.insert('', tk.END, values=(entry.name, size_display, mod_time), iid=entry.path, tags=('file',))
                        except OSError as e: print(f"Warn: No se pudo leer info de archivo {entry.path}: {e}")
                        except Exception as e: print(f"Error procesando archivo {entry.path}: {e}")

            except OSError as e:
                print(f"Error listando directorio {folder_path}: {e}")
                self.document_tree.insert('', tk.END, values=(f"Error al leer directorio: {e}", "", ""), iid="error_dir_listing")
            except Exception as e:
                print(f"Error inesperado listando directorio {folder_path}: {e}")
                self.document_tree.insert('', tk.END, values=("Error inesperado al listar", "", ""), iid="error_unexpected_listing")
        elif self.selected_case:
            self.document_tree.insert('', tk.END, values=("Carpeta no asignada o no encontrada.", "", ""), iid="no_folder_or_invalid")
        
        # Actualizar la etiqueta de la ruta que se está mostrando actualmente
        self.folder_path_lbl.config(text=current_folder_for_display if current_folder_for_display else "Carpeta no asignada")
        # El botón de "Abrir Carpeta" siempre abre la carpeta raíz del caso, no la subcarpeta actual
        root_folder_path = self.selected_case.get('ruta_carpeta', '') if self.selected_case else ''
        self.open_folder_btn.config(state=tk.NORMAL if root_folder_path and os.path.isdir(root_folder_path) else tk.DISABLED)


    def clear_document_list(self):
        for i in self.document_tree.get_children(): self.document_tree.delete(i)


    def on_document_double_click(self, event):
        item_id = self.document_tree.identify_row(event.y)
        if not item_id: return

        path_to_open = item_id # El iid es la ruta completa
        item_tags = self.document_tree.item(item_id, "tags")

        if 'file' in item_tags and os.path.isfile(path_to_open):
            try:
                if sys.platform == "win32": os.startfile(path_to_open)
                elif sys.platform == "darwin": subprocess.call(["open", path_to_open])
                else: subprocess.call(["xdg-open", path_to_open])

                if self.selected_case and self.selected_case.get('id'):
                    try:
                        file_name = os.path.basename(path_to_open)
                        self._save_new_actividad(
                            caso_id=self.selected_case['id'],
                            tipo_actividad="Documento Abierto",
                            descripcion=f"Se abrió el documento: {file_name}",
                            referencia_doc=file_name
                        )
                    except Exception as e_act: print(f"Error al registrar actividad por abrir documento: {e_act}")
            except FileNotFoundError: messagebox.showerror("Error", f"El archivo no se encuentra:\n{path_to_open}", parent=self.root)
            except Exception as e: messagebox.showerror("Error al abrir archivo", f"No se pudo abrir:\n{path_to_open}\n\nError: {e}", parent=self.root)
        
        elif ('folder' in item_tags or 'parent_folder' in item_tags) and os.path.isdir(path_to_open):
            print(f"Navegando a carpeta: {path_to_open}")
            self.load_case_documents(path_to_open) # Recargar con el contenido de la (sub)carpeta
        

    # --- Métodos para SeguimientoTab (Llamadas a diálogos) ---
    def open_actividad_dialog_for_seguimiento_tab(self, caso_id):
        if not caso_id: messagebox.showwarning("Advertencia", "No hay un caso seleccionado.", parent=self.root); return
        current_case_info = db.get_case_by_id(caso_id)
        case_display_name = current_case_info.get('caratula', f"ID {caso_id}") if current_case_info else f"ID {caso_id}"
        
        dialog = Toplevel(self.root); dialog.title(f"Agregar Actividad a: {case_display_name[:50]}"); dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False)
        parent_x = self.root.winfo_x(); parent_y = self.root.winfo_y(); parent_width = self.root.winfo_width(); parent_height = self.root.winfo_height()
        dialog_width = 450; dialog_height = 380; x = parent_x + (parent_width - dialog_width) // 2; y = parent_y + (parent_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding="15"); main_frame.pack(expand=True, fill=tk.BOTH); main_frame.columnconfigure(1, weight=1)
        
        ttk.Label(main_frame, text="*Tipo de Actividad:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5), padx=5)
        tipos_actividad = ["Llamada Telefónica", "Reunión", "Correo Electrónico Enviado", "Correo Electrónico Recibido", "Escrito Presentado", "Cédula/Notificación Recibida", "Movimiento del Expediente", "Análisis de Documentación", "Preparación de Audiencia", "Asistencia a Audiencia", "Consulta con Colega", "Investigación Jurídica", "Redacción de Documento", "Tarea Administrativa", "Nota Interna", "Documento Abierto", "Otro Evento Relevante"]
        tipo_actividad_var = tk.StringVar(); tipo_actividad_combo = ttk.Combobox(main_frame, textvariable=tipo_actividad_var, values=tipos_actividad, width=37, state="readonly")
        tipo_actividad_combo.grid(row=0, column=1, sticky=tk.EW, pady=(0, 10), padx=5)
        if tipos_actividad: tipo_actividad_combo.current(0)
        
        ttk.Label(main_frame, text="*Descripción Detallada:").grid(row=1, column=0, sticky=tk.NW, pady=(5, 5), padx=5) # Corregido row
        desc_outer_frame = ttk.Frame(main_frame); desc_outer_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0,10), padx=5) # Corregido row
        desc_outer_frame.rowconfigure(0, weight=1); desc_outer_frame.columnconfigure(0, weight=1)
        descripcion_text = tk.Text(desc_outer_frame, height=10, width=50, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1); descripcion_text.grid(row=0, column=0, sticky="nsew")
        desc_scrollbar = ttk.Scrollbar(desc_outer_frame, orient=tk.VERTICAL, command=descripcion_text.yview); descripcion_text.configure(yscrollcommand=desc_scrollbar.set); desc_scrollbar.grid(row=0, column=1, sticky="ns")
        main_frame.rowconfigure(2, weight=1) # Corregido row para que descripción se expanda
        
        # Opcional: Campo para Referencia de Documento si el tipo lo amerita
        ref_doc_var_act = tk.StringVar()
        ref_doc_label = ttk.Label(main_frame, text="Ref. Documento:")
        ref_doc_entry = ttk.Entry(main_frame, textvariable=ref_doc_var_act, width=37)

        def toggle_ref_doc_field(*args):
            if tipo_actividad_var.get() in ["Escrito Presentado", "Análisis de Documentación", "Documento Abierto"]:
                ref_doc_label.grid(row=3, column=0, sticky=tk.W, pady=(5,5), padx=5)
                ref_doc_entry.grid(row=3, column=1, sticky=tk.EW, pady=(5,10), padx=5)
            else:
                ref_doc_label.grid_remove()
                ref_doc_entry.grid_remove()
        
        tipo_actividad_var.trace_add("write", toggle_ref_doc_field)
        toggle_ref_doc_field() # Llamada inicial para establecer visibilidad

        buttons_frame = ttk.Frame(main_frame); buttons_frame.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=(10, 0))
        
        def on_save_actividad():
            tipo = tipo_actividad_var.get(); descripcion = descripcion_text.get("1.0", tk.END).strip()
            ref_doc = ref_doc_var_act.get().strip() if ref_doc_entry.winfo_ismapped() else None

            if not tipo: messagebox.showerror("Error de Validación", "El tipo de actividad es obligatorio.", parent=dialog); return
            if not descripcion: messagebox.showerror("Error de Validación", "La descripción es obligatoria.", parent=dialog); return
            self._save_new_actividad(caso_id, tipo, descripcion, ref_doc); dialog.destroy()

        save_button = ttk.Button(buttons_frame, text="Guardar Actividad", command=on_save_actividad); save_button.pack(side=tk.RIGHT, padx=(5,0))
        cancel_button = ttk.Button(buttons_frame, text="Cancelar", command=dialog.destroy); cancel_button.pack(side=tk.RIGHT, padx=(0,10))
        
        tipo_actividad_combo.focus_set(); dialog.protocol("WM_DELETE_WINDOW", dialog.destroy); self.root.wait_window(dialog)


    def open_edit_actividad_dialog(self, actividad_id, caso_id):
        if not actividad_id or not caso_id: messagebox.showerror("Error", "Información insuficiente.", parent=self.root); return
        actividad_actual = self.db_crm.get_actividad_by_id(actividad_id)
        if not actividad_actual: messagebox.showerror("Error", f"No se encontró actividad ID {actividad_id}.", parent=self.root); return
        
        current_case_info = self.db_crm.get_case_by_id(caso_id)
        case_display_name = current_case_info.get('caratula', f"ID {caso_id}") if current_case_info else f"ID {caso_id}"
        dialog = Toplevel(self.root); dialog.title(f"Editar Actividad (ID: {actividad_id}) de: {case_display_name[:40]}")
        dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False)
        
        parent_x = self.root.winfo_x(); parent_y = self.root.winfo_y(); parent_width = self.root.winfo_width(); parent_height = self.root.winfo_height()
        dialog_width = 450; dialog_height = 420; x_pos = parent_x + (parent_width - dialog_width) // 2; y_pos = parent_y + (parent_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x_pos}+{y_pos}")
        
        main_frame = ttk.Frame(dialog, padding="15"); main_frame.pack(expand=True, fill=tk.BOTH); main_frame.columnconfigure(1, weight=1)
        
        ttk.Label(main_frame, text="Fecha/Hora Registro:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5), padx=5)
        try: fecha_hora_dt = datetime.datetime.strptime(actividad_actual.get('fecha_hora', ''), "%Y-%m-%d %H:%M:%S"); fecha_hora_display = fecha_hora_dt.strftime("%d-%m-%Y %H:%M")
        except ValueError: fecha_hora_display = actividad_actual.get('fecha_hora', 'N/A')
        ttk.Label(main_frame, text=fecha_hora_display).grid(row=0, column=1, sticky=tk.W, pady=(0,5), padx=5)
        
        ttk.Label(main_frame, text="*Tipo de Actividad:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5), padx=5)
        tipos_actividad_list = ["Llamada Telefónica", "Reunión", "Correo Electrónico Enviado", "Correo Electrónico Recibido", "Escrito Presentado", "Cédula/Notificación Recibida", "Movimiento del Expediente", "Análisis de Documentación", "Preparación de Audiencia", "Asistencia a Audiencia", "Consulta con Colega", "Investigación Jurídica", "Redacción de Documento", "Tarea Administrativa", "Nota Interna", "Documento Abierto", "Otro Evento Relevante"]
        tipo_actividad_var = tk.StringVar(value=actividad_actual.get('tipo_actividad', ''))
        tipo_actividad_combo = ttk.Combobox(main_frame, textvariable=tipo_actividad_var, values=tipos_actividad_list, width=37, state="readonly")
        tipo_actividad_combo.grid(row=1, column=1, sticky=tk.EW, pady=(0, 10), padx=5)
        if actividad_actual.get('tipo_actividad') in tipos_actividad_list: tipo_actividad_combo.set(actividad_actual.get('tipo_actividad'))
        elif tipos_actividad_list: tipo_actividad_combo.current(0)
        
        ttk.Label(main_frame, text="*Descripción Detallada:").grid(row=2, column=0, sticky=tk.NW, pady=(5, 5), padx=5)
        desc_outer_frame = ttk.Frame(main_frame); desc_outer_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0,10), padx=5)
        desc_outer_frame.rowconfigure(0, weight=1); desc_outer_frame.columnconfigure(0, weight=1)
        descripcion_text = tk.Text(desc_outer_frame, height=10, width=50, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1); descripcion_text.grid(row=0, column=0, sticky="nsew"); desc_scrollbar = ttk.Scrollbar(desc_outer_frame, orient=tk.VERTICAL, command=descripcion_text.yview); descripcion_text.configure(yscrollcommand=desc_scrollbar.set); desc_scrollbar.grid(row=0, column=1, sticky="ns"); descripcion_text.insert('1.0', actividad_actual.get('descripcion', ''))
        main_frame.rowconfigure(3, weight=1)
        
        ref_doc_var_act = tk.StringVar(value=actividad_actual.get('referencia_documento', ''))
        ref_doc_label = ttk.Label(main_frame, text="Ref. Documento:")
        ref_doc_entry = ttk.Entry(main_frame, textvariable=ref_doc_var_act, width=37)

        def toggle_ref_doc_field_edit(*args):
            if tipo_actividad_var.get() in ["Escrito Presentado", "Análisis de Documentación", "Documento Abierto"]:
                ref_doc_label.grid(row=4, column=0, sticky=tk.W, pady=(5,5), padx=5)
                ref_doc_entry.grid(row=4, column=1, sticky=tk.EW, pady=(5,10), padx=5)
            else:
                ref_doc_label.grid_remove()
                ref_doc_entry.grid_remove()
        
        tipo_actividad_var.trace_add("write", toggle_ref_doc_field_edit)
        toggle_ref_doc_field_edit() # Llamada inicial

        buttons_frame = ttk.Frame(main_frame); buttons_frame.grid(row=5, column=0, columnspan=2, sticky=tk.E, pady=(10, 0))
        
        def on_save_edited_actividad():
            nuevo_tipo = tipo_actividad_var.get(); nueva_descripcion = descripcion_text.get("1.0", tk.END).strip()
            nueva_ref_doc = ref_doc_var_act.get().strip() if ref_doc_entry.winfo_ismapped() else None
            if not nuevo_tipo: messagebox.showerror("Error de Validación", "Tipo de actividad obligatorio.", parent=dialog); return
            if not nueva_descripcion: messagebox.showerror("Error de Validación", "Descripción obligatoria.", parent=dialog); return
            self._save_edited_actividad(actividad_id, caso_id, nuevo_tipo, nueva_descripcion, nueva_ref_doc); dialog.destroy()

        save_button = ttk.Button(buttons_frame, text="Guardar Cambios", command=on_save_edited_actividad); save_button.pack(side=tk.RIGHT, padx=(5,0))
        cancel_button = ttk.Button(buttons_frame, text="Cancelar", command=dialog.destroy); cancel_button.pack(side=tk.RIGHT, padx=(0,10))
        
        tipo_actividad_combo.focus_set(); dialog.protocol("WM_DELETE_WINDOW", dialog.destroy); self.root.wait_window(dialog)


    def _save_new_actividad(self, caso_id, tipo_actividad, descripcion, referencia_doc=None):
        fecha_hora_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Guardando actividad para caso ID {caso_id}: Tipo='{tipo_actividad}', Desc='{descripcion[:30]}...', RefDoc='{referencia_doc}'")
        try:
            nuevo_id_actividad = db.add_actividad_caso(caso_id=caso_id, fecha_hora=fecha_hora_actual, tipo_actividad=tipo_actividad, descripcion=descripcion, creado_por=None, referencia_documento=referencia_doc)
            if nuevo_id_actividad:
                messagebox.showinfo("Éxito", f"Actividad (ID: {nuevo_id_actividad}) agregada.", parent=self.root)
                if hasattr(self, 'seguimiento_tab_frame'): self.seguimiento_tab_frame.load_actividades(caso_id)
            else: messagebox.showerror("Error BD", "No se pudo guardar la actividad (ID nulo).", parent=self.root)
        except sqlite3.Error as e: messagebox.showerror("Error BD", f"Error al guardar actividad:\n{e}", parent=self.root); print(f"Error SQLite: {e}")
        except Exception as e: messagebox.showerror("Error", f"Error inesperado guardando actividad:\n{e}", parent=self.root); print(f"Error general: {e}")


    def _save_edited_actividad(self, actividad_id, caso_id, nuevo_tipo, nueva_descripcion, nueva_ref_doc=None):
        print(f"Guardando cambios actividad ID {actividad_id} (caso {caso_id})")
        try:
            success = self.db_crm.update_actividad_caso(actividad_id, nuevo_tipo, nueva_descripcion, nueva_ref_doc)
            if success:
                messagebox.showinfo("Éxito", f"Actividad ID {actividad_id} actualizada.", parent=self.root)
                if hasattr(self, 'seguimiento_tab_frame'): self.seguimiento_tab_frame.load_actividades(caso_id)
            else: messagebox.showwarning("Advertencia", f"No se actualizó actividad ID {actividad_id} (sin cambios o error).", parent=self.root)
        except sqlite3.Error as e: messagebox.showerror("Error BD", f"Error actualizando actividad ID {actividad_id}:\n{e}", parent=self.root); print(f"Error SQLite: {e}")
        except Exception as e: messagebox.showerror("Error", f"Error inesperado actualizando actividad ID {actividad_id}:\n{e}", parent=self.root); print(f"Error general: {e}")


    def delete_selected_actividad(self, actividad_id, caso_id):
        if not actividad_id or not caso_id: messagebox.showerror("Error", "Información insuficiente.", parent=self.root); return
        act_details = self.db_crm.get_actividad_by_id(actividad_id); desc_confirm = f"(ID: {actividad_id})"
        if act_details: desc_confirm = f"'{act_details.get('tipo_actividad','Evento')} - {act_details.get('descripcion','')[:30]}...' (ID: {actividad_id})"
        
        if messagebox.askyesno("Confirmar", f"¿Eliminar actividad:\n{desc_confirm}?", parent=self.root, icon='warning'):
            print(f"Intentando eliminar actividad ID {actividad_id} del caso ID {caso_id}")
            try:
                success = self.db_crm.delete_actividad_caso(actividad_id)
                if success:
                    messagebox.showinfo("Éxito", f"Actividad ID {actividad_id} eliminada.", parent=self.root)
                    if hasattr(self, 'seguimiento_tab_frame'): self.seguimiento_tab_frame.load_actividades(caso_id)
                else: messagebox.showerror("Error", f"No se pudo eliminar actividad ID {actividad_id}.", parent=self.root)
            except sqlite3.Error as e: messagebox.showerror("Error BD", f"Error eliminando actividad ID {actividad_id}:\n{e}", parent=self.root); print(f"Error SQLite: {e}")
            except Exception as e: messagebox.showerror("Error", f"Error inesperado eliminando actividad ID {actividad_id}:\n{e}", parent=self.root); print(f"Error general: {e}")


    # --- Métodos de Diálogo y Lógica para Partes Intervinientes ---
    def open_parte_dialog(self, parte_id=None, caso_id=None):
        if not caso_id and not self.selected_case:
            messagebox.showwarning("Advertencia", "Seleccione un caso primero.", parent=self.root)
            return
        
        current_caso_id = caso_id if caso_id else self.selected_case['id']
        current_case_info = self.db_crm.get_case_by_id(current_caso_id)
        case_display_name = current_case_info.get('caratula', f"ID {current_caso_id}") if current_case_info else f"ID {current_caso_id}"

        is_edit = parte_id is not None
        parte_data = {}
        dialog_title = f"Agregar Parte a Caso: {case_display_name[:40]}"
        if is_edit:
            parte_data = self.db_crm.get_parte_by_id(parte_id)
            if not parte_data: messagebox.showerror("Error", f"No se pudo cargar la parte ID {parte_id}.", parent=self.root); return
            dialog_title = f"Editar Parte ID: {parte_id} (Caso: {case_display_name[:30]})"

        dialog = Toplevel(self.root); dialog.title(dialog_title); dialog.transient(self.root); dialog.grab_set(); dialog.resizable(True, True) # Permitir redimensionar
        
        dialog_width = 500; dialog_height = 480 # Altura inicial
        parent_x = self.root.winfo_x(); parent_y = self.root.winfo_y(); parent_width = self.root.winfo_width(); parent_height = self.root.winfo_height()
        x_pos = parent_x + (parent_width - dialog_width) // 2; y_pos = parent_y + (parent_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x_pos}+{y_pos}")
        dialog.minsize(dialog_width, 380) # Mínimo para que se vea bien

        frame = ttk.Frame(dialog, padding="15"); frame.pack(expand=True, fill=tk.BOTH)
        frame.columnconfigure(1, weight=1)

        nombre_var = tk.StringVar(value=parte_data.get('nombre', ''))
        tipo_var = tk.StringVar(value=parte_data.get('tipo', ''))
        tipos_parte_comunes = ["", "Actor/a", "Demandado/a", "Tercero Interesado", "Testigo", "Perito", "Abogado Contraparte", "Abogado Propio (Referencia)", "Juez", "Secretario/a", "Mediador/a", "Síndico", "Asesor Técnico", "Otro"]
        direccion_initial = parte_data.get('direccion', '')
        contacto_var = tk.StringVar(value=parte_data.get('contacto', ''))
        notas_initial_case = parte_data.get('notas', '')

        row_idx = 0
        ttk.Label(frame, text="Caso:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text=case_display_name, wraplength=350).grid(row=row_idx, column=1, sticky=tk.W, pady=3, padx=5); row_idx += 1

        ttk.Label(frame, text="*Nombre Completo:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        nombre_entry = ttk.Entry(frame, textvariable=nombre_var, width=50); nombre_entry.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5); row_idx += 1

        ttk.Label(frame, text="Tipo/Rol:").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        tipo_combo = ttk.Combobox(frame, textvariable=tipo_var, values=tipos_parte_comunes, width=47)
        tipo_combo.grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5); row_idx += 1
        if tipo_var.get() == "" and tipos_parte_comunes: tipo_combo.current(0) # Seleccionar el vacío si no hay valor

        ttk.Label(frame, text="Dirección:").grid(row=row_idx, column=0, sticky=tk.NW, pady=3, padx=5)
        dir_frame = ttk.Frame(frame); dir_frame.grid(row=row_idx, column=1, sticky=tk.NSEW, pady=3, padx=5)
        dir_frame.rowconfigure(0, weight=1); dir_frame.columnconfigure(0, weight=1)
        direccion_text = tk.Text(dir_frame, height=3, width=40, wrap=tk.WORD); direccion_text.grid(row=0, column=0, sticky='nsew')
        dir_scroll = ttk.Scrollbar(dir_frame, orient=tk.VERTICAL, command=direccion_text.yview); dir_scroll.grid(row=0, column=1, sticky='ns')
        direccion_text['yscrollcommand'] = dir_scroll.set; direccion_text.insert('1.0', direccion_initial)
        frame.rowconfigure(row_idx, weight=0); row_idx += 1 # No expandir mucho

        ttk.Label(frame, text="Contacto (Tel/Email):").grid(row=row_idx, column=0, sticky=tk.W, pady=3, padx=5)
        ttk.Entry(frame, textvariable=contacto_var, width=50).grid(row=row_idx, column=1, sticky=tk.EW, pady=3, padx=5); row_idx += 1

        ttk.Label(frame, text="Notas Adicionales:").grid(row=row_idx, column=0, sticky=tk.NW, pady=3, padx=5)
        notas_frame_dialog = ttk.Frame(frame); notas_frame_dialog.grid(row=row_idx, column=1, sticky=tk.NSEW, pady=3, padx=5)
        notas_frame_dialog.rowconfigure(0, weight=1); notas_frame_dialog.columnconfigure(0, weight=1)
        notas_text_widget_dialog = tk.Text(notas_frame_dialog, height=5, width=40, wrap=tk.WORD); notas_text_widget_dialog.grid(row=0, column=0, sticky='nsew')
        notas_scroll_dialog = ttk.Scrollbar(notas_frame_dialog, orient=tk.VERTICAL, command=notas_text_widget_dialog.yview); notas_scroll_dialog.grid(row=0, column=1, sticky='ns')
        notas_text_widget_dialog['yscrollcommand'] = notas_scroll_dialog.set; notas_text_widget_dialog.insert('1.0', notas_initial_case)
        frame.rowconfigure(row_idx, weight=1); row_idx += 1 # Notas expandibles

        button_frame_dialog = ttk.Frame(frame); button_frame_dialog.grid(row=row_idx, column=0, columnspan=2, pady=15, sticky=tk.E)
        save_cmd = lambda: self._save_parte(parte_id, current_caso_id, nombre_var.get(), tipo_var.get(), direccion_text.get("1.0", tk.END).strip(), contacto_var.get(), notas_text_widget_dialog.get("1.0", tk.END).strip(), dialog)
        ttk.Button(button_frame_dialog, text="Guardar", command=save_cmd).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame_dialog, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        nombre_entry.focus_set(); dialog.protocol("WM_DELETE_WINDOW", dialog.destroy); self.root.wait_window(dialog)

    def _save_parte(self, parte_id, caso_id, nombre, tipo, direccion, contacto, notas, dialog):
        if not nombre.strip(): messagebox.showerror("Validación", "El nombre de la parte es obligatorio.", parent=dialog); return
        success = False; msg_op = ""
        if parte_id is None:
            new_id = self.db_crm.add_parte_interviniente(caso_id, nombre.strip(), tipo.strip(), direccion.strip(), contacto.strip(), notas.strip())
            success = new_id is not None; msg_op = "agregada"
        else:
            success = self.db_crm.update_parte_interviniente(parte_id, nombre.strip(), tipo.strip(), direccion.strip(), contacto.strip(), notas.strip())
            msg_op = "actualizada"
        if success:
            messagebox.showinfo("Éxito", f"Parte interviniente {msg_op}.", parent=self.root)
            if hasattr(self, 'partes_tab_frame'): self.partes_tab_frame.load_partes(caso_id)
            dialog.destroy()
        else: messagebox.showerror("Error", f"No se pudo {msg_op} la parte.", parent=dialog)

    def delete_selected_parte(self, parte_id, caso_id):
        if not parte_id or not caso_id: messagebox.showerror("Error", "Información insuficiente.", parent=self.root); return
        parte_info = self.db_crm.get_parte_by_id(parte_id)
        nombre_parte = parte_info.get('nombre', f"ID {parte_id}") if parte_info else f"ID {parte_id}"
        if messagebox.askyesno("Confirmar", f"¿Eliminar parte:\n'{nombre_parte}'?", parent=self.root, icon='warning'):
            success = self.db_crm.delete_parte_interviniente(parte_id)
            if success:
                messagebox.showinfo("Éxito", f"Parte '{nombre_parte}' eliminada.", parent=self.root)
                if hasattr(self, 'partes_tab_frame'): self.partes_tab_frame.load_partes(caso_id)
            else: messagebox.showerror("Error", f"No se pudo eliminar '{nombre_parte}'.", parent=self.root)


    # --- Métodos de Lógica para la Agenda Global ---
    def marcar_dias_audiencias_calendario(self):
        self.agenda_cal.calevent_remove(tag='audiencia_marcador'); fechas = db.get_fechas_con_audiencias()
        for fecha_str in fechas:
            try:
                fecha_dt = datetime.datetime.strptime(fecha_str, "%Y-%m-%d").date()
                self.agenda_cal.calevent_create(fecha_dt, 'Audiencia', tags='audiencia_marcador')
            except ValueError: print(f"Advertencia: Formato fecha inválido en BD: {fecha_str}")
            except Exception as e: print(f"Error marcando fecha {fecha_str}: {e}")

    def actualizar_lista_audiencias(self, event=None):
        if event: self.fecha_seleccionada_agenda = self.agenda_cal.get_date()
        for i in self.audiencia_tree.get_children(): self.audiencia_tree.delete(i)
        audiencias = db.get_audiencias_by_fecha(self.fecha_seleccionada_agenda)
        for aud in audiencias:
            hora = aud.get('hora', '--:--') or "--:--"; desc_full = aud.get('descripcion',''); desc_corta = (desc_full.split('\n')[0])[:60] + ('...' if len(desc_full) > 60 else '')
            caso_full = aud.get('caso_caratula', 'Caso Desc.'); caso_corto = caso_full[:50] + ('...' if len(caso_full) > 50 else '')
            link_full = aud.get('link','') or ""; link_corto = link_full[:40] + ('...' if len(link_full) > 40 else '')
            self.audiencia_tree.insert("", tk.END, values=(aud['id'], hora, desc_corta, caso_corto, link_corto), iid=str(aud['id']))
        self.deshabilitar_botones_audiencia(); self.limpiar_detalles_audiencia()

    def cargar_audiencias_fecha_actual(self):
        self.fecha_seleccionada_agenda = datetime.date.today().strftime("%Y-%m-%d")
        self.agenda_cal.selection_set(datetime.date.today()); self.actualizar_lista_audiencias()

    def on_audiencia_tree_select(self, event=None):
        selected_items = self.audiencia_tree.selection()
        if selected_items:
            try:
                audiencia_id = int(selected_items[0]); self.audiencia_seleccionada_id = audiencia_id
                self.mostrar_detalles_audiencia(audiencia_id); self.habilitar_botones_audiencia()
            except (IndexError, ValueError, TypeError): print("Error seleccionando audiencia."); self.audiencia_seleccionada_id = None; self.limpiar_detalles_audiencia(); self.deshabilitar_botones_audiencia()
        else: self.audiencia_seleccionada_id = None; self.limpiar_detalles_audiencia(); self.deshabilitar_botones_audiencia()

    def mostrar_detalles_audiencia(self, audiencia_id):
        audiencia = db.get_audiencia_by_id(audiencia_id); self.limpiar_detalles_audiencia(); self.audiencia_details_text.config(state=tk.NORMAL)
        if audiencia:
            hora = audiencia.get('hora') or "Sin hora"; link = audiencia.get('link') or "Sin link"; rec_activo = "Sí" if audiencia.get('recordatorio_activo') else "No"; rec_minutos = f" ({audiencia.get('recordatorio_minutos', 15)} min antes)" if audiencia.get('recordatorio_activo') else ""
            caso_caratula = audiencia.get('caso_caratula', 'Caso Desc.'); cliente_nombre = audiencia.get('cliente_nombre', 'Cliente Desc.')
            texto = (f"**Audiencia ID:** {audiencia['id']}\n" f"**Cliente:** {cliente_nombre}\n" f"**Caso:** {caso_caratula} (ID: {audiencia['caso_id']})\n" f"------------------------------------\n" f"**Fecha:** {audiencia.get('fecha', 'N/A')}\n" f"**Hora:** {hora}\n\n" f"**Descripción:**\n{audiencia.get('descripcion', 'N/A')}\n\n" f"**Link:**\n{link}\n\n" f"**Recordatorio:** {rec_activo}{rec_minutos}")
            self.audiencia_details_text.insert('1.0', texto)
        else: self.audiencia_details_text.insert('1.0', "Detalles no disponibles.")
        self.audiencia_details_text.config(state=tk.DISABLED)

    def limpiar_detalles_audiencia(self):
        self.audiencia_details_text.config(state=tk.NORMAL); self.audiencia_details_text.delete('1.0', tk.END); self.audiencia_details_text.config(state=tk.DISABLED)

    def habilitar_botones_audiencia(self):
        state = tk.NORMAL; self.edit_audiencia_btn.config(state=state); self.delete_audiencia_btn.config(state=state); self.share_audiencia_btn.config(state=state)
        link_presente = False
        if self.audiencia_seleccionada_id:
            audiencia = db.get_audiencia_by_id(self.audiencia_seleccionada_id)
            if audiencia and audiencia.get('link'): link_presente = True
        self.open_link_audiencia_btn.config(state=tk.NORMAL if link_presente else tk.DISABLED)

    def deshabilitar_botones_audiencia(self):
        state = tk.DISABLED; self.edit_audiencia_btn.config(state=state); self.delete_audiencia_btn.config(state=state); self.share_audiencia_btn.config(state=state); self.open_link_audiencia_btn.config(state=state)

    def update_add_audiencia_button_state(self): # Botón global para agregar audiencia
        is_case_selected = self.selected_case is not None
        print(f"[DEBUG update_add_audiencia_button_state] self.selected_case is {'SET' if is_case_selected else 'None'}. Button state to: {'NORMAL' if is_case_selected else 'DISABLED'}")
        self.add_audiencia_btn.config(state=tk.NORMAL if self.selected_case else tk.DISABLED)


    def abrir_link_audiencia_seleccionada(self, event=None):
        if not self.audiencia_seleccionada_id:
            if event: return
            else: messagebox.showinfo("Info", "Selecciona una audiencia con link.", parent=self.root); return
        audiencia = db.get_audiencia_by_id(self.audiencia_seleccionada_id); link = audiencia.get('link') if audiencia else None
        if link:
            try:
                if not link.startswith(('http://', 'https://')): link = 'http://' + link
                webbrowser.open_new_tab(link)
                if audiencia and audiencia.get('caso_id'): db.update_last_activity(audiencia['caso_id'])
            except Exception as e: messagebox.showerror("Error", f"No se pudo abrir link:\n{e}", parent=self.root)
        elif event is None: messagebox.showinfo("Info", "Audiencia sin link.", parent=self.root)

    def _formatear_texto_audiencia_para_compartir(self, audiencia):
        if not audiencia: return "Error: Audiencia no encontrada."
        texto = "**Audiencia Programada**\n------------------\n"; texto += f"**Fecha:** {audiencia.get('fecha', 'N/A')}\n"
        if audiencia.get('hora'): texto += f"**Hora:** {audiencia['hora']}\n"
        texto += f"**Caso:** {audiencia.get('caso_caratula', 'N/A')}\n"; texto += f"**Descripción:**\n{audiencia.get('descripcion', 'N/A')}\n"
        if audiencia.get('link'): texto += f"\n**Link:** {audiencia['link']}\n"
        texto += "------------------"; return texto

    def _compartir_audiencia_por_email(self):
        if not self.audiencia_seleccionada_id: return
        audiencia = db.get_audiencia_by_id(self.audiencia_seleccionada_id)
        if not audiencia: messagebox.showerror("Error", "No se pudo obtener info de audiencia.", parent=self.root); return
        desc_corta = (audiencia.get('descripcion','Evento')).split('\n')[0][:30]; asunto = f"Audiencia: {audiencia.get('fecha','')} - {desc_corta}"; cuerpo = self._formatear_texto_audiencia_para_compartir(audiencia)
        asunto_codificado = urllib.parse.quote(asunto); cuerpo_codificado = urllib.parse.quote(cuerpo)
        try: webbrowser.open(f"mailto:?subject={asunto_codificado}&body={cuerpo_codificado}"); db.update_last_activity(audiencia['caso_id'])
        except Exception as e: messagebox.showerror("Error", f"No se pudo abrir cliente email:\n{e}", parent=self.root)

    def _compartir_audiencia_por_whatsapp(self):
        if not self.audiencia_seleccionada_id: return
        audiencia = db.get_audiencia_by_id(self.audiencia_seleccionada_id)
        if not audiencia: messagebox.showerror("Error", "No se pudo obtener info de audiencia.", parent=self.root); return
        texto = self._formatear_texto_audiencia_para_compartir(audiencia); texto_codificado = urllib.parse.quote(texto)
        try: webbrowser.open(f"https://wa.me/?text={texto_codificado}"); db.update_last_activity(audiencia['caso_id'])
        except Exception as e: messagebox.showerror("Error", f"No se pudo abrir WhatsApp:\n{e}", parent=self.root)

    def mostrar_menu_compartir_audiencia(self):
        if not self.audiencia_seleccionada_id: messagebox.showwarning("Advertencia", "Selecciona audiencia para compartir.", parent=self.root); return
        menu = tk.Menu(self.root, tearoff=0); menu.add_command(label="Compartir por Email", command=self._compartir_audiencia_por_email); menu.add_separator(); menu.add_command(label="Compartir por WhatsApp", command=self._compartir_audiencia_por_whatsapp)
        try: widget = self.share_audiencia_btn; x = widget.winfo_rootx(); y = widget.winfo_rooty() + widget.winfo_height(); menu.tk_popup(x, y)
        except Exception as e: print(f"Error mostrando menú compartir: {e}."); menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally: menu.grab_release()

    def abrir_dialogo_audiencia(self, audiencia_id=None):
        is_edit = audiencia_id is not None; datos_audiencia = {}; caso_asociado_id = None; caso_asociado_caratula = "N/A"
        if is_edit:
            datos_audiencia = db.get_audiencia_by_id(audiencia_id)
            if not datos_audiencia: messagebox.showerror("Error", "No se cargó info de audiencia.", parent=self.root); return
            dialog_title = f"Editar Audiencia ID: {audiencia_id}"; caso_asociado_id = datos_audiencia['caso_id']; caso_asociado_caratula = datos_audiencia.get('caso_caratula', f"Caso ID {caso_asociado_id}")
        else:
            if not self.selected_case: messagebox.showwarning("Advertencia", "Selecciona un caso para agregar audiencia.", parent=self.root); return
            caso_asociado_id = self.selected_case['id']; caso_asociado_caratula = self.selected_case.get('caratula', f"Caso ID {caso_asociado_id}")
            dialog_title = f"Agregar Audiencia para: {caso_asociado_caratula[:50]}..."
        
        dialog = tk.Toplevel(self.root); dialog.title(dialog_title); dialog.geometry("480x420"); dialog.resizable(False, False); dialog.transient(self.root); dialog.grab_set()
        frame = ttk.Frame(dialog, padding="15"); frame.pack(expand=True, fill=tk.BOTH); frame.columnconfigure(1, weight=1); frame.rowconfigure(4, weight=1) # Desc se expande
        
        ttk.Label(frame, text="Caso:").grid(row=0, column=0, sticky=tk.W, pady=3, padx=5); ttk.Label(frame, text=caso_asociado_caratula, wraplength=300).grid(row=0, column=1, sticky=tk.W, pady=3, padx=5)
        fecha_inicial = datos_audiencia.get('fecha') if is_edit else self.fecha_seleccionada_agenda; ttk.Label(frame, text="*Fecha (YYYY-MM-DD):").grid(row=1, column=0, sticky=tk.W, pady=3, padx=5); fecha_var = tk.StringVar(value=fecha_inicial); entry_fecha = ttk.Entry(frame, textvariable=fecha_var, width=12); entry_fecha.grid(row=1, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text="Hora (HH:MM):").grid(row=2, column=0, sticky=tk.W, pady=3, padx=5); hora_var = tk.StringVar(value=datos_audiencia.get('hora', '')); entry_hora = ttk.Entry(frame, textvariable=hora_var, width=7); entry_hora.grid(row=2, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text="Link:").grid(row=3, column=0, sticky=tk.W, pady=3, padx=5); link_var = tk.StringVar(value=datos_audiencia.get('link', '')); ttk.Entry(frame, textvariable=link_var).grid(row=3, column=1, sticky=tk.EW, pady=3, padx=5)
        
        ttk.Label(frame, text="*Descripción:").grid(row=4, column=0, sticky=tk.NW, pady=3, padx=5); desc_frame = ttk.Frame(frame); desc_frame.grid(row=4, column=1, sticky=tk.NSEW, pady=3, padx=5); desc_frame.rowconfigure(0, weight=1); desc_frame.columnconfigure(0, weight=1); desc_text_dialog = tk.Text(desc_frame, height=6, wrap=tk.WORD); desc_text_dialog.grid(row=0, column=0, sticky='nsew'); desc_scroll_dialog = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=desc_text_dialog.yview); desc_scroll_dialog.grid(row=0, column=1, sticky='ns'); desc_text_dialog['yscrollcommand'] = desc_scroll_dialog.set
        if is_edit: desc_text_dialog.insert('1.0', datos_audiencia.get('descripcion', ''))
        
        rec_frame = ttk.LabelFrame(frame, text="Recordatorio"); rec_frame.grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=10, padx=5); rec_act_var = tk.IntVar(value=datos_audiencia.get('recordatorio_activo', 0)); rec_chk = ttk.Checkbutton(rec_frame, text="Activar", variable=rec_act_var); rec_chk.pack(side=tk.LEFT, padx=(5, 10)); ttk.Label(rec_frame, text="Minutos antes:").pack(side=tk.LEFT); rec_min_var = tk.IntVar(value=datos_audiencia.get('recordatorio_minutos', 15)); vcmd = (frame.register(self.validate_int_positive), '%P'); rec_spin = ttk.Spinbox(rec_frame, from_=1, to=1440, width=5, textvariable=rec_min_var, validate='key', validatecommand=vcmd); rec_spin.pack(side=tk.LEFT, padx=5)
        
        btn_frame_dialog = ttk.Frame(frame); btn_frame_dialog.grid(row=6, column=0, columnspan=2, pady=15)
        save_cmd = lambda: self.guardar_audiencia(audiencia_id, caso_asociado_id, fecha_var.get(), hora_var.get(), link_var.get(), desc_text_dialog.get("1.0", tk.END).strip(), rec_act_var.get(), rec_min_var.get(), dialog)
        ttk.Button(btn_frame_dialog, text="Guardar", command=save_cmd).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_dialog, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        entry_fecha.focus_set(); self.root.wait_window(dialog)


    def validate_int_positive(self, P): return (P.isdigit() and int(P) >= 0) or P == ""

    def parsear_hora(self, hora_str):
        if not hora_str or hora_str.isspace(): return None
        hora_str = hora_str.strip().replace('.', ':').replace(' ', '')
        match_hm = re.fullmatch(r"(\d{1,2}):(\d{1,2})", hora_str)
        if match_hm:
            h, m = int(match_hm.group(1)), int(match_hm.group(2))
            if 0 <= h <= 23 and 0 <= m <= 59: return f"{h:02d}:{m:02d}"
            else: return None
        match_h = re.fullmatch(r"(\d{1,2})", hora_str)
        if match_h:
             h = int(match_h.group(1))
             if 0 <= h <= 23: return f"{h:02d}:00"
             else: return None
        return None

    def guardar_audiencia(self, audiencia_id, caso_id, fecha_str, hora_str, link, desc, r_act, r_min, dialog):
        try: fecha_dt = datetime.datetime.strptime(fecha_str, "%Y-%m-%d"); fecha_db = fecha_dt.strftime("%Y-%m-%d")
        except ValueError: messagebox.showerror("Validación", "Formato fecha: YYYY-MM-DD.", parent=dialog); return
        hora_db = self.parsear_hora(hora_str)
        if hora_str and not hora_str.isspace() and hora_db is None: messagebox.showerror("Validación", "Formato hora inválido (HH:MM o H).", parent=dialog); return
        if not desc: messagebox.showerror("Validación", "Descripción obligatoria.", parent=dialog); return
        try: minutos_rec = int(r_min)
        except ValueError: minutos_rec = 15
        
        success = False; msg_op = ""
        if audiencia_id is None:
            new_id = db.add_audiencia(caso_id, fecha_db, hora_db, desc, link.strip(), r_act, minutos_rec); success = new_id is not None; msg_op = "agregada"
        else:
            success = db.update_audiencia(audiencia_id, fecha_db, hora_db, desc, link.strip(), r_act, minutos_rec); msg_op = "actualizada"
        
        if success:
            messagebox.showinfo("Éxito", f"Audiencia {msg_op}.", parent=self.root); dialog.destroy()
            self.agenda_cal.selection_set(fecha_dt.date()); self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario()
            # db.update_last_activity(caso_id) # Ya se hace en add/update_audiencia en db
        else: messagebox.showerror("Error", f"No se pudo {msg_op} audiencia.", parent=dialog)


    def editar_audiencia_seleccionada(self):
        if self.audiencia_seleccionada_id: self.abrir_dialogo_audiencia(self.audiencia_seleccionada_id)
        else: messagebox.showwarning("Advertencia", "Selecciona audiencia para editar.", parent=self.root)

    def eliminar_audiencia_seleccionada(self):
        if not self.audiencia_seleccionada_id: messagebox.showwarning("Advertencia", "Selecciona audiencia para eliminar.", parent=self.root); return
        try: desc_corta = self.audiencia_tree.item(str(self.audiencia_seleccionada_id))['values'][2]
        except: desc_corta = f"ID {self.audiencia_seleccionada_id}"
        
        if messagebox.askyesno("Confirmar", f"¿Eliminar audiencia:\n'{desc_corta}'?", parent=self.root, icon='warning'):
            # audiencia_info = db.get_audiencia_by_id(self.audiencia_seleccionada_id) # Para caso_id, ya se maneja en delete_audiencia en db
            if db.delete_audiencia(self.audiencia_seleccionada_id):
                messagebox.showinfo("Éxito", "Audiencia eliminada.", parent=self.root)
                self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario(); self.limpiar_detalles_audiencia()
                # if audiencia_info and audiencia_info.get('caso_id'): db.update_last_activity(audiencia_info['caso_id']) # Ya se maneja en db
            else: messagebox.showerror("Error", "No se pudo eliminar audiencia.", parent=self.root)


    # --- Funciones de Recordatorios y Bandeja del Sistema ---
    def verificar_recordatorios_periodicamente(self):
        print("[Recordatorios] Hilo iniciado.")
        while not self.stop_event.is_set():
            current_processing_start_time = time.monotonic()
            try:
                ahora = datetime.datetime.now(); hoy_str = ahora.strftime("%Y-%m-%d")
                if not hasattr(self, '_dia_verificacion_recordatorios') or self._dia_verificacion_recordatorios != hoy_str:
                    print(f"[Recordatorios] Nuevo día ({hoy_str}), reseteando mostrados."); self.recordatorios_mostrados_hoy = set(); self._dia_verificacion_recordatorios = hoy_str
                
                audiencias_a_revisar = db.get_audiencias_con_recordatorio_activo()
                for aud in audiencias_a_revisar:
                    if self.stop_event.is_set(): break
                    aud_id = aud['id']
                    if not aud.get('fecha') or not aud.get('hora') or aud_id in self.recordatorios_mostrados_hoy: continue
                    try:
                        tiempo_audiencia = datetime.datetime.strptime(f"{aud['fecha']} {aud['hora']}", "%Y-%m-%d %H:%M"); minutos_antes = aud.get('recordatorio_minutos', 15)
                        tiempo_recordatorio = tiempo_audiencia - datetime.timedelta(minutes=minutos_antes)
                        if tiempo_recordatorio <= ahora < tiempo_audiencia:
                            print(f"[Recordatorios] ¡Alerta! Audiencia ID: {aud_id} ({aud['hora']}) en {aud['fecha']}.")
                            self.root.after(0, self.mostrar_recordatorio, aud.copy()); self.recordatorios_mostrados_hoy.add(aud_id)
                    except ValueError as ve: print(f"[Recordatorios] Error parseando fecha/hora ID {aud_id}: {ve}")
                    except Exception as e: print(f"[Recordatorios] Error procesando recordatorio ID {aud_id}: {e}")
            except sqlite3.Error as dbe: print(f"[Recordatorios] Error BD en hilo: {dbe}"); self.stop_event.wait(300)
            except Exception as ex: print(f"[Recordatorios] Error inesperado en hilo: {ex}"); self.stop_event.wait(120)
            
            processing_duration = time.monotonic() - current_processing_start_time
            sleep_interval = max(1.0, 60.0 - processing_duration)
            self.stop_event.wait(sleep_interval)
        print("[Recordatorios] Hilo detenido.")


    def mostrar_recordatorio(self, audiencia):
        if not audiencia: return
        print(f"[Notificación] Mostrando para Audiencia ID: {audiencia.get('id')}")
        hora_audiencia = audiencia.get('hora', 'N/A'); desc_full = audiencia.get('descripcion', ''); desc_alerta = (desc_full.split('\n')[0])[:100] + ('...' if len(desc_full) > 100 else '')
        link = audiencia.get('link', ''); link_corto = (link[:60] + '...') if len(link) > 60 else link; mensaje = f"Próxima audiencia: {desc_alerta}"
        if link_corto: mensaje += f"\nLink: {link_corto}"
        titulo = f"Recordatorio CRM Legal: {hora_audiencia}"; app_nombre = "CRM Legal"; icon_path_notif = ""
        try:
            icon_path_notif = resource_path('assets/icono.ico')
            if not os.path.exists(icon_path_notif): print(f"Advertencia: Icono notif. no encontrado: {icon_path_notif}"); icon_path_notif = ""
        except Exception as e: print(f"Error ruta icono notif.: {e}"); icon_path_notif = ""
        
        try:
            print(f"[Notificación] Enviando: T='{titulo}', M='{mensaje}', Icono='{icon_path_notif}'")
            plyer.notification.notify(title=titulo, message=mensaje, app_name=app_nombre, app_icon=icon_path_notif, timeout=20)
            print("[Notificación] Plyer notify() llamado.")
        except NotImplementedError: print("[Notificación] Plataforma no soportada. Usando fallback."); self.root.after(0, messagebox.showwarning, titulo, mensaje, {'parent': self.root})
        except Exception as e: print(f"[Notificación] Error Plyer: {e}. Usando fallback."); self.root.after(0, messagebox.showwarning, titulo, mensaje, {'parent': self.root})


    def ocultar_a_bandeja(self):
        self.root.withdraw(); print("[Bandeja] Ventana ocultada.")
        try:
            icon_p = resource_path('assets/icono.ico')
            if os.path.exists(icon_p): plyer.notification.notify(title="CRM Legal", message="Ejecutándose en segundo plano.", app_name="CRM Legal", app_icon=icon_p, timeout=10)
            else: print(f"Advertencia: Icono notif. ocultado no encontrado: {icon_p}")
        except Exception as e: print(f"[Bandeja - Notif Ocultado] Error Plyer: {e}")


    def _mostrar_ventana_callback(self, icon=None, item=None): # icon e item son pasados por pystray
        print("[Bandeja] Solicitud para mostrar ventana.");
        self.root.after(0, self.root.deiconify) # Deiconify en el hilo de Tkinter
        self.root.after(10, self.root.lift)     # Traer al frente
        self.root.after(20, self.root.focus_force) # Forzar foco


    def _salir_app_callback(self, icon=None, item=None): # icon e item son pasados por pystray
        print("[Bandeja] Solicitud de salida.")
        # No es necesario detener el icono aquí si cerrar_aplicacion lo hace y luego destruye root.
        # Si el icono no se detiene antes de self.root.destroy(), puede dar error.
        self.cerrar_aplicacion_directamente() # Pedir confirmación y cerrar


    def setup_tray_icon(self):
        print("[Bandeja] Iniciando config. icono...")
        image = None
        try:
            icon_path = resource_path("assets/icono.png")
            if not os.path.exists(icon_path):
                print(f"ERROR CRÍTICO [Bandeja]: Icono no encontrado: {icon_path}. No se creará icono."); return
            print(f"[Bandeja] Cargando icono desde: {icon_path}"); image = Image.open(icon_path)
        except FileNotFoundError as fnf: print(f"ERROR CRÍTICO [Bandeja]: {fnf}. No se creará icono."); return
        except Exception as e_img: print(f"ERROR FATAL [Bandeja]: No se cargó imagen icono: {e_img}. No se creará icono."); return

        menu = (item('Mostrar CRM Legal', self._mostrar_ventana_callback, default=True), item('Salir', self._salir_app_callback))
        try:
            self.tray_icon = icon("CRMLegalAppTray", image, "CRM Legal", menu)
            print("[Bandeja] Icono creado. Ejecutando run() (hilo se bloqueará aquí hasta stop())...")
            self.tray_icon.run() # Bloqueante, se ejecuta en su propio hilo daemon
            print("[Bandeja] Icono run() terminado (stop() fue llamado)."); self.tray_icon = None
        except Exception as e:
            print(f"ERROR FATAL [Bandeja]: No se pudo iniciar icono: {e}")
            self.tray_icon = None


# --- Punto de entrada principal ---
if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style(root)
    available_themes = style.theme_names()
    print("Temas disponibles:", available_themes)
    desired_themes = ['vista', 'xpnative', 'winnative', 'clam', 'alt', 'default']
    theme_applied = False
    for theme in desired_themes:
        if theme in available_themes:
            try:
                style.theme_use(theme); print(f"Tema '{theme}' aplicado."); theme_applied = True; break
            except tk.TclError: print(f"Advertencia: No se pudo aplicar tema '{theme}'.")
    if not theme_applied: print(f"Ninguno de los temas preferidos estaba disponible. Usando tema por defecto: {style.theme_use()}")
    
    app = CRMLegalApp(root)
    root.mainloop()
    print("Aplicación CRM Legal cerrada.")
