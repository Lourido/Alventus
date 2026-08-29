# -*- coding: utf-8 -*-
from . import models
import logging

_logger = logging.getLogger(__name__)


def _rename_project_to_trip_hook(env):
    """
    1. Cambia automáticamente la palabra 'Proyecto' por 'Viaje' en todos los menús.
    2. Configura TODOS los usuarios no administradores existentes.
    """
    _logger.info("=" * 60)
    _logger.info("INICIANDO HOOK DE POST-INSTALACIÓN")
    _logger.info("=" * 60)
    
    # ========================================
    # PARTE 1: Renombrar "Proyecto" por "Viaje"
    # ========================================
    _logger.info("Renombrando menús de Proyecto a Viaje...")
    
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
    
    _logger.info("Menús renombrados correctamente")

    # ========================================
    # PARTE 2: Configurar usuarios existentes
    # ========================================
    _logger.info("Buscando usuarios no administradores...")
    
    # Obtener el grupo de administradores
    admin_group = env.ref('base.group_system', raise_if_not_found=False)
    
    # Buscar todos los usuarios internos (no portales)
    all_users = env['res.users'].search([('share', '=', False)])
    
    _logger.info(f"Total de usuarios internos encontrados: {len(all_users)}")
    
    configured_count = 0
    for user in all_users:
        # Verificar si NO es administrador
        is_admin = admin_group and admin_group.id in user.groups_id.ids
        
        if not is_admin:
            _logger.info(f"Configurando usuario: {user.login} (ID: {user.id})")
            user._configure_as_trip_manager()
            configured_count += 1
        else:
            _logger.info(f"Usuario {user.login} es administrador, omitido")
    
    _logger.info(f"Total de usuarios configurados: {configured_count}")
    
    # Forzar la recarga de los menús
    env['ir.ui.menu']._invalidate_cache()
    
    _logger.info("=" * 60)
    _logger.info("HOOK COMPLETADO")
    _logger.info("=" * 60)