import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, Toplevel
import crm_database as db # Tu módulo de base de datos
import os
import datetime
import time
import sys
import subprocess
import sqlite3 # Importar sqlite3 directamente para referenciar errores

# --- Nuevos Imports para Agenda/Recordatorios/Bandeja ---
from tkcalendar import Calendar
import threading
import webbrowser
import re
import urllib.parse # Para codificar URLs (Compartir)
from PIL import Image, ImageTk # Para imagen del logo y bandeja
import plyer # Para notificaciones nativas
from pystray import MenuItem as item, Icon as icon # Para bandeja sistema

# --- Import para la Pestaña de Seguimiento ---
from seguimiento_ui import SeguimientoTab


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
        filemenu.add_command(label="Mostrar Ventana", command=self._mostrar_ventana_callback)
        filemenu.add_separator()
        filemenu.add_command(label="Ocultar a Bandeja", command=self.ocultar_a_bandeja)
        filemenu.add_separator()
        filemenu.add_command(label="Salir (Cerrar Aplicación)", command=self.cerrar_aplicacion_directamente)
        menubar.add_cascade(label="Archivo", menu=filemenu)
        self.root.config(menu=menubar)
        # --- Fin Barra de Menú ---

        # Variables de estado CRM
        self.selected_client = None
        self.selected_case = None

        # --- Referencia al módulo de base de datos para SeguimientoTab y otros usos ---
        self.db_crm = db

        # --- Variables para Agenda/Recordatorios/Bandeja ---
        self.fecha_seleccionada_agenda = datetime.date.today().strftime("%Y-%m-%d") # Corregido formato
        self.audiencia_seleccionada_id = None
        self.recordatorios_mostrados_hoy = set()
        self.logo_image_tk = None
        self.tray_icon = None
        self.hilo_recordatorios = None
        self.hilo_bandeja = None
        self.stop_event = threading.Event()
        # --- Fin Variables Agenda ---

        # db.create_tables() # Asegurado en database.py al importar

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

    def cerrar_aplicacion_directamente(self):
        if messagebox.askokcancel("Confirmar Salida", "¿Estás seguro de que quieres cerrar completamente la aplicación?", parent=self.root):
            self.cerrar_aplicacion()

    def cerrar_aplicacion(self):
        print("Iniciando secuencia de cierre de la aplicación...")
        self.stop_event.set()
        if self.tray_icon and hasattr(self.tray_icon, 'stop') and self.tray_icon.visible:
            print("Deteniendo icono de bandeja explícitamente...")
            try:
                self.tray_icon.stop()
            except Exception as e:
                print(f"Error al intentar detener icono de bandeja (puede ser normal si ya se detuvo): {e}")
        else:
            print("Icono de bandeja no visible, no iniciado, o ya detenido.")
        self.root.after(100, self.root.destroy)
        print("Solicitud de cierre completada.")

    def create_widgets(self):
        crm_main_frame = ttk.Frame(self.root, padding="10")
        crm_main_frame.pack(fill=tk.BOTH, expand=True)

        crm_main_frame.rowconfigure(0, weight=1)
        crm_main_frame.columnconfigure(0, weight=0)
        crm_main_frame.columnconfigure(1, weight=0)
        crm_main_frame.columnconfigure(2, weight=2)

        # --- Columna 1: Clientes ---
        col1_frame = ttk.Frame(crm_main_frame)
        col1_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5), pady=5)
        col1_frame.rowconfigure(0, weight=1); col1_frame.rowconfigure(1, weight=0); col1_frame.rowconfigure(2, weight=0)
        col1_frame.columnconfigure(0, weight=1)

        client_list_frame = ttk.LabelFrame(col1_frame, text="Clientes", padding="5")
        client_list_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        client_list_frame.columnconfigure(0, weight=1); client_list_frame.rowconfigure(0, weight=1); client_list_frame.rowconfigure(1, weight=0)
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

        # --- Columna 2: Casos / Calendario ---
        col2_frame = ttk.Frame(crm_main_frame); col2_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        col2_frame.rowconfigure(0, weight=1); col2_frame.rowconfigure(1, weight=0); col2_frame.rowconfigure(2, weight=1); col2_frame.rowconfigure(3, weight=0)
        col2_frame.columnconfigure(0, weight=1)

        case_list_frame = ttk.LabelFrame(col2_frame, text="Casos Cliente", padding="5"); case_list_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        case_list_frame.columnconfigure(0, weight=1); case_list_frame.rowconfigure(0, weight=1); case_list_frame.rowconfigure(1, weight=0)
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
        cal_frame.rowconfigure(0, weight=1); cal_frame.columnconfigure(0, weight=1)
        self.agenda_cal = Calendar(cal_frame, selectmode='day', date_pattern='y-mm-dd', tooltipforeground='black', tooltipbackground='#FFFFE0', locale='es_ES')
        self.agenda_cal.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        self.agenda_cal.bind("<<CalendarSelected>>", self.actualizar_lista_audiencias)
        self.agenda_cal.tag_config('audiencia_marcador', background='lightblue', foreground='black')

        add_aud_frame = ttk.Frame(col2_frame); add_aud_frame.grid(row=3, column=0, sticky='ew', pady=(5, 0))
        self.add_audiencia_btn = ttk.Button(add_aud_frame, text="Agregar Audiencia", command=lambda: self.abrir_dialogo_audiencia(), state=tk.NORMAL)
        self.add_audiencia_btn.pack(fill=tk.X, padx=10, pady=5)
        self.update_add_audiencia_button_state() # Estado inicial correcto

        # --- Columna 3: Detalles / Audiencias ---
        col3_frame = ttk.Frame(crm_main_frame); col3_frame.grid(row=0, column=2, sticky='nsew', padx=(5, 0), pady=5)
        col3_frame.rowconfigure(0, weight=3); col3_frame.rowconfigure(1, weight=1); col3_frame.rowconfigure(2, weight=0); col3_frame.rowconfigure(3, weight=1) # Pesos originales
        col3_frame.columnconfigure(0, weight=1)

        right_notebook_frame = ttk.Frame(col3_frame); right_notebook_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        right_notebook_frame.rowconfigure(0, weight=1); right_notebook_frame.columnconfigure(0, weight=1)
        self.main_notebook = ttk.Notebook(right_notebook_frame); self.main_notebook.grid(row=0, column=0, sticky='nsew')

        self.case_details_tab = ttk.Frame(self.main_notebook, padding="10"); self.main_notebook.add(self.case_details_tab, text='Detalles del Caso')
        self.case_details_tab.columnconfigure(1, weight=1); self.case_details_tab.rowconfigure(5, weight=1)
        ttk.Label(self.case_details_tab, text="Carátula:").grid(row=0, column=0, sticky=tk.W, pady=2); self.caratula_lbl = ttk.Label(self.case_details_tab, text="", wraplength=300); self.caratula_lbl.grid(row=0, column=1, sticky=tk.EW, pady=2)
        ttk.Label(self.case_details_tab, text="Expediente:").grid(row=1, column=0, sticky=tk.W, pady=2); self.expediente_lbl = ttk.Label(self.case_details_tab, text=""); self.expediente_lbl.grid(row=1, column=1, sticky=tk.EW, pady=2)
        ttk.Label(self.case_details_tab, text="Juzgado:").grid(row=2, column=0, sticky=tk.W, pady=2); self.juzgado_lbl = ttk.Label(self.case_details_tab, text="", wraplength=300); self.juzgado_lbl.grid(row=2, column=1, sticky=tk.EW, pady=2)
        ttk.Label(self.case_details_tab, text="Jurisdicción:").grid(row=3, column=0, sticky=tk.W, pady=2); self.jurisdiccion_lbl = ttk.Label(self.case_details_tab, text="", wraplength=300); self.jurisdiccion_lbl.grid(row=3, column=1, sticky=tk.EW, pady=2)
        ttk.Label(self.case_details_tab, text="Etapa Procesal:").grid(row=4, column=0, sticky=tk.W, pady=2); self.etapa_lbl = ttk.Label(self.case_details_tab, text="", wraplength=300); self.etapa_lbl.grid(row=4, column=1, sticky=tk.EW, pady=2)
        ttk.Label(self.case_details_tab, text="Notas:").grid(row=5, column=0, sticky=tk.NW, pady=2); self.notas_text = tk.Text(self.case_details_tab, height=4, wrap=tk.WORD, state=tk.DISABLED); self.notas_text.grid(row=5, column=1, sticky=tk.NSEW, pady=2); notas_scrollbar = ttk.Scrollbar(self.case_details_tab, orient=tk.VERTICAL, command=self.notas_text.yview); notas_scrollbar.grid(row=5, column=2, sticky=tk.NS, pady=2); self.notas_text['yscrollcommand'] = notas_scrollbar.set
        inactivity_frame = ttk.LabelFrame(self.case_details_tab, text="Alarma Inactividad", padding="5"); inactivity_frame.grid(row=6, column=0, columnspan=3, sticky=tk.EW, pady=5); inactivity_frame.columnconfigure(1, weight=1)
        ttk.Label(inactivity_frame, text="Habilitada:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=1); self.inactivity_enabled_lbl = ttk.Label(inactivity_frame, text=""); self.inactivity_enabled_lbl.grid(row=0, column=1, sticky=tk.W, pady=1)
        ttk.Label(inactivity_frame, text="Umbral Días:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=1); self.inactivity_threshold_lbl = ttk.Label(inactivity_frame, text=""); self.inactivity_threshold_lbl.grid(row=1, column=1, sticky=tk.W, pady=1)

        self.documents_tab = ttk.Frame(self.main_notebook, padding="10"); self.main_notebook.add(self.documents_tab, text='Documentación')
        self.documents_tab.columnconfigure(0, weight=1); self.documents_tab.rowconfigure(3, weight=1)
        ttk.Label(self.documents_tab, text="Carpeta Documentos:").grid(row=0, column=0, pady=(0, 5), sticky=tk.W)
        folder_frame = ttk.Frame(self.documents_tab); folder_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 5)); folder_frame.columnconfigure(0, weight=1)
        self.folder_path_lbl = ttk.Label(folder_frame, text="Selecciona un caso", relief=tk.SUNKEN, anchor=tk.W, wraplength=250); self.folder_path_lbl.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        self.select_folder_btn = ttk.Button(folder_frame, text="...", command=self.select_case_folder, state=tk.DISABLED, width=3); self.select_folder_btn.grid(row=0, column=1, sticky=tk.E, padx=(0,5))
        self.open_folder_btn = ttk.Button(folder_frame, text="Abrir", command=self.open_case_folder, state=tk.DISABLED, width=5); self.open_folder_btn.grid(row=0, column=2, sticky=tk.E)
        ttk.Label(self.documents_tab, text="Archivos:").grid(row=2, column=0, pady=(0, 5), sticky=tk.NW)
        documents_tree_frame = ttk.Frame(self.documents_tab); documents_tree_frame.grid(row=3, column=0, sticky='nsew'); documents_tree_frame.columnconfigure(0, weight=1); documents_tree_frame.rowconfigure(0, weight=1)
        self.document_tree = ttk.Treeview(documents_tree_frame, columns=('Nombre', 'Tamaño', 'Fecha Mod.'), show='headings'); self.document_tree.heading('Nombre', text='Nombre'); self.document_tree.heading('Tamaño', text='Tamaño'); self.document_tree.heading('Fecha Mod.', text='Modificado'); self.document_tree.column('Tamaño', width=80, stretch=tk.NO, anchor=tk.E); self.document_tree.column('Fecha Mod.', width=120, stretch=tk.NO)
        document_scrollbar = ttk.Scrollbar(documents_tree_frame, orient=tk.VERTICAL, command=self.document_tree.yview); self.document_tree.configure(yscrollcommand=document_scrollbar.set); document_scrollbar.pack(side=tk.RIGHT, fill=tk.Y); self.document_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.partes_tab = ttk.Frame(self.main_notebook, padding="10"); self.main_notebook.add(self.partes_tab, text='Partes')
        ttk.Label(self.partes_tab, text="Gestión de Partes Intervinientes (Próximamente).").pack()

        # --- Pestaña de Seguimiento ---
        self.seguimiento_tab_frame = SeguimientoTab(self.main_notebook, self) # 'self' es CRMLegalApp (app_controller)
        self.main_notebook.add(self.seguimiento_tab_frame, text="Seguimiento")

        # --- Área de audiencias (lista y detalles) ---
        # El layout original para audiencias se mantiene, pero ahora el notebook está encima.
        audiencia_area_frame = ttk.Frame(col3_frame)
        audiencia_area_frame.grid(row=1, column=0, sticky='nsew', pady=5) # Fila 1 de col3_frame
        audiencia_area_frame.columnconfigure(0, weight=1) # Columna para lista+botones (0)
        audiencia_area_frame.columnconfigure(1, weight=1) # Columna para detalles audiencia (1)
        audiencia_area_frame.rowconfigure(0, weight=1)

        audiencias_list_with_actions_frame = ttk.Frame(audiencia_area_frame)
        audiencias_list_with_actions_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        audiencias_list_with_actions_frame.rowconfigure(0, weight=1); audiencias_list_with_actions_frame.rowconfigure(1, weight=0)
        audiencias_list_with_actions_frame.columnconfigure(0, weight=1)

        agenda_list_frame = ttk.LabelFrame(audiencias_list_with_actions_frame, text="Audiencias del Día", padding="5")
        agenda_list_frame.grid(row=0, column=0, sticky='nsew', pady=(0,5))
        agenda_list_frame.columnconfigure(0, weight=1); agenda_list_frame.rowconfigure(0, weight=1)
        agenda_cols = ("ID", "Hora", "Detalle", "Caso Asociado", "Link")
        self.audiencia_tree = ttk.Treeview(agenda_list_frame, columns=agenda_cols, show='headings', selectmode="browse")
        self.audiencia_tree.heading("ID", text="ID"); self.audiencia_tree.heading("Hora", text="Hora"); self.audiencia_tree.heading("Detalle", text="Detalle"); self.audiencia_tree.heading("Caso Asociado", text="Caso"); self.audiencia_tree.heading("Link", text="Link")
        self.audiencia_tree.column("ID", width=30, stretch=tk.NO, anchor=tk.CENTER); self.audiencia_tree.column("Hora", width=50, stretch=tk.NO, anchor=tk.CENTER); self.audiencia_tree.column("Detalle", width=150, stretch=True); self.audiencia_tree.column("Caso Asociado", width=120, stretch=True); self.audiencia_tree.column("Link", width=100, stretch=True)
        agenda_scroll_y = ttk.Scrollbar(agenda_list_frame, orient=tk.VERTICAL, command=self.audiencia_tree.yview); self.audiencia_tree.configure(yscrollcommand=agenda_scroll_y.set)
        agenda_scroll_y.grid(row=0, column=1, sticky='ns'); self.audiencia_tree.grid(row=0, column=0, sticky='nsew')
        self.audiencia_tree.bind('<<TreeviewSelect>>', self.on_audiencia_tree_select)
        self.audiencia_tree.bind("<Double-1>", self.abrir_link_audiencia_seleccionada)

        audiencia_actions_frame = ttk.Frame(audiencias_list_with_actions_frame); audiencia_actions_frame.grid(row=1, column=0, sticky='ew', pady=5)
        self.edit_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Editar", command=self.editar_audiencia_seleccionada, state=tk.DISABLED); self.edit_audiencia_btn.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        self.delete_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Eliminar", command=self.eliminar_audiencia_seleccionada, state=tk.DISABLED); self.delete_audiencia_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.share_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Compartir", command=self.mostrar_menu_compartir_audiencia, state=tk.DISABLED); self.share_audiencia_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.open_link_audiencia_btn = ttk.Button(audiencia_actions_frame, text="Abrir Link", command=self.abrir_link_audiencia_seleccionada, state=tk.DISABLED); self.open_link_audiencia_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        audiencia_details_frame = ttk.LabelFrame(audiencia_area_frame, text="Detalles Completos Audiencia", padding="5")
        audiencia_details_frame.grid(row=0, column=1, sticky='nsew', pady=(0,0))
        audiencia_details_frame.columnconfigure(0, weight=1); audiencia_details_frame.rowconfigure(0, weight=1)
        self.audiencia_details_text = tk.Text(audiencia_details_frame, height=5, wrap=tk.WORD, state=tk.DISABLED, background=self.root.cget('bg'))
        audiencia_details_scroll = ttk.Scrollbar(audiencia_details_frame, orient=tk.VERTICAL, command=self.audiencia_details_text.yview); self.audiencia_details_text.configure(yscrollcommand=audiencia_details_scroll.set)
        audiencia_details_scroll.grid(row=0, column=1, sticky='ns'); self.audiencia_details_text.grid(row=0, column=0, sticky='nsew')

        # --- Estado Inicial de Pestañas y Botones ---
        self.main_notebook.tab(self.case_details_tab, state='disabled')
        self.main_notebook.tab(self.documents_tab, state='disabled')
        self.main_notebook.tab(self.partes_tab, state='disabled')
        self.main_notebook.tab(self.seguimiento_tab_frame, state='disabled') # Pestaña de seguimiento deshabilitada
        self.seguimiento_tab_frame.set_add_button_state(tk.DISABLED) # Botón en pestaña seguimiento deshabilitado

        print("Widgets creados con la estructura de 3 columnas y pestaña de Seguimiento.")

            # --- Métodos de Lógica CRM (Clientes y Casos) ---
    def load_clients(self):
        for i in self.client_tree.get_children(): self.client_tree.delete(i)
        clients = db.get_clients()
        for client in clients: self.client_tree.insert('', tk.END, values=(client['id'], client['nombre']), iid=str(client['id']))

        self.selected_client = None
        self.selected_case = None
        
        self.clear_client_details()
        self.clear_case_list() 
        # clear_case_details es llamado por clear_case_list o explícitamente
        
        self.disable_client_buttons()
        # disable_case_buttons y disable_detail_tabs_for_case son llamados por clear_case_details

        if hasattr(self, 'seguimiento_tab_frame'):
            self.main_notebook.tab(self.seguimiento_tab_frame, state='disabled')
            self.seguimiento_tab_frame.load_actividades(None)
        
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
                self.load_cases_by_client(self.selected_client['id'])
                self.enable_client_buttons()
            else:
                self.selected_client = None
                self.clear_client_details(); self.clear_case_list()
                self.disable_client_buttons()
                if hasattr(self, 'seguimiento_tab_frame'):
                     self.main_notebook.tab(self.seguimiento_tab_frame, state='disabled')
                     self.seguimiento_tab_frame.load_actividades(None)
        else:
            self.selected_client = None
            self.clear_client_details(); self.clear_case_list()
            self.disable_client_buttons()
            if hasattr(self, 'seguimiento_tab_frame'):
                 self.main_notebook.tab(self.seguimiento_tab_frame, state='disabled')
                 self.seguimiento_tab_frame.load_actividades(None)
        self.update_add_audiencia_button_state()

    def display_client_details(self, client_data):
        if client_data:
            self.client_detail_name_lbl.config(text=client_data.get('nombre', 'N/A'))
            self.client_detail_address_lbl.config(text=client_data.get('direccion', 'N/A'))
            self.client_detail_email_lbl.config(text=client_data.get('email', 'N/A'))
            self.client_detail_whatsapp_lbl.config(text=client_data.get('whatsapp', 'N/A'))
        else: self.clear_client_details()

    def clear_client_details(self):
        self.client_detail_name_lbl.config(text=""); self.client_detail_address_lbl.config(text="")
        self.client_detail_email_lbl.config(text=""); self.client_detail_whatsapp_lbl.config(text="")

    def enable_client_buttons(self):
        self.edit_client_btn.config(state=tk.NORMAL); self.delete_client_btn.config(state=tk.NORMAL)

    def disable_client_buttons(self):
        self.edit_client_btn.config(state=tk.DISABLED); self.delete_client_btn.config(state=tk.DISABLED)

    def load_cases_by_client(self, client_id):
        self.clear_case_list() # Limpia el treeview de casos
        self.selected_case = None 
        self.clear_case_details() # Limpia detalles, deshabilita botones y pestañas de caso (incluida seguimiento)

        cases = db.get_cases_by_client(client_id)
        for case in cases:
            num_anio = f"{case.get('numero_expediente','?')}/{case.get('anio_caratula','?')}"
            self.case_tree.insert('', tk.END, values=(case['id'], num_anio, case['caratula']), iid=str(case['id']))

        self.add_case_btn.config(state=tk.NORMAL if self.selected_client else tk.DISABLED)
        # No es necesario llamar a self.seguimiento_tab_frame.load_actividades(None) aquí,
        # porque clear_case_details ya lo hace a través de disable_detail_tabs_for_case.
        self.update_add_audiencia_button_state()


    def clear_case_list(self):
        for i in self.case_tree.get_children(): self.case_tree.delete(i)
        # Es buena práctica también limpiar los detalles del caso si se limpia la lista
        # y resetear la selección de caso.
        self.selected_case = None
        self.clear_case_details()


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
                print(f"Caso seleccionado ID: {self.selected_case['id']}")
                self.display_case_details(self.selected_case)
                self.load_case_documents(self.selected_case.get('ruta_carpeta', ''))
                self.enable_case_buttons()
                self.enable_detail_tabs_for_case() # Habilita todas las pestañas de detalles

                if hasattr(self, 'seguimiento_tab_frame'):
                    self.seguimiento_tab_frame.load_actividades(self.selected_case['id'])
                    self.seguimiento_tab_frame.set_add_button_state(tk.NORMAL)
            else: # Error al cargar el caso o ID inválido
                self.selected_case = None
                self.clear_case_details() # Esto limpia y deshabilita todo lo relacionado al caso
        else: # Deselección en el treeview de casos
            self.selected_case = None
            self.clear_case_details() # Limpia y deshabilita
        self.update_add_audiencia_button_state()


    def display_case_details(self, case_data):
        if case_data:
            self.caratula_lbl.config(text=case_data.get('caratula', 'N/A'))
            exp = f"{case_data.get('numero_expediente', 'S/N')}/{case_data.get('anio_caratula', 'S/A')}"
            self.expediente_lbl.config(text=exp)
            self.juzgado_lbl.config(text=case_data.get('juzgado', 'N/A'))
            self.jurisdiccion_lbl.config(text=case_data.get('jurisdiccion', 'N/A'))
            self.etapa_lbl.config(text=case_data.get('etapa_procesal', 'N/A'))
            self.notas_text.config(state=tk.NORMAL); self.notas_text.delete('1.0', tk.END); self.notas_text.insert('1.0', case_data.get('notas', '')); self.notas_text.config(state=tk.DISABLED)
            inactivity_enabled = "Sí" if case_data.get('inactivity_enabled') else "No"
            inactivity_threshold = case_data.get('inactivity_threshold_days', 30)
            self.inactivity_enabled_lbl.config(text=inactivity_enabled); self.inactivity_threshold_lbl.config(text=str(inactivity_threshold))
            folder_path = case_data.get('ruta_carpeta', ''); self.folder_path_lbl.config(text=folder_path if folder_path else "Carpeta no asignada")
            self.select_folder_btn.config(state=tk.NORMAL); self.open_folder_btn.config(state=tk.NORMAL if folder_path and os.path.exists(folder_path) else tk.DISABLED)
        # No hay 'else: self.clear_case_details()' aquí, porque display_case_details
        # solo se llama si case_data es válido. La limpieza se hace en on_case_select o clear_case_list.


    def clear_case_details(self):
        self.caratula_lbl.config(text=""); self.expediente_lbl.config(text=""); self.juzgado_lbl.config(text="")
        self.jurisdiccion_lbl.config(text=""); self.etapa_lbl.config(text="")
        self.notas_text.config(state=tk.NORMAL); self.notas_text.delete('1.0', tk.END); self.notas_text.config(state=tk.DISABLED)
        self.inactivity_enabled_lbl.config(text=""); self.inactivity_threshold_lbl.config(text="")
        self.folder_path_lbl.config(text="Selecciona un caso para ver/asignar carpeta");
        self.select_folder_btn.config(state=tk.DISABLED); self.open_folder_btn.config(state=tk.DISABLED)
        
        self.clear_document_list()
        self.disable_case_buttons()
        self.disable_detail_tabs_for_case() # Esto deshabilita todas las pestañas, incluida Seguimiento.
                                            # Y dentro de disable_detail_tabs_for_case, se limpia SeguimientoTab.


    def enable_case_buttons(self):
        self.edit_case_btn.config(state=tk.NORMAL); self.delete_case_btn.config(state=tk.NORMAL)

    def disable_case_buttons(self):
        self.edit_case_btn.config(state=tk.DISABLED); self.delete_case_btn.config(state=tk.DISABLED)

    def enable_detail_tabs_for_case(self):
        self.main_notebook.tab(self.case_details_tab, state='normal')
        self.main_notebook.tab(self.documents_tab, state='normal')
        self.main_notebook.tab(self.partes_tab, state='normal')
        if hasattr(self, 'seguimiento_tab_frame'):
            self.main_notebook.tab(self.seguimiento_tab_frame, state='normal')
        if self.selected_case:
             self.main_notebook.select(self.case_details_tab)

    def disable_detail_tabs_for_case(self):
        self.main_notebook.tab(self.case_details_tab, state='disabled')
        self.main_notebook.tab(self.documents_tab, state='disabled')
        self.main_notebook.tab(self.partes_tab, state='disabled')
        if hasattr(self, 'seguimiento_tab_frame'):
            self.main_notebook.tab(self.seguimiento_tab_frame, state='disabled')
            self.seguimiento_tab_frame.load_actividades(None) # Limpia y deshabilita botón
            # self.seguimiento_tab_frame.set_add_button_state(tk.DISABLED) # ya lo hace load_actividades(None)

    def open_client_dialog(self, client_id=None):
        is_edit = client_id is not None; dialog = tk.Toplevel(self.root)
        dialog.title("Editar Cliente" if is_edit else "Agregar Cliente"); dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding="15"); frame.pack(fill=tk.BOTH, expand=True); name_var = tk.StringVar(); address_var = tk.StringVar(); email_var = tk.StringVar(); whatsapp_var = tk.StringVar()
        if is_edit:
            client_data = db.get_client_by_id(client_id)
            if client_data: name_var.set(client_data.get('nombre', '')); address_var.set(client_data.get('direccion', '')); email_var.set(client_data.get('email', '')); whatsapp_var.set(client_data.get('whatsapp', ''))
            else: messagebox.showerror("Error", "No se pudo cargar datos.", parent=dialog); dialog.destroy(); return
        ttk.Label(frame, text="Nombre:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5); name_entry = ttk.Entry(frame, textvariable=name_var, width=40); name_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Label(frame, text="Dirección:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=5); address_entry = ttk.Entry(frame, textvariable=address_var, width=40); address_entry.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Label(frame, text="Email:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5); email_entry = ttk.Entry(frame, textvariable=email_var, width=40); email_entry.grid(row=2, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Label(frame, text="WhatsApp:").grid(row=3, column=0, sticky=tk.W, pady=5, padx=5); whatsapp_entry = ttk.Entry(frame, textvariable=whatsapp_var, width=40); whatsapp_entry.grid(row=3, column=1, sticky=tk.EW, pady=5, padx=5)
        frame.columnconfigure(1, weight=1); button_frame = ttk.Frame(frame); button_frame.grid(row=4, column=0, columnspan=2, pady=15)
        ttk.Button(button_frame, text="Guardar", command=lambda: self.save_client(client_id, name_var.get(), address_var.get(), email_var.get(), whatsapp_var.get(), dialog)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        name_entry.focus_set(); self.root.wait_window(dialog)

    def save_client(self, client_id, nombre, direccion, email, whatsapp, dialog):
        if not nombre.strip(): messagebox.showwarning("Advertencia", "El nombre no puede estar vacío.", parent=dialog); return
        success = False
        if client_id is None:
            new_id = db.add_client(nombre.strip(), direccion.strip(), email.strip(), whatsapp.strip())
            success = new_id is not None; msg_op = "agregado"
        else:
            success = db.update_client(client_id, nombre.strip(), direccion.strip(), email.strip(), whatsapp.strip())
            msg_op = "actualizado"
            if success and self.selected_client and self.selected_client['id'] == client_id:
                self.selected_client = db.get_client_by_id(client_id)
                self.display_client_details(self.selected_client)
        if success: messagebox.showinfo("Éxito", f"Cliente {msg_op}.", parent=dialog); dialog.destroy(); self.load_clients()
        else: messagebox.showerror("Error", f"No se pudo {msg_op} el cliente.", parent=dialog)

    def delete_client(self):
        if not self.selected_client: messagebox.showwarning("Advertencia", "Selecciona un cliente."); return
        client_id = self.selected_client['id']; client_name = self.selected_client.get('nombre', f'ID {client_id}')
        if messagebox.askyesno("Confirmar", f"¿Eliminar cliente '{client_name}' y TODOS sus casos y audiencias?", parent=self.root):
            if db.delete_client(client_id):
                messagebox.showinfo("Éxito", "Cliente eliminado.", parent=self.root)
                self.load_clients()
                self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario()
            else: messagebox.showerror("Error", "No se pudo eliminar el cliente.", parent=self.root)

    def open_case_dialog(self, case_id=None):
        is_edit = case_id is not None; client_context_id = None; client_context_name = "N/A"
        if is_edit:
            case_data = db.get_case_by_id(case_id)
            if not case_data: messagebox.showerror("Error", "No se pudieron cargar los datos del caso.", parent=self.root); return
            dialog_title = f"Editar Caso ID: {case_id}"; client_context_id = case_data['cliente_id']
            client_info = db.get_client_by_id(client_context_id)
            if client_info: client_context_name = client_info.get('nombre', f"ID {client_context_id}")
        else:
            if not self.selected_client: messagebox.showwarning("Advertencia", "Selecciona un cliente para agregarle un caso.", parent=self.root); return
            client_context_id = self.selected_client['id']; client_context_name = self.selected_client.get('nombre', f"ID {client_context_id}")
            dialog_title = f"Agregar Caso para: {client_context_name}"; case_data = {}
        dialog = tk.Toplevel(self.root); dialog.title(dialog_title); dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding="15"); frame.pack(fill=tk.BOTH, expand=True); frame.columnconfigure(1, weight=1)
        caratula_var = tk.StringVar(value=case_data.get('caratula', '')); num_exp_var = tk.StringVar(value=case_data.get('numero_expediente', '')); anio_car_var = tk.StringVar(value=case_data.get('anio_caratula', '')); juzgado_var = tk.StringVar(value=case_data.get('juzgado', '')); jurisdiccion_var = tk.StringVar(value=case_data.get('jurisdiccion', '')); etapa_var = tk.StringVar(value=case_data.get('etapa_procesal', '')); notas_initial = case_data.get('notas', ''); ruta_var = tk.StringVar(value=case_data.get('ruta_carpeta', '')); inact_days_var = tk.IntVar(value=case_data.get('inactivity_threshold_days', 30)); inact_enabled_var = tk.IntVar(value=case_data.get('inactivity_enabled', 1))
        ttk.Label(frame, text="Cliente:").grid(row=0, column=0, sticky=tk.W, pady=3, padx=5); ttk.Label(frame, text=f"{client_context_name} (ID: {client_context_id})").grid(row=0, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text="*Carátula:").grid(row=1, column=0, sticky=tk.W, pady=3, padx=5); caratula_entry = ttk.Entry(frame, textvariable=caratula_var, width=50); caratula_entry.grid(row=1, column=1, sticky=tk.EW, pady=3, padx=5)
        ttk.Label(frame, text="Núm. Exp.:").grid(row=2, column=0, sticky=tk.W, pady=3, padx=5); ttk.Entry(frame, textvariable=num_exp_var, width=20).grid(row=2, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text="Año Carát.:").grid(row=3, column=0, sticky=tk.W, pady=3, padx=5); ttk.Entry(frame, textvariable=anio_car_var, width=10).grid(row=3, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text="Juzgado:").grid(row=4, column=0, sticky=tk.W, pady=3, padx=5); ttk.Entry(frame, textvariable=juzgado_var, width=50).grid(row=4, column=1, sticky=tk.EW, pady=3, padx=5)
        ttk.Label(frame, text="Jurisdicción:").grid(row=5, column=0, sticky=tk.W, pady=3, padx=5); ttk.Entry(frame, textvariable=jurisdiccion_var, width=50).grid(row=5, column=1, sticky=tk.EW, pady=3, padx=5)
        ttk.Label(frame, text="Etapa Procesal:").grid(row=6, column=0, sticky=tk.W, pady=3, padx=5); ttk.Entry(frame, textvariable=etapa_var, width=50).grid(row=6, column=1, sticky=tk.EW, pady=3, padx=5)
        ttk.Label(frame, text="Notas:").grid(row=7, column=0, sticky=tk.NW, pady=3, padx=5); notas_frame = ttk.Frame(frame); notas_frame.grid(row=7, column=1, sticky=tk.NSEW, pady=3, padx=5); notas_frame.rowconfigure(0, weight=1); notas_frame.columnconfigure(0, weight=1); case_notas_text = tk.Text(notas_frame, height=4, wrap=tk.WORD); case_notas_text.grid(row=0, column=0, sticky='nsew'); case_notas_scroll = ttk.Scrollbar(notas_frame, orient=tk.VERTICAL, command=case_notas_text.yview); case_notas_scroll.grid(row=0, column=1, sticky='ns'); case_notas_text['yscrollcommand'] = case_notas_scroll.set; case_notas_text.insert('1.0', notas_initial); frame.rowconfigure(7, weight=1)
        ttk.Label(frame, text="Ruta Carpeta Docs:").grid(row=8, column=0, sticky=tk.W, pady=3, padx=5); ruta_frame = ttk.Frame(frame); ruta_frame.grid(row=8, column=1, sticky=tk.EW, pady=3, padx=5); ruta_frame.columnconfigure(0, weight=1); ruta_entry = ttk.Entry(ruta_frame, textvariable=ruta_var, width=40); ruta_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0,5))
        inact_frame = ttk.LabelFrame(frame, text="Alarma Inactividad"); inact_frame.grid(row=9, column=0, columnspan=2, sticky=tk.EW, pady=10, padx=5); ttk.Checkbutton(inact_frame, text="Habilitada", variable=inact_enabled_var).pack(side=tk.LEFT, padx=5); ttk.Label(inact_frame, text="Umbral (días):").pack(side=tk.LEFT, padx=5); ttk.Spinbox(inact_frame, from_=1, to=365, width=5, textvariable=inact_days_var).pack(side=tk.LEFT, padx=5)
        button_frame = ttk.Frame(frame); button_frame.grid(row=10, column=0, columnspan=2, pady=15)
        ttk.Button(button_frame, text="Guardar", command=lambda: self.save_case(case_id, client_context_id, caratula_var.get(), num_exp_var.get(), anio_car_var.get(), juzgado_var.get(), jurisdiccion_var.get(), etapa_var.get(), case_notas_text.get("1.0", tk.END).strip(), ruta_var.get(), inact_days_var.get(), inact_enabled_var.get(), dialog)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        caratula_entry.focus_set(); self.root.wait_window(dialog)

    def save_case(self, case_id, cliente_id, caratula, num_exp, anio_car, juzgado, juris, etapa, notas, ruta, inact_days, inact_enabled, dialog):
        if not caratula.strip(): messagebox.showwarning("Advertencia", "La carátula del caso no puede estar vacía.", parent=dialog); return
        success = False
        if case_id is None:
            new_id = db.add_case(cliente_id, caratula.strip(), num_exp.strip(), anio_car.strip(), juzgado.strip(), juris.strip(), etapa.strip(), notas.strip(), ruta.strip(), inact_days, inact_enabled)
            success = new_id is not None; msg_op = "agregado"
        else:
            success = db.update_case(case_id, caratula.strip(), num_exp.strip(), anio_car.strip(), juzgado.strip(), juris.strip(), etapa.strip(), notas.strip(), ruta.strip(), inact_days, inact_enabled)
            msg_op = "actualizado"
            if success and self.selected_case and self.selected_case['id'] == case_id:
                self.selected_case = db.get_case_by_id(case_id)
                self.display_case_details(self.selected_case)
                self.load_case_documents(self.selected_case.get('ruta_carpeta', ''))
        if success:
            messagebox.showinfo("Éxito", f"Caso {msg_op} con éxito.", parent=dialog); dialog.destroy()
            if self.selected_client: self.load_cases_by_client(self.selected_client['id'])
        else: messagebox.showerror("Error", f"No se pudo {msg_op} el caso.", parent=dialog)

    def delete_case(self):
        if not self.selected_case: messagebox.showwarning("Advertencia", "Selecciona un caso para eliminar.", parent=self.root); return
        case_id = self.selected_case['id']; case_caratula = self.selected_case.get('caratula', f'ID {case_id}')
        if messagebox.askyesno("Confirmar Eliminación", f"¿Eliminar caso '{case_caratula}' y sus audiencias/partes relacionadas?", parent=self.root):
            if db.delete_case(case_id):
                messagebox.showinfo("Éxito", "Caso eliminado con éxito.", parent=self.root)
                if self.selected_client: self.load_cases_by_client(self.selected_client['id'])
                else: self.clear_case_list(); self.clear_case_details()
                self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario()
            else: messagebox.showerror("Error", "No se pudo eliminar el caso.", parent=self.root)

    def select_case_folder(self):
        if not self.selected_case: messagebox.showwarning("Advertencia", "Selecciona un caso.", parent=self.root); return
        initial_dir = self.selected_case.get('ruta_carpeta') or os.path.expanduser("~")
        folder_selected = filedialog.askdirectory(initialdir=initial_dir, title="Seleccionar Carpeta Docs", parent=self.root)
        if folder_selected:
            case_id = self.selected_case['id']
            if db.update_case_folder(case_id, folder_selected):
                self.selected_case['ruta_carpeta'] = folder_selected
                self.folder_path_lbl.config(text=folder_selected); self.open_folder_btn.config(state=tk.NORMAL)
                self.load_case_documents(folder_selected)
                messagebox.showinfo("Éxito", "Carpeta asignada.", parent=self.root)
            else: messagebox.showerror("Error", "No se pudo guardar la ruta.", parent=self.root)

    def open_case_folder(self):
        if not self.selected_case or not self.selected_case.get('ruta_carpeta'): messagebox.showwarning("Advertencia", "Selecciona caso con carpeta.", parent=self.root); return
        folder_path = self.selected_case['ruta_carpeta']
        if folder_path and os.path.isdir(folder_path):
            try:
                if sys.platform == "win32": os.startfile(folder_path)
                elif sys.platform == "darwin": subprocess.call(["open", folder_path])
                else: subprocess.call(["xdg-open", folder_path])
            except Exception as e: messagebox.showerror("Error", f"No se pudo abrir:\n{e}", parent=self.root)
        else: messagebox.showwarning("Advertencia", "Carpeta no existe o inválida.", parent=self.root); self.open_folder_btn.config(state=tk.DISABLED)

    def load_case_documents(self, folder_path):
        self.clear_document_list()
        if folder_path and os.path.isdir(folder_path):
            try:
                for entry in os.scandir(folder_path):
                    if entry.is_file():
                        try:
                            stat_info = entry.stat(); size_bytes = stat_info.st_size
                            if size_bytes < 1024: size_display = f"{size_bytes} B"
                            elif size_bytes < 1024**2: size_display = f"{size_bytes/1024:.1f} KB"
                            elif size_bytes < 1024**3: size_display = f"{size_bytes/1024**2:.1f} MB"
                            else: size_display = f"{size_bytes/1024**3:.1f} GB"
                            mod_time = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M')
                            self.document_tree.insert('', tk.END, values=(entry.name, size_display, mod_time), iid=entry.path)
                        except OSError as e: print(f"Warn: No se pudo leer info de {entry.path}: {e}")
                        except Exception as e: print(f"Error procesando archivo {entry.path}: {e}")
            except OSError as e: print(f"Error listando dir {folder_path}: {e}"); self.document_tree.insert('', tk.END, values=(f"Error al leer: {e}", "", ""), iid="error_dir")
            except Exception as e: print(f"Error inesperado listando {folder_path}: {e}"); self.document_tree.insert('', tk.END, values=("Error inesperado", "", ""), iid="error_inesperado")
        elif self.selected_case: self.document_tree.insert('', tk.END, values=("Carpeta no asignada o no encontrada.", "", ""), iid="no_folder")

    def clear_document_list(self):
        for i in self.document_tree.get_children(): self.document_tree.delete(i)

    # --- Métodos para SeguimientoTab ---
    def open_actividad_dialog_for_seguimiento_tab(self, caso_id):
        if not caso_id:
            messagebox.showwarning("Advertencia", "No hay un caso seleccionado para agregar actividad.", parent=self.root)
            return
        current_case_info = db.get_case_by_id(caso_id)
        case_display_name = current_case_info.get('caratula', f"ID {caso_id}") if current_case_info else f"ID {caso_id}"
        dialog = Toplevel(self.root); dialog.title(f"Agregar Actividad a: {case_display_name[:50]}"); dialog.transient(self.root); dialog.grab_set(); dialog.resizable(False, False)
        parent_x = self.root.winfo_x(); parent_y = self.root.winfo_y(); parent_width = self.root.winfo_width(); parent_height = self.root.winfo_height()
        dialog_width = 450; dialog_height = 380; x = parent_x + (parent_width - dialog_width) // 2; y = parent_y + (parent_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        main_frame = ttk.Frame(dialog, padding="15 15 15 15"); main_frame.pack(expand=True, fill=tk.BOTH); main_frame.columnconfigure(1, weight=1)
        ttk.Label(main_frame, text="*Tipo de Actividad:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5), padx=5)
        tipos_actividad = ["Llamada Telefónica", "Reunión", "Correo Electrónico Enviado", "Correo Electrónico Recibido", "Escrito Presentado", "Cédula/Notificación Recibida", "Movimiento del Expediente", "Análisis de Documentación", "Preparación de Audiencia", "Asistencia a Audiencia", "Consulta con Colega", "Investigación Jurídica", "Redacción de Documento", "Tarea Administrativa", "Nota Interna", "Otro Evento Relevante"]
        tipo_actividad_var = tk.StringVar(); tipo_actividad_combo = ttk.Combobox(main_frame, textvariable=tipo_actividad_var, values=tipos_actividad, width=37, state="readonly")
        tipo_actividad_combo.grid(row=0, column=1, sticky=tk.EW, pady=(0, 10), padx=5)
        if tipos_actividad: tipo_actividad_combo.current(0)
        ttk.Label(main_frame, text="*Descripción Detallada:").grid(row=2, column=0, sticky=tk.NW, pady=(5, 5), padx=5)
        desc_outer_frame = ttk.Frame(main_frame); desc_outer_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0,10), padx=5); desc_outer_frame.rowconfigure(0, weight=1); desc_outer_frame.columnconfigure(0, weight=1)
        descripcion_text = tk.Text(desc_outer_frame, height=10, width=50, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1); descripcion_text.grid(row=0, column=0, sticky="nsew")
        desc_scrollbar = ttk.Scrollbar(desc_outer_frame, orient=tk.VERTICAL, command=descripcion_text.yview); descripcion_text.configure(yscrollcommand=desc_scrollbar.set); desc_scrollbar.grid(row=0, column=1, sticky="ns")
        main_frame.rowconfigure(3, weight=1)
        buttons_frame = ttk.Frame(main_frame); buttons_frame.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=(10, 0))
        def on_save_actividad():
            tipo = tipo_actividad_var.get(); descripcion = descripcion_text.get("1.0", tk.END).strip()
            if not tipo: messagebox.showerror("Error de Validación", "El tipo de actividad no puede estar vacío.", parent=dialog); tipo_actividad_combo.focus_set(); return
            if not descripcion: messagebox.showerror("Error de Validación", "La descripción no puede estar vacía.", parent=dialog); descripcion_text.focus_set(); return
            self._save_new_actividad(caso_id, tipo, descripcion); dialog.destroy()
        save_button = ttk.Button(buttons_frame, text="Guardar Actividad", command=on_save_actividad); save_button.pack(side=tk.RIGHT, padx=(5,0)) # Accent.TButton
        cancel_button = ttk.Button(buttons_frame, text="Cancelar", command=dialog.destroy); cancel_button.pack(side=tk.RIGHT, padx=(0,10))
        tipo_actividad_combo.focus_set(); dialog.protocol("WM_DELETE_WINDOW", dialog.destroy); self.root.wait_window(dialog)

    def _save_new_actividad(self, caso_id, tipo_actividad, descripcion):
        fecha_hora_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        creado_por_usuario = None; referencia_doc = None
        print(f"Guardando actividad para caso ID {caso_id}: Tipo='{tipo_actividad}', Desc='{descripcion[:30]}...'")
        try:
            nuevo_id_actividad = db.add_actividad_caso(caso_id=caso_id, fecha_hora=fecha_hora_actual, tipo_actividad=tipo_actividad, descripcion=descripcion, creado_por=creado_por_usuario, referencia_documento=referencia_doc)
            if nuevo_id_actividad:
                messagebox.showinfo("Éxito", f"Actividad (ID: {nuevo_id_actividad}) agregada correctamente al caso.", parent=self.root)
                if hasattr(self, 'seguimiento_tab_frame'): self.seguimiento_tab_frame.load_actividades(caso_id)
            else: messagebox.showerror("Error de Base de Datos", "No se pudo guardar la actividad en la base de datos.\nEl ID devuelto fue None.", parent=self.root)
        except sqlite3.Error as e: messagebox.showerror("Error de Base de Datos", f"Ocurrió un error al intentar guardar la actividad:\n{e}", parent=self.root); print(f"Error SQLite al guardar actividad: {e}")
        except Exception as e: messagebox.showerror("Error Inesperado", f"Ocurrió un error inesperado al guardar la actividad:\n{e}", parent=self.root); print(f"Error general al guardar actividad: {e}")

    # --- Métodos de Lógica para la Agenda Global ---
    def marcar_dias_audiencias_calendario(self):
        self.agenda_cal.calevent_remove(tag='audiencia_marcador'); fechas = db.get_fechas_con_audiencias()
        for fecha_str in fechas:
            try:
                fecha_dt = datetime.datetime.strptime(fecha_str, "%Y-%m-%d").date()
                self.agenda_cal.calevent_create(fecha_dt, 'Audiencia', tags='audiencia_marcador')
            except ValueError: print(f"Advertencia: Formato de fecha inválido en la base de datos: {fecha_str}")
            except Exception as e: print(f"Error al marcar fecha {fecha_str} en calendario: {e}")

    def actualizar_lista_audiencias(self, event=None):
        if event: self.fecha_seleccionada_agenda = self.agenda_cal.get_date()
        for i in self.audiencia_tree.get_children(): self.audiencia_tree.delete(i)
        audiencias = db.get_audiencias_by_fecha(self.fecha_seleccionada_agenda)
        for aud in audiencias:
            hora = aud.get('hora', '--:--') or "--:--"; desc_full = aud.get('descripcion',''); desc_corta = (desc_full.split('\n')[0])[:60] + ('...' if len(desc_full) > 60 else '')
            caso_full = aud.get('caso_caratula', 'Caso Desconocido'); caso_corto = caso_full[:50] + ('...' if len(caso_full) > 50 else '')
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
            except (IndexError, ValueError, TypeError): print("Error: Selección de audiencia inválida."); self.audiencia_seleccionada_id = None; self.limpiar_detalles_audiencia(); self.deshabilitar_botones_audiencia()
        else: self.audiencia_seleccionada_id = None; self.limpiar_detalles_audiencia(); self.deshabilitar_botones_audiencia()

    def mostrar_detalles_audiencia(self, audiencia_id):
        audiencia = db.get_audiencia_by_id(audiencia_id); self.limpiar_detalles_audiencia(); self.audiencia_details_text.config(state=tk.NORMAL)
        if audiencia:
            hora = audiencia.get('hora') or "Sin hora especificada"; link = audiencia.get('link') or "Sin link"; rec_activo = "Sí" if audiencia.get('recordatorio_activo') else "No"; rec_minutos = f" ({audiencia.get('recordatorio_minutos', 15)} min antes)" if audiencia.get('recordatorio_activo') else ""
            caso_caratula = audiencia.get('caso_caratula', 'Caso Desconocido'); cliente_nombre = audiencia.get('cliente_nombre', 'Cliente Desconocido')
            texto_detalles = (f"**Audiencia ID:** {audiencia['id']}\n" f"**Cliente:** {cliente_nombre}\n" f"**Caso:** {caso_caratula} (ID: {audiencia['caso_id']})\n" f"------------------------------------\n" f"**Fecha:** {audiencia.get('fecha', 'N/A')}\n" f"**Hora:** {hora}\n\n" f"**Descripción:**\n{audiencia.get('descripcion', 'N/A')}\n\n" f"**Link:**\n{link}\n\n" f"**Recordatorio:** {rec_activo}{rec_minutos}")
            self.audiencia_details_text.insert('1.0', texto_detalles)
        else: self.audiencia_details_text.insert('1.0', "Detalles no disponibles o audiencia no encontrada.")
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

    def update_add_audiencia_button_state(self):
        self.add_audiencia_btn.config(state=tk.NORMAL if self.selected_case else tk.DISABLED)

    def abrir_link_audiencia_seleccionada(self, event=None):
        if not self.audiencia_seleccionada_id:
            if event: return
            else: messagebox.showinfo("Info", "Selecciona una audiencia con link primero.", parent=self.root); return
        audiencia = db.get_audiencia_by_id(self.audiencia_seleccionada_id); link = audiencia.get('link') if audiencia else None
        if link:
            try:
                if not link.startswith(('http://', 'https://')): link = 'http://' + link
                webbrowser.open_new_tab(link)
                if audiencia: db.update_last_activity(audiencia['caso_id'])
            except Exception as e: messagebox.showerror("Error", f"No se pudo abrir el link:\n{e}", parent=self.root)
        elif event is None: messagebox.showinfo("Info", "La audiencia seleccionada no tiene link.", parent=self.root)

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
        if not audiencia: messagebox.showerror("Error", "No se pudo obtener información de la audiencia.", parent=self.root); return
        desc_corta = (audiencia.get('descripcion','Evento')).split('\n')[0][:30]; asunto = f"Audiencia: {audiencia.get('fecha','')} - {desc_corta}"; cuerpo = self._formatear_texto_audiencia_para_compartir(audiencia)
        asunto_codificado = urllib.parse.quote(asunto); cuerpo_codificado = urllib.parse.quote(cuerpo)
        try: webbrowser.open(f"mailto:?subject={asunto_codificado}&body={cuerpo_codificado}"); db.update_last_activity(audiencia['caso_id'])
        except Exception as e: messagebox.showerror("Error", f"No se pudo abrir el cliente de email:\n{e}", parent=self.root)

    def _compartir_audiencia_por_whatsapp(self):
        if not self.audiencia_seleccionada_id: return
        audiencia = db.get_audiencia_by_id(self.audiencia_seleccionada_id)
        if not audiencia: messagebox.showerror("Error", "No se pudo obtener información de la audiencia.", parent=self.root); return
        texto = self._formatear_texto_audiencia_para_compartir(audiencia); texto_codificado = urllib.parse.quote(texto)
        try: webbrowser.open(f"https://wa.me/?text={texto_codificado}"); db.update_last_activity(audiencia['caso_id'])
        except Exception as e: messagebox.showerror("Error", f"No se pudo abrir WhatsApp:\n{e}", parent=self.root)

    def mostrar_menu_compartir_audiencia(self):
        if not self.audiencia_seleccionada_id: messagebox.showwarning("Advertencia", "Selecciona una audiencia para compartir.", parent=self.root); return
        menu = tk.Menu(self.root, tearoff=0); menu.add_command(label="Compartir por Email", command=self._compartir_audiencia_por_email); menu.add_separator(); menu.add_command(label="Compartir por WhatsApp", command=self._compartir_audiencia_por_whatsapp)
        try: widget = self.share_audiencia_btn; x = widget.winfo_rootx(); y = widget.winfo_rooty() + widget.winfo_height(); menu.tk_popup(x, y)
        except Exception as e: print(f"Error mostrando menú de compartir: {e}. Usando coordenadas del puntero."); menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally: menu.grab_release()

    def abrir_dialogo_audiencia(self, audiencia_id=None):
        is_edit = audiencia_id is not None; datos_audiencia = {}; caso_asociado_id = None; caso_asociado_caratula = "N/A"
        if is_edit:
            datos_audiencia = db.get_audiencia_by_id(audiencia_id)
            if not datos_audiencia: messagebox.showerror("Error", "No se pudo cargar la información de la audiencia.", parent=self.root); return
            dialog_title = f"Editar Audiencia ID: {audiencia_id}"; caso_asociado_id = datos_audiencia['caso_id']; caso_asociado_caratula = datos_audiencia.get('caso_caratula', f"Caso ID {caso_asociado_id}")
        else:
            if not self.selected_case: messagebox.showwarning("Advertencia", "Selecciona un caso en la lista de casos para poder agregarle una audiencia.", parent=self.root); return
            caso_asociado_id = self.selected_case['id']; caso_asociado_caratula = self.selected_case.get('caratula', f"Caso ID {caso_asociado_id}")
            dialog_title = f"Agregar Audiencia para: {caso_asociado_caratula[:50]}..."
        dialog = tk.Toplevel(self.root); dialog.title(dialog_title); dialog.geometry("480x420"); dialog.resizable(False, False); dialog.transient(self.root); dialog.grab_set()
        frame = ttk.Frame(dialog, padding="15"); frame.pack(expand=True, fill=tk.BOTH); frame.columnconfigure(1, weight=1); frame.rowconfigure(4, weight=1)
        ttk.Label(frame, text="Caso:").grid(row=0, column=0, sticky=tk.W, pady=3, padx=5); ttk.Label(frame, text=caso_asociado_caratula).grid(row=0, column=1, sticky=tk.W, pady=3, padx=5)
        fecha_inicial = datos_audiencia.get('fecha') if is_edit else self.fecha_seleccionada_agenda; ttk.Label(frame, text="*Fecha (YYYY-MM-DD):").grid(row=1, column=0, sticky=tk.W, pady=3, padx=5); fecha_var = tk.StringVar(value=fecha_inicial); entry_fecha = ttk.Entry(frame, textvariable=fecha_var, width=12); entry_fecha.grid(row=1, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text="Hora (HH:MM):").grid(row=2, column=0, sticky=tk.W, pady=3, padx=5); hora_var = tk.StringVar(value=datos_audiencia.get('hora', '')); entry_hora = ttk.Entry(frame, textvariable=hora_var, width=7); entry_hora.grid(row=2, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Label(frame, text="Link:").grid(row=3, column=0, sticky=tk.W, pady=3, padx=5); link_var = tk.StringVar(value=datos_audiencia.get('link', '')); ttk.Entry(frame, textvariable=link_var).grid(row=3, column=1, sticky=tk.EW, pady=3, padx=5)
        ttk.Label(frame, text="*Descripción:").grid(row=4, column=0, sticky=tk.NW, pady=3, padx=5); desc_frame = ttk.Frame(frame); desc_frame.grid(row=4, column=1, sticky=tk.NSEW, pady=3, padx=5); desc_frame.rowconfigure(0, weight=1); desc_frame.columnconfigure(0, weight=1); desc_text = tk.Text(desc_frame, height=6, wrap=tk.WORD); desc_text.grid(row=0, column=0, sticky='nsew'); desc_scroll = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=desc_text.yview); desc_scroll.grid(row=0, column=1, sticky='ns'); desc_text['yscrollcommand'] = desc_scroll.set
        if is_edit: desc_text.insert('1.0', datos_audiencia.get('descripcion', ''))
        rec_frame = ttk.LabelFrame(frame, text="Recordatorio"); rec_frame.grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=10, padx=5); rec_act_var = tk.IntVar(value=datos_audiencia.get('recordatorio_activo', 0)); rec_chk = ttk.Checkbutton(rec_frame, text="Activar", variable=rec_act_var); rec_chk.pack(side=tk.LEFT, padx=(5, 10)); ttk.Label(rec_frame, text="Minutos antes:").pack(side=tk.LEFT); rec_min_var = tk.IntVar(value=datos_audiencia.get('recordatorio_minutos', 15)); vcmd = (frame.register(self.validate_int_positive), '%P'); rec_spin = ttk.Spinbox(rec_frame, from_=1, to=1440, width=5, textvariable=rec_min_var, validate='key', validatecommand=vcmd); rec_spin.pack(side=tk.LEFT, padx=5)
        btn_frame = ttk.Frame(frame); btn_frame.grid(row=6, column=0, columnspan=2, pady=15); ttk.Button(btn_frame, text="Guardar", command=lambda: self.guardar_audiencia(audiencia_id, caso_asociado_id, fecha_var.get(), hora_var.get(), link_var.get(), desc_text.get("1.0", tk.END).strip(), rec_act_var.get(), rec_min_var.get(), dialog)).pack(side=tk.LEFT, padx=5); ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
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
        except ValueError: messagebox.showerror("Error de Validación", "El formato de fecha debe ser YYYY-MM-DD.", parent=dialog); return
        hora_db = self.parsear_hora(hora_str)
        if hora_str and hora_db is None: messagebox.showerror("Error de Validación", "Formato de hora inválido. Use HH:MM o H.", parent=dialog); return
        if not desc: messagebox.showerror("Error de Validación", "La descripción no puede estar vacía.", parent=dialog); return
        try: minutos_rec = int(r_min);_ = False # Asignar success a False para evitar error de variable no definida
        except ValueError: minutos_rec = 15
        success = False
        if audiencia_id is None: new_id = db.add_audiencia(caso_id, fecha_db, hora_db, desc, link.strip(), r_act, minutos_rec); success = new_id is not None; msg_op = "agregada"
        else: success = db.update_audiencia(audiencia_id, fecha_db, hora_db, desc, link.strip(), r_act, minutos_rec); msg_op = "actualizada"
        if success:
            messagebox.showinfo("Éxito", f"Audiencia {msg_op} con éxito.", parent=dialog); dialog.destroy()
            self.agenda_cal.selection_set(fecha_dt.date()); self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario()
        else: messagebox.showerror("Error", f"No se pudo {msg_op} la audiencia.", parent=dialog)

    def editar_audiencia_seleccionada(self):
        if self.audiencia_seleccionada_id: self.abrir_dialogo_audiencia(self.audiencia_seleccionada_id)
        else: messagebox.showwarning("Advertencia", "Selecciona una audiencia de la lista para editar.", parent=self.root)

    def eliminar_audiencia_seleccionada(self):
        if not self.audiencia_seleccionada_id: messagebox.showwarning("Advertencia", "Selecciona una audiencia de la lista para eliminar.", parent=self.root); return
        try: desc_corta = self.audiencia_tree.item(str(self.audiencia_seleccionada_id))['values'][2]
        except: desc_corta = f"ID {self.audiencia_seleccionada_id}"
        if messagebox.askyesno("Confirmar Eliminación", f"¿Estás seguro de eliminar la audiencia:\n'{desc_corta}'?", parent=self.root):
            if db.delete_audiencia(self.audiencia_seleccionada_id):
                messagebox.showinfo("Éxito", "Audiencia eliminada.", parent=self.root)
                self.actualizar_lista_audiencias(); self.marcar_dias_audiencias_calendario(); self.limpiar_detalles_audiencia()
            else: messagebox.showerror("Error", "No se pudo eliminar la audiencia.", parent=self.root)

    # --- Funciones de Recordatorios y Bandeja del Sistema ---
    def verificar_recordatorios_periodicamente(self):
        print("[Recordatorios] Hilo iniciado.")
        last_check_time = time.monotonic()
        while not self.stop_event.is_set():
            try:
                ahora = datetime.datetime.now(); hoy_str = ahora.strftime("%Y-%m-%d")
                if not hasattr(self, '_dia_verificacion_recordatorios') or self._dia_verificacion_recordatorios != hoy_str:
                    print(f"[Recordatorios] Nuevo día ({hoy_str}), reseteando mostrados."); self.recordatorios_mostrados_hoy = set(); self._dia_verificacion_recordatorios = hoy_str
                audiencias_a_revisar = db.get_audiencias_con_recordatorio_activo()
                for aud in audiencias_a_revisar:
                    if self.stop_event.is_set(): break
                    aud_id = aud['id']
                    if not aud.get('hora') or aud_id in self.recordatorios_mostrados_hoy: continue
                    try:
                        tiempo_audiencia = datetime.datetime.strptime(f"{aud['fecha']} {aud['hora']}", "%Y-%m-%d %H:%M"); minutos_antes = aud.get('recordatorio_minutos', 15)
                        tiempo_recordatorio = tiempo_audiencia - datetime.timedelta(minutes=minutos_antes)
                        if tiempo_recordatorio <= ahora < tiempo_audiencia:
                            print(f"[Recordatorios] ¡Alerta! Audiencia ID: {aud_id} ({aud['hora']}) en {aud['fecha']}. Notificando...")
                            self.root.after(0, self.mostrar_recordatorio, aud); self.recordatorios_mostrados_hoy.add(aud_id)
                    except ValueError as ve: print(f"[Recordatorios] Error parseando fecha/hora para ID {aud_id}: {ve}")
                    except Exception as e: print(f"[Recordatorios] Error procesando recordatorio para ID {aud_id}: {e}")
            except sqlite3.Error as dbe: print(f"[Recordatorios] Error de base de datos en hilo: {dbe}"); self.stop_event.wait(300); continue
            except Exception as ex: print(f"[Recordatorios] Error inesperado en bucle principal del hilo: {ex}"); self.stop_event.wait(120); continue
            wait_time = 60.0 - (time.monotonic() - last_check_time); self.stop_event.wait(max(1.0, wait_time)); last_check_time = time.monotonic()
        print("[Recordatorios] Hilo detenido.")

    def mostrar_recordatorio(self, audiencia):
        if not audiencia: return
        print(f"[Notificación] Mostrando para Audiencia ID: {audiencia.get('id')}")
        hora_audiencia = audiencia.get('hora', 'N/A'); descripcion_full = audiencia.get('descripcion', ''); desc_alerta = (descripcion_full.split('\n')[0])[:100] + ('...' if len(descripcion_full) > 100 else '')
        link = audiencia.get('link', ''); link_corto = (link[:60] + '...') if len(link) > 60 else link; mensaje = f"Próxima audiencia: {desc_alerta}"
        if link_corto: mensaje += f"\nLink: {link_corto}"
        titulo = f"Recordatorio CRM Legal: {hora_audiencia}"; app_nombre = "CRM Legal"; icon_path_notif = ""
        try:
            icon_notif_file = "icono.ico"; icon_path_notif = resource_path(f'assets/{icon_notif_file}')
            if not os.path.exists(icon_path_notif): print(f"Advertencia: Icono de notificación (.ico) no encontrado en {icon_path_notif}"); icon_path_notif = ""
        except Exception as e: print(f"Error al obtener ruta del icono de notificación (.ico): {e}"); icon_path_notif = ""
        try:
            print(f"[Notificación] Enviando: T='{titulo}', M='{mensaje}', Icono='{icon_path_notif}'")
            plyer.notification.notify(title=titulo, message=mensaje, app_name=app_nombre, app_icon=icon_path_notif, timeout=20)
            print("[Notificación] Plyer notify() llamado.")
        except NotImplementedError: print("[Notificación] Plataforma no soportada por Plyer o backend no instalado. Usando fallback messagebox."); self.root.after(0, messagebox.showwarning, titulo, mensaje, {'parent': self.root})
        except Exception as e: print(f"[Notificación] Error al enviar notificación nativa vía Plyer: {e}. Usando fallback."); self.root.after(0, messagebox.showwarning, titulo, mensaje, {'parent': self.root})

    def ocultar_a_bandeja(self):
        self.root.withdraw(); print("[Bandeja] Ventana ocultada.")
        try:
            icon_notif_file = "icono.ico"; icon_p = resource_path(f'assets/{icon_notif_file}')
            if os.path.exists(icon_p): plyer.notification.notify(title="CRM Legal", message="Ejecutándose en segundo plano.\nClick derecho en el icono de la bandeja para opciones.", app_name="CRM Legal", app_icon=icon_p, timeout=10)
            else: print(f"Advertencia: Icono de notificación (.ico) no encontrado en {icon_p} para mensaje de ocultado.")
        except NotImplementedError: print("[Bandeja - Notif Ocultado] Plataforma no soportada por Plyer o backend no instalado.")
        except Exception as e: print(f"[Bandeja - Notif Ocultado] No se pudo mostrar notificación de ocultado vía Plyer: {e}")

    def _mostrar_ventana_callback(self, icon=None, item=None):
        print("[Bandeja] Solicitud para mostrar ventana."); self.root.after(0, self.root.deiconify); self.root.after(10, self.root.lift); self.root.after(20, self.root.focus_force)

    def _salir_app_callback(self, icon=None, item=None):
        print("[Bandeja] Solicitud de salida.")
        if self.tray_icon and hasattr(self.tray_icon, 'stop'): print("[Bandeja] Deteniendo icono..."); self.tray_icon.stop()
        else: print("[Bandeja] No se pudo detener el icono (¿ya detenido o no iniciado?).")
        self.cerrar_aplicacion()

    def setup_tray_icon(self):
        print("[Bandeja] Iniciando configuración del icono...")
        try:
            icon_file = "icono.png"; icon_path = resource_path(f"assets/{icon_file}")
            if not os.path.exists(icon_path): raise FileNotFoundError(f"Icono de bandeja no encontrado en: {icon_path}")
            print(f"[Bandeja] Cargando icono desde: {icon_path}"); image = Image.open(icon_path)
            menu = (item('Mostrar CRM Legal', self._mostrar_ventana_callback, default=True), item('Salir', self._salir_app_callback))
            self.tray_icon = icon("CRMLegalAppTray", image, "CRM Legal", menu)
            print("[Bandeja] Icono creado. Ejecutando run()... (Este hilo se bloqueará aquí)")
            self.tray_icon.run()
            print("[Bandeja] Icono run() terminado (stop() fue llamado)."); self.tray_icon = None
        except FileNotFoundError as fnf: print(f"ERROR CRÍTICO [Bandeja]: {fnf}")
        except Exception as e: print(f"ERROR FATAL [Bandeja]: No se pudo iniciar el icono de la bandeja: {e}")

# --- Punto de entrada principal ---
if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style(root)
    available_themes = style.theme_names()
    print("Temas disponibles:", available_themes)
    desired_themes = ['vista', 'clam', 'alt', 'default'] # Puedes añadir más temas preferidos
    theme_applied = False
    for theme in desired_themes:
        if theme in available_themes:
            try:
                style.theme_use(theme); print(f"Tema '{theme}' aplicado."); theme_applied = True; break
            except tk.TclError: print(f"Advertencia: No se pudo aplicar el tema '{theme}'.")
    if not theme_applied: print(f"Ninguno de los temas preferidos estaba disponible o aplicable. Usando tema por defecto: {style.theme_use()}")
    
    # Puedes definir estilos personalizados aquí si lo deseas, ej:
    # style.configure("Accent.TButton", font=('Helvetica', 10, 'bold'), background='#0078D7', foreground='white')
    # style.map("Accent.TButton", background=[('active', '#005EA2')], relief=[('pressed', 'sunken')])

    app = CRMLegalApp(root)
    root.mainloop()
    print("Aplicación CRM Legal cerrada limpiamente.")