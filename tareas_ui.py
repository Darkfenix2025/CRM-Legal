# tareas_ui.py
import tkinter as tk
from tkinter import ttk, messagebox
import datetime # Lo necesitaremos para formatear fechas si es necesario

class TareasTab(ttk.Frame):
    def __init__(self, parent, app_controller, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app_controller = app_controller
        self.db_crm = self.app_controller.db_crm # Acceso al módulo de base de datos
        self.selected_tarea_id = None # Para guardar el ID de la tarea seleccionada en el treeview

        self._create_widgets()

    def _create_widgets(self):
        # Configuración general de la pestaña de Tareas
        self.columnconfigure(0, weight=1) # Panel izquierdo (lista y acciones)
        self.columnconfigure(1, weight=1) # Panel derecho (detalles de la tarea) - peso igual por ahora
        self.rowconfigure(0, weight=1)    # Fila única para ambos paneles

        # --- Panel Izquierdo: Lista de Tareas y Botones de Acción ---
        left_panel = ttk.Frame(self)
        left_panel.grid(row=0, column=0, sticky='nsew', padx=(0, 5), pady=5)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(0, weight=0) # Frame de filtros (opcional, altura fija)
        left_panel.rowconfigure(1, weight=1) # Treeview de tareas (expandible)
        left_panel.rowconfigure(2, weight=0) # Botones de acción (altura fija)

        # TODO: Frame para Filtros (lo dejaremos para una mejora futura si es necesario)
        # filter_frame = ttk.LabelFrame(left_panel, text="Filtros", padding="5")
        # filter_frame.grid(row=0, column=0, sticky='ew', pady=(0,5))
        # ttk.Label(filter_frame, text="Mostrar: (Próximamente)").pack()

        # --- Treeview para listar las Tareas ---
        tree_frame = ttk.LabelFrame(left_panel, text="Lista de Tareas", padding="5")
        tree_frame.grid(row=1, column=0, sticky='nsew') # Ocupa la fila 1 del left_panel
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        # Definición de columnas para el Treeview de tareas
        # Podríamos añadir 'Caso Asociado' si implementamos una vista de "Todas las Tareas"
        self.tareas_cols = ('ID', 'Descripción', 'Vencimiento', 'Prioridad', 'Estado')
        self.tareas_tree = ttk.Treeview(tree_frame, columns=self.tareas_cols, show='headings', selectmode='browse')

        self.tareas_tree.heading('ID', text='ID')
        self.tareas_tree.heading('Descripción', text='Descripción')
        self.tareas_tree.heading('Vencimiento', text='F. Venc.')
        self.tareas_tree.heading('Prioridad', text='Prio.')
        self.tareas_tree.heading('Estado', text='Estado')

        self.tareas_tree.column('ID', width=40, stretch=tk.NO, anchor=tk.CENTER)
        self.tareas_tree.column('Descripción', width=300, stretch=True)
        self.tareas_tree.column('Vencimiento', width=90, stretch=tk.NO, anchor=tk.CENTER)
        self.tareas_tree.column('Prioridad', width=70, stretch=tk.NO, anchor=tk.CENTER)
        self.tareas_tree.column('Estado', width=100, stretch=tk.NO)

        # Scrollbars para el Treeview
        tareas_scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tareas_tree.yview)
        self.tareas_tree.configure(yscrollcommand=tareas_scrollbar_y.set)
        tareas_scrollbar_y.grid(row=0, column=1, sticky='ns')
        
        tareas_scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tareas_tree.xview)
        self.tareas_tree.configure(xscrollcommand=tareas_scrollbar_x.set)
        # Colocamos el scrollbar X debajo del treeview, dentro del tree_frame
        # Para esto, necesitamos una fila adicional en tree_frame o usar pack/place para el scrollbar_x
        # Por simplicidad ahora, lo omitimos visualmente, pero si las descripciones son muy largas, sería útil.
        # Opcional: tree_frame.rowconfigure(1, weight=0); tareas_scrollbar_x.grid(row=1, column=0, sticky='ew')


        self.tareas_tree.grid(row=0, column=0, sticky='nsew')
        self.tareas_tree.bind('<<TreeviewSelect>>', self.on_tarea_select_treeview)
        self.tareas_tree.bind("<Double-1>", self._on_double_click_editar_tarea) # Para editar con doble clic

        # --- Botones de Acción para Tareas ---
        actions_frame = ttk.Frame(left_panel)
        actions_frame.grid(row=2, column=0, sticky='ew', pady=5) # Ocupa la fila 2 del left_panel

        self.add_tarea_btn = ttk.Button(actions_frame, text="Agregar Tarea",
                                        command=self._open_add_tarea_dialog_wrapper, state=tk.DISABLED)
        self.add_tarea_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.edit_tarea_btn = ttk.Button(actions_frame, text="Editar Tarea",
                                         command=self._open_edit_tarea_dialog_wrapper, state=tk.DISABLED)
        self.edit_tarea_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.complete_tarea_btn = ttk.Button(actions_frame, text="Completar",
                                           command=self._mark_selected_tarea_completed_wrapper, state=tk.DISABLED)
        self.complete_tarea_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        self.delete_tarea_btn = ttk.Button(actions_frame, text="Eliminar Tarea",
                                           command=self._delete_selected_tarea_wrapper, state=tk.DISABLED)
        self.delete_tarea_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # --- Panel Derecho: Detalles de la Tarea Seleccionada ---
        self.details_tarea_frame = ttk.LabelFrame(self, text="Detalles de la Tarea", padding="10")
        self.details_tarea_frame.grid(row=0, column=1, sticky='nsew', pady=5, padx=(5,0))
        self.details_tarea_frame.columnconfigure(0, weight=1) # Para el Text widget
        self.details_tarea_frame.rowconfigure(0, weight=1)    # Para el Text widget

        try: # Intentar obtener el color de fondo del root para consistencia
            root_bg_color = self.app_controller.root.cget('bg')
        except tk.TclError:
            root_bg_color = 'SystemButtonFace' # Fallback color

        self.tarea_detail_text = tk.Text(
            self.details_tarea_frame,
            height=8, # Altura inicial, se expandirá con el frame
            wrap=tk.WORD,
            state=tk.DISABLED, # Inicialmente deshabilitado, se habilita para insertar texto
            relief=tk.FLAT,    # Para que parezca más una etiqueta que un campo de entrada
            background=root_bg_color, # Color de fondo consistente
            padx=5, pady=5
        )
        self.tarea_detail_text.grid(row=0, column=0, sticky="nsew")
        
        detail_scroll = ttk.Scrollbar(self.details_tarea_frame, orient=tk.VERTICAL, command=self.tarea_detail_text.yview)
        self.tarea_detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.grid(row=0, column=1, sticky="ns")

        self.details_tarea_frame.grid_remove() # Ocultar el panel de detalles inicialmente

    # --- Métodos de Lógica Interna de la Pestaña Tareas ---

    def load_tareas(self, caso_id=None, mostrar_solo_pendientes_activas=True):
        """
        Carga las tareas en el Treeview.
        Si caso_id es proporcionado, carga tareas de ese caso.
        Si caso_id es None y mostrar_solo_pendientes_activas es True, podría cargar tareas generales pendientes.
        (Por ahora, nos enfocaremos en tareas por caso_id si se provee, o nada si no se provee)
        """
        for i in self.tareas_tree.get_children():
            self.tareas_tree.delete(i)

        self.selected_tarea_id = None # Resetear selección
        self.limpiar_detalle_completo_tarea() # Limpiar panel de detalles

        tareas_a_mostrar = []
        if caso_id:
            # Por defecto, no incluimos completadas/canceladas para la vista de un caso
            tareas_a_mostrar = self.db_crm.get_tareas_by_caso_id(caso_id, incluir_completadas=False, orden="fecha_vencimiento_asc")
            print(f"[TareasTab] Cargando {len(tareas_a_mostrar)} tareas para caso ID: {caso_id}")
        # else:
            # Futuro: Podríamos cargar aquí tareas generales pendientes si mostrar_solo_pendientes_activas es True
            # tareas_a_mostrar = self.db_crm.get_todas_las_tareas_pendientes_o_activas()
            # print(f"[TareasTab] Cargando tareas generales pendientes/activas.")
            # pass


        for tarea in tareas_a_mostrar:
            item_iid = f"tarea_{tarea['id']}" # IID único para el treeview item
            
            # Formatear fecha de vencimiento para mejor visualización (ej. manejar Nones)
            fecha_venc_display = tarea.get('fecha_vencimiento', '')
            if fecha_venc_display:
                try:
                    # Asumimos que la BD guarda YYYY-MM-DD
                    fv_dt = datetime.datetime.strptime(fecha_venc_display, "%Y-%m-%d")
                    fecha_venc_display = fv_dt.strftime("%d-%m-%Y") # Mostrar en formato más legible
                except ValueError:
                    pass # Dejar como está si no se puede parsear (aunque debería estar bien desde la BD)
            
            self.tareas_tree.insert('', tk.END, values=(
                tarea['id'],
                tarea.get('descripcion', 'N/A')[:100], # Limitar descripción en el treeview
                fecha_venc_display,
                tarea.get('prioridad', 'N/A'),
                tarea.get('estado', 'N/A')
            ), iid=item_iid)
        
        self._update_action_buttons_state()

    def on_tarea_select_treeview(self, event=None):
        """ Maneja la selección de un item en el Treeview de tareas. """
        selected_items = self.tareas_tree.selection()
        if selected_items:
            item_iid = selected_items[0]
            try:
                if item_iid.startswith("tarea_"):
                    self.selected_tarea_id = int(item_iid.split('_')[1])
                else:
                    self.selected_tarea_id = int(item_iid) # Fallback
                print(f"[TareasTab] Tarea seleccionada: ID {self.selected_tarea_id}")
            except (IndexError, ValueError):
                print(f"[TareasTab] Error extrayendo ID de tarea desde iid: {item_iid}")
                self.selected_tarea_id = None

            if self.selected_tarea_id:
                self.mostrar_detalle_completo_tarea(self.selected_tarea_id)
            else:
                self.limpiar_detalle_completo_tarea()
        else: # No hay selección
            self.selected_tarea_id = None
            self.limpiar_detalle_completo_tarea()
        
        self._update_action_buttons_state()

    def _update_action_buttons_state(self):
        """ Actualiza el estado (habilitado/deshabilitado) de los botones de acción. """
        # El botón "Agregar Tarea" depende de si hay un caso seleccionado en la app principal
        # (o si permitimos tareas generales, entonces siempre estaría habilitado).
        # Por ahora, lo vincularemos a la selección de un caso.
        caso_seleccionado_en_app = self.app_controller.selected_case is not None
        tarea_seleccionada_en_lista = self.selected_tarea_id is not None

        add_state = tk.NORMAL if caso_seleccionado_en_app else tk.DISABLED
        # Editar, Completar y Eliminar requieren una tarea seleccionada en ESTA lista
        edit_complete_delete_state = tk.NORMAL if tarea_seleccionada_en_lista else tk.DISABLED
        
        # Si la tarea seleccionada ya está completada o cancelada, deshabilitar "Completar"
        if tarea_seleccionada_en_lista:
            tarea_actual = self.db_crm.get_tarea_by_id(self.selected_tarea_id)
            if tarea_actual and tarea_actual.get('estado') in ['Completada', 'Cancelada']:
                self.complete_tarea_btn.config(state=tk.DISABLED)
            else:
                self.complete_tarea_btn.config(state=edit_complete_delete_state) # Usar el estado general si no está completada/cancelada
        else:
             self.complete_tarea_btn.config(state=tk.DISABLED)


        if hasattr(self, 'add_tarea_btn'):
            self.add_tarea_btn.config(state=add_state)
        if hasattr(self, 'edit_tarea_btn'):
            self.edit_tarea_btn.config(state=edit_complete_delete_state)
        # El estado de complete_tarea_btn ya se manejó arriba
        if hasattr(self, 'delete_tarea_btn'):
            self.delete_tarea_btn.config(state=edit_complete_delete_state)

    def mostrar_detalle_completo_tarea(self, tarea_id):
        """ Muestra todos los detalles de la tarea en el panel derecho. """
        if not hasattr(self, 'tarea_detail_text'): return

        if not tarea_id:
            self.limpiar_detalle_completo_tarea()
            return

        self.details_tarea_frame.grid() # Asegurarse que el frame de detalles sea visible
        self.tarea_detail_text.config(state=tk.NORMAL) # Habilitar para escribir
        self.tarea_detail_text.delete('1.0', tk.END)   # Limpiar contenido anterior

        tarea_details = self.db_crm.get_tarea_by_id(tarea_id)
        if tarea_details:
            caso_info = "General (No asociada a caso)"
            if tarea_details.get('caso_id'):
                caso_obj = self.db_crm.get_case_by_id(tarea_details['caso_id'])
                if caso_obj:
                    caso_info = f"{caso_obj.get('caratula', 'Caso Desconocido')} (ID: {tarea_details['caso_id']})"
                else:
                    caso_info = f"Caso ID: {tarea_details['caso_id']} (No encontrado)"
            
            fecha_creacion_dt = datetime.datetime.strptime(tarea_details['fecha_creacion'], "%Y-%m-%d %H:%M:%S")
            fecha_creacion_display = fecha_creacion_dt.strftime("%d-%m-%Y %H:%M")

            fecha_venc_display = "No definida"
            if tarea_details.get('fecha_vencimiento'):
                try:
                    fv_dt = datetime.datetime.strptime(tarea_details['fecha_vencimiento'], "%Y-%m-%d")
                    fecha_venc_display = fv_dt.strftime("%d-%m-%Y")
                except ValueError:
                    fecha_venc_display = tarea_details['fecha_vencimiento'] # Mostrar como está si hay error de formato

            texto = f"**ID de Tarea:** {tarea_details['id']}\n"
            texto += f"**Caso Asociado:** {caso_info}\n"
            texto += "--------------------------------------------------\n"
            texto += f"**Descripción:**\n{tarea_details.get('descripcion', 'N/A')}\n\n"
            texto += f"**Fecha de Creación:** {fecha_creacion_display}\n"
            texto += f"**Fecha de Vencimiento:** {fecha_venc_display}\n"
            texto += f"**Prioridad:** {tarea_details.get('prioridad', 'N/A')}\n"
            texto += f"**Estado:** {tarea_details.get('estado', 'N/A')}\n"
            if tarea_details.get('es_plazo_procesal'):
                texto += "**Tipo:** Plazo Procesal\n"
            if tarea_details.get('recordatorio_activo'):
                texto += f"**Recordatorio:** Activado ({tarea_details.get('recordatorio_dias_antes', 1)} días antes)\n"
            else:
                 texto += "**Recordatorio:** Desactivado\n"

            texto += "\n**Notas Adicionales:**\n"
            texto += f"{tarea_details.get('notas', 'Sin notas.')}"
            
            self.tarea_detail_text.insert('1.0', texto)
        else:
            self.tarea_detail_text.insert('1.0', "Detalles de la tarea no encontrados o no disponibles.")
        
        self.tarea_detail_text.config(state=tk.DISABLED) # Deshabilitar después de escribir

    def limpiar_detalle_completo_tarea(self):
        """ Limpia el panel de detalles de la tarea y lo oculta. """
        if not hasattr(self, 'tarea_detail_text'): return
        self.tarea_detail_text.config(state=tk.NORMAL)
        self.tarea_detail_text.delete('1.0', tk.END)
        self.tarea_detail_text.config(state=tk.DISABLED)
        if hasattr(self, 'details_tarea_frame'): # Asegurarse que existe el frame
            self.details_tarea_frame.grid_remove() # Ocultar el frame

    # --- Métodos Wrapper para llamar a las funciones de diálogo en main_app.py ---
    # Estos métodos serán llamados por los botones de esta pestaña.
    # La implementación real de los diálogos estará en main_app.py (CRMLegalApp)

    def _open_add_tarea_dialog_wrapper(self):
        if self.app_controller.selected_case:
            # Llamar a un método en app_controller (main_app) que abrirá el diálogo
            self.app_controller.open_tarea_dialog(caso_id=self.app_controller.selected_case['id'])
        else:
            # Opcional: Permitir crear tareas generales (sin caso_id)
            # self.app_controller.open_tarea_dialog() 
            messagebox.showwarning("Aviso", "Seleccione un caso para agregarle una tarea, o habilite tareas generales.", parent=self)


    def _open_edit_tarea_dialog_wrapper(self):
        if self.selected_tarea_id:
            self.app_controller.open_tarea_dialog(tarea_id=self.selected_tarea_id)
        else:
            messagebox.showwarning("Aviso", "Seleccione una tarea de la lista para editar.", parent=self)

    def _mark_selected_tarea_completed_wrapper(self):
        if self.selected_tarea_id:
            tarea_actual = self.db_crm.get_tarea_by_id(self.selected_tarea_id)
            if tarea_actual and tarea_actual.get('estado') not in ['Completada', 'Cancelada']:
                 # Llamar a un método en app_controller que manejará el cambio de estado
                self.app_controller.marcar_tarea_como_completada(self.selected_tarea_id, tarea_actual.get('caso_id'))
            elif tarea_actual:
                 messagebox.showinfo("Info", f"La tarea ya está '{tarea_actual.get('estado')}'.", parent=self)
        else:
            messagebox.showwarning("Aviso", "Seleccione una tarea para marcar como completada.", parent=self)


    def _delete_selected_tarea_wrapper(self):
        if self.selected_tarea_id:
            # Llamar a un método en app_controller que manejará la eliminación
            tarea_info = self.db_crm.get_tarea_by_id(self.selected_tarea_id)
            caso_id_asociado = tarea_info.get('caso_id') if tarea_info else None
            self.app_controller.delete_selected_tarea(self.selected_tarea_id, caso_id_asociado)
        else:
            messagebox.showwarning("Aviso", "Seleccione una tarea de la lista para eliminar.", parent=self)
    
    def _on_double_click_editar_tarea(self, event=None):
        """ Permite editar una tarea haciendo doble clic en ella en el Treeview. """
        # La selección ya debería estar actualizada por el clic que precede al doble clic,
        # así que self.selected_tarea_id debería ser correcto.
        if self.selected_tarea_id:
            self._open_edit_tarea_dialog_wrapper()
            
    def set_add_button_state(self, state_ignored=None): # Para consistencia con otras pestañas
        """Actualiza el estado de los botones de acción, llamado desde main_app."""
        self._update_action_buttons_state()