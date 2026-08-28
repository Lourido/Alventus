# -*- coding: utf-8 -*-
from . import models

def _rename_project_menus_hook(env):
    """Fuerza el renombrado de los menús de Proyecto a Viajes usando el ORM"""
    new_names = {
        'project.menu_main_pm': 'Viajes',
        'project.menu_projects': 'Viajes',
        'project.menu_project_management': 'Tareas de Viaje'
    }
    for xml_id, new_name in new_names.items():
        menu = env.ref(xml_id, raise_if_not_found=False)
        if menu:
            menu.sudo().write({'name': new_name})