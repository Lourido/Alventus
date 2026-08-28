# -*- coding: utf-8 -*-
{
    'name': 'ALF - Gestión de Viajes (ICS)',
    'version': '18.0.7.0.0',
    'category': 'Project',
    'summary': 'Gestión de viajes con importación/exportación ICS y creación por días',
    'depends': ['project'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/res_users.xml',
        'views/project_task_views.xml',
        'views/project_project_views.xml',
        'views/project_wizard_views.xml',
        'views/project_menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'alf_proyecto_alventus/static/src/css/custom.css',
        ],
    },
    'installable': True,
    'application': False,
    'post_init_hook': '_rename_project_menus_hook',
}