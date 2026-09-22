# -*- coding: utf-8 -*-
"""
Registro de uso de la app: quién la usa, con qué teléfono, desde cuándo y
qué hace dentro.

Dos modelos:

- `alventus.app.session`: una fila por cada vez que alguien abre la app
  (usuario, tipo de teléfono, hora de inicio, hora del último movimiento y
  número de cosas que ha hecho).
- `alventus.app.event`: lo que va haciendo dentro (pantallas que abre y
  acciones: crear una tarea, subir una foto, generar un PDF...).

La app no manda un aviso al servidor por cada toque: los va apuntando en el
teléfono y los sube en grupo cada poco (y cuando vuelve la cobertura, si se
quedó sin ella), con la hora real de cada uno. Ver
lib/services/usage_log_service.dart.

Se guarda tres meses; una tarea programada borra cada noche lo más antiguo.
Solo lo ve Administración (menú Viajes > Registro de uso de la app).
"""
import logging
from datetime import datetime, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Cuánto tiempo se conserva el registro.
DIAS_QUE_SE_GUARDA = 90

# Tope de eventos por llamada, para que un teléfono que lleve mucho tiempo
# sin cobertura no mande de golpe una lista enorme.
MAX_EVENTOS = 200


class AlventusAppSession(models.Model):
    _name = 'alventus.app.session'
    _description = 'Uso de la app: sesión'
    _order = 'start desc'

    user_id = fields.Many2one('res.users', string='Usuario', required=True,
                              ondelete='cascade', index=True)
    device_type = fields.Selection(
        [('ios', 'iPhone / iPad'), ('android', 'Android'), ('other', 'Otro')],
        string='Tipo de teléfono', default='other', index=True)
    device_detail = fields.Char(string='Detalle del teléfono')
    timezone = fields.Char(string='Zona horaria del teléfono')
    start = fields.Datetime(string='Hora de inicio', required=True,
                            default=fields.Datetime.now, index=True)
    last_activity = fields.Datetime(string='Última actividad')
    event_count = fields.Integer(string='Nº de acciones', default=0)
    event_ids = fields.One2many('alventus.app.event', 'session_id', string='Qué ha hecho')

    @api.depends('user_id', 'start')
    def _compute_display_name(self):
        """Nombre que se ve al referirse a una sesión: "Ana - 23/09/2026 08:15"."""
        for session in self:
            momento = fields.Datetime.context_timestamp(session, session.start) if session.start else False
            session.display_name = '%s - %s' % (
                session.user_id.name or '',
                momento.strftime('%d/%m/%Y %H:%M') if momento else '',
            )

    # ------------------------------------------------------------------
    # Llamadas desde la app
    # ------------------------------------------------------------------

    @api.model
    def app_start_session(self, device_type=None, device_detail=None, timezone=None, start=None):
        """Abre una sesión de uso para el usuario que llama y devuelve su id.

        [start]: hora de inicio real ("2026-09-23 08:15:00", en UTC). Se manda
        porque la app puede haber arrancado sin cobertura y subir esto más
        tarde; si no viene, se usa la hora de ahora.
        """
        tipo = device_type if device_type in ('ios', 'android', 'other') else 'other'
        session = self.sudo().create({
            'user_id': self.env.uid,
            'device_type': tipo,
            'device_detail': (device_detail or '')[:120],
            'timezone': (timezone or '')[:60],
            'start': self._parse_moment(start) or fields.Datetime.now(),
            'last_activity': fields.Datetime.now(),
        })
        return session.id

    @api.model
    def app_log(self, session_id, events):
        """Apunta lo que ha hecho el usuario. [events]: lista de
        {t, kind, action, detail} — t en UTC ("2026-09-23 08:15:00"),
        kind 'screen' o 'action'."""
        if not events:
            return {'ok': True}
        session = self.sudo().browse(int(session_id or 0)).exists()
        if not session or session.user_id.id != self.env.uid:
            # La sesión no existe (registro ya borrado, o de otro usuario):
            # se abre una nueva para no perder lo que haya hecho.
            session = self.sudo().browse(self.app_start_session())
        valores = []
        ultimo = None
        for evento in events[:MAX_EVENTOS]:
            if not isinstance(evento, dict):
                continue
            momento = self._parse_moment(evento.get('t')) or fields.Datetime.now()
            ultimo = max(ultimo, momento) if ultimo else momento
            valores.append({
                'session_id': session.id,
                'timestamp': momento,
                'kind': evento.get('kind') if evento.get('kind') in ('screen', 'action', 'error') else 'action',
                'action': (evento.get('action') or '')[:120],
                'detail': (evento.get('detail') or '')[:200],
                'offline': bool(evento.get('offline')),
            })
        if valores:
            self.env['alventus.app.event'].sudo().create(valores)
            session.write({
                'last_activity': ultimo or fields.Datetime.now(),
                'event_count': session.event_count + len(valores),
            })
        return {'ok': True, 'session_id': session.id}

    @api.model
    def _parse_moment(self, value):
        """Convierte "2026-09-23 08:15:00" (o con T y Z) a datetime, o False.
        Nunca acepta una hora futura de más de un día (reloj mal puesto)."""
        if not value:
            return False
        texto = str(value).strip().replace('T', ' ').replace('Z', '')
        if '.' in texto:
            texto = texto.split('.')[0]
        try:
            momento = datetime.strptime(texto[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return False
        if momento > datetime.utcnow() + timedelta(days=1):
            return False
        return momento

    # ------------------------------------------------------------------
    # Limpieza
    # ------------------------------------------------------------------

    @api.model
    def _cron_clean_usage_log(self):
        limite = fields.Datetime.now() - timedelta(days=DIAS_QUE_SE_GUARDA)
        eventos = self.env['alventus.app.event'].sudo().search([('timestamp', '<', limite)])
        if eventos:
            eventos.unlink()
        sesiones = self.sudo().search([('start', '<', limite)])
        if sesiones:
            sesiones.unlink()


class AlventusAppEvent(models.Model):
    _name = 'alventus.app.event'
    _description = 'Uso de la app: pantalla o acción'
    _order = 'timestamp desc, id desc'

    session_id = fields.Many2one('alventus.app.session', string='Sesión',
                                 required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one(related='session_id.user_id', string='Usuario',
                              store=True, index=True)
    device_type = fields.Selection(related='session_id.device_type',
                                   string='Tipo de teléfono', store=True)
    timestamp = fields.Datetime(string='Momento', required=True, index=True)
    kind = fields.Selection(
        [('screen', 'Pantalla'), ('action', 'Acción'), ('error', 'Error')],
        string='Tipo', default='action', index=True)
    action = fields.Char(string='Qué hace', required=True)
    detail = fields.Char(string='Sobre qué')
    offline = fields.Boolean(string='Sin cobertura')
