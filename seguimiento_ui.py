# seguimiento_ui.py
import tkinter as tk
from tkinter import ttk, messagebox
import datetime

class SeguimientoTab(ttk.Frame):
    def __init__(self, parent, app_controller, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app_controller = app_controller
        self.db_crm = self.app_controller.db_crm
        self.selected_actividad_id = None
        self._create_widgets()

    def _create_widgets(self):
        # Configurar SeguimientoTab para tener dos columnas principales
        # Columna 0 para la lista y acciones, Columna 1 para los detalles
        self.columnconfigure(0, weight=1) # Panel izquierdo (lista y acciones)
        self.columnconfigure(1, weight=2) # Panel derecho (detalles) - damos más peso para que sea más ancho
        self.rowconfigure(0, weight=1)    # La fila única que contendrá ambos paneles

        # --- Panel Izquierdo (para agrupar Treeview y botones de acción) ---
        left_panel = ttk.Frame(self)
        left_panel.grid(row=0, column=0, sticky='nsew', padx=(0, 5)) # Añadimos un poco de espacio a la derecha
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(0, weight=1)  # Para el tree_frame
        left_panel.rowconfigure(1, weight=0)  # Para el actions_frame

        # --- Tree Frame (dentro del panel izquierdo) ---
        tree_frame = ttk.Frame(left_panel) # Cambiado el parent a left_panel
        tree_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.rowconfigure(1, weight=0)

        actividad_cols = ('ID', 'Fecha/Hora', 'Tipo', 'Descripción Resumida')
        self.actividad_tree = ttk.Treeview(tree_frame, columns=actividad_cols, show='headings', selectmode='browse')
        self.actividad_tree.heading('ID', text='ID')
        self.actividad_tree.heading('Fecha/Hora', text='Fecha y Hora')
        self.actividad_tree.heading('Tipo', text='Tipo Actividad')
        self.actividad_tree.heading('Descripción Resumida', text='Descripción')

        self.actividad_tree.column('ID', width=40, stretch=tk.NO, anchor=tk.CENTER)
        self.actividad_tree.column('Fecha/Hora', width=140, stretch=tk.NO)
        self.actividad_tree.column('Tipo', width=120, stretch=tk.NO)
        self.actividad_tree.column('Descripción Resumida', width=300, stretch=True) # Ajustar ancho si es necesario

        actividad_scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.actividad_tree.yview)
        self.actividad_tree.configure(yscrollcommand=actividad_scrollbar_y.set)
        actividad_scrollbar_y.grid(row=0, column=1, sticky='ns')

        actividad_scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.actividad_tree.xview)
        self.actividad_tree.configure(xscrollcommand=actividad_scrollbar_x.set)
        actividad_scrollbar_x.grid(row=1, column=0, sticky='ew')

        self.actividad_tree.grid(row=0, column=0, sticky='nsew')
        self.actividad_tree.bind('<<TreeviewSelect>>', self.on_actividad_select_treeview)
        self.actividad_tree.bind("<Double-1>", self._on_double_click_editar)

        # --- Actions Frame (dentro del panel izquierdo) ---
        actions_frame = ttk.Frame(left_panel) # Cambiado el parent a left_panel
        actions_frame.grid(row=1, column=0, sticky='ew', pady=5)

        self.add_actividad_btn = ttk.Button(actions_frame, text="Agregar Nueva Actividad",
                                            command=self._open_add_actividad_dialog_wrapper, state=tk.DISABLED)
        self.add_actividad_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.edit_actividad_btn = ttk.Button(actions_frame, text="Editar",
                                            command=self._open_edit_actividad_dialog_wrapper, state=tk.DISABLED)
        self.edit_actividad_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.delete_actividad_btn = ttk.Button(actions_frame, text="Eliminar",
                                            command=self._delete_selected_actividad_wrapper, state=tk.DISABLED)
        self.delete_actividad_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # --- Panel Derecho (Detalles completos de la actividad) ---
        self.details_text_frame = ttk.LabelFrame(self, text="Detalle Completo de Actividad", padding="10")
        # Colocar en la columna 1 de la grilla principal de SeguimientoTab
        self.details_text_frame.grid(row=0, column=1, sticky='nsew', pady=0, padx=(5,0))
        self.details_text_frame.columnconfigure(0, weight=1)
        self.details_text_frame.rowconfigure(0, weight=1)

        try:
            root_bg_color = self.app_controller.root.cget('bg')
        except tk.TclError:
            print("Advertencia: No se pudo obtener el color de fondo del root. Usando color por defecto para Text.")
            root_bg_color = 'SystemButtonFace'

        self.actividad_detail_text = tk.Text(
            self.details_text_frame,
            height=5, # La altura se gestionará por el peso de la fila del frame contenedor
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            background=root_bg_color
        )
        self.actividad_detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(self.details_text_frame, orient=tk.VERTICAL, command=self.actividad_detail_text.yview)
        self.actividad_detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.grid(row=0, column=1, sticky="ns")

        self.details_text_frame.grid_remove() # Ocultar inicialmente


    def _open_add_actividad_dialog_wrapper(self):
        if self.app_controller.selected_case:
            self.app_controller.open_actividad_dialog_for_seguimiento_tab(self.app_controller.selected_case['id'])
        else:
            messagebox.showwarning("Advertencia", "No hay un caso seleccionado para agregar actividad.", parent=self)

    def _open_edit_actividad_dialog_wrapper(self):
        if self.selected_actividad_id and self.app_controller.selected_case:
            self.app_controller.open_edit_actividad_dialog(self.selected_actividad_id, self.app_controller.selected_case['id'])
        else:
            messagebox.showwarning("Advertencia", "Selecciona una actividad para editar.", parent=self)

    def _delete_selected_actividad_wrapper(self):
        if self.selected_actividad_id and self.app_controller.selected_case:
            self.app_controller.delete_selected_actividad(self.selected_actividad_id, self.app_controller.selected_case['id'])
        else:
            messagebox.showwarning("Advertencia", "Selecciona una actividad para eliminar.", parent=self)

    def _on_double_click_editar(self, event=None):
        item_id_str = self.actividad_tree.identify_row(event.y)
        if item_id_str:
            if self.selected_actividad_id:
                 self._open_edit_actividad_dialog_wrapper()

    def load_actividades(self, caso_id):
        for i in self.actividad_tree.get_children():
            self.actividad_tree.delete(i)

        self.selected_actividad_id = None
        self.limpiar_detalle_completo_actividad()

        if caso_id:
            actividades = self.db_crm.get_actividades_by_caso_id(caso_id, order_desc=True)
            for act in actividades:
                try:
                    # Asumiendo que la fecha viene como YYYY-MM-DD HH:MM:SS desde la BD
                    # y se quiere mostrar como DD-MM-YYYY HH:MM
                    fecha_hora_dt = datetime.datetime.strptime(act['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                    fecha_hora_display = fecha_hora_dt.strftime("%d-%m-%Y %H:%M")
                except ValueError:
                     # Si falla el parseo (quizás ya está en otro formato o es solo fecha)
                    fecha_hora_display = act['fecha_hora']


                desc_completa = act.get('descripcion', '')
                desc_resumida = (desc_completa[:75] + '...') if len(desc_completa) > 75 else desc_completa

                item_iid = f"act_{act['id']}"

                self.actividad_tree.insert('', tk.END, values=(
                    act['id'], fecha_hora_display, act.get('tipo_actividad', 'N/A'), desc_resumida
                ), iid=item_iid)
        self._update_action_buttons_state()


    def on_actividad_select_treeview(self, event=None):
        selected_items = self.actividad_tree.selection()
        if selected_items:
            item_iid = selected_items[0]
            try:
                if item_iid.startswith("act_"):
                    self.selected_actividad_id = int(item_iid.split('_')[1])
                else:
                    self.selected_actividad_id = int(item_iid) # Fallback por si el iid no tiene prefijo
            except (IndexError, ValueError):
                print(f"Error: No se pudo extraer el ID numérico del iid: {item_iid}")
                self.selected_actividad_id = None

            if self.selected_actividad_id:
                self.mostrar_detalle_completo_actividad(self.selected_actividad_id)
                print(f"Actividad seleccionada en SeguimientoTab: ID {self.selected_actividad_id}")
            else:
                self.limpiar_detalle_completo_actividad()
        else:
            self.selected_actividad_id = None
            self.limpiar_detalle_completo_actividad()

        self._update_action_buttons_state()

    def set_add_button_state(self, state_ignored):
        self._update_action_buttons_state()

    def _update_action_buttons_state(self):
        case_selected = self.app_controller.selected_case is not None
        activity_selected = self.selected_actividad_id is not None

        add_state = tk.NORMAL if case_selected else tk.DISABLED
        edit_delete_state = tk.NORMAL if case_selected and activity_selected else tk.DISABLED

        if hasattr(self, 'add_actividad_btn'):
            self.add_actividad_btn.config(state=add_state)
        if hasattr(self, 'edit_actividad_btn'):
            self.edit_actividad_btn.config(state=edit_delete_state)
        if hasattr(self, 'delete_actividad_btn'):
            self.delete_actividad_btn.config(state=edit_delete_state)

    def mostrar_detalle_completo_actividad(self, actividad_id):
        if not hasattr(self, 'actividad_detail_text'): return

        if not actividad_id:
            self.limpiar_detalle_completo_actividad()
            return

        self.details_text_frame.grid() # Asegurarse que es visible
        self.actividad_detail_text.config(state=tk.NORMAL)
        self.actividad_detail_text.delete('1.0', tk.END)

        act_details = self.db_crm.get_actividad_by_id(actividad_id)
        if act_details:
            try:
                fecha_hora_dt = datetime.datetime.strptime(act_details['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                fecha_hora_display = fecha_hora_dt.strftime("%d-%m-%Y %H:%M")
            except ValueError:
                fecha_hora_display = act_details['fecha_hora']

            texto = f"ID de Actividad: {act_details['id']}\n"
            texto += f"Fecha y Hora: {fecha_hora_display}\n"
            texto += f"Tipo de Actividad: {act_details.get('tipo_actividad', 'N/A')}\n"
            if act_details.get('referencia_documento'):
                texto += f"Referencia Documento: {act_details['referencia_documento']}\n"
            texto += f"-------------------------\nDescripción Detallada:\n{act_details.get('descripcion', 'Sin descripción.')}"
            self.actividad_detail_text.insert('1.0', texto)
        else:
            self.actividad_detail_text.insert('1.0', "Detalles de la actividad no encontrados o no disponibles.")

        self.actividad_detail_text.config(state=tk.DISABLED)

    def limpiar_detalle_completo_actividad(self):
        if not hasattr(self, 'actividad_detail_text'): return
        self.actividad_detail_text.config(state=tk.NORMAL)
        self.actividad_detail_text.delete('1.0', tk.END)
        self.actividad_detail_text.config(state=tk.DISABLED)
        if hasattr(self, 'details_text_frame'):
            self.details_text_frame.grid_remove() # Ocultar si no hay nada que mostrar