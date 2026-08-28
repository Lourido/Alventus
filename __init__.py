# -*- coding: utf-8 -*-
from . import models


def _rename_project_to_trip_hook(env):
    """
    Cambia automáticamente la palabra 'Proyecto' por 'Viaje' en todos los 
    menús del sistema, tanto en el nombre original como en las traducciones.
    Se ejecuta al instalar o actualizar el módulo.
    """
    # 1. Cambiar los nombres de los menús en español (tabla principal)
    env.cr.execute("""
        UPDATE ir_ui_menu 
        SET name = REPLACE(name, 'Proyecto', 'Viaje')
        WHERE name LIKE '%%Proyecto%%'
    """)
    env.cr.execute("""
        UPDATE ir_ui_menu 
        SET name = REPLACE(name, 'proyecto', 'viaje')
        WHERE name LIKE '%%proyecto%%'
    """)

    # 2. Cambiar las traducciones en la tabla ir_translation
    # (Esto asegura que el cambio sea persistente y no se sobrescriba)
    env.cr.execute("""
        UPDATE ir_translation
        SET value = REPLACE(value, 'Proyecto', 'Viaje')
        WHERE src LIKE '%%Proyecto%%'
          AND value LIKE '%%Proyecto%%'
          AND type = 'model'
          AND name LIKE 'ir.ui.menu,%%'
    """)
    env.cr.execute("""
        UPDATE ir_translation
        SET value = REPLACE(value, 'proyecto', 'viaje')
        WHERE src LIKE '%%proyecto%%'
          AND value LIKE '%%proyecto%%'
          AND type = 'model'
          AND name LIKE 'ir.ui.menu,%%'
    """)

    # 3. Forzar la recarga de los menús en la sesión actual
    env['ir.ui.menu']._invalidate_cache()