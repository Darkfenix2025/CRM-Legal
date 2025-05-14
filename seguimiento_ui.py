# seguimiento_ui.py
import tkinter as tk
from tkinter import ttk, messagebox
import datetime
# Asumiremos que db_crm se pasa o se importa de alguna manera si es necesario directamente,
# pero es mejor que la lógica de BD la maneje CRMLegalApp y pase datos.
# O, si esta clase llama directamente a la BD:
# import crm_database as db_crm # O el nombre que estés usando

class SeguimientoTab(ttk.Frame):
    def __init__(self, parent, app_controller, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app_controller = app_controller # Referencia a CRMLegalApp para llamar a sus métodos
                                            # o acceder a self.selected_case, etc.
        self.db_crm = self.app_controller.db_crm # Acceder al manejador de BD del CRM
                                                 # Asumiendo que CRMLegalApp tiene un atributo self.db_crm

        self.selected_actividad_id = None # Para rastrear la actividad seleccionada en el treeview

        self._create_widgets()
        # No cargamos datos aquí directamente, CRMLegalApp lo hará cuando se seleccione un caso

    def _create_widgets(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1) # Fila para Treeview
        self.rowconfigure(1, weight=0) # Fila para botones

        # Frame para el Treeview y su Scrollbar
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.rowconfigure(1, weight=0) # Scrollbar X

        actividad_cols = ('ID', 'Fecha/Hora', 'Tipo', 'Descripción Resumida')
        self.actividad_tree = ttk.Treeview(tree_frame, columns=actividad_cols, show='headings', selectmode='browse')
        # ... (configuración de headings y columns igual que antes) ...
        self.actividad_tree.heading('ID', text='ID')
        self.actividad_tree.heading('Fecha/Hora', text='Fecha y Hora')
        self.actividad_tree.heading('Tipo', text='Tipo Actividad')
        self.actividad_tree.heading('Descripción Resumida', text='Descripción')

        self.actividad_tree.column('ID', width=40, stretch=tk.NO, anchor=tk.CENTER)
        self.actividad_tree.column('Fecha/Hora', width=140, stretch=tk.NO)
        self.actividad_tree.column('Tipo', width=120, stretch=tk.NO)
        self.actividad_tree.column('Descripción Resumida', width=400, stretch=True)

        actividad_scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.actividad_tree.yview)
        self.actividad_tree.configure(yscrollcommand=actividad_scrollbar_y.set)
        actividad_scrollbar_y.grid(row=0, column=1, sticky='ns')

        actividad_scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.actividad_tree.xview)
        self.actividad_tree.configure(xscrollcommand=actividad_scrollbar_x.set)
        actividad_scrollbar_x.grid(row=1, column=0, sticky='ew')
        
        self.actividad_tree.grid(row=0, column=0, sticky='nsew')
        self.actividad_tree.bind('<<TreeviewSelect>>', self.on_actividad_select_treeview) # Renombrado para claridad

        # Frame para botones
        actions_frame = ttk.Frame(self)
        actions_frame.grid(row=1, column=0, sticky='ew', pady=5)
        
        self.add_actividad_btn = ttk.Button(actions_frame, text="Agregar Nueva Actividad", 
                                            command=self._open_actividad_dialog_wrapper, state=tk.DISABLED)
        self.add_actividad_btn.pack(side=tk.LEFT, padx=5)
        # (Botones de Editar/Eliminar podrían ir aquí después)

    def _open_actividad_dialog_wrapper(self):
        # Este wrapper llama al método en app_controller (CRMLegalApp)
        # para mantener la lógica del diálogo principal allí o también modularizar el diálogo.
        # Por ahora, asumimos que el diálogo es manejado por CRMLegalApp.
        if self.app_controller.selected_case:
            self.app_controller.open_actividad_dialog_for_seguimiento_tab(self.app_controller.selected_case['id'])
        else:
            messagebox.showwarning("Advertencia", "No hay un caso seleccionado.", parent=self)


    def load_actividades(self, caso_id):
        for i in self.actividad_tree.get_children():
            self.actividad_tree.delete(i)

        if caso_id:
            actividades = self.db_crm.get_actividades_by_caso_id(caso_id, order_desc=True)
            for act in actividades:
                fecha_hora_display = datetime.datetime.strptime(act['fecha_hora'], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
                desc_completa = act.get('descripcion', '')
                desc_resumida = (desc_completa[:75] + '...') if len(desc_completa) > 75 else desc_completa
                self.actividad_tree.insert('', tk.END, values=(
                    act['id'], fecha_hora_display, act.get('tipo_actividad', 'N/A'), desc_resumida
                ), iid=str(act['id']))
            self.add_actividad_btn.config(state=tk.NORMAL)
        else:
            self.add_actividad_btn.config(state=tk.DISABLED)
            self.selected_actividad_id = None # Limpiar selección

    def on_actividad_select_treeview(self, event=None):
        selected_items = self.actividad_tree.selection()
        if selected_items:
            self.selected_actividad_id = int(selected_items[0])
            # Podrías emitir un evento personalizado o llamar a un método en app_controller
            # si otras partes de la UI necesitan saber sobre la actividad seleccionada.
            # Por ahora, solo guardamos el ID.
            # self.app_controller.mostrar_detalle_actividad_completo(self.selected_actividad_id) # Si el detalle está en CRMLegalApp
            print(f"Actividad seleccionada en SeguimientoTab: ID {self.selected_actividad_id}")
        else:
            self.selected_actividad_id = None

    def set_add_button_state(self, state):
        self.add_actividad_btn.config(state=state)