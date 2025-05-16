# partes_ui.py
import tkinter as tk
from tkinter import ttk, messagebox
import datetime # Aunque no se use directamente aquí, es bueno tenerlo por si acaso

class PartesTab(ttk.Frame):
    def __init__(self, parent, app_controller, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app_controller = app_controller
        self.db_crm = self.app_controller.db_crm # Acceso directo al módulo de BD
        self.selected_parte_id = None
        self._create_widgets()

    def _create_widgets(self):
        # Configurar PartesTab para tener dos columnas principales
        # Columna 0 para la lista y acciones, Columna 1 para los detalles
        self.columnconfigure(0, weight=1) # Panel izquierdo (lista y acciones)
        self.columnconfigure(1, weight=2) # Panel derecho (detalles)
        self.rowconfigure(0, weight=1)    # La fila única que contendrá ambos paneles

        # --- Panel Izquierdo (para agrupar Treeview y botones de acción) ---
        left_panel = ttk.Frame(self)
        left_panel.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(0, weight=1)  # Para el tree_frame
        left_panel.rowconfigure(1, weight=0)  # Para el actions_frame

        # --- Tree Frame (dentro del panel izquierdo) ---
        tree_frame = ttk.LabelFrame(left_panel, text="Partes Intervinientes en el Caso", padding="5")
        tree_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        partes_cols = ('ID', 'Nombre', 'Tipo', 'Contacto')
        self.partes_tree = ttk.Treeview(tree_frame, columns=partes_cols, show='headings', selectmode='browse')
        self.partes_tree.heading('ID', text='ID')
        self.partes_tree.heading('Nombre', text='Nombre Completo')
        self.partes_tree.heading('Tipo', text='Tipo/Rol')
        self.partes_tree.heading('Contacto', text='Contacto Principal')

        self.partes_tree.column('ID', width=40, stretch=tk.NO, anchor=tk.CENTER)
        self.partes_tree.column('Nombre', width=200, stretch=True)
        self.partes_tree.column('Tipo', width=120, stretch=tk.NO)
        self.partes_tree.column('Contacto', width=150, stretch=True)

        partes_scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.partes_tree.yview)
        self.partes_tree.configure(yscrollcommand=partes_scrollbar_y.set)
        partes_scrollbar_y.grid(row=0, column=1, sticky='ns')
        
        partes_scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.partes_tree.xview)
        self.partes_tree.configure(xscrollcommand=partes_scrollbar_x.set)
        partes_scrollbar_x.grid(row=1, column=0, sticky='ew')

        self.partes_tree.grid(row=0, column=0, sticky='nsew')
        self.partes_tree.bind('<<TreeviewSelect>>', self.on_parte_select_treeview)
        self.partes_tree.bind("<Double-1>", self._on_double_click_editar_parte)

        # --- Actions Frame (dentro del panel izquierdo) ---
        actions_frame = ttk.Frame(left_panel)
        actions_frame.grid(row=1, column=0, sticky='ew', pady=5)

        self.add_parte_btn = ttk.Button(actions_frame, text="Agregar Parte",
                                          command=self._open_add_parte_dialog_wrapper, state=tk.DISABLED)
        self.add_parte_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.edit_parte_btn = ttk.Button(actions_frame, text="Editar Parte",
                                           command=self._open_edit_parte_dialog_wrapper, state=tk.DISABLED)
        self.edit_parte_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.delete_parte_btn = ttk.Button(actions_frame, text="Eliminar Parte",
                                             command=self._delete_selected_parte_wrapper, state=tk.DISABLED)
        self.delete_parte_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # --- Panel Derecho (Detalles completos de la parte) ---
        self.details_parte_frame = ttk.LabelFrame(self, text="Detalles Completos de la Parte", padding="10")
        self.details_parte_frame.grid(row=0, column=1, sticky='nsew', pady=0, padx=(5,0))
        self.details_parte_frame.columnconfigure(0, weight=1) # Para el Text widget
        self.details_parte_frame.rowconfigure(0, weight=1)    # Para el Text widget

        try:
            root_bg_color = self.app_controller.root.cget('bg')
        except tk.TclError:
            root_bg_color = 'SystemButtonFace' # Fallback

        self.parte_detail_text = tk.Text(
            self.details_parte_frame,
            height=8, # Altura inicial, se expandirá
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            background=root_bg_color,
            padx=5, pady=5
        )
        self.parte_detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(self.details_parte_frame, orient=tk.VERTICAL, command=self.parte_detail_text.yview)
        self.parte_detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.grid(row=0, column=1, sticky="ns")

        self.details_parte_frame.grid_remove() # Ocultar inicialmente

    def _open_add_parte_dialog_wrapper(self):
        if self.app_controller.selected_case:
            self.app_controller.open_parte_dialog(caso_id=self.app_controller.selected_case['id'])
        else:
            messagebox.showwarning("Advertencia", "Seleccione un caso para agregar una parte.", parent=self)

    def _open_edit_parte_dialog_wrapper(self):
        if self.selected_parte_id and self.app_controller.selected_case:
            self.app_controller.open_parte_dialog(parte_id=self.selected_parte_id, caso_id=self.app_controller.selected_case['id'])
        else:
            messagebox.showwarning("Advertencia", "Seleccione una parte para editar.", parent=self)

    def _delete_selected_parte_wrapper(self):
        if self.selected_parte_id and self.app_controller.selected_case:
            self.app_controller.delete_selected_parte(self.selected_parte_id, self.app_controller.selected_case['id'])
        else:
            messagebox.showwarning("Advertencia", "Seleccione una parte para eliminar.", parent=self)

    def _on_double_click_editar_parte(self, event=None):
        item_id_str = self.partes_tree.identify_row(event.y)
        if item_id_str:
            if self.selected_parte_id: # Debería estar seteado por el on_parte_select que precede
                 self._open_edit_parte_dialog_wrapper()

    def load_partes(self, caso_id):
        for i in self.partes_tree.get_children():
            self.partes_tree.delete(i)

        self.selected_parte_id = None
        self.limpiar_detalle_completo_parte()

        if caso_id:
            partes = self.db_crm.get_partes_by_caso_id(caso_id)
            for parte in partes:
                # Usar iid con prefijo para evitar colisiones si los IDs son solo números
                item_iid = f"parte_{parte['id']}"
                self.partes_tree.insert('', tk.END, values=(
                    parte['id'],
                    parte.get('nombre', 'N/A'),
                    parte.get('tipo', 'N/A'),
                    parte.get('contacto', 'N/A')
                ), iid=item_iid)
        self._update_action_buttons_state()

    def on_parte_select_treeview(self, event=None):
        selected_items = self.partes_tree.selection()
        if selected_items:
            item_iid = selected_items[0]
            try:
                if item_iid.startswith("parte_"):
                    self.selected_parte_id = int(item_iid.split('_')[1])
                else: # Fallback por si el iid no tiene prefijo (aunque debería)
                    self.selected_parte_id = int(item_iid)
            except (IndexError, ValueError):
                print(f"Error: No se pudo extraer el ID numérico de la parte desde iid: {item_iid}")
                self.selected_parte_id = None

            if self.selected_parte_id:
                self.mostrar_detalle_completo_parte(self.selected_parte_id)
                print(f"Parte seleccionada en PartesTab: ID {self.selected_parte_id}")
            else:
                self.limpiar_detalle_completo_parte()
        else:
            self.selected_parte_id = None
            self.limpiar_detalle_completo_parte()

        self._update_action_buttons_state()

    def set_add_button_state(self, state_ignored=None): # state_ignored para mantener consistencia con SeguimientoTab
        self._update_action_buttons_state()

    def _update_action_buttons_state(self):
        case_selected = self.app_controller.selected_case is not None
        parte_selected = self.selected_parte_id is not None

        add_state = tk.NORMAL if case_selected else tk.DISABLED
        edit_delete_state = tk.NORMAL if case_selected and parte_selected else tk.DISABLED

        if hasattr(self, 'add_parte_btn'):
            self.add_parte_btn.config(state=add_state)
        if hasattr(self, 'edit_parte_btn'):
            self.edit_parte_btn.config(state=edit_delete_state)
        if hasattr(self, 'delete_parte_btn'):
            self.delete_parte_btn.config(state=edit_delete_state)

    def mostrar_detalle_completo_parte(self, parte_id):
        if not hasattr(self, 'parte_detail_text'): return

        if not parte_id:
            self.limpiar_detalle_completo_parte()
            return

        self.details_parte_frame.grid() # Asegurarse que es visible
        self.parte_detail_text.config(state=tk.NORMAL)
        self.parte_detail_text.delete('1.0', tk.END)

        parte_details = self.db_crm.get_parte_by_id(parte_id)
        if parte_details:
            texto = f"ID de Parte: {parte_details['id']}\n"
            texto += f"Nombre: {parte_details.get('nombre', 'N/A')}\n"
            texto += f"Tipo/Rol: {parte_details.get('tipo', 'N/A')}\n"
            texto += f"Dirección: {parte_details.get('direccion', 'N/A')}\n"
            texto += f"Contacto: {parte_details.get('contacto', 'N/A')}\n"
            texto += "--------------------------------------------------\nNotas:\n"
            texto += f"{parte_details.get('notas', 'Sin notas.')}"
            self.parte_detail_text.insert('1.0', texto)
        else:
            self.parte_detail_text.insert('1.0', "Detalles de la parte no encontrados o no disponibles.")

        self.parte_detail_text.config(state=tk.DISABLED)

    def limpiar_detalle_completo_parte(self):
        if not hasattr(self, 'parte_detail_text'): return
        self.parte_detail_text.config(state=tk.NORMAL)
        self.parte_detail_text.delete('1.0', tk.END)
        self.parte_detail_text.config(state=tk.DISABLED)
        if hasattr(self, 'details_parte_frame'):
            self.details_parte_frame.grid_remove() # Ocultar si no hay nada que mostrar