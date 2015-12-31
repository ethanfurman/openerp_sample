# -*- coding: utf-8 -*-

# always
from openerp.osv import fields, osv
from openerp.osv.osv import except_osv as ERPError
import logging

# often useful
from openerp import SUPERUSER_ID

# occasionally useful
import base64
import time
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, ormcache


_logger = logging.getLogger(__name__)

COMMON_SHIPPING = (
        ('fedex_first', 'FedEx First Overnight'),
        ('fedex_next', 'FedEx Next Overnight (10:30am)'),
        ('fedex_overnight', 'FedEx Overnight (5pm)'),
        ('fedex_2', 'FedEx 2-Day'),
        ('fedex_3', 'FedEx 3-Day'),
        ('fedex_ground', 'FedEx Ground'),
        ('ups_first', 'UPS First Overnight'),
        ('ups_next', 'UPS Next Overnight (10:30am)'),
        ('ups_overnight', 'UPS Overnight (5pm)'),
        ('ups_2', 'UPS 2-Day'),
        ('ups_3', 'UPS 3-Day'),
        ('ups_ground', 'UPS Ground'),
        ('ontrack_first', 'ONTRACK First Overnight'),
        ('ontrack_next', 'ONTRACK Next Overnight (8am)'),
        ('ontrack_overnight', 'ONTRACK Overnight (5pm)'),
        ('ontrack_2', 'ONTRACK 2-Day'),
        )

REQUEST_SHIPPING = (
        ('cheap_1', 'Cheapest 1-Day'),
        ('cheap_2', 'Cheapest 2-Day'),
        ('cheap_3', 'Cheapest 3-Day'),
        ('cheap_ground', 'Cheapest Ground'),
        ) + COMMON_SHIPPING + (
        ('dhl', 'DHL (give to receptionist)'),
        ('international', 'International (give to receptionist)'),
        )

# custom tables
class sample_request(osv.Model):
    _name = 'sample.request'

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

    _columns = {
            'department': fields.selection([('marketing', 'SAMMA - Marketing'), ('sales', 'SAMSA - Sales')], string='Department', required=True),
            'user_id': fields.many2one('res.users', 'Request by', required=True),
            'create_date': fields.datetime('Request created on', readonly=True),
            'send_to': fields.selection([('rep', 'Sales Rep in office'), ('address', 'Customer')], string='Send to', required=True),
            'target_date_type': fields.selection([('ship', 'Ship'), ('arrive', 'Arrive')], string='Samples must', required=True),
            'target_date': fields.date('Target Date', required=True),
            'instructions': fields.text('Special Instructions'),
            'partner_id': fields.many2one('res.partner', 'Recipient', required=True),
            # fields needed for shipping
            'address': fields.function(_get_address, type='text', string='Shipping Label'),
            'address_type': fields.selection([('business', 'Commercial'), ('personal', 'Residential')], string='Address type', required=True),
            'ice': fields.boolean('Add ice'),
            'request_ship': fields.selection(REQUEST_SHIPPING, string='Ship Via'),
            'actual_ship': fields.selection(COMMON_SHIPPING, string='Actual Shipping Method'),
            'third_party_account': fields.char('3rd Party Account Number', size=64),
            # field for samples department only
            'invoice': fields.char('Invoice #', size=32),
            'julian_date_code': fields.char('Julian Date Code', size=12),
            # products to sample
            'product_ids': fields.one2many('sample.product', 'request_id', string='Items'),
            }

    _defaults = {
        'user_id': lambda obj, cr, uid, ctx: uid,
        'address_type': 'business',

        }

    def onchange_partner_id(self, cr, uid, ids, partner_id, context=None):
        res = {}
        if partner_id:
            res_partner = self.pool.get('res.partner')
            partner = res_partner.browse(cr, uid, partner_id)
            label = partner.name + '\n' + res_partner._display_address(cr, uid, partner)
            res['value'] = {'address': label}
        return res


class sample_product(osv.Model):
    _name = 'sample.product'

    _columns = {
        'request_id': fields.many2one('sample.request', string='Request'),
        'product_id': fields.many2one(
            'product.product',
            string='Item',
            domain=[('categ_id','child_of','Saleable')],
            ),
        'qty': fields.char('Qty', size=24, help='Most common are "2 oz" and "4 oz".'),
        }
