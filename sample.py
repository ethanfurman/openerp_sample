# -*- coding: utf-8 -*-

# always
from openerp.osv import fields, osv
from openerp.osv.osv import except_osv as ERPError
from openerp.osv.orm import THREE_DAYS, FORTNIGHT
import logging

# often useful
from openerp import SUPERUSER_ID

# occasionally useful
import base64
import time
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, ormcache

from fnx.oe import Proposed

_logger = logging.getLogger(__name__)

COMMON_SHIPPING = (
        ('fedex_first', 'FedEx First Overnight'),
        ('fedex_next', 'FedEx Next Overnight (10:30am)'),
        ('fedex_overnight', 'FedEx Overnight (5pm)'),
        ('fedex_2', 'FedEx 2-Day'),
        ('fedex_3', 'FedEx 3-Day'),
        ('fedex', 'FedEx Select Saver'),
        ('fedex_ground', 'FedEx Ground'),
        ('ups_first', 'UPS First Overnight'),
        ('ups_next', 'UPS Next Overnight (10:30am)'),
        ('ups_overnight', 'UPS Overnight (5pm)'),
        ('ups_2', 'UPS 2-Day'),
        ('ups_3', 'UPS 3-Day'),
        ('ups_ground', 'UPS Ground'),
        ('ontrac_first', 'ONTRAC First Overnight'),
        ('ontrac_next', 'ONTRAC Next Overnight (8am)'),
        ('ontrac_overnight', 'ONTRAC Overnight (5pm)'),
        ('ontrac_2', 'ONTRACK 2-Day'),
        ('dhl', 'DHL (give to receptionist)'),
        )

REQUEST_SHIPPING = (
        ('cheap_1', 'Cheapest 1-Day'),
        ('cheap_2', 'Cheapest 2-Day'),
        ('cheap_3', 'Cheapest 3-Day'),
        ('cheap_ground', 'Cheapest Ground'),
        ) + COMMON_SHIPPING + (
        ('international', 'International (give to receptionist)'),
        )

shipping_urls = {
        'fedex':  'https://www.fedex.com/apps/fedextrack/?tracknumbers=%s&cntry_code=us',
        'ups':    'https://wwwapps.ups.com/WebTracking/track/?tracking=%s',
        'ontrac': 'https://www.ontrac.com/trackingres.asp?tracking_number=%s',
        'dhl':    'http://webtrack.dhlglobalmail.com/?trackingnumber=%s',
        }

