# -*- coding: utf-8 -*-
"""
Avisos (notificaciones push) en el teléfono para las tareas con hora de
inicio.

Cómo funciona, de principio a fin:

1. En la app (PWA), el usuario activa los avisos. El navegador del
   teléfono crea una "suscripción" (una dirección del servicio de avisos de
   Apple o de Google más dos claves) y la app la manda aquí con
   `app_register`. Se guarda en `alventus.push.subscription`, junto con la
   zona horaria del teléfono.
2. Una tarea programada (ir.cron, cada minuto) mira las tareas con hora de
   inicio (`fecha_desde`) y, cuando llega el momento del aviso que tenga
   elegido la tarea (a la hora, o 15/30/60 minutos antes), manda el aviso a
   los teléfonos de todos los usuarios que ven ese viaje en la app.
3. `alventus.push.log` apunta cada aviso mandado, para no repetirlo.

El envío sigue el estándar "Web Push" (RFC 8030), con el contenido cifrado
(RFC 8291, aes128gcm) y firmado con claves VAPID (RFC 8292). Funciona igual
con iPhone (iOS 16.4 o superior, con la app añadida a la pantalla de
inicio) y con Android. Se hace a mano con la librería `cryptography`, que
Odoo ya trae, para no tener que instalar nada más en el servidor (como
pywebpush). Las claves VAPID se generan solas la primera vez y se guardan
en Parámetros del sistema (alventus.push_vapid_private /
alventus.push_vapid_public). NO hay que cambiarlas: si se cambian, todos
los teléfonos tendrían que volver a activar los avisos.

Sobre las horas: la app guarda en `fecha_desde` la hora TAL CUAL la ve el
usuario ("10:00" se guarda como 10:00, sin pasarla a UTC). Por eso aquí se
interpreta como hora local del teléfono, con la zona horaria que el
teléfono manda al registrarse (y que actualiza cada vez que se abre la
app: si el viaje es a otro país, vale la hora de allí). El DÍA se toma de la
fecha que lleva el nombre de la etapa ("Día 3 - 23/09/2026"), que es la que
ve el usuario; si la etapa no la lleva, el de `fecha_desde`.
"""
import base64
import json
import logging
import os
import re
import struct
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import pytz
import requests

from odoo import api, fields, models
from odoo.osv import expression
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError:  # pragma: no cover - Odoo siempre la trae
    ec = None
    _logger.warning("Avisos push: falta la librería 'cryptography'; no se podrán mandar avisos.")


# Margen para un aviso que llega tarde (servidor reiniciado, cron
# atrasado...): hasta 15 minutos después de su momento todavía se manda;
# más tarde ya no tiene sentido ("empieza dentro de 15 minutos" dos horas
# después).
AVISO_MARGEN = timedelta(minutes=15)

# Cuánto guarda el servicio de avisos un aviso si el teléfono está apagado
# o sin cobertura (en segundos). Pasado este tiempo, se descarta.
AVISO_TTL = 3 * 3600

PARAM_PRIVADA = 'alventus.push_vapid_private'
PARAM_PUBLICA = 'alventus.push_vapid_public'

_FECHA_EN_NOMBRE = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})')


# ---------------------------------------------------------------------------
# Web Push: cifrado (RFC 8291) y firma VAPID (RFC 8292)
# ---------------------------------------------------------------------------

def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(text):
    text = (text or '').strip()
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _hkdf(salt, ikm, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def webpush_encrypt(p256dh, auth, payload, _salt=None, _as_private=None):
    """Cifra [payload] (bytes) para una suscripción, en formato aes128gcm.

    [_salt] y [_as_private] solo se usan en las pruebas (vector del RFC 8291,
    apéndice A); en uso normal se generan al azar en cada aviso.
    """
    ua_public = _b64url_decode(p256dh)
    auth_secret = _b64url_decode(auth)

    as_private = _as_private or ec.generate_private_key(ec.SECP256R1())
    as_public = as_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = as_private.exchange(ec.ECDH(), ua_key)

    ikm = _hkdf(auth_secret, shared, b'WebPush: info\x00' + ua_public + as_public, 32)
    salt = _salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b'Content-Encoding: aes128gcm\x00', 16)
    nonce = _hkdf(salt, ikm, b'Content-Encoding: nonce\x00', 12)

    # Un único registro: contenido + delimitador 0x02 (último registro).
    cifrado = AESGCM(cek).encrypt(nonce, payload + b'\x02', None)
    cabecera = salt + struct.pack('!I', 4096) + bytes([len(as_public)]) + as_public
    return cabecera + cifrado


