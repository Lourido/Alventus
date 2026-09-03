# -*- coding: utf-8 -*-
import base64
import re
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    start_date = fields.Date(string='Fecha de inicio del viaje')

    # -1. Oculto para todos (excepto Administracion). Se usa para "borrar" un
    # viaje sin eliminarlo: mientras este marcado, nadie salvo Administracion
    # puede verlo, ni siquiera el propio Gestor del proyecto.
    invisible = fields.Boolean(string='Invisible', default=False)

    # Solo para pintar la insignia VISIBLE/INVISIBLE en la lista de proyectos
    # (el widget "badge" no admite campos booleanos, solo texto/seleccion).
    invisible_label = fields.Char(string='Visibilidad', compute='_compute_invisible_label')

    @api.depends('invisible')
    def _compute_invisible_label(self):
        for record in self:
            record.invisible_label = 'Invisible' if record.invisible else 'Visible'

    def action_toggle_invisible(self):
        """Alterna el campo "invisible" (usado por los dos botones-insignia
        VISIBLE/INVISIBLE del formulario de proyectos)."""
        for record in self:
            record.invisible = not record.invisible

    # 0. Responsables adicionales (ademas del "Usuario responsable" / user_id).
    # Cualquier usuario que aparezca aqui, o como user_id, puede ver y gestionar
    # el proyecto (ver la regla de seguridad en security/security.xml).
    responsible_user_ids = fields.Many2many(
        'res.users',
        'project_additional_responsible_rel',
        'project_id',
        'user_id',
        string='Responsables adicionales',
        help="Usuarios adicionales, aparte del Usuario responsable, que tambien pueden ver y gestionar este proyecto."
    )

    # 1. Campo para contactos de referencia (Personas o empresas)
    reference_contact_ids = fields.Many2many(
        'res.partner',
        'project_reference_contact_rel',
        'project_id',
        'partner_id',
        string='Contactos de Referencia',
        help="Personas o empresas de contacto para este proyecto."
    )

    # 2. Campo para archivos de ruta específicos (KMZ, GPX, GeoJSON)
    route_file_ids = fields.One2many(
        'project.route.file',
        'project_id',
        string='Archivos de Ruta'
    )

    def copy(self, default=None):
        """
        Al duplicar un proyecto, también se copian los contactos de referencia 
        y los archivos de ruta con sus descripciones.
        """
        self.ensure_one()
        
        # A. Duplicar el proyecto (comportamiento estándar de Odoo)
        new_project = super().copy(default)
        
        # B. Copiar los contactos de referencia al nuevo proyecto
        if self.reference_contact_ids:
            new_project.write({
                'reference_contact_ids': [(6, 0, self.reference_contact_ids.ids)]
            })
        
        # C. Copiar los archivos de ruta con sus descripciones
        for route_file in self.route_file_ids:
            route_file.copy({'project_id': new_project.id})
        
        return new_project

    def action_export_tasks_to_ics(self):
        """
        Método existente para exportar las tareas a formato ICS.
        ¡IMPORTANTE! Pega aquí tu código existente de exportación a ICS.
        """
        self.ensure_one()
        
        # ---------------------------------------------------------------------
        # PEGA AQUÍ TU LÓGICA EXISTENTE DE EXPORTACIÓN A ICS
        # ---------------------------------------------------------------------
        # Ejemplo:
        # raise UserError(_("Funcionalidad de exportación ICS pendiente de restaurar."))
        # Ejemplo de cómo podría verse (ajústalo a tu código real):
        # 
        # tasks = self.env['project.task'].search([('project_id', '=', self.id)])
        # if not tasks:
        #     raise UserError(_("No hay tareas para exportar."))
        # 
        # # ... tu lógica de generación del archivo ICS ...
        # 
        # attachment = self.env['ir.attachment'].create({
        #     'name': f'{self.name}.ics',
        #     'type': 'binary',
        #     'datas': base64.b64encode(ics_content.encode('utf-8')),
        #     'res_model': 'project.project',
        #     'res_id': self.id,
        # })
        # 
        # return {
        #     'type': 'ir.actions.act_url',
        #     'url': f'/web/content/{attachment.id}?download=true',
        #     'target': 'new',
        # }
        # ---------------------------------------------------------------------
        
        raise UserError(_("Por favor, restaura tu código de exportación ICS en este método."))