# custom tables
class sample_request(osv.Model):
    _name = 'sample.request'
    _inherit = ['mail.thread']

    _track = {
        'state' : {
            'sample.mt_sample_request_new': lambda s, c, u, r, ctx: r['state'] == 'draft',
            'sample.mt_sample_request_production': lambda s, c, u, r, ctx: r['state'] == 'production',
            'sample.mt_sample_request_ready': lambda s, c, u, r, ctx: r['state'] == 'shipping',
            'sample.mt_sample_request_transiting': lambda s, c, u, r, ctx: r['state'] == 'transit',
            'sample.mt_sample_request_received': lambda s, c, u, r, ctx: r['state'] == 'complete',
            }
        }

    def _get_address(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        if ids:
            res_partner = self.pool.get('res.partner')
            for record in self.read(cr, uid, ids, fields=['partner_id']):
                id = record['id']
                partner_id = record['partner_id'][0]
                partner = res_partner.browse(cr, uid, partner_id)
                label = partner.name + '\n' + res_partner._display_address(cr, uid, partner)
                res[id] = label
        return res

    def _get_pdf(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        dbname = cr.dbname
        if ids:
            for id in ids:
                res[id] = '<a href="/samplerequest/%s/SampleRequest_%d.pdf">Printer Friendly</a>' % (dbname, id)
        return res

    def _get_tracking_url(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        for row in self.read(cr, uid, ids, fields=['id', 'actual_ship', 'tracking'], context=context):
            id = row['id']
            tracking_no = row['tracking']
            shipper = row['actual_ship']
            res[id] = False
            if shipper and tracking_no:
                shipper = shipper.split('_')[0]
                res[id] = '<a href="%s" target="_blank">%s</a>' % (shipping_urls[shipper] % tracking_no, tracking_no)
        return res

    _columns = {
        'state': fields.selection(
            (
                ('draft', 'Draft'),
                ('production', 'Production'),   # <- julian_date_code set
                ('shipping', 'Ready to Ship'),  # <- all product_lot's filled in
                ('transit', 'In Transit'),      # <- tracking number entered
                ('complete', 'Received'),       # <- received_datetime entered
                ),
            string='Status',
            ),
        'department': fields.selection([('marketing', 'SAMMA - Marketing'), ('sales', 'SAMSA - Sales')], string='Department', required=True, track_visibility='onchange'),
        'user_id': fields.many2one('res.users', 'Request by', required=True, track_visibility='onchange'),
        'create_date': fields.datetime('Request created on', readonly=True, track_visibility='onchange'),
        'send_to': fields.selection([('rep', 'Sales Rep in office'), ('address', 'Customer')], string='Send to', required=True, track_visibility='onchange'),
        'target_date_type': fields.selection([('ship', 'Ship'), ('arrive', 'Arrive')], string='Samples must', required=True, track_visibility='onchange'),
        'target_date': fields.date('Target Date', required=True, track_visibility='onchange'),
        'instructions': fields.text('Special Instructions', track_visibility='onchange'),
        'partner_id': fields.many2one('res.partner', 'Recipient', required=True, track_visibility='onchange'),
        # fields needed for shipping
        'address': fields.function(_get_address, type='text', string='Shipping Label', track_visibility='onchange'),
        'address_type': fields.selection([('business', 'Commercial'), ('personal', 'Residential')], string='Address type', required=True, track_visibility='onchange'),
        'ice': fields.boolean('Add ice', track_visibility='onchange'),
        'request_ship': fields.selection(REQUEST_SHIPPING, string='Ship Via', required=True, track_visibility='onchange'),
        'actual_ship': fields.selection(COMMON_SHIPPING, string='Actual Shipping Method', track_visibility='onchange'),
        'actual_ship_date': fields.date('Shipped on', track_visibility='onchange'),
        'third_party_account': fields.char('3rd Party Account Number', size=64, track_visibility='onchange'),
        'tracking': fields.char('Tracking #', size=32, track_visibility='onchange'),
        'tracking_url': fields.function(_get_tracking_url, type='char', size=256, string='Tracking #', store=False),
        'shipping_cost': fields.float('Shipping Cost', track_visibility='onchange'),
        'received_by': fields.char('Received by', size=32, track_visibility='onchange'),
        'received_datetime': fields.datetime('Received when', track_visibility='onchange'),
        # field for samples department only
        'invoice': fields.char('Invoice #', size=32, track_visibility='onchange'),
        'julian_date_code': fields.char('Julian Date Code', size=12, track_visibility='onchange'),
        'production_order': fields.char('Production Order #', size=12, track_visibility='onchange'),
        'prep_time': fields.float('Preparation Time'),
        'finish_date': fields.date('Sample Packaged Date', track_visibility='onchange'),
        # products to sample
        'product_ids': fields.one2many('sample.product', 'request_id', string='Items', track_visibility='onchange'),
        # link to printer-friendly form
        'printer_friendly': fields.function(_get_pdf, type='html', store=False),
        }

    _defaults = {
        'user_id': lambda obj, cr, uid, ctx: uid,
        'address_type': 'business',
        'state': 'draft',
        }

    _permissions = [
        (('department', 'user_id', 'create_date', 'send_to', 'target_date_type', 'target_date', 'instructions', 'partner_id', 'address_type', 'request_ship', 'ice'),
            ('sample.group_sample_manager', {'readonly': False}),
            ('sample.group_sample_user', {'readonly': ['|',('state','in',['transit', 'complete']), ('write_date','>',FORTNIGHT)]}),
            ('base.group_sale_salesman', {'readonly': ['|',('state','in',['production', 'shipping', 'transit', 'complete']), ('write_date','>',FORTNIGHT)]}),
            ('default', {'readonly': True}),
            ),
        (('invoice', 'julian_date_code', 'production_order', 'finish_date'),
            ('sample.group_sample_manager', {'readonly': False}),
            ('sample.group_sample_user', {'readonly': [('write_date','>',FORTNIGHT)]}),
            ('default', {'readonly': True}),
            ),
        (('actual_ship', 'actual_ship_date', 'third_party_account', 'tracking', 'shipping_cost'),
            ('sample.group_sample_manager', {'readonly': False}),
            ('sample.group_sample_user', {'readonly': [('write_date','>',FORTNIGHT)]}),
            ('sample.group_sample_shipping', {'readonly': ['|',('state','in',['complete']), ('write_date','>',THREE_DAYS)]}),
            ('default', {'readonly': True}),
            ),
        (('received_by', 'received_datetime'),
            ('sample.group_sample_manager', {'readonly': False}),
            ('sample.group_sample_user', {'readonly': [('write_date','>',THREE_DAYS)]}),
            ('default', {'readonly': True}),
            ),
        ]

    def create(self, cr, uid, values, context=None):
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        follower_ids = [u.id for u in user.company_id.sample_request_followers_ids]
        if follower_ids:
            values['message_follower_user_ids'] = follower_ids
        return super(sample_request, self).create(cr, uid, values, context=context)

    def name_get(self, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = []
        for record in self.browse(cr, uid, ids, context=context):
            name = record.partner_id.name
            if record.partner_id.parent_id:
                name = name + ' (%s)' % record.partner_id.parent_id.name
            invoice = record.invoice or ''
            if invoice:
                invoice += ': '
            res.append((record.id, invoice + name))
        return res

    def onchange_partner_id(self, cr, uid, ids, partner_id, context=None):
        res = {}
        if partner_id:
            res_partner = self.pool.get('res.partner')
            partner = res_partner.browse(cr, uid, partner_id)
            label = partner.name + '\n' + res_partner._display_address(cr, uid, partner)
            res['value'] = {'address': label}
        return res

    def write(self, cr, uid, ids, values, context=None):
        if ids:
            if isinstance(ids, (int, long)):
                ids = [ids]
            user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
            for record in self.browse(cr, SUPERUSER_ID, ids, context=context):
                vals = values.copy()
                proposed = Proposed(self, cr, values, record)
                state = 'draft'
                old_state = record.state
                if proposed.julian_date_code:
                    state = 'production'
                if proposed.product_ids:
                    for sample_product in proposed.product_ids:
                        if not sample_product.product_lot:
                            break
                    else:
                        state = 'shipping'
                if proposed.finish_date:
                    state = 'shipping'
                if proposed.tracking:
                    state = 'transit'
                if proposed.received_datetime:
                    state = 'complete'
                if proposed.state != state:
                    vals['state'] = state
                if 'product_ids' in vals and old_state == 'production':
                    if not user.has_group('sample.group_sample_user'):
                        raise ERPError('Error', 'Order is already in Production.  Talk to someone in Samples to get more productios added.')
                super(sample_request, self).write(cr, uid, [record.id], vals, context=context)
            return True
        return super(sample_request, self).write(cr, uid, ids, values, context=context)


class sample_qty_label(osv.Model):
    _name = 'sample.qty_label'
    _order = 'common desc, name asc'

    _columns = {
        'name': fields.char('Qty Label', size=16, required=True),
        'common': fields.boolean('Commonly Used Size'),
        }


class sample_product(osv.Model):
    _name = 'sample.product'

    _columns = {
        'request_id': fields.many2one('sample.request', string='Request'),
        'qty_id': fields.many2one('sample.qty_label', string='Qty', oldname='qty'),
        'product_id': fields.many2one('product.product', string='Item', domain=[('categ_id','child_of','Saleable')]),
        'product_lot': fields.char('Lot #', size=12),
        'product_cost': fields.float('Product Cost'),
        }