def vapid_authorization(endpoint, private_key, public_b64, subject):
    """Cabecera Authorization (esquema "vapid") para mandar a [endpoint]."""
    url = urlparse(endpoint)
    claims = {
        'aud': '%s://%s' % (url.scheme, url.netloc),
        'exp': int(time.time()) + 12 * 3600,
        'sub': subject,
    }
    cabecera = _b64url(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
    cuerpo = _b64url(json.dumps(claims, separators=(',', ':')).encode())
    firmado = ('%s.%s' % (cabecera, cuerpo)).encode('ascii')
    der = private_key.sign(firmado, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    firma = _b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))
    return 'vapid t=%s.%s, k=%s' % (firmado.decode('ascii'), firma, public_b64)


# ---------------------------------------------------------------------------
# Suscripciones (un registro por teléfono)
# ---------------------------------------------------------------------------

class AlventusPushSubscription(models.Model):
    _name = 'alventus.push.subscription'
    _description = 'Avisos en el teléfono (suscripción push)'
    _order = 'last_seen desc'

    user_id = fields.Many2one('res.users', string='Usuario', required=True,
                              ondelete='cascade', index=True)
    endpoint = fields.Char(string='Dirección del servicio de avisos', required=True)
    p256dh = fields.Char(required=True)
    auth = fields.Char(required=True)
    timezone = fields.Char(string='Zona horaria del teléfono', default='Europe/Madrid')
    device = fields.Char(string='Teléfono / navegador')
    last_seen = fields.Datetime(string='Última vez', default=fields.Datetime.now)
    last_error = fields.Char(string='Último error')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('endpoint_unique', 'unique(endpoint)', 'Este teléfono ya está registrado.'),
    ]

    # ------------------------------------------------------------------
    # Llamadas desde la app (siempre sobre el usuario que llama)
    # ------------------------------------------------------------------

    @api.model
    def app_public_key(self):
        """Clave pública VAPID, que el teléfono necesita para suscribirse."""
        _private, public_b64 = self._vapid_keys()
        return public_b64

    @api.model
    def app_register(self, endpoint, p256dh, auth, timezone=None, device=None):
        """Registra (o actualiza) este teléfono para el usuario que llama.

        La app lo llama al activar los avisos y cada vez que se abre, para
        mantener al día la zona horaria y el usuario (si en el mismo
        teléfono entra otra persona, los avisos pasan a ser los suyos).
        """
        if not endpoint or not p256dh or not auth:
            return {'ok': False, 'error': 'Faltan datos de la suscripción'}
        tz = timezone if timezone in pytz.all_timezones_set else 'Europe/Madrid'
        vals = {
            'user_id': self.env.uid,
            'p256dh': p256dh,
            'auth': auth,
            'timezone': tz,
            'device': (device or '')[:200],
            'last_seen': fields.Datetime.now(),
            'last_error': False,
            'active': True,
        }
        existente = self.sudo().with_context(active_test=False).search(
            [('endpoint', '=', endpoint)], limit=1)
        if existente:
            existente.write(vals)
        else:
            self.sudo().create(dict(vals, endpoint=endpoint))
        return {'ok': True}

    @api.model
    def app_unregister(self, endpoint):
        """Da de baja este teléfono (al desactivar los avisos o cerrar sesión)."""
        if endpoint:
            self.sudo().with_context(active_test=False).search(
                [('endpoint', '=', endpoint)]).unlink()
        return {'ok': True}

    @api.model
    def app_send_test(self, endpoint=None):
        """Manda un aviso de prueba al teléfono que llama (o a todos los del
        usuario si no se indica cuál). Devuelve cuántos se han mandado y los
        errores, para que la app pueda decir si ha funcionado."""
        domain = [('user_id', '=', self.env.uid)]
        if endpoint:
            domain.append(('endpoint', '=', endpoint))
        subs = self.sudo().search(domain)
        mensaje = {
            'title': 'Alventus',
            'body': 'Los avisos funcionan. Te avisaremos de las tareas con hora de inicio.',
            'tag': 'alventus-prueba',
        }
        enviados, errores = 0, []
        for sub in subs:
            ok, error = sub._send(mensaje)
            if ok:
                enviados += 1
            elif error:
                errores.append(error)
        return {'sent': enviados, 'errors': errores}

    # ------------------------------------------------------------------
    # Claves y envío
    # ------------------------------------------------------------------

    @api.model
    def _vapid_keys(self):
        """Devuelve (clave privada, clave pública en base64url). La primera
        vez las genera y las guarda en Parámetros del sistema."""
        params = self.env['ir.config_parameter'].sudo()
        privada_pem = params.get_param(PARAM_PRIVADA)
        if privada_pem:
            privada = serialization.load_pem_private_key(privada_pem.encode(), password=None)
        else:
            privada = ec.generate_private_key(ec.SECP256R1())
            privada_pem = privada.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode()
            params.set_param(PARAM_PRIVADA, privada_pem)
        publica = _b64url(privada.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        if params.get_param(PARAM_PUBLICA) != publica:
            params.set_param(PARAM_PUBLICA, publica)
        return privada, publica

    @api.model
    def _vapid_subject(self):
        """Contacto que exige VAPID (Apple rechaza los avisos sin uno
        válido): el correo de la empresa o, si no hay, la web de Odoo."""
        correo = self.env.company.email
        if correo and '@' in correo:
            return 'mailto:%s' % correo.strip()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        if base.startswith('https://'):
            return base
        return 'mailto:avisos@alventus.app'

    def _send(self, mensaje):
        """Manda [mensaje] (dict con title, body, tag...) a este teléfono.
        Devuelve (ok, error). Si el servicio dice que la suscripción ya no
        existe (el usuario desinstaló la app o quitó el permiso), se borra."""
        self.ensure_one()
        if ec is None:
            return False, 'Falta la librería cryptography en el servidor'
        try:
            privada, publica = self._vapid_keys()
            cuerpo = webpush_encrypt(self.p256dh, self.auth,
                                     json.dumps(mensaje, ensure_ascii=False).encode('utf-8'))
            respuesta = requests.post(
                self.endpoint,
                data=cuerpo,
                headers={
                    'Authorization': vapid_authorization(
                        self.endpoint, privada, publica, self._vapid_subject()),
                    'Content-Encoding': 'aes128gcm',
                    'Content-Type': 'application/octet-stream',
                    'TTL': str(AVISO_TTL),
                    'Urgency': 'high',
                },
                timeout=15,
            )
        except Exception as e:  # noqa: BLE001 - un teléfono no puede tumbar el cron
            _logger.warning('Avisos push: error mandando a %s: %s', self.id, e)
            self.sudo().write({'last_error': str(e)[:250]})
            return False, str(e)

        if respuesta.status_code in (200, 201, 202):
            if self.last_error:
                self.sudo().write({'last_error': False})
            return True, None
        if respuesta.status_code in (404, 410):
            _logger.info('Avisos push: suscripción %s caducada, se borra', self.id)
            self.sudo().unlink()
            return False, None
        error = 'HTTP %s: %s' % (respuesta.status_code, (respuesta.text or '')[:200])
        _logger.warning('Avisos push: %s -> %s', self.id, error)
        self.sudo().write({'last_error': error[:250]})
        return False, error

    # ------------------------------------------------------------------
    # Tarea programada: avisos de las tareas con hora
    # ------------------------------------------------------------------

    @api.model
    def _cron_send_task_reminders(self):
        subs = self.sudo().search([])
        if not subs:
            return

        ahora_utc = pytz.utc.localize(datetime.utcnow())
        por_zona = {}
        for sub in subs:
            por_zona.setdefault(sub.timezone or 'Europe/Madrid', self.sudo().browse())
            por_zona[sub.timezone or 'Europe/Madrid'] |= sub
        ahora_local = {}
        for zona in por_zona:
            try:
                ahora_local[zona] = ahora_utc.astimezone(pytz.timezone(zona)).replace(tzinfo=None)
            except Exception:  # noqa: BLE001
                ahora_local[zona] = ahora_utc.replace(tzinfo=None)

        tareas = self._candidate_tasks(list(ahora_local.values()))
        if not tareas:
            return

        Log = self.env['alventus.push.log'].sudo()
        puede_ver = {}  # (usuario, viaje) -> bool

        for tarea in tareas:
            minutos_antes = tarea._alventus_offset_minutes()
            if minutos_antes is None:  # "Sin aviso"
                continue
            inicio = tarea._alventus_start_local()
            if not inicio:
                continue
            momento = inicio - timedelta(minutes=minutos_antes)
            for zona, subs_zona in por_zona.items():
                ahora = ahora_local[zona]
                if not (momento <= ahora < momento + AVISO_MARGEN):
                    continue
                mensaje = None
                for sub in subs_zona:
                    if not sub.exists():  # borrada en este mismo pase (caducada)
                        continue
                    clave = (sub.user_id.id, tarea.project_id.id)
                    if clave not in puede_ver:
                        puede_ver[clave] = sub.user_id.active and bool(
                            self.env['project.project'].with_user(sub.user_id).search_count(
                                [('id', '=', tarea.project_id.id), ('invisible', '=', False)]))
                    if not puede_ver[clave]:
                        continue
                    if Log.search_count([('task_id', '=', tarea.id),
                                         ('subscription_id', '=', sub.id),
                                         ('scheduled_for', '=', momento)]):
                        continue
                    if mensaje is None:
                        mensaje = tarea._alventus_push_message(inicio)
                    # Se apunta ANTES de mandar: si el envío falla, mejor
                    # perder un aviso que mandarlo en bucle cada minuto.
                    Log.create({'task_id': tarea.id, 'subscription_id': sub.id,
                                'scheduled_for': momento})
                    sub._send(mensaje)

        # Limpieza: el registro de avisos mandados solo hace falta unos días.
        Log.search([('create_date', '<', fields.Datetime.now() - timedelta(days=7))]).unlink()

    @api.model
    def _candidate_tasks(self, ahoras):
        """Tareas con hora que podrían tocar ahora: las de etapas con la fecha
        de hoy o mañana en el nombre, o con `fecha_desde` cerca de hoy."""
        dias = set()
        for ahora in ahoras:
            for delta in (-1, 0, 1):
                dias.add((ahora + timedelta(days=delta)).date())
        por_nombre = [[('stage_id.name', 'ilike', d.strftime('%d/%m/%Y'))] for d in dias]
        desde = datetime.combine(min(dias), datetime.min.time())
        hasta = datetime.combine(max(dias) + timedelta(days=1), datetime.min.time())
        por_fecha = [('fecha_desde', '>=', desde), ('fecha_desde', '<', hasta)]
        dominio = expression.AND([
            [('fecha_desde', '!=', False), ('project_id', '!=', False),
             ('aviso_antelacion', '!=', 'no'),
             ('project_id.invisible', '=', False)],
            expression.OR(por_nombre + [por_fecha]),
        ])
        return self.env['project.task'].sudo().search(dominio)


class AlventusPushLog(models.Model):
    _name = 'alventus.push.log'
    _description = 'Avisos push mandados'

    task_id = fields.Many2one('project.task', required=True, ondelete='cascade', index=True)
    subscription_id = fields.Many2one('alventus.push.subscription', required=True,
                                      ondelete='cascade', index=True)
    scheduled_for = fields.Datetime(string='Momento del aviso (hora local)', required=True)


# ---------------------------------------------------------------------------
# Tareas: momento del aviso y texto
# ---------------------------------------------------------------------------

class ProjectTaskPush(models.Model):
    _inherit = 'project.task'

    def _alventus_offset_minutes(self):
        """Minutos de antelación del aviso, o None si la tarea es "Sin aviso"."""
        self.ensure_one()
        if self.aviso_antelacion == 'no':
            return None
        try:
            return int(self.aviso_antelacion or 0)
        except (TypeError, ValueError):
            return 0

    def _alventus_start_local(self):
        """Fecha y hora de inicio "de reloj" (sin zona): el día de la etapa
        y la hora de `fecha_desde`."""
        self.ensure_one()
        if not self.fecha_desde:
            return None
        # Las 00:00 se toman como "sin hora" (igual que en la app): una
        # fecha sin hora queda a medianoche, y no se quiere avisar de
        # madrugada por eso.
        if self.fecha_desde.hour == 0 and self.fecha_desde.minute == 0:
            return None
        dia = self.fecha_desde.date()
        m = _FECHA_EN_NOMBRE.search(self.stage_id.name or '')
        if m:
            try:
                dia = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
            except ValueError:
                pass
        return datetime.combine(dia, self.fecha_desde.time().replace(second=0, microsecond=0))

    def _alventus_push_message(self, inicio):
        self.ensure_one()
        hora = inicio.strftime('%H:%M')
        minutos = self._alventus_offset_minutes() or 0
        if minutos >= 60:
            cuando = 'Empieza dentro de 1 hora'
        elif minutos > 0:
            cuando = 'Empieza dentro de %d minutos' % minutos
        else:
            cuando = 'Empieza ahora'
        lineas = [cuando]
        descripcion = html2plaintext(self.description or '').strip()
        if descripcion:
            lineas.append(descripcion[:160] + ('…' if len(descripcion) > 160 else ''))
        lineas.append('%s · %s' % (self.stage_id.name or '', self.project_id.name or ''))
        return {
            'title': '%s · %s' % (hora, self.name),
            'body': '\n'.join(lineas),
            'tag': 'alventus-tarea-%s' % self.id,
            'projectId': self.project_id.id,
            'stageName': self.stage_id.name or '',
        }
