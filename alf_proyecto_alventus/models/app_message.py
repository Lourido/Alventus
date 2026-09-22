# -*- coding: utf-8 -*-
"""
Mensajes de la app que se pueden personalizar desde Odoo.

La app trae de serie un texto para cada aviso o error ("Lo siento. Tendrás
que esperar a que tengas cobertura para hacerlo."...). Aquí se puede
escribir otro, y la app lo usa a partir de la próxima vez que se abra, sin
tener que volver a compilarla ni desplegar nada.

Cada mensaje tiene:
 - un CÓDIGO, que es lo que la app pide (no se toca);
 - dónde sale, para saber de cuál se trata;
 - el texto original de la app (solo para verlo);
 - "Tu mensaje": lo que se quiera poner. Si se deja vacío, vale el original.

Los códigos y textos originales se cargan solos al actualizar el módulo
(data/app_messages.xml); "Tu mensaje" NUNCA se pisa al actualizar.

Ver también lib/utils/app_messages.dart en la app.
"""
from odoo import api, fields, models


class AlventusAppMessage(models.Model):
    _name = 'alventus.app.message'
    _description = 'Mensaje de la app'
    _order = 'sequence, code'

    sequence = fields.Integer(default=10)
    code = fields.Char(string='Código', required=True, readonly=True, index=True)
    name = fields.Char(string='Dónde sale', required=True)
    default_text = fields.Text(string='Texto original de la app', readonly=True)
    text = fields.Text(
        string='Tu mensaje',
        help='Déjalo vacío para que la app use el texto original.')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Ya existe un mensaje con ese código.'),
    ]

    def action_restore_default(self):
        """Botón "Volver al texto original": borra el personalizado."""
        self.write({'text': False})
        return True

    @api.model
    def app_messages(self):
        """Lo que pide la app al abrirse: {código: texto a enseñar}.

        Solo devuelve los que están personalizados; de los demás, la app ya
        tiene su texto original.
        """
        mensajes = self.sudo().search([('text', '!=', False)])
        return {m.code: (m.text or '').strip() for m in mensajes if (m.text or '').strip()}
