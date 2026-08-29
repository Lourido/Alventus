# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribe la creación de usuarios para configurar automáticamente
        a los usuarios no administradores.
        """
        users = super().create(vals_list)
        
        for user in users:
            admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
            is_admin = admin_group and admin_group.id in user.groups_id.ids
            
            if not is_admin:
                _logger.info(f"Configurando usuario no administrador: {user.login}")
                user._configure_as_trip_manager()
            else:
                _logger.info(f"Usuario {user.login} es administrador, no se configura")
        
        return users

    def _configure_as_trip_manager(self):
        """
        Configura al usuario como Gestor de Viajes con acceso exclusivo
        al módulo de Viajes. NO asigna project.group_project_user.
        """
        self.ensure_one()
        
        _logger.info(f"Iniciando configuración de usuario: {self.login}")
        
        # Obtener los grupos necesarios
        group_user = self.env.ref('base.group_user', raise_if_not_found=False)
        group_gestor_viajes = self.env.ref('alf_proyecto_alventus.group_gestor_viajes', raise_if_not_found=False)
        
        # Obtener la acción de Viajes (Kanban de proyectos)
        action_viajes = self.env.ref('project.open_view_project_all', raise_if_not_found=False)
        
        # Construir la lista de grupos (SOLO estos 2, SIN project.group_project_user)
        group_ids = []
        if group_user:
            group_ids.append(group_user.id)
            _logger.info(f"Añadiendo grupo: {group_user.name}")
        if group_gestor_viajes:
            group_ids.append(group_gestor_viajes.id)
            _logger.info(f"Añadiendo grupo: {group_gestor_viajes.name}")
        
        # Configurar el usuario
        vals = {
            'groups_id': [(6, 0, group_ids)],  # (6, 0, [...]) REEMPLAZA todos los grupos
        }
        
        if action_viajes:
            vals['action_id'] = action_viajes.id
            _logger.info(f"Acción de inicio configurada: {action_viajes.name}")
        
        self.write(vals)
        _logger.info(f"Usuario {self.login} configurado correctamente con {len(group_ids)} grupos